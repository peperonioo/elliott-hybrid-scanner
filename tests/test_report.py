"""Tests del informe diario."""

from __future__ import annotations

import pandas as pd

from ehs.config import Config
from ehs.confluence.scorer import ConfluenceResult, FactorScore
from ehs.elliott.validator import BULLISH, ElliottParams, validate_sequence
from ehs.report.daily import ReportEntry, render_markdown
from ehs.structure.swings import HIGH, LOW, Pivot


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


def make_count():
    prices = [100.0, 200.0, 140.0, 301.8, 240.0, 320.0]
    pivots = [pivot(i * 10, p, LOW if i % 2 == 0 else HIGH) for i, p in enumerate(prices)]
    return validate_sequence(pivots, ElliottParams())[0]


def make_result(scores: list[float]) -> ConfluenceResult:
    nombres = ["fibonacci", "rsi_divergence", "market_structure", "volume_profile", "trend"]
    factors = tuple(
        FactorScore(name=n, score=s, threshold=0.6, weight=0.2, detail=f"detalle de {n}")
        for n, s in zip(nombres, scores, strict=True)
    )
    return ConfluenceResult(
        symbol="BTC/USDT",
        timeframe="4h",
        timestamp=pd.Timestamp("2026-08-01 08:00", tz="UTC"),
        price=63000.0,
        count=make_count(),
        signal_direction=BULLISH,
        factors=factors,
        min_active_factors=3,
        zone=(60000.0, 61000.0),
        count_invalidation=55000.0,
        signal_invalidation=58000.0,
    )


def make_config() -> Config:
    return Config(
        {
            "paths": {"cache_dir": "data/cache", "reports_dir": "reports"},
            "exchanges": {"primary": {"id": "binance", "quote": "USDT"}},
            "universe": {"bases": ["BTC", "ETH"]},
            "timeframes": {"context": "1d", "structure": "4h", "timing": "1h"},
            "history": {"start_date": "2022-01-01", "page_limit": 1000},
            "confluence": {"min_active_factors": 3},
        }
    )


NOW = pd.Timestamp("2026-08-06 09:00", tz="UTC")


def test_una_senal_se_renderiza_con_todos_sus_campos():
    entry = ReportEntry(result=make_result([0.9, 0.8, 0.7, 0.1, 0.1]), is_signal=True, bars_ago=2)
    md = render_markdown([entry], [], cfg=make_config(), now=NOW)

    assert "Señales activas (1)" in md
    assert "BTC/USDT" in md
    assert "largo" in md
    assert "Zona de interés" in md and "60,000.00" in md
    assert "Invalidación de la señal" in md and "58,000.00" in md
    assert "Invalidación del conteo" in md and "55,000.00" in md
    assert "| fibonacci | 0.900 | 0.60 | ✅ |" in md
    assert "no ejecuta órdenes" in md


def test_sin_senales_lo_dice_sin_dramatismo():
    md = render_markdown([], [], cfg=make_config(), now=NOW)
    assert "Señales activas (0)" in md
    assert "comportamiento esperado" in md


def test_los_casi_umbral_van_en_su_propia_seccion():
    cerca = ReportEntry(result=make_result([0.9, 0.8, 0.1, 0.1, 0.1]), is_signal=False, bars_ago=1)
    md = render_markdown([cerca], [], cfg=make_config(), now=NOW)

    assert "Cerca del umbral (1)" in md
    assert "Señales activas (0)" in md
    assert "fibonacci, rsi_divergence" in md


def test_un_conteo_con_un_solo_factor_no_aparece_ni_como_cercano():
    lejos = ReportEntry(result=make_result([0.9, 0.1, 0.1, 0.1, 0.1]), is_signal=False, bars_ago=1)
    md = render_markdown([lejos], [], cfg=make_config(), now=NOW)
    assert "Cerca del umbral" not in md


def test_los_avisos_se_incluyen():
    md = render_markdown([], ["ETH/USDT: sin datos en caché"], cfg=make_config(), now=NOW)
    assert "## Avisos" in md
    assert "ETH/USDT: sin datos en caché" in md


def test_el_conteo_ambiguo_lista_sus_alternativas():
    result = make_result([0.9, 0.8, 0.7, 0.1, 0.1])
    prices = [100.0, 200.0, 150.0, 250.0]
    pivots = [pivot(i * 10, p, LOW if i % 2 == 0 else HIGH) for i, p in enumerate(prices)]
    ambiguo = next(c for c in validate_sequence(pivots, ElliottParams()) if c.is_ambiguous)
    result = ConfluenceResult(**{**result.__dict__, "count": ambiguo})
    entry = ReportEntry(result=result, is_signal=True, bars_ago=0)
    md = render_markdown([entry], [], cfg=make_config(), now=NOW)

    assert "Hipótesis alternativas" in md
    assert "el conteo es ambiguo" in md
