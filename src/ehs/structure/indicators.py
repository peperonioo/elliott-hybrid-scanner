"""Indicadores de volatilidad usados por la detección de swings.

El ATR se implementa aquí en lugar de delegarlo en una librería porque es el
número más crítico del sistema: gobierna el umbral del ZigZag y, con él, qué
conteos de Elliott son siquiera posibles. Necesitamos una garantía dura de dos
propiedades:

  1. **Causalidad**: `atr[i]` depende solo de las velas hasta `i`.
  2. **Estabilidad ante prefijos**: calcular el ATR sobre `frame[:t+1]` da
     exactamente los mismos valores que calcularlo sobre la serie completa y
     quedarse con los primeros `t+1`.

La segunda es la que permite escribir un test de ausencia de lookahead bias que
signifique algo. `tests/test_indicators.py` comprueba además que el resultado
coincide con la implementación de referencia de la librería `ta`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(frame: pd.DataFrame) -> pd.Series:
    """True Range de Wilder.

    TR = max(high - low, |high - close_prev|, |low - close_prev|)

    En la primera vela no hay cierre previo, así que TR = high - low.
    """
    high = frame["high"].to_numpy(dtype="float64")
    low = frame["low"].to_numpy(dtype="float64")
    close_prev = np.empty_like(high)
    close_prev[0] = np.nan
    close_prev[1:] = frame["close"].to_numpy(dtype="float64")[:-1]

    spans = np.vstack(
        [
            high - low,
            np.abs(high - close_prev),
            np.abs(low - close_prev),
        ]
    )
    tr = np.nanmax(spans, axis=0)
    return pd.Series(tr, index=frame.index, name="true_range")


def wilder_atr(frame: pd.DataFrame, period: int) -> pd.Series:
    """ATR con el suavizado de Wilder (RMA).

    Se siembra con la media simple de los `period` primeros TR y a partir de
    ahí es puramente recursivo hacia atrás:

        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period

    Las primeras `period - 1` posiciones quedan a NaN: no hay ATR definido
    todavía y rellenarlas sería inventarse volatilidad.
    """
    if period < 1:
        raise ValueError(f"El periodo del ATR debe ser >= 1, es {period}")

    tr = true_range(frame).to_numpy(dtype="float64")
    atr = np.full(len(tr), np.nan, dtype="float64")
    if len(tr) < period:
        return pd.Series(atr, index=frame.index, name="atr")

    atr[period - 1] = tr[:period].mean()
    for i in range(period, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return pd.Series(atr, index=frame.index, name="atr")


def wilder_rsi(frame: pd.DataFrame, period: int, column: str = "close") -> pd.Series:
    """RSI con el suavizado de Wilder.

    Mismo criterio que el ATR: implementación propia para garantizar causalidad
    y estabilidad ante prefijos. Las primeras `period` posiciones quedan a NaN.

    La recursión se siembra con la media simple de los `period` primeros
    valores, que es la formulación original de Wilder y la que usa TradingView
    —donde se validarán las señales a ojo—. La librería `ta` arranca desde el
    primer valor en lugar de sembrar, así que difiere durante el arranque
    aunque ambas series convergen después. Los tests comprueban las dos cosas.
    """
    if period < 1:
        raise ValueError(f"El periodo del RSI debe ser >= 1, es {period}")

    values = frame[column].to_numpy(dtype="float64")
    rsi = np.full(len(values), np.nan, dtype="float64")
    if len(values) <= period:
        return pd.Series(rsi, index=frame.index, name="rsi")

    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    rsi[period] = _rsi_from(avg_gain, avg_loss)

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rsi[i + 1] = _rsi_from(avg_gain, avg_loss)

    return pd.Series(rsi, index=frame.index, name="rsi")


def _rsi_from(avg_gain: float, avg_loss: float) -> float:
    # Sin pérdidas medias el RSI satura en 100; es el límite del cociente.
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def ema(series: pd.Series, period: int) -> pd.Series:
    """Media exponencial sembrada con la media simple de los `period` primeros.

    La siembra con SMA —en lugar del primer valor— es lo que la hace estable
    ante prefijos: el arranque no depende de cuántas velas haya después.
    """
    if period < 1:
        raise ValueError(f"El periodo de la EMA debe ser >= 1, es {period}")

    values = series.to_numpy(dtype="float64")
    out = np.full(len(values), np.nan, dtype="float64")
    if len(values) < period:
        return pd.Series(out, index=series.index, name="ema")

    alpha = 2.0 / (period + 1.0)
    out[period - 1] = values[:period].mean()
    for i in range(period, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]

    return pd.Series(out, index=series.index, name="ema")


def first_valid_position(series: pd.Series) -> int | None:
    """Posición entera del primer valor no nulo, o None si no hay ninguno."""
    valid = np.flatnonzero(~np.isnan(series.to_numpy(dtype="float64")))
    return int(valid[0]) if valid.size else None
