"""Baselines contra los que medir el sistema.

Sin baseline un backtest no dice nada: un retorno positivo en un mercado que
subió un 300% no demuestra ninguna habilidad. Se comparan dos:

  - **Buy & hold**: comprar al principio y aguantar, con los mismos costes de
    entrada y salida.
  - **Señales aleatorias**: la misma cantidad de operaciones, la misma mezcla de
    direcciones y **exactamente las mismas reglas de salida y costes**, pero con
    los momentos de entrada elegidos al azar. Es el baseline que importa: aísla
    si el valor está en *cuándo* entra el sistema o solo en cómo sale.

El p-valor es empírico: la proporción de simulaciones aleatorias que igualan o
superan al sistema. Un p-valor de 0.30 significa que casi un tercio de las
carteras aleatorias lo habrían hecho igual de bien, y entonces no hay evidencia
de ventaja por mucho que la esperanza salga positiva.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ehs.backtest.engine import CostModel, ExitRules, Trade, simulate_trade
from ehs.backtest.metrics import Metrics, compute_metrics
from ehs.elliott.validator import BEARISH, BULLISH

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuyAndHold:
    symbol: str
    start: pd.Timestamp
    end: pd.Timestamp
    gross_return: float
    net_return: float


@dataclass(frozen=True)
class RandomBaseline:
    """Distribución de resultados de las carteras aleatorias."""

    trials: int
    expectancies: np.ndarray
    total_returns: np.ndarray
    actual_expectancy: float
    actual_total_return: float

    @property
    def p_value_expectancy(self) -> float:
        """Proporción de simulaciones que igualan o superan al sistema.

        Se cuenta el sistema como una observación más (corrección de Davison &
        Hinkley), que es lo estándar en tests de permutación y evita el p-valor
        exactamente 0, que sería engañoso con un número finito de simulaciones.
        """
        better = int(np.sum(self.expectancies >= self.actual_expectancy))
        return (better + 1) / (self.trials + 1)

    @property
    def p_value_total(self) -> float:
        better = int(np.sum(self.total_returns >= self.actual_total_return))
        return (better + 1) / (self.trials + 1)

    @property
    def percentile(self) -> float:
        """Percentil que ocupa el sistema dentro de la distribución aleatoria."""
        return float((self.expectancies < self.actual_expectancy).mean() * 100)

    def summary(self) -> str:
        return (
            f"aleatorio: esperanza media {self.expectancies.mean():+.3%} "
            f"(p5 {np.percentile(self.expectancies, 5):+.3%}, "
            f"p95 {np.percentile(self.expectancies, 95):+.3%}) | "
            f"sistema {self.actual_expectancy:+.3%} → percentil {self.percentile:.1f}, "
            f"p={self.p_value_expectancy:.3f}"
        )

    def verdict(self, alpha: float = 0.05) -> str:
        """Lectura sin adornos del contraste."""
        if self.p_value_expectancy <= alpha:
            return (
                f"El sistema bate al azar de forma significativa "
                f"(p={self.p_value_expectancy:.3f} ≤ {alpha})."
            )
        return (
            f"NO hay evidencia de que el sistema bata al azar "
            f"(p={self.p_value_expectancy:.3f} > {alpha}). "
            f"{self.p_value_expectancy:.0%} de las carteras aleatorias con la misma "
            f"frecuencia y las mismas reglas de salida lo igualan o superan."
        )


def buy_and_hold(frame: pd.DataFrame, symbol: str, costs: CostModel) -> BuyAndHold:
    """Comprar en la primera vela y vender en la última, pagando costes."""
    first = float(frame["open"].iloc[0])
    last = float(frame["close"].iloc[-1])
    gross = last / first - 1.0
    net = costs.apply(gross)
    return BuyAndHold(
        symbol=symbol,
        start=frame.index[0],
        end=frame.index[-1],
        gross_return=gross,
        net_return=net,
    )


def random_trades(
    frames: dict[str, pd.DataFrame],
    template: Sequence[Trade],
    *,
    rules: ExitRules,
    costs: CostModel,
    rng: np.random.Generator,
) -> list[Trade]:
    """Reproduce la cartera con entradas al azar.

    Se conserva de cada operación real el par y la dirección; solo se cambia el
    momento de entrada. Así el contraste aísla el poder de la señal y no la
    mezcla de mercados ni el sesgo direccional.
    """
    trades: list[Trade] = []
    for original in template:
        frame = frames.get(original.symbol)
        if frame is None or len(frame) < rules.max_bars + 3:
            continue
        # El índice de señal debe dejar sitio para la entrada y el horizonte.
        high = len(frame) - rules.max_bars - 2
        if high <= 0:
            continue
        signal_index = int(rng.integers(0, high))

        # El stop se replica en riesgo relativo, no en precio absoluto: un nivel
        # de hace dos años no significa nada en otro punto de la serie.
        entry_reference = float(frame["open"].iloc[signal_index + 1])
        risk_fraction = abs(original.entry_price - original.stop_price) / original.entry_price
        sign = -1.0 if original.direction == BULLISH else 1.0
        stop_price = entry_reference * (1 + sign * risk_fraction)

        outcome = simulate_trade(
            frame,
            symbol=original.symbol,
            signal_index=signal_index,
            direction=original.direction,
            stop_price=stop_price,
            rules=rules,
            costs=costs,
        )
        if not isinstance(outcome, str):
            trades.append(outcome)
    return trades


def random_baseline(
    frames: dict[str, pd.DataFrame],
    actual: Sequence[Trade],
    *,
    rules: ExitRules,
    costs: CostModel,
    trials: int = 1000,
    seed: int = 20240101,
) -> RandomBaseline | None:
    """Ejecuta `trials` carteras aleatorias equivalentes a la real."""
    if not actual:
        return None

    rng = np.random.default_rng(seed)
    actual_metrics = compute_metrics(actual)

    expectancies = np.empty(trials, dtype="float64")
    totals = np.empty(trials, dtype="float64")
    for i in range(trials):
        simulated = random_trades(frames, actual, rules=rules, costs=costs, rng=rng)
        metrics = compute_metrics(simulated)
        expectancies[i] = metrics.expectancy
        totals[i] = metrics.total_return

    return RandomBaseline(
        trials=trials,
        expectancies=expectancies,
        total_returns=totals,
        actual_expectancy=actual_metrics.expectancy,
        actual_total_return=actual_metrics.total_return,
    )


def direction_mix(trades: Sequence[Trade]) -> dict[str, int]:
    mix = {BULLISH: 0, BEARISH: 0}
    for trade in trades:
        mix[trade.direction] = mix.get(trade.direction, 0) + 1
    return mix


def summarise_buy_and_hold(results: Sequence[BuyAndHold]) -> str:
    if not results:
        return "sin datos"
    nets = np.array([r.net_return for r in results], dtype="float64")
    detalle = ", ".join(f"{r.symbol.split('/')[0]} {r.net_return:+.1%}" for r in results)
    return f"media {nets.mean():+.1%} | mediana {np.median(nets):+.1%}\n    {detalle}"


def metrics_or_empty(trades: Sequence[Trade]) -> Metrics:
    return compute_metrics(trades)
