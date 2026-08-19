"""Tests de las órdenes límite sugeridas (probabilidad de ejecución)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ehs.report.orders import PROB_LIKELY, compute_order_levels
from ehs.report.web import render_html
from tests_report_fixtures import NOW, make_config


def _frame(closes: np.ndarray, spread: float = 0.01) -> pd.DataFrame:
    index = pd.date_range("2022-01-01", periods=len(closes), freq="4h", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * (1 + spread),
            "low": closes * (1 - spread),
            "close": closes,
            "volume": np.ones(len(closes)),
        },
        index=index,
    )


def test_los_limites_rodean_al_precio_actual():
    rng = np.random.default_rng(7)
    closes = 100.0 * np.cumprod(1 + rng.normal(0, 0.01, 1500))
    lv = compute_order_levels(_frame(closes))

    assert lv is not None
    # Compras por debajo del precio, ventas por encima.
    assert lv.buy_deep < lv.buy_likely <= lv.price
    assert lv.price <= lv.sell_likely < lv.sell_ambitious
    assert lv.n > 1000


def test_el_limite_probable_esta_mas_cerca_que_el_ambicioso():
    """A mayor probabilidad de ejecución, más cerca del precio."""
    rng = np.random.default_rng(3)
    closes = 50.0 * np.cumprod(1 + rng.normal(0, 0.008, 1200))
    lv = compute_order_levels(_frame(closes))

    assert lv is not None
    assert lv.sell_likely - lv.price < lv.sell_ambitious - lv.price
    assert lv.price - lv.buy_likely < lv.price - lv.buy_deep
    assert PROB_LIKELY > 0.5  # el "probable" lo es de verdad


def test_un_mercado_plano_da_limites_pegados_al_precio():
    closes = np.full(1000, 100.0)
    lv = compute_order_levels(_frame(closes, spread=0.0))
    assert lv is not None
    assert lv.sell_likely == lv.price == lv.buy_likely


def test_sin_historia_suficiente_no_hay_niveles():
    assert compute_order_levels(_frame(np.full(100, 10.0))) is None


def test_la_seccion_de_ordenes_avisa_de_la_trampa():
    from ehs.report.orders import OrderLevels

    rows = [
        {
            "base": "BTC",
            "lv": OrderLevels(
                price=64000.0,
                buy_likely=63400.0,
                buy_deep=62000.0,
                sell_likely=64700.0,
                sell_ambitious=66100.0,
                median_up=0.012,
                median_down=-0.011,
                n=1900,
            ),
        }
    ]
    page = render_html([], [], cfg=make_config(), now=NOW, orders=rows)

    assert "Órdenes límite" in page
    assert "probabilidad de ejecución" in page
    assert "no probabilidad de ganar" in page
    assert "63,400" in page and "66,100" in page
    assert 'href="#sec-ordenes"' in page
