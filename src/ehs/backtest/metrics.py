"""Métricas de un conjunto de operaciones.

Se reporta la **distribución** y no solo la media, porque en sistemas con pocas
operaciones la media la puede escribir un único resultado extremo. Los
percentiles y el peor caso dicen más sobre lo que se puede esperar que la
esperanza matemática.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ehs.backtest.engine import Trade

PERCENTILES: tuple[int, ...] = (5, 25, 50, 75, 95)


@dataclass(frozen=True)
class Metrics:
    """Resumen de rendimiento. Todos los retornos son netos de costes."""

    n_trades: int
    win_rate: float
    profit_factor: float
    expectancy: float
    median_return: float
    std_return: float
    sharpe: float
    max_drawdown: float
    total_return: float
    best: float
    worst: float
    avg_bars_held: float
    percentiles: dict[int, float] = field(default_factory=dict)
    by_exit_reason: dict[str, int] = field(default_factory=dict)
    by_direction: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        if self.n_trades == 0:
            return "sin operaciones"
        return (
            f"{self.n_trades} operaciones | acierto {self.win_rate:.1%} | "
            f"profit factor {self.profit_factor:.2f} | esperanza {self.expectancy:+.3%} | "
            f"Sharpe {self.sharpe:.2f} | max DD {self.max_drawdown:.1%} | "
            f"retorno total {self.total_return:+.1%}"
        )

    def detail(self) -> str:
        if self.n_trades == 0:
            return "sin operaciones"
        pct = "  ".join(f"p{p}={self.percentiles[p]:+.2%}" for p in sorted(self.percentiles))
        salidas = ", ".join(f"{k}={v}" for k, v in sorted(self.by_exit_reason.items()))
        direcciones = ", ".join(f"{k}={v}" for k, v in sorted(self.by_direction.items()))
        return (
            f"{self.summary()}\n"
            f"    distribución: {pct}\n"
            f"    mejor {self.best:+.2%} | peor {self.worst:+.2%} | "
            f"mediana {self.median_return:+.3%} | desv. {self.std_return:.3%}\n"
            f"    salidas: {salidas}\n"
            f"    dirección: {direcciones} | duración media {self.avg_bars_held:.1f} velas"
        )


def equity_curve(trades: Sequence[Trade]) -> pd.Series:
    """Capital compuesto, con las operaciones ordenadas por cierre."""
    if not trades:
        return pd.Series(dtype="float64")
    ordered = sorted(trades, key=lambda t: t.exit_time)
    equity = np.cumprod([1.0 + t.net_return for t in ordered])
    return pd.Series(equity, index=[t.exit_time for t in ordered], name="equity")


def max_drawdown(curve: pd.Series) -> float:
    """Caída máxima desde máximo previo, como fracción positiva."""
    if curve.empty:
        return 0.0
    running_max = curve.cummax()
    return float((1.0 - curve / running_max).max())


def compute_metrics(trades: Sequence[Trade]) -> Metrics:
    """Calcula todas las métricas sobre los retornos netos."""
    if not trades:
        return Metrics(
            n_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            expectancy=0.0,
            median_return=0.0,
            std_return=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            total_return=0.0,
            best=0.0,
            worst=0.0,
            avg_bars_held=0.0,
        )

    returns = np.array([t.net_return for t in trades], dtype="float64")
    wins = returns[returns > 0]
    losses = returns[returns <= 0]

    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    # Sin pérdidas el profit factor es infinito; se reporta como inf en vez de
    # como un número grande arbitrario.
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else math.inf

    curve = equity_curve(trades)

    by_reason: dict[str, int] = {}
    by_direction: dict[str, int] = {}
    for trade in trades:
        by_reason[trade.exit_reason] = by_reason.get(trade.exit_reason, 0) + 1
        by_direction[trade.direction] = by_direction.get(trade.direction, 0) + 1

    return Metrics(
        n_trades=len(trades),
        win_rate=float(len(wins) / len(returns)),
        profit_factor=profit_factor,
        expectancy=float(returns.mean()),
        median_return=float(np.median(returns)),
        std_return=float(returns.std(ddof=1)) if len(returns) > 1 else 0.0,
        sharpe=annualised_sharpe(trades),
        max_drawdown=max_drawdown(curve),
        total_return=float(curve.iloc[-1] - 1.0),
        best=float(returns.max()),
        worst=float(returns.min()),
        avg_bars_held=float(np.mean([t.bars_held for t in trades])),
        percentiles={p: float(np.percentile(returns, p)) for p in PERCENTILES},
        by_exit_reason=by_reason,
        by_direction=by_direction,
    )


def annualised_sharpe(trades: Sequence[Trade]) -> float:
    """Sharpe por operación, anualizado con la frecuencia real observada.

    Se anualiza con las operaciones por año que el sistema produjo de hecho, no
    con una constante: un sistema que opera cuatro veces al año no puede
    presumir del mismo factor de escala que uno que opera cada día.
    """
    if len(trades) < 2:
        return 0.0
    returns = np.array([t.net_return for t in trades], dtype="float64")
    std = returns.std(ddof=1)
    if std <= 0:
        return 0.0

    span = max(t.exit_time for t in trades) - min(t.entry_time for t in trades)
    years = span.total_seconds() / (365.25 * 24 * 3600)
    if years <= 0:
        return 0.0
    trades_per_year = len(trades) / years
    return float(returns.mean() / std * math.sqrt(trades_per_year))
