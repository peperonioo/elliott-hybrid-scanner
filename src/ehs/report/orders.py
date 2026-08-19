"""Órdenes límite sugeridas: a qué distancia se llenan, empíricamente.

Una orden límite solo sirve si el precio la visita. Este módulo mide, sobre
todo el histórico de cada moneda, la **excursión** del precio en las siguientes
24 horas: cuánto llegó a subir (máximo) y cuánto llegó a bajar (mínimo) desde
el cierre de cada vela. De esa distribución sale la respuesta directa a "¿dónde
pongo el límite?": el precio al que, históricamente, el mercado llegó el 60% de
las veces (probable) o el 30% (ambicioso).

Es probabilidad de EJECUCIÓN, no de beneficio: una compra límite que se llena
el 90% de las veces se llena porque el precio está cayendo. Las dos cosas se
leen juntas, no por separado.

Todo es estadística descriptiva del pasado — ni predice ni forma parte del
sistema de señales validado.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

HORIZON_BARS = 6  # 24 h en velas de 4 h
PROB_LIKELY = 0.60  # límite "probable"
PROB_AMBITIOUS = 0.30  # límite "ambicioso"
MIN_WINDOWS = 200  # por debajo, la distribución no es fiable


@dataclass
class OrderLevels:
    """Distancias de ejecución para una moneda, en fracción sobre el precio."""

    price: float
    buy_likely: float  # precio de compra con ~60% de probabilidad de toque
    buy_deep: float  # ~30%
    sell_likely: float  # ~60%
    sell_ambitious: float  # ~30%
    median_up: float  # subida típica en 24 h (fracción)
    median_down: float  # bajada típica en 24 h (fracción, negativa)
    n: int


def compute_order_levels(
    structure: pd.DataFrame, *, horizon: int = HORIZON_BARS
) -> OrderLevels | None:
    """Niveles de orden límite a partir de las excursiones históricas a 24 h."""
    if len(structure) < MIN_WINDOWS + horizon + 1:
        return None

    closes = structure["close"].to_numpy(dtype="float64")
    highs = structure["high"].to_numpy(dtype="float64")
    lows = structure["low"].to_numpy(dtype="float64")

    n = len(closes) - horizon
    # Máximo y mínimo alcanzados en las `horizon` velas siguientes a cada cierre.
    ventanas_high = np.lib.stride_tricks.sliding_window_view(highs[1:], horizon).max(axis=1)
    ventanas_low = np.lib.stride_tricks.sliding_window_view(lows[1:], horizon).min(axis=1)
    base = closes[:n]
    up = ventanas_high[:n] / base - 1.0  # subida máxima alcanzada
    down = ventanas_low[:n] / base - 1.0  # bajada máxima alcanzada (negativa)

    valid = np.isfinite(up) & np.isfinite(down) & (base > 0)
    up, down = up[valid], down[valid]
    if len(up) < MIN_WINDOWS:
        return None

    price = float(closes[-1])
    # P(tocar +d) = p  →  d es el cuantil (1-p) de la distribución de subidas.
    d_sell_likely = float(np.quantile(up, 1 - PROB_LIKELY))
    d_sell_ambitious = float(np.quantile(up, 1 - PROB_AMBITIOUS))
    # Para las bajadas, la cola es la izquierda: P(tocar -d) = p → cuantil p.
    d_buy_likely = float(np.quantile(down, PROB_LIKELY))
    d_buy_deep = float(np.quantile(down, PROB_AMBITIOUS))

    return OrderLevels(
        price=price,
        buy_likely=price * (1 + d_buy_likely),
        buy_deep=price * (1 + d_buy_deep),
        sell_likely=price * (1 + d_sell_likely),
        sell_ambitious=price * (1 + d_sell_ambitious),
        median_up=float(np.median(up)),
        median_down=float(np.median(down)),
        n=len(up),
    )
