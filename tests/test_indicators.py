"""Tests del ATR: equivalencia con la referencia, causalidad y estabilidad."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ehs.structure.indicators import first_valid_position, true_range, wilder_atr
from helpers import make_frame, random_walk_frame


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
