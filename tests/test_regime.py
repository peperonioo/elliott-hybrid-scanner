"""Tests del régimen de mercado y del retroceso corto."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ehs.report.regime import classify_regime, coin_context, pullback_zone
from ehs.report.web import render_html
from ehs.structure.swings import Pivot
from tests_report_fixtures import NOW, make_config, make_entry


def _daily(closes: np.ndarray) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(closes), freq="1d", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": np.ones(len(closes)),
        },
        index=index,
    )


def _pivot(index: int, price: float, kind: str) -> Pivot:
    stamp = pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(index * 4, unit="h")
    return Pivot(
        index=index,
        timestamp=stamp,
        price=price,
        kind=kind,
        atr_at_pivot=1.0,
        magnitude_atr=None,
        confirmed_index=index + 3,
        confirmed_at=stamp,
    )


def test_un_mercado_disparado_se_llama_impulso_alcista_fuerte():
    lecturas = [(12.0, True)] * 10 + [(4.0, True)] * 3
    reg = classify_regime(lecturas)

    assert reg is not None
    assert reg.label == "impulso alcista fuerte"
    assert reg.breadth == 1.0
    assert "quedan muy por debajo del precio" in reg.text
    assert "retroceso corto" in reg.text


def test_los_regimenes_cubren_todo_el_rango():
    assert classify_regime([(0.2, True)] * 5).label == "lateral"
    assert classify_regime([(3.0, True)] * 5).label == "alcista"
    assert classify_regime([(-3.0, False)] * 5).label == "bajista"
    assert classify_regime([(-12.0, False)] * 5).label == "caída fuerte"
    # Subida fuerte pero sin amplitud: no es impulso de mercado.
    assert classify_regime([(9.0, False)] * 5).label == "alcista"
    assert classify_regime([]) is None


def test_la_lectura_por_moneda_mide_siete_dias_y_la_media():
    subida = _daily(100.0 * np.cumprod(np.full(120, 1.01)))
    lectura = coin_context(subida)
    assert lectura is not None
    move, sobre_media = lectura
    assert move > 6 and sobre_media is True
    assert coin_context(_daily(np.full(10, 100.0))) is None


def test_el_retroceso_corto_solo_existe_por_debajo_del_precio():
    pivots = [_pivot(0, 100.0, "L"), _pivot(10, 200.0, "H")]
    zona = pullback_zone(pivots, price=195.0)

    assert zona is not None
    lower, upper = zona
    assert 150 < lower < upper < 195  # 0.382 y 0.236 del tramo 100→200
    # Si el precio ya cayó dentro de la banda, no es un nivel futuro.
    assert pullback_zone(pivots, price=170.0) is None
    assert pullback_zone([], price=100.0) is None


def test_la_web_muestra_el_regimen_y_el_retroceso_en_la_tarjeta():
    reg = classify_regime([(12.0, True)] * 13)
    # Precio 63,000 muy por encima de la zona 60,000–61,000.
    entry = make_entry([0.9, 0.8, 0.1, 0.1, 0.1], is_signal=False)
    page = render_html(
        [entry],
        [],
        cfg=make_config(),
        now=NOW,
        regime=reg,
        pullbacks={"BTC": (61500.0, 62200.0)},
    )

    assert "impulso alcista fuerte" in page
    assert "Retroceso corto · impulso" in page
    assert "61,500 – 62,200" in page
    assert "no validado" in page  # la advertencia viaja con el nivel
