"""Fixtures compartidas."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def config_dict() -> dict[str, Any]:
    """Configuración mínima y válida para los tests de ingesta."""
    return {
        "paths": {"cache_dir": "data/cache"},
        "exchanges": {
            "primary": {"id": "binance", "quote": "USDT"},
            "fallback": {"id": "kraken", "quote": "USD"},
            "symbol_overrides": {},
            "rate_limit": {"enable_throttle": True, "extra_sleep_ms": 0},
            "retry": {
                "max_attempts": 3,
                "base_delay_s": 0.0,
                "backoff_factor": 1.0,
                "max_delay_s": 0.0,
                "jitter": False,
            },
        },
        "universe": {"bases": ["BTC"]},
        "timeframes": {"context": "1d", "structure": "4h", "timing": "1h"},
        "history": {
            "start_date": "2024-01-01",
            "page_limit": 100,
            "overlap_candles": 2,
            "drop_incomplete_candle": True,
        },
        "validation": {
            "on_gap": "warn",
            "on_zero_volume": "warn",
            "on_duplicate": "fix",
            "on_ohlc_inconsistency": "warn",
            "max_gap_ratio": 1.0,
            "min_candles": 0,
        },
    }
