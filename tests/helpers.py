"""Dobles y generadores de datos para los tests.

Ningún test de esta suite toca la red: los exchanges se sustituyen por un doble
determinista que sirve velas sintéticas y pagina como el original.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ehs.data.schema import OHLCV_COLUMNS, frame_from_ccxt, normalise, timeframe_to_ms


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


def frame_from_closes(
    closes: np.ndarray | list[float],
    *,
    start: str = "2024-01-01",
    timeframe: str = "4h",
    wick: float = 0.0,
    volume: float = 100.0,
) -> pd.DataFrame:
    """Construye una serie OHLCV coherente a partir de una curva de cierres.

    Cada vela abre en el cierre anterior; `wick` añade mecha simétrica por
    encima y por debajo del cuerpo.
    """
    closes = np.asarray(closes, dtype="float64")
    opens = np.empty_like(closes)
    if len(closes):
        opens[0] = closes[0]
        opens[1:] = closes[:-1]

    body_high = np.maximum(opens, closes)
    body_low = np.minimum(opens, closes)
    index = pd.date_range(ts(start), periods=len(closes), freq=timeframe, tz="UTC")
    volumes = (
        np.full(len(closes), float(volume))
        if np.isscalar(volume)
        else np.asarray(volume, dtype="float64")
    )

    frame = pd.DataFrame(
        {
            "open": opens,
            "high": body_high + wick,
            "low": body_low - wick,
            "close": closes,
            "volume": volumes,
        },
        index=index,
    )
    frame.index.name = "timestamp"
    return normalise(frame[list(OHLCV_COLUMNS)])


def path_closes(waypoints: list[tuple[int, float]]) -> np.ndarray:
    """Curva de cierres que pasa exactamente por los puntos indicados.

    Interpola linealmente entre cada par consecutivo, de modo que los índices
    de los waypoints son giros conocidos y sirven de pivotes en los tests.
    """
    positions = [int(w[0]) for w in waypoints]
    prices = [float(w[1]) for w in waypoints]
    return np.interp(np.arange(positions[-1] + 1), positions, prices)


def random_walk_frame(
    count: int,
    *,
    seed: int = 0,
    start_price: float = 100.0,
    sigma: float = 0.01,
    wick: float = 0.3,
) -> pd.DataFrame:
    """Camino aleatorio reproducible, para tests que necesitan una serie realista."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, sigma, size=count)
    closes = start_price * np.exp(np.cumsum(steps))
    return frame_from_closes(closes, wick=wick)


def zigzag_closes(
    leg_lengths: list[int], amplitude: float, start_price: float = 100.0
) -> np.ndarray:
    """Curva en dientes de sierra con tramos alternos de subida y bajada.

    El primer tramo sube. Cada tramo recorre `amplitude` en `leg_lengths[k]`
    pasos, de modo que los puntos de giro son conocidos de antemano.
    """
    closes = [start_price]
    direction = 1.0
    for length in leg_lengths:
        step = direction * amplitude / length
        closes.extend(closes[-1] + step * (i + 1) for i in range(length))
        direction *= -1.0
    return np.asarray(closes, dtype="float64")


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
