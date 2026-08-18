"""Panel «¿sube o baja?»: frecuencias históricas condicionadas al estado actual.

Para cada moneda se clasifica cada vela de 4h de su historia en un «estado»
sencillo y causal (tendencia larga, momentum de 24h y zona de RSI) y se mide
qué hizo el precio 24 horas después. El estado ACTUAL de la moneda se busca en
esa tabla: «en los N casos parecidos del histórico, el precio estaba más alto
24h después el P% de las veces».

Esto NO es el sistema de señales ni una predicción: es estadística descriptiva
transparente, pensada para responder rápido a la pregunta de una competición
de predicción («¿BTC sube o baja?») con la base histórica real. Un 50% aquí
significa literalmente «moneda al aire». Los estados se definieron a priori
(las tres variables más estándar de un panel direccional) y no se han
optimizado contra ningún resultado.

Todo es causal: el estado de la vela t usa solo datos hasta t (EMA y RSI de
Wilder son estables ante prefijos), y el desenlace mira t+6 velas.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ehs.structure.indicators import ema, wilder_rsi

HORIZON_BARS = 6  # 24 h en velas de 4 h
TREND_EMA_PERIOD = 300  # ~EMA50 diaria expresada en velas de 4h
RSI_PERIOD = 14
MIN_SAMPLE = 150  # por debajo, la frecuencia no es fiable y se dice


@dataclass
class DirectionStats:
    """Resultado del panel para una moneda."""

    trend_up: bool
    momentum_up: bool
    rsi_zone: str  # "sobreventa" | "débil" | "fuerte" | "sobrecompra"
    p_up: float  # frecuencia histórica de cierre más alto a 24h, en [0,1]
    avg_move: float  # variación media a 24h en los casos del estado (fracción)
    n: int  # tamaño de muestra del estado
    reliable: bool  # n >= MIN_SAMPLE

    @property
    def estado_txt(self) -> str:
        tend = "tendencia ↑" if self.trend_up else "tendencia ↓"
        mom = "momentum ↑" if self.momentum_up else "momentum ↓"
        return f"{tend} · {mom} · RSI {self.rsi_zone}"


def _rsi_zone(value: float) -> str:
    if value < 30:
        return "sobreventa"
    if value < 50:
        return "débil"
    if value < 70:
        return "fuerte"
    return "sobrecompra"


def compute_direction_stats(structure: pd.DataFrame) -> DirectionStats | None:
    """Clasifica el estado actual y devuelve sus frecuencias históricas a 24h.

    `structure` es el frame de 4h completo de la moneda (velas cerradas).
    Devuelve None si no hay historia suficiente para definir el estado.
    """
    closes = structure["close"].to_numpy(dtype="float64")
    if len(closes) < TREND_EMA_PERIOD + HORIZON_BARS + 2:
        return None

    trend = ema(structure["close"], TREND_EMA_PERIOD).to_numpy(dtype="float64")
    rsi = wilder_rsi(structure, RSI_PERIOD).to_numpy(dtype="float64")

    # Estado por vela (causal): cada componente usa solo datos hasta t.
    trend_up = closes > trend
    momentum_up = np.empty(len(closes), dtype=bool)
    momentum_up[:HORIZON_BARS] = False
    momentum_up[HORIZON_BARS:] = closes[HORIZON_BARS:] > closes[:-HORIZON_BARS]

    valid = ~np.isnan(trend) & ~np.isnan(rsi)
    valid[:HORIZON_BARS] = False  # sin momentum definido

    last = len(closes) - 1
    if not valid[last]:
        return None
    zone_now = _rsi_zone(rsi[last])

    # Casos históricos en el mismo estado, con desenlace conocido (t+6 dentro).
    matches: list[float] = []
    for t in range(len(closes) - HORIZON_BARS):
        if not valid[t]:
            continue
        if trend_up[t] != trend_up[last]:
            continue
        if momentum_up[t] != momentum_up[last]:
            continue
        if _rsi_zone(rsi[t]) != zone_now:
            continue
        matches.append(closes[t + HORIZON_BARS] / closes[t] - 1)

    if not matches:
        return None
    moves = np.array(matches, dtype="float64")
    return DirectionStats(
        trend_up=bool(trend_up[last]),
        momentum_up=bool(momentum_up[last]),
        rsi_zone=zone_now,
        p_up=float((moves > 0).mean()),
        avg_move=float(moves.mean()),
        n=len(moves),
        reliable=len(moves) >= MIN_SAMPLE,
    )
