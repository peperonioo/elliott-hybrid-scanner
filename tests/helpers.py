"""Dobles y generadores de datos para los tests.

Ningún test de esta suite toca la red: los exchanges se sustituyen por un doble
determinista que sirve velas sintéticas y pagina como el original.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ehs.data.schema import frame_from_ccxt, timeframe_to_ms


def ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def to_ms(value: str) -> int:
    return int(ts(value).timestamp() * 1000)


def make_rows(
    start: str, timeframe: str, count: int, *, price: float = 100.0, volume: float = 10.0
) -> list[list[float]]:
    """Velas crudas al estilo ccxt: [timestamp_ms, open, high, low, close, volume]."""
    tf_ms = timeframe_to_ms(timeframe)
    origin = to_ms(start)
    rows: list[list[float]] = []
    for i in range(count):
        open_ = price + i
        close = open_ + 0.5
        rows.append([origin + i * tf_ms, open_, close + 0.5, open_ - 0.5, close, volume])
    return rows


def make_frame(start: str, timeframe: str, count: int, **kwargs: Any) -> pd.DataFrame:
    return frame_from_ccxt(make_rows(start, timeframe, count, **kwargs))


class FakeExchange:
    """Doble de un exchange ccxt con paginación real sobre velas en memoria."""

    def __init__(
        self,
        rows: list[list[float]] | None = None,
        *,
        markets: dict[str, Any] | None = None,
        timeframes: dict[str, str] | None = None,
        ignores_since: bool = False,
        max_per_page: int | None = None,
    ) -> None:
        self.rows = sorted(rows or [], key=lambda r: r[0])
        self.markets = markets if markets is not None else {"BTC/USDT": {"active": True}}
        self.timeframes = (
            timeframes if timeframes is not None else {"1h": "1h", "4h": "4h", "1d": "1d"}
        )
        # `ignores_since=True` emula a Kraken: devuelve siempre las últimas
        # velas disponibles sin respetar el punto de partida solicitado.
        self.ignores_since = ignores_since
        self.max_per_page = max_per_page
        self.calls: list[tuple[str, str, int | None, int | None]] = []

    def load_markets(self) -> dict[str, Any]:
        return self.markets

    def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None
    ) -> list[list[float]]:
        self.calls.append((symbol, timeframe, since, limit))
        effective = limit or len(self.rows)
        if self.max_per_page is not None:
            effective = min(effective, self.max_per_page)
        if self.ignores_since:
            return self.rows[-effective:]
        selected = [row for row in self.rows if since is None or row[0] >= since]
        return selected[:effective]


class FlakyExchange(FakeExchange):
    """Falla las primeras `fail_times` llamadas con el error indicado."""

    def __init__(self, *args: Any, error: Exception, fail_times: int, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.error = error
        self.fail_times = fail_times
        self.attempts = 0

    def fetch_ohlcv(self, *args: Any, **kwargs: Any) -> list[list[float]]:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise self.error
        return super().fetch_ohlcv(*args, **kwargs)
