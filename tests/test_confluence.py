"""Tests de la capa de confluencia.

El test central es `test_no_lee_la_vela_de_contexto_todavia_abierta`: los demás
describen cada factor, pero ese es el que garantiza que la capa no lee el
futuro a través del desfase entre timeframes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ehs.config import Config, project_root
from ehs.confluence.scorer import (
    FIBONACCI,
    HIGHER_TIMEFRAME_TREND,
    MARKET_STRUCTURE,
    RSI_DIVERGENCE,
    VOLUME_PROFILE,
    ConfluenceParams,
    ConfluenceResult,
    FactorScore,
    factor_fibonacci,
    factor_higher_timeframe_trend,
    factor_market_structure,
    factor_rsi_divergence,
    factor_volume_profile,
    score_confluence,
    signal_direction,
)
from ehs.elliott.validator import BEARISH, BULLISH, ElliottParams, validate_sequence
from ehs.structure.swings import HIGH, LOW, Pivot, detect_swings
from helpers import frame_from_closes, path_closes, random_walk_frame

PARAMS = ConfluenceParams()
ELLIOTT = ElliottParams()

# Impulso alcista de libro. Termina en la vela 110 y se confirma en la 113,
# de modo que en un frame de 120 velas el conteo ya se conocía por completo.
WAYPOINTS = [(0, 100.0), (20, 200.0), (40, 140.0), (70, 301.8), (90, 240.0), (110, 320.0)]


def pivot(index: int, price: float, kind: str) -> Pivot:
    stamp = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(index * 4, unit="h")
    return Pivot(
        index=index,
        timestamp=stamp,
        price=price,
        kind=kind,
        atr_at_pivot=1.0,
        magnitude_atr=None,
        confirmed_index=index + 3,
        confirmed_at=stamp + pd.Timedelta(12, unit="h"),
    )


def impulse_pivots(waypoints=WAYPOINTS, *, bullish: bool = True) -> list[Pivot]:
    first, second = (LOW, HIGH) if bullish else (HIGH, LOW)
    return [
        pivot(idx, price, first if i % 2 == 0 else second)
        for i, (idx, price) in enumerate(waypoints)
    ]


def impulse_count(waypoints=WAYPOINTS, *, bullish: bool = True):
    counts = validate_sequence(impulse_pivots(waypoints, bullish=bullish), ELLIOTT)
    assert counts, "los waypoints de prueba deben producir un conteo válido"
    return counts[0]


def structure_frame(waypoints=WAYPOINTS, *, volume=100.0, pad_to=None) -> pd.DataFrame:
    """Frame de 4h. `pad_to` añade cola para que el conteo quede por detrás."""
    points = list(waypoints)
    if pad_to is not None:
        points.append((pad_to, points[-1][1] * 1.05))
    return frame_from_closes(path_closes(points), timeframe="4h", wick=0.0, volume=volume)


def context_frame(bars: int = 200, *, trend: float = 0.0, start: str = "2023-06-01"):
    closes = 200.0 + trend * np.arange(bars)
    return frame_from_closes(closes, start=start, timeframe="1d", wick=1.0)


# --------------------------------------------------------------------------
# Dirección de la señal
# --------------------------------------------------------------------------


def test_un_impulso_alcista_completo_da_senal_bajista():
    """No es una señal alcista: es la antesala de la corrección."""
    assert signal_direction(impulse_count()) == BEARISH


def test_un_impulso_bajista_completo_da_senal_alcista():
    espejo = [(0, 400.0), (20, 300.0), (40, 360.0), (70, 198.2), (90, 260.0), (119, 180.0)]
    assert signal_direction(impulse_count(espejo, bullish=False)) == BULLISH


def test_un_abc_completo_da_senal_contraria():
    """La corrección ha terminado: se espera que se reanude la tendencia."""
    tres = [(0, 100.0), (30, 200.0), (60, 150.0), (100, 250.0)]
    counts = validate_sequence(impulse_pivots(tres), ELLIOTT)
    abc = next(c for c in counts if c.hypothesis == "corrective_abc")
    assert signal_direction(abc) == BEARISH


def test_un_impulso_parcial_da_senal_a_favor():
    """Sigue vivo: se espera la onda 4 contra y después la 5 a favor."""
    tres = [(0, 100.0), (30, 200.0), (60, 150.0), (100, 250.0)]
    counts = validate_sequence(impulse_pivots(tres), ELLIOTT)
    parcial = next(c for c in counts if c.hypothesis == "impulse_1_2_3")
    assert signal_direction(parcial) == BULLISH


# --------------------------------------------------------------------------
# Factor: Fibonacci
# --------------------------------------------------------------------------


def test_fibonacci_puntua_1_en_el_nivel_exacto():
    count = impulse_count()
    last = count.waves[-1]
    nivel_0618 = last.end.price - (last.end.price - last.start.price) * 0.618

    factor = factor_fibonacci(count, nivel_0618, atr=5.0, params=PARAMS)

    assert factor.score == pytest.approx(1.0)
    assert factor.active
    assert "0.618" in factor.detail


def test_fibonacci_decae_con_la_distancia_y_se_anula_lejos():
    count = impulse_count()
    last = count.waves[-1]
    nivel = last.end.price - (last.end.price - last.start.price) * 0.618
    atr = 5.0

    cerca = factor_fibonacci(count, nivel + 0.2 * atr, atr, PARAMS)
    medio = factor_fibonacci(count, nivel + 0.5 * atr, atr, PARAMS)
    lejos = factor_fibonacci(count, nivel + 500 * atr, atr, PARAMS)

    assert 1.0 > cerca.score > medio.score > 0.0
    assert lejos.score == 0.0
    assert "lejos de todo nivel" in lejos.detail


def test_fibonacci_se_mide_en_atr_y_no_en_porcentaje():
    """El mismo alejamiento relativo puntúa distinto según la volatilidad."""
    count = impulse_count()
    last = count.waves[-1]
    nivel = last.end.price - (last.end.price - last.start.price) * 0.618

    volatil = factor_fibonacci(count, nivel + 3.0, atr=20.0, params=PARAMS)
    tranquilo = factor_fibonacci(count, nivel + 3.0, atr=2.0, params=PARAMS)

    assert volatil.score > tranquilo.score


# --------------------------------------------------------------------------
# Factor: divergencia de RSI
# --------------------------------------------------------------------------


def test_divergencia_bajista_detectada_en_la_onda_5():
    """Precio con máximo superior en la 5 y RSI que no lo acompaña.

    La onda 5 es corta y arranca justo después de la onda 4, así que el
    suavizado de Wilder todavía arrastra las pérdidas de esa corrección y el
    RSI no acompaña al nuevo máximo de precio.
    """
    waypoints = [(0, 100.0), (60, 200.0), (80, 140.0), (100, 301.8), (120, 240.0), (130, 320.0)]
    count = impulse_count(waypoints)
    frame = structure_frame(waypoints)

    factor = factor_rsi_divergence(count, frame, PARAMS)

    assert factor.score > 0.0
    assert "divergencia bajista" in factor.detail


def test_sin_divergencia_el_factor_se_anula():
    """Onda 5 larga y sostenida: el RSI acompaña al máximo en vez de divergir."""
    waypoints = [(0, 100.0), (20, 200.0), (40, 140.0), (46, 301.8), (90, 240.0), (200, 320.0)]
    count = impulse_count(waypoints)
    factor = factor_rsi_divergence(count, structure_frame(waypoints), PARAMS)

    assert factor.score == 0.0
    assert "sin divergencia" in factor.detail


def test_un_impulso_parcial_no_tiene_divergencia_evaluable():
    tres = [(0, 100.0), (30, 200.0), (60, 150.0), (100, 250.0)]
    counts = validate_sequence(impulse_pivots(tres), ELLIOTT)
    parcial = next(c for c in counts if c.hypothesis == "impulse_1_2_3")

    factor = factor_rsi_divergence(parcial, structure_frame(tres), PARAMS)

    assert factor.score == 0.0
    assert "1-2-3" in factor.detail


# --------------------------------------------------------------------------
# Factor: estructura de mercado
# --------------------------------------------------------------------------


def build_context_with_pivots(closes: np.ndarray):
    frame = frame_from_closes(closes, start="2023-06-01", timeframe="1d", wick=1.0)
    pivots = detect_swings(frame, atr_period=14, atr_threshold=2.0, confirmation_bars=0)
    return frame, pivots


# Ruta con giros alternos reales: máximos en 30/70/110 y mínimos en 50/85/115.
ESTRUCTURA_BASE = [
    (0, 100.0),
    (30, 160.0),
    (50, 130.0),
    (70, 175.0),
    (85, 150.0),
    (110, 190.0),
    (115, 170.0),
]


def estructura(final_index: int, final_price: float):
    return path_closes([*ESTRUCTURA_BASE, (final_index, final_price)])


def test_estructura_puntua_cuando_hay_ruptura_reciente_a_favor():
    # Rompe al alza el último máximo (190) poco después de formarse.
    frame, pivots = build_context_with_pivots(estructura(118, 200.0))

    factor = factor_market_structure(BULLISH, frame, pivots, PARAMS)

    assert factor.score > 0.0
    assert "alcista" in factor.detail


def test_estructura_se_anula_sin_ruptura():
    # Se queda en 185, por debajo del último máximo (190).
    frame, pivots = build_context_with_pivots(estructura(118, 185.0))

    factor = factor_market_structure(BULLISH, frame, pivots, PARAMS)

    assert factor.score == 0.0
    assert "sin ruptura" in factor.detail


def test_estructura_sin_pivotes_suficientes():
    frame = frame_from_closes(np.full(30, 100.0), timeframe="1d")
    factor = factor_market_structure(BULLISH, frame, [], PARAMS)

    assert factor.score == 0.0
    assert "insuficientes" in factor.detail


def test_una_ruptura_antigua_puntua_menos_que_una_reciente():
    """El máximo roto es el mismo; solo cambia cuánto hace que se formó."""
    reciente = factor_market_structure(
        BULLISH, *build_context_with_pivots(estructura(118, 200.0)), PARAMS
    )
    antigua = factor_market_structure(
        BULLISH, *build_context_with_pivots(estructura(128, 200.0)), PARAMS
    )

    assert reciente.score > antigua.score > 0.0


# --------------------------------------------------------------------------
# Factor: perfil de volumen
# --------------------------------------------------------------------------


def volumes_for(waypoints, *, wave3_boost: float, wave4_drop: float) -> np.ndarray:
    """Volumen base con la onda 3 expandida y la onda 4 contraída."""
    volume = np.full(waypoints[-1][0] + 1, 100.0)
    volume[waypoints[1][0] : waypoints[2][0]] = 100.0  # onda 2
    volume[waypoints[2][0] : waypoints[3][0]] = 100.0 * wave3_boost
    volume[waypoints[3][0] : waypoints[4][0]] = 100.0 * wave3_boost * wave4_drop
    return volume


def test_volumen_coherente_con_la_fase_puntua_alto():
    count = impulse_count()
    frame = structure_frame(volume=volumes_for(WAYPOINTS, wave3_boost=2.0, wave4_drop=0.4))

    factor = factor_volume_profile(count, frame, PARAMS)

    assert factor.score > 0.9
    assert factor.active


def test_volumen_plano_no_puntua():
    count = impulse_count()
    factor = factor_volume_profile(count, structure_frame(volume=100.0), PARAMS)

    assert factor.score == 0.0
    assert not factor.active


def test_volumen_contrario_a_la_fase_no_puntua():
    """Onda 3 seca y onda 4 expandida: lo contrario de lo esperado."""
    count = impulse_count()
    frame = structure_frame(volume=volumes_for(WAYPOINTS, wave3_boost=0.5, wave4_drop=3.0))

    factor = factor_volume_profile(count, frame, PARAMS)

    assert factor.score == 0.0


# --------------------------------------------------------------------------
# Factor: tendencia del timeframe superior
# --------------------------------------------------------------------------


def test_la_tendencia_diaria_a_favor_puntua_por_encima_de_la_mitad():
    alcista = context_frame(200, trend=1.0)
    factor = factor_higher_timeframe_trend(BULLISH, alcista, PARAMS)

    assert factor.score > 0.5


def test_la_tendencia_diaria_en_contra_puntua_por_debajo_de_la_mitad():
    """Penalizar el contra-tendencia es exactamente la función del factor."""
    alcista = context_frame(200, trend=1.0)
    factor = factor_higher_timeframe_trend(BEARISH, alcista, PARAMS)

    assert factor.score < 0.5


def test_sin_tendencia_el_factor_queda_neutro():
    plano = context_frame(200, trend=0.0)
    factor = factor_higher_timeframe_trend(BULLISH, plano, PARAMS)

    assert factor.score == pytest.approx(0.5, abs=0.05)


def test_historico_insuficiente_en_el_contexto():
    corto = context_frame(20, trend=1.0)
    factor = factor_higher_timeframe_trend(BULLISH, corto, PARAMS)

    assert factor.score == 0.0
    assert "insuficiente" in factor.detail


# --------------------------------------------------------------------------
# Ausencia de lookahead entre timeframes
# --------------------------------------------------------------------------


def test_no_lee_la_vela_de_contexto_todavia_abierta():
    """Al evaluar en una vela de 4h, la diaria de hoy aún no ha cerrado.

    Se evalúa dos veces con contextos idénticos salvo por una vela diaria
    posterior, de valor extremo, que en ese instante todavía está abierta. Si
    la capa la leyese, los factores de estructura y de tendencia cambiarían.
    """
    # El conteo termina en la vela 110 y se confirma en la 113, así que en la
    # 116 ya se conocía por completo.
    waypoints = [(0, 100.0), (20, 200.0), (40, 140.0), (70, 301.8), (90, 240.0), (110, 320.0)]
    count = impulse_count(waypoints)
    structure = frame_from_closes(path_closes([*waypoints, (119, 335.0)]), timeframe="4h", wick=0.0)

    base = context_frame(200, trend=1.0, start="2023-06-01")
    # Se evalúa a media sesión (vela de 4h de las 08:00). La de las 20:00 no
    # serviría: cierra en el mismo instante que la diaria, así que en ese punto
    # leerla sería legítimo.
    at = 116
    evaluado_en = structure.index[at]
    assert evaluado_en.hour == 8
    dia_en_curso = pd.DataFrame(
        {
            "open": [10_000.0],
            "high": [99_000.0],
            "low": [1.0],
            "close": [50_000.0],
            "volume": [1e9],
        },
        index=pd.DatetimeIndex([evaluado_en.floor("D")], name="timestamp", tz="UTC"),
    )
    con_vela_abierta = pd.concat([base, dia_en_curso])

    comun = dict(
        symbol="BTC/USDT",
        structure_timeframe="4h",
        context_timeframe="1d",
        params=PARAMS,
        swing_kwargs={"atr_period": 14, "atr_threshold": 2.0, "confirmation_bars": 0},
    )
    sin = score_confluence(count, structure=structure, context=base, at=at, **comun)
    con = score_confluence(count, structure=structure, context=con_vela_abierta, at=at, **comun)

    assert sin.factors == con.factors
    assert sin.score == con.score


def test_el_contexto_se_recorta_a_lo_ya_cerrado():
    structure = structure_frame(pad_to=119)
    count = impulse_count()
    # Contexto que empieza mucho después: nada ha cerrado todavía.
    futuro = context_frame(200, trend=1.0, start="2030-01-01")

    resultado = score_confluence(
        count,
        structure=structure,
        context=futuro,
        symbol="BTC/USDT",
        structure_timeframe="4h",
        context_timeframe="1d",
        params=PARAMS,
    )

    estructura = next(f for f in resultado.factors if f.name == MARKET_STRUCTURE)
    tendencia = next(f for f in resultado.factors if f.name == HIGHER_TIMEFRAME_TREND)
    assert estructura.score == 0.0
    assert tendencia.score == 0.0


def test_el_parametro_at_recorta_la_estructura():
    structure = structure_frame(pad_to=119)
    count = impulse_count()
    comun = dict(
        symbol="BTC/USDT",
        structure_timeframe="4h",
        context_timeframe="1d",
        params=PARAMS,
        context=context_frame(200, trend=1.0),
    )

    completo = score_confluence(count, structure=structure, **comun)
    recortado = score_confluence(count, structure=structure, at=len(structure) - 1, **comun)

    assert completo.timestamp == recortado.timestamp
    assert completo.factors == recortado.factors


# --------------------------------------------------------------------------
# Agregación y regla de emisión
# --------------------------------------------------------------------------


def result_with(scores: dict[str, float], *, min_active: int = 3) -> ConfluenceResult:
    factors = tuple(
        FactorScore(name=name, score=score, threshold=0.6, weight=0.2, detail="")
        for name, score in scores.items()
    )
    return ConfluenceResult(
        symbol="BTC/USDT",
        timeframe="4h",
        timestamp=pd.Timestamp("2024-01-01", tz="UTC"),
        price=100.0,
        count=impulse_count(),
        signal_direction=BEARISH,
        factors=factors,
        min_active_factors=min_active,
        zone=None,
        count_invalidation=None,
        signal_invalidation=0.0,
    )


def test_un_solo_factor_fuerte_no_emite_senal():
    """Es la regla clave: confluencia, no un máximo aislado."""
    resultado = result_with(
        {FIBONACCI: 1.0, RSI_DIVERGENCE: 0.1, MARKET_STRUCTURE: 0.0, VOLUME_PROFILE: 0.0}
    )

    assert len(resultado.active_factors) == 1
    assert not resultado.emits_signal


def test_tres_factores_por_encima_de_umbral_emiten_senal():
    resultado = result_with(
        {FIBONACCI: 0.7, RSI_DIVERGENCE: 0.65, MARKET_STRUCTURE: 0.9, VOLUME_PROFILE: 0.1}
    )

    assert len(resultado.active_factors) == 3
    assert resultado.emits_signal


def test_el_umbral_es_inclusivo():
    resultado = result_with(
        {FIBONACCI: 0.6, RSI_DIVERGENCE: 0.6, MARKET_STRUCTURE: 0.6, VOLUME_PROFILE: 0.0}
    )
    assert resultado.emits_signal


def test_el_score_es_la_media_ponderada():
    resultado = result_with({FIBONACCI: 1.0, RSI_DIVERGENCE: 0.0, MARKET_STRUCTURE: 0.5})
    assert resultado.score == pytest.approx(0.5)


def test_min_active_factors_es_configurable():
    scores = {FIBONACCI: 0.7, RSI_DIVERGENCE: 0.7, MARKET_STRUCTURE: 0.1, VOLUME_PROFILE: 0.1}
    assert not result_with(scores, min_active=3).emits_signal
    assert result_with(scores, min_active=2).emits_signal


def test_el_resumen_distingue_senal_de_no_senal():
    con = result_with({FIBONACCI: 0.9, RSI_DIVERGENCE: 0.9, MARKET_STRUCTURE: 0.9})
    sin = result_with({FIBONACCI: 0.9, RSI_DIVERGENCE: 0.1, MARKET_STRUCTURE: 0.1})

    assert "SEÑAL" in con.summary()
    assert "sin señal" in sin.summary()


# --------------------------------------------------------------------------
# Integración y configuración
# --------------------------------------------------------------------------


def test_score_confluence_devuelve_los_cinco_factores():
    resultado = score_confluence(
        impulse_count(),
        structure=structure_frame(pad_to=119),
        context=context_frame(200, trend=1.0),
        symbol="BTC/USDT",
        structure_timeframe="4h",
        context_timeframe="1d",
        params=PARAMS,
    )

    nombres = [f.name for f in resultado.factors]
    assert nombres == [
        FIBONACCI,
        RSI_DIVERGENCE,
        MARKET_STRUCTURE,
        VOLUME_PROFILE,
        HIGHER_TIMEFRAME_TREND,
    ]
    assert all(0.0 <= f.score <= 1.0 for f in resultado.factors)
    assert resultado.count_invalidation == 100.0
    assert resultado.signal_invalidation == 320.0
    assert resultado.zone is not None and resultado.zone[0] < resultado.zone[1]


def test_una_estructura_demasiado_corta_falla_de_forma_explicita():
    """Conteo comprimido en las primeras velas: cabe, pero no hay ATR todavía."""
    comprimido = [(0, 100.0), (1, 200.0), (2, 140.0), (3, 301.8), (4, 240.0), (5, 320.0)]
    corta = structure_frame(comprimido, pad_to=12)

    with pytest.raises(ValueError, match="ATR sin definir"):
        score_confluence(
            impulse_count(comprimido),
            structure=corta,
            context=context_frame(200),
            symbol="BTC/USDT",
            structure_timeframe="4h",
            context_timeframe="1d",
            params=PARAMS,
        )


def test_evaluar_un_conteo_aun_no_confirmado_falla():
    """Salvaguarda contra el lookahead más fácil de cometer desde fuera."""
    structure = structure_frame()
    with pytest.raises(ValueError, match="leer el futuro"):
        score_confluence(
            impulse_count(),
            structure=structure,
            context=context_frame(200),
            symbol="BTC/USDT",
            structure_timeframe="4h",
            context_timeframe="1d",
            params=PARAMS,
            at=60,
        )


def test_una_estructura_vacia_falla():
    with pytest.raises(ValueError, match="vacío"):
        score_confluence(
            impulse_count(),
            structure=random_walk_frame(0),
            context=context_frame(200),
            symbol="BTC/USDT",
            structure_timeframe="4h",
            context_timeframe="1d",
            params=PARAMS,
        )


def test_los_parametros_se_leen_del_yaml():
    cfg = Config.load(project_root() / "config.yaml")
    params = ConfluenceParams.from_config(cfg)

    assert params.min_active_factors == 3
    assert set(params.weights) == {
        FIBONACCI,
        RSI_DIVERGENCE,
        MARKET_STRUCTURE,
        VOLUME_PROFILE,
        HIGHER_TIMEFRAME_TREND,
    }
    assert params.fib_retracements == (0.618, 0.786)
    assert params.fib_extensions == (1.618,)
    assert params.trend_ema_period == 50
