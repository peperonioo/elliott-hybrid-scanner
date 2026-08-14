"""Fixtures compartidas entre los tests del informe Markdown y de la web."""

from __future__ import annotations

import pandas as pd

from ehs.config import Config
from ehs.confluence.scorer import ConfluenceResult, FactorScore
from ehs.elliott.validator import BULLISH, ElliottParams, validate_sequence
from ehs.report.daily import ReportEntry
from ehs.structure.swings import HIGH, LOW, Pivot

NOW = pd.Timestamp("2026-08-06 09:00", tz="UTC")


def _pivot(index: int, price: float, kind: str) -> Pivot:
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
    pivots = [_pivot(i * 10, p, LOW if i % 2 == 0 else HIGH) for i, p in enumerate(prices)]
    return validate_sequence(pivots, ElliottParams())[0]


def make_entry(scores: list[float], *, is_signal: bool, detail: str | None = None) -> ReportEntry:
    nombres = ["fibonacci", "rsi_divergence", "market_structure", "volume_profile", "trend"]
    factors = tuple(
        FactorScore(
            name=n,
            score=s,
            threshold=0.6,
            weight=0.2,
            detail=detail if detail is not None else f"detalle de {n}",
        )
        for n, s in zip(nombres, scores, strict=True)
    )
    result = ConfluenceResult(
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
    return ReportEntry(result=result, is_signal=is_signal, bars_ago=2)


def make_config() -> Config:
    return Config(
        {
            "paths": {"cache_dir": "data/cache", "reports_dir": "reports", "web_dir": "docs"},
            "exchanges": {"primary": {"id": "binance", "quote": "USDT"}},
            "universe": {"bases": ["BTC", "ETH"]},
            "timeframes": {"context": "1d", "structure": "4h", "timing": "1h"},
            "history": {"start_date": "2022-01-01", "page_limit": 1000},
            "confluence": {"min_active_factors": 3},
            "report": {
                "projection": {
                    "n_trades": 195,
                    "target_pct": 21.5,
                    "stop_pct": 34.9,
                    "timeout_pct": 43.6,
                    "timeout_avg_pct": 1.4,
                    "expectancy_pct": 1.9,
                }
            },
        }
    )
