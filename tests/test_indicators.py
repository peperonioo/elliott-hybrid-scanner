"""Tests del ATR: equivalencia con la referencia, causalidad y estabilidad."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ehs.structure.indicators import (
    ema,
    first_valid_position,
    true_range,
    wilder_atr,
    wilder_rsi,
)
from helpers import frame_from_closes, make_frame, random_walk_frame


def test_true_range_primera_vela_sin_cierre_previo():
    frame = make_frame("2024-01-01", "4h", 3)
    tr = true_range(frame)
    assert tr.iloc[0] == pytest.approx(frame["high"].iloc[0] - frame["low"].iloc[0])
    assert not tr.isna().any()


def test_true_range_usa_el_cierre_previo_cuando_hay_hueco():
    frame = make_frame("2024-01-01", "4h", 2)
    # Segunda vela muy por encima: el rango real lo marca el hueco.
    frame.iloc[1] = [200.0, 210.0, 199.0, 205.0, 10.0]
    tr = true_range(frame)
    expected = abs(210.0 - frame["close"].iloc[0])
    assert tr.iloc[1] == pytest.approx(expected)


def test_el_atr_coincide_con_la_implementacion_de_referencia():
    """Contraste con la librería `ta` para descartar un error propio."""
    ta = pytest.importorskip("ta")
    frame = random_walk_frame(600, seed=7)

    ours = wilder_atr(frame, 14)
    reference = ta.volatility.AverageTrueRange(
        high=frame["high"], low=frame["low"], close=frame["close"], window=14
    ).average_true_range()

    # `ta` arranca su recursión igual, pero rellena el warm-up en vez de dejar
    # NaN; se comparan solo las posiciones donde ambos están definidos.
    both = ours.notna() & reference.notna() & (reference != 0)
    assert both.sum() > 500
    np.testing.assert_allclose(ours[both], reference[both], rtol=1e-9)


def test_el_atr_es_estable_ante_prefijos():
    """atr(serie[:t]) debe ser idéntico a atr(serie)[:t].

    Es la propiedad de la que depende el test anti-lookahead de los swings: si
    el ATR cambiase al añadir velas nuevas, los pivotes pasados se moverían.
    """
    frame = random_walk_frame(400, seed=11)
    full = wilder_atr(frame, 14)

    for cut in (50, 137, 300, 400):
        prefix = wilder_atr(frame.iloc[:cut], 14)
        pd.testing.assert_series_equal(prefix, full.iloc[:cut])


def test_el_warm_up_queda_a_nan_y_no_se_rellena():
    frame = random_walk_frame(60, seed=3)
    atr = wilder_atr(frame, 14)
    assert atr.iloc[:13].isna().all()
    assert not atr.iloc[13:].isna().any()
    assert first_valid_position(atr) == 13


def test_serie_mas_corta_que_el_periodo_devuelve_todo_nan():
    atr = wilder_atr(random_walk_frame(5, seed=1), 14)
    assert atr.isna().all()
    assert first_valid_position(atr) is None


def test_periodo_invalido():
    with pytest.raises(ValueError, match="debe ser >= 1"):
        wilder_atr(random_walk_frame(30, seed=1), 0)


def test_el_atr_es_positivo():
    atr = wilder_atr(random_walk_frame(300, seed=5), 14).dropna()
    assert (atr > 0).all()


# --------------------------------------------------------------------------
# RSI
# --------------------------------------------------------------------------


def test_el_rsi_se_siembra_como_wilder():
    """Wilder arranca la recursión con la media simple de los primeros valores.

    Es también lo que hace TradingView, que es donde se validarán las señales
    a ojo. La librería `ta` arranca desde el primer valor en vez de sembrar, y
    por eso difiere durante el arranque (ver el test siguiente).
    """
    frame = random_walk_frame(200, seed=17)
    deltas = frame["close"].diff()
    ganancias = deltas.clip(lower=0).iloc[1:15].mean()
    perdidas = (-deltas).clip(lower=0).iloc[1:15].mean()
    esperado = 100.0 - 100.0 / (1.0 + ganancias / perdidas)

    assert wilder_rsi(frame, 14).iloc[14] == pytest.approx(esperado)


def test_el_rsi_converge_con_la_implementacion_de_referencia():
    """Solo difiere en la siembra, así que las dos series convergen."""
    ta = pytest.importorskip("ta")
    frame = random_walk_frame(600, seed=17)

    ours = wilder_rsi(frame, 14)
    reference = ta.momentum.RSIIndicator(close=frame["close"], window=14).rsi()

    both = ours.notna() & reference.notna()
    assert both.sum() > 500
    diferencia = (ours[both] - reference[both]).abs()
    assert diferencia.iloc[:50].max() > 1.0, "sin diferencia de siembra no hay nada que probar"
    np.testing.assert_allclose(ours[both][-200:], reference[both][-200:], atol=1e-6)


def test_el_rsi_es_estable_ante_prefijos():
    frame = random_walk_frame(400, seed=23)
    full = wilder_rsi(frame, 14)

    for cut in (60, 150, 299, 400):
        pd.testing.assert_series_equal(wilder_rsi(frame.iloc[:cut], 14), full.iloc[:cut])


def test_el_rsi_se_mueve_entre_0_y_100():
    rsi = wilder_rsi(random_walk_frame(500, seed=29), 14).dropna()
    assert ((rsi >= 0) & (rsi <= 100)).all()


def test_una_subida_monotona_satura_el_rsi_en_100():
    frame = frame_from_closes(np.linspace(100.0, 200.0, 60))
    assert wilder_rsi(frame, 14).iloc[-1] == pytest.approx(100.0)


def test_el_warm_up_del_rsi_queda_a_nan():
    rsi = wilder_rsi(random_walk_frame(60, seed=31), 14)
    assert rsi.iloc[:14].isna().all()
    assert not rsi.iloc[14:].isna().any()


def test_serie_mas_corta_que_el_periodo_del_rsi():
    assert wilder_rsi(random_walk_frame(10, seed=1), 14).isna().all()


def test_periodo_invalido_del_rsi():
    with pytest.raises(ValueError, match="RSI debe ser >= 1"):
        wilder_rsi(random_walk_frame(50, seed=1), 0)


# --------------------------------------------------------------------------
# EMA
# --------------------------------------------------------------------------


def test_la_ema_es_estable_ante_prefijos():
    """La siembra con SMA es lo que lo garantiza: el arranque no depende de
    cuántas velas vengan después."""
    frame = random_walk_frame(400, seed=37)
    full = ema(frame["close"], 50)

    for cut in (60, 200, 400):
        pd.testing.assert_series_equal(ema(frame["close"].iloc[:cut], 50), full.iloc[:cut])


def test_la_ema_arranca_en_la_media_simple():
    frame = random_walk_frame(100, seed=41)
    resultado = ema(frame["close"], 20)

    assert resultado.iloc[:19].isna().all()
    assert resultado.iloc[19] == pytest.approx(frame["close"].iloc[:20].mean())


def test_la_ema_de_una_serie_constante_es_esa_constante():
    serie = frame_from_closes(np.full(80, 42.0))["close"]
    assert ema(serie, 20).dropna().eq(42.0).all()


def test_la_ema_sigue_a_la_tendencia_por_debajo():
    serie = frame_from_closes(np.linspace(100.0, 300.0, 200))["close"]
    resultado = ema(serie, 50)
    assert resultado.iloc[-1] < serie.iloc[-1]


def test_serie_mas_corta_que_el_periodo_de_la_ema():
    assert ema(frame_from_closes(np.linspace(1.0, 5.0, 10))["close"], 50).isna().all()


def test_periodo_invalido_de_la_ema():
    with pytest.raises(ValueError, match="EMA debe ser >= 1"):
        ema(frame_from_closes(np.linspace(1.0, 5.0, 60))["close"], 0)
