"""Tests del panel «¿sube o baja?» (frecuencias condicionadas a 24h)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ehs.report.direction import HORIZON_BARS, compute_direction_stats
from ehs.report.web import render_html
from tests_report_fixtures import NOW, make_config


def _frame(closes: np.ndarray) -> pd.DataFrame:
    index = pd.date_range("2022-01-01", periods=len(closes), freq="4h", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.001,
            "low": closes * 0.999,
            "close": closes,
            "volume": np.ones(len(closes)),
        },
        index=index,
    )


def test_en_una_subida_sostenida_la_frecuencia_alcista_es_maxima():
    # Subida suave y monótona: todo estado se resuelve al alza a 24h.
    closes = 100.0 * np.cumprod(np.full(1200, 1.001))
    stats = compute_direction_stats(_frame(closes))

    assert stats is not None
    assert stats.trend_up and stats.momentum_up
    assert stats.p_up == 1.0
    assert stats.avg_move > 0
    assert stats.n > 0


def test_sin_historia_suficiente_no_hay_panel():
    closes = 100.0 * np.cumprod(np.full(50, 1.001))
    assert compute_direction_stats(_frame(closes)) is None


def test_el_desenlace_mira_exactamente_24h_despues():
    # 6 velas de 4h = 24h: el horizonte debe ser ese, ni una más.
    assert HORIZON_BARS == 6


def test_la_seccion_sube_o_baja_aparece_con_su_advertencia():
    from ehs.report.direction import DirectionStats

    rows = [
        {
            "base": "BTC",
            "stats": DirectionStats(
                trend_up=True,
                momentum_up=False,
                rsi_zone="débil",
                p_up=0.56,
                avg_move=0.004,
                n=320,
                reliable=True,
            ),
        },
        {
            "base": "ETH",
            "stats": DirectionStats(
                trend_up=False,
                momentum_up=False,
                rsi_zone="fuerte",
                p_up=0.50,
                avg_move=0.0,
                n=90,
                reliable=False,
            ),
        },
    ]
    page = render_html([], [], cfg=make_config(), now=NOW, direction=rows)

    assert "¿Sube o baja?" in page
    assert "subió el 56%" in page
    assert "muestra insuficiente (n=90)" in page
    assert "frecuencia histórica, no predicción" in page
    assert "tendencia ↑ · momentum ↓ · RSI débil" in page


def test_sin_panel_no_hay_seccion():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert 'id="sec-dir"' not in page  # la guía lo menciona, la sección no está
