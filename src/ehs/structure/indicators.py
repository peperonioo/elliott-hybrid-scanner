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


def first_valid_position(series: pd.Series) -> int | None:
    """Posición entera del primer valor no nulo, o None si no hay ninguno."""
    valid = np.flatnonzero(~np.isnan(series.to_numpy(dtype="float64")))
    return int(valid[0]) if valid.size else None
