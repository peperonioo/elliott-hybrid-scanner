"""Régimen de mercado y zonas de retroceso corto.

El sistema de señales compra retrocesos profundos de una estructura terminada.
Cuando el mercado entra en un impulso vertical, esas zonas quedan muy por
debajo del precio y la página repetía «espera a que baje» en todas las monedas
— cierto, pero inútil: no distinguía «no hay nada» de «el tren ya salió».

Este módulo añade el contexto que faltaba, con dos piezas:

1. `classify_regime`: mide la **amplitud** (cuántas monedas están sobre su
   media larga) y el movimiento agregado reciente del universo, y nombra el
   régimen. Es el aviso de que el mapa de zonas está calculado para otro
   mercado.
2. `pullback_zone`: en un tramo alcista en marcha, el retroceso **corto**
   (0.236-0.382 del tramo) es donde compra quien sigue tendencias, en vez del
   0.618-0.786 que espera el sistema.

Nada de esto toca la lógica de señales ni está validado por el backtest: es
contexto declarado como tal, igual que la zona DCA.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ehs.structure.indicators import ema
from ehs.structure.swings import Pivot

TREND_EMA_DAILY = 50
MOVE_LOOKBACK_DAYS = 7
PULLBACK_RETR = (0.236, 0.382)

STRONG_UP = 6.0  # % medio del universo en 7 días
MILD_UP = 1.5
MILD_DOWN = -1.5
STRONG_DOWN = -6.0
BREADTH_WIDE = 0.70  # fracción de monedas sobre su media


@dataclass
class Regime:
    """Estado agregado del mercado y qué implica para la herramienta."""

    label: str
    cls: str  # win | flat | loss
    move_pct: float  # movimiento medio del universo en 7 días
    breadth: float  # fracción de monedas sobre su EMA50 diaria
    n: int
    text: str


def coin_context(context: pd.DataFrame) -> tuple[float, bool] | None:
    """Movimiento de 7 días y si la moneda está sobre su media larga."""
    if len(context) < TREND_EMA_DAILY + MOVE_LOOKBACK_DAYS + 1:
        return None
    closes = context["close"]
    trend = ema(closes, TREND_EMA_DAILY)
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-1 - MOVE_LOOKBACK_DAYS])
    if prev <= 0:
        return None
    ema_last = float(trend.iloc[-1])
    return (last / prev - 1.0) * 100, last > ema_last


def classify_regime(readings: list[tuple[float, bool]]) -> Regime | None:
    """Nombra el régimen a partir de las lecturas de todas las monedas."""
    if not readings:
        return None
    moves = sorted(m for m, _ in readings)
    n = len(moves)
    # Mediana: un par de alts disparadas no deciden el régimen del universo.
    move = moves[n // 2] if n % 2 else (moves[n // 2 - 1] + moves[n // 2]) / 2
    breadth = sum(1 for _, up in readings if up) / n

    if move >= STRONG_UP and breadth >= BREADTH_WIDE:
        label, cls = "impulso alcista fuerte", "win"
        text = (
            "El mercado se ha movido con fuerza al alza y casi todo está sobre su media. "
            "<b>Las zonas de compra del plan quedan muy por debajo del precio</b>: son "
            "retrocesos profundos de la estructura anterior, y en un impulso así el "
            "precio rara vez vuelve ahí. Lo que dice el sistema es <b>«ya no es momento "
            "de comprar barato»</b>, no «esto no sirve». Dos salidas honestas: esperar a "
            "que se forme una estructura nueva (pasa solo, cada 4 h), o —si operas el "
            "impulso por tu cuenta— usar la <b>zona de retroceso corto</b> de cada "
            "tarjeta, que no está validada por el backtest."
        )
    elif move >= MILD_UP:
        label, cls = "alcista", "win"
        text = (
            "Mercado al alza sin verticalidad. Las zonas de compra del plan siguen "
            "siendo relevantes: si el precio corrige hacia ellas, la jugada mantiene "
            "sentido."
        )
    elif move <= STRONG_DOWN:
        label, cls = "caída fuerte", "loss"
        text = (
            "Caída generalizada. Un sistema que solo compra sufre aquí: lo esperable es "
            "que no haya señales y que las lecturas sean bajistas. Las zonas de compra "
            "pueden quedar por encima del precio — eso <b>no</b> es una rebaja, es una "
            "estructura rota. Paciencia."
        )
    elif move <= MILD_DOWN:
        label, cls = "bajista", "loss"
        text = (
            "Mercado a la baja. Habrá pocas señales y muchas lecturas bajistas; es el "
            "comportamiento correcto de un sistema solo-largos, no un fallo."
        )
    else:
        label, cls = "lateral", "flat"
        text = (
            "Mercado sin dirección clara. Es el terreno donde las zonas de compra por "
            "retroceso tienen más sentido: el precio va y viene sobre ellas."
        )

    return Regime(label=label, cls=cls, move_pct=move, breadth=breadth, n=n, text=text)


def pullback_zone(pivots: list[Pivot], price: float) -> tuple[float, float] | None:
    """Retroceso corto (0.236-0.382) del tramo alcista en marcha.

    Definido sobre el último mínimo del ZigZag y el máximo alcanzado después.
    Solo tiene sentido si el precio sigue por encima de la banda: si ya cayó
    dentro, el «retroceso corto» no es un nivel futuro sino pasado.
    """
    if len(pivots) < 2:
        return None
    lows = [p for p in pivots if p.kind == "L"]
    if not lows:
        return None
    low = lows[-1]
    posteriores = [p.price for p in pivots if p.index > low.index]
    high = max([*posteriores, price]) if posteriores else price
    span = high - low.price
    if span <= 0:
        return None
    upper = high - span * PULLBACK_RETR[0]
    lower = high - span * PULLBACK_RETR[1]
    if price <= upper:
        return None
    return lower, upper
