"""Esquema canónico de las series OHLCV y utilidades de timeframe.

Todo el sistema asume, a partir de la fase 1, que una serie de precios es un
DataFrame con:

  - índice `timestamp`: DatetimeIndex en UTC, ordenado, único, tz-aware
  - columnas `open, high, low, close, volume`: float64

Cualquier módulo posterior puede darlo por hecho sin volver a comprobarlo.
"""

from __future__ import annotations

import pandas as pd

INDEX_NAME = "timestamp"
OHLCV_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")

# Columnas tal y como las devuelve ccxt.fetch_ohlcv (lista de listas).
CCXT_COLUMNS: tuple[str, ...] = (INDEX_NAME, *OHLCV_COLUMNS)

_MINUTE_MS = 60_000
_TIMEFRAME_UNITS_MS: dict[str, int] = {
    "m": _MINUTE_MS,
    "h": 60 * _MINUTE_MS,
    "d": 24 * 60 * _MINUTE_MS,
    "w": 7 * 24 * 60 * _MINUTE_MS,
}


class SchemaError(Exception):
    """Una serie no cumple el esquema canónico."""


def timeframe_to_ms(timeframe: str) -> int:
    """Convierte "4h", "1d", "15m"... a milisegundos.

    No se delega en ccxt para poder usarlo en tests sin red ni exchange.
    """
    tf = timeframe.strip().lower()
    if len(tf) < 2:
        raise ValueError(f"Timeframe inválido: {timeframe!r}")
    unit = tf[-1]
    if unit not in _TIMEFRAME_UNITS_MS:
        raise ValueError(f"Unidad de timeframe no soportada: {timeframe!r}")
    try:
        amount = int(tf[:-1])
    except ValueError as exc:
        raise ValueError(f"Timeframe inválido: {timeframe!r}") from exc
    if amount <= 0:
        raise ValueError(f"El timeframe debe ser positivo: {timeframe!r}")
    return amount * _TIMEFRAME_UNITS_MS[unit]


def timeframe_to_timedelta(timeframe: str) -> pd.Timedelta:
    return pd.Timedelta(timeframe_to_ms(timeframe), unit="ms")


def empty_frame() -> pd.DataFrame:
    """DataFrame vacío que ya cumple el esquema canónico."""
    frame = pd.DataFrame({col: pd.Series(dtype="float64") for col in OHLCV_COLUMNS})
    frame.index = pd.DatetimeIndex([], tz="UTC", name=INDEX_NAME)
    return frame


def frame_from_ccxt(rows: list[list[float]]) -> pd.DataFrame:
    """Convierte la salida cruda de `fetch_ohlcv` al esquema canónico."""
    if not rows:
        return empty_frame()

    frame = pd.DataFrame(rows, columns=list(CCXT_COLUMNS))
    frame[INDEX_NAME] = pd.to_datetime(frame[INDEX_NAME], unit="ms", utc=True)
    frame = frame.set_index(INDEX_NAME)
    for col in OHLCV_COLUMNS:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").astype("float64")
    return frame.sort_index()


def normalise(frame: pd.DataFrame) -> pd.DataFrame:
    """Fuerza el esquema: tipos, orden, unicidad y zona horaria.

    Ante timestamps duplicados conserva la última aparición, que es la lectura
    más reciente que el exchange ha dado de esa vela.
    """
    if frame.empty:
        return empty_frame()

    out = frame.copy()
    missing = [col for col in OHLCV_COLUMNS if col not in out.columns]
    if missing:
        raise SchemaError(f"Faltan columnas OHLCV: {missing}")

    index = pd.DatetimeIndex(out.index)
    index = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    out.index = index.rename(INDEX_NAME)

    out = out[list(OHLCV_COLUMNS)].astype("float64")
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()


def closed_candles(frame: pd.DataFrame, timeframe: str, now_ms: int) -> pd.DataFrame:
    """Velas de `frame` que ya habían cerrado en el instante `now_ms`.

    Una vela con apertura en `t` cierra en `t + tf`, así que solo es conocida
    cuando `now >= t + tf`.

    Es la pieza que evita dos fugas de información distintas: la vela en curso
    en la ingesta, y —más traicionera— el desfase entre timeframes. Al evaluar
    una señal en la vela de 4h de las 08:00, la vela diaria de hoy todavía no
    ha cerrado: usar su `close` sería leer el futuro.
    """
    if frame.empty:
        return frame
    tf_ms = timeframe_to_ms(timeframe)
    open_ms = frame.index.astype("int64") // 1_000_000
    return frame[open_ms + tf_ms <= now_ms]


def close_time_ms(timestamp: pd.Timestamp, timeframe: str) -> int:
    """Instante en el que cierra la vela abierta en `timestamp`."""
    return int(timestamp.timestamp() * 1000) + timeframe_to_ms(timeframe)


def assert_valid(frame: pd.DataFrame) -> None:
    """Comprobación defensiva del esquema. Lanza `SchemaError` si no cumple."""
    if list(frame.columns) != list(OHLCV_COLUMNS):
        raise SchemaError(f"Columnas inesperadas: {list(frame.columns)}")
    if frame.index.name != INDEX_NAME:
        raise SchemaError(f"El índice debe llamarse {INDEX_NAME!r}")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise SchemaError("El índice debe ser un DatetimeIndex")
    if frame.index.tz is None:
        raise SchemaError("El índice debe ser tz-aware en UTC")
    # Los duplicados se comprueban antes que el orden: un índice ordenado con
    # timestamps repetidos sigue siendo monótono, así que el mensaje de error
    # útil es siempre el de duplicados.
    if frame.index.has_duplicates:
        raise SchemaError("El índice contiene timestamps duplicados")
    if not frame.index.is_monotonic_increasing:
        raise SchemaError("El índice debe estar ordenado ascendentemente")
