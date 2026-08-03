"""Tests del ZigZag con umbral en ATR.

El test central es `test_no_hay_lookahead_bias_invariancia_ante_prefijos`: todo
lo demás describe el comportamiento, pero ese es el que garantiza que el módulo
no lee el futuro.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from ehs.config import Config, project_root
from ehs.data.cache import ParquetCache
from ehs.structure.swings import (
    HIGH,
    LOW,
    Pivot,
    detect_swings,
    detect_swings_from_config,
    pivots_to_frame,
    pivots_visible_at,
)
from helpers import frame_from_closes, random_walk_frame, zigzag_closes

PARAMS = {"atr_period": 14, "atr_threshold": 2.0, "confirmation_bars": 3}


def sawtooth(legs: int = 8, length: int = 25, amplitude: float = 30.0):
    """Serie en dientes de sierra con giros en posiciones conocidas."""
    return frame_from_closes(zigzag_closes([length] * legs, amplitude), wick=0.2)


# --------------------------------------------------------------------------
# Ausencia de lookahead bias — el requisito duro del módulo
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_no_hay_lookahead_bias_invariancia_ante_prefijos(seed):
    """Ejecutar sobre `frame[:t+1]` debe dar exactamente lo mismo que ejecutar
    sobre la serie completa y filtrar por `confirmed_index <= t`.

    Si la detección usara cualquier dato posterior a `t` —el ATR, un extremo
    futuro, una reversión que aún no ha ocurrido— las dos listas divergirían.
    """
    frame = random_walk_frame(300, seed=seed, sigma=0.02)
    full = detect_swings(frame, **PARAMS)
    assert len(full) >= 5, "la serie de prueba debe producir pivotes suficientes"

    for cut in range(40, len(frame) + 1, 7):
        online = detect_swings(frame.iloc[:cut], **PARAMS)
        offline = pivots_visible_at(full, cut - 1)
        assert online == offline, f"divergencia en la vela {cut - 1}"


def test_un_pivote_nunca_se_confirma_antes_de_formarse():
    frame = random_walk_frame(400, seed=9, sigma=0.02)
    pivots = detect_swings(frame, **PARAMS)

    assert pivots
    for pivot in pivots:
        assert pivot.confirmed_index > pivot.index, "confirmación en la vela del extremo o antes"
        assert pivot.confirmation_lag >= PARAMS["confirmation_bars"]
        assert pivot.confirmed_at > pivot.timestamp


def test_confirmation_bars_retrasa_la_confirmacion():
    frame = random_walk_frame(400, seed=13, sigma=0.02)
    sin_retardo = detect_swings(frame, atr_period=14, atr_threshold=2.0, confirmation_bars=0)
    con_retardo = detect_swings(frame, atr_period=14, atr_threshold=2.0, confirmation_bars=10)

    por_indice = {p.index: p for p in con_retardo}
    for pivot in sin_retardo:
        if pivot.index in por_indice:
            assert por_indice[pivot.index].confirmed_index >= pivot.confirmed_index
            assert por_indice[pivot.index].confirmation_lag >= 10


def test_los_pivotes_solo_dependen_de_velas_anteriores_a_su_confirmacion():
    """Alterar el futuro posterior a la confirmación no puede mover un pivote."""
    frame = random_walk_frame(300, seed=21, sigma=0.02)
    pivots = detect_swings(frame, **PARAMS)
    assert len(pivots) >= 4

    corte = pivots[len(pivots) // 2].confirmed_index
    alterado = frame.copy()
    alterado.iloc[corte + 1 :] *= 3.0  # el futuro se vuelve irreconocible

    esperado = pivots_visible_at(pivots, corte)
    obtenido = pivots_visible_at(detect_swings(alterado, **PARAMS), corte)
    assert obtenido == esperado


# --------------------------------------------------------------------------
# Comportamiento del ZigZag
# --------------------------------------------------------------------------


def test_detecta_los_giros_de_una_sierra():
    frame = sawtooth(legs=8, length=25, amplitude=30.0)
    pivots = detect_swings(frame, atr_period=14, atr_threshold=1.5, confirmation_bars=0)

    assert len(pivots) >= 5
    for pivot in pivots:
        vela = frame.iloc[pivot.index]
        referencia = vela["high"] if pivot.kind == HIGH else vela["low"]
        assert pivot.price == pytest.approx(referencia)


def test_los_pivotes_alternan_maximo_y_minimo():
    frame = random_walk_frame(500, seed=33, sigma=0.02)
    tipos = [p.kind for p in detect_swings(frame, **PARAMS)]

    assert len(tipos) >= 6
    assert all(a != b for a, b in pairwise(tipos))
    assert set(tipos) <= {HIGH, LOW}


def test_un_maximo_es_el_punto_mas_alto_de_su_tramo():
    frame = random_walk_frame(400, seed=41, sigma=0.02)
    pivots = detect_swings(frame, **PARAMS)
    assert len(pivots) >= 3

    for anterior, actual in pairwise(pivots):
        tramo = frame.iloc[anterior.index : actual.index + 1]
        if actual.kind == HIGH:
            assert actual.price == pytest.approx(tramo["high"].max())
        else:
            assert actual.price == pytest.approx(tramo["low"].min())


@pytest.mark.parametrize("seed", [2, 8, 17])
def test_subir_el_umbral_no_aumenta_el_numero_de_pivotes(seed):
    """El umbral en ATR debe comportarse de forma monótona: es lo que lo hace
    calibrable a ojo sobre el gráfico."""
    frame = random_walk_frame(600, seed=seed, sigma=0.02)
    counts = [
        len(detect_swings(frame, atr_period=14, atr_threshold=t, confirmation_bars=0))
        for t in (1.0, 1.5, 2.0, 3.0, 4.0, 5.0)
    ]
    assert counts == sorted(counts, reverse=True), counts
    assert counts[0] > counts[-1], "el umbral no está discriminando nada"


def test_la_magnitud_se_normaliza_por_atr():
    frame = random_walk_frame(400, seed=55, sigma=0.02)
    pivots = detect_swings(frame, **PARAMS)

    assert pivots[0].magnitude_atr is None, "el primer pivote no tiene tramo previo"
    for anterior, actual in pairwise(pivots):
        esperada = abs(actual.price - anterior.price) / actual.atr_at_pivot
        assert actual.magnitude_atr == pytest.approx(esperada)
        assert actual.magnitude_atr > 0


def test_una_serie_plana_no_produce_pivotes():
    frame = frame_from_closes(np.full(200, 100.0), wick=0.0)
    assert detect_swings(frame, **PARAMS) == []


def test_una_tendencia_limpia_solo_ancla_su_minimo_de_partida():
    """En una subida monótona el único pivote legítimo es el mínimo inicial:
    no hay ningún retroceso que confirme un máximo."""
    frame = frame_from_closes(np.linspace(100.0, 300.0, 200), wick=0.1)
    pivots = detect_swings(frame, **PARAMS)

    assert [p.kind for p in pivots] == [LOW]


# --------------------------------------------------------------------------
# Casos límite y validación de parámetros
# --------------------------------------------------------------------------


def test_serie_vacia_o_demasiado_corta():
    assert detect_swings(random_walk_frame(0, seed=1), **PARAMS) == []
    assert detect_swings(random_walk_frame(10, seed=1), **PARAMS) == []
    assert detect_swings(random_walk_frame(15, seed=1), **PARAMS) == []


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"atr_threshold": 0.0}, "positivo"),
        ({"atr_threshold": -1.0}, "positivo"),
        ({"confirmation_bars": -1}, "negativo"),
        ({"atr_reference": "mañana"}, "atr_reference"),
    ],
)
def test_parametros_invalidos(kwargs, match):
    frame = random_walk_frame(100, seed=1)
    params = {**PARAMS, **kwargs}
    with pytest.raises(ValueError, match=match):
        detect_swings(frame, **params)


def test_atr_reference_current_es_una_alternativa_valida():
    frame = random_walk_frame(400, seed=63, sigma=0.02)
    con_extremo = detect_swings(frame, **PARAMS, atr_reference="extreme")
    con_actual = detect_swings(frame, **PARAMS, atr_reference="current")

    assert con_extremo and con_actual
    for pivotes in (con_extremo, con_actual):
        tipos = [p.kind for p in pivotes]
        assert all(a != b for a, b in pairwise(tipos))


# --------------------------------------------------------------------------
# Utilidades de salida
# --------------------------------------------------------------------------


def test_pivots_visible_at_filtra_por_confirmacion():
    frame = random_walk_frame(300, seed=71, sigma=0.02)
    pivots = detect_swings(frame, **PARAMS)
    corte = pivots[1].confirmed_index

    visibles = pivots_visible_at(pivots, corte)
    assert visibles == pivots[:2]
    assert pivots_visible_at(pivots, -1) == []


def test_pivots_to_frame():
    frame = random_walk_frame(300, seed=77, sigma=0.02)
    salida = pivots_to_frame(detect_swings(frame, **PARAMS))

    assert list(salida.columns) == list(Pivot.__dataclass_fields__)
    assert salida.index.name == "timestamp"
    assert set(salida["kind"]) <= {HIGH, LOW}


def test_pivots_to_frame_con_lista_vacia():
    salida = pivots_to_frame([])
    assert salida.empty
    assert list(salida.columns) == list(Pivot.__dataclass_fields__)


def test_detect_swings_from_config_usa_el_yaml():
    cfg = Config.load(project_root() / "config.yaml")
    frame = random_walk_frame(400, seed=83, sigma=0.02)

    esperado = detect_swings(
        frame,
        atr_period=int(cfg.get("swings.atr_period")),
        atr_threshold=float(cfg.get("swings.atr_threshold")),
        confirmation_bars=int(cfg.get("swings.confirmation_bars")),
        atr_reference=str(cfg.get("swings.atr_reference")),
    )
    assert detect_swings_from_config(frame, cfg) == esperado


# --------------------------------------------------------------------------
# Contraste sobre datos reales (se omite si no hay caché descargada)
# --------------------------------------------------------------------------


def _cached_frame():
    cache_dir = project_root() / "data" / "cache"
    if not Path(cache_dir).is_dir():
        return None
    frame = ParquetCache(cache_dir).read("binance", "BTC/USDT", "4h")
    return None if frame.empty else frame


def test_invariancia_ante_prefijos_sobre_datos_reales():
    frame = _cached_frame()
    if frame is None:
        pytest.skip("no hay caché local descargada")

    ventana = frame.iloc[-800:]
    full = detect_swings(ventana, **PARAMS)
    assert len(full) >= 5

    for cut in range(200, len(ventana) + 1, 37):
        assert detect_swings(ventana.iloc[:cut], **PARAMS) == pivots_visible_at(full, cut - 1)
