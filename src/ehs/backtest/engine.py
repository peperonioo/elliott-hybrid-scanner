"""Simulación de operaciones: costes reales y reglas de salida explícitas.

Se escribe aquí en lugar de delegar en vectorbt por dos razones concretas. La
primera es que el coste es lo que decide si este sistema tiene o no ventaja
—0.68% de ida y vuelta en Kraken es un listón alto—, así que conviene que su
aplicación sea legible línea a línea. La segunda es que el baseline aleatorio
tiene que pasar por exactamente el mismo motor para que la comparación
signifique algo; con dos motores distintos no lo sería.

## Ausencia de lookahead

  - La señal se evalúa con datos hasta el cierre de la vela `t`; la entrada
    ocurre en la **apertura de `t+1`**. Nunca se entra al cierre de la vela que
    generó la señal, porque ese precio no era operable cuando se supo.
  - Si en la misma vela se tocan stop y objetivo, se asume que saltó el
    **stop**. Con solo OHLC no sabemos el orden intrabar, y suponer lo
    contrario sería regalarse el resultado favorable.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from ehs.config import Config
from ehs.confluence.scorer import ConfluenceResult
from ehs.elliott.validator import BULLISH

LOGGER = logging.getLogger(__name__)

EXIT_STOP = "stop"
EXIT_TARGET = "objetivo"
EXIT_TIMEOUT = "tiempo"


@dataclass(frozen=True)
class CostModel:
    """Costes por lado, en porcentaje del nominal.

    `spread_pct` es el coste de cruzar la horquilla en **un** lado; el viaje
    completo lo paga dos veces, igual que la comisión y el slippage.
    """

    taker_fee_pct: float = 0.26
    slippage_pct: float = 0.05
    spread_pct: float = 0.03

    @property
    def per_side_pct(self) -> float:
        return self.taker_fee_pct + self.slippage_pct + self.spread_pct

    @property
    def round_trip_pct(self) -> float:
        return 2 * self.per_side_pct

    def apply(self, gross_return: float) -> float:
        """Aplica el coste a un retorno bruto.

        El capital se multiplica por `(1 + bruto)` y por `(1 - c)` una vez al
        entrar y otra al salir, pagando el coste sobre el nominal movido en cada
        lado. La formulación es idéntica para largos y cortos, cosa que no
        ocurre si se ajustan los precios de entrada y salida por separado: ahí
        el nominal desplegado difiere y el coste sale asimétrico por un artefacto
        del modelo, no por nada real.
        """
        side = 1 - self.per_side_pct / 100
        return (1.0 + gross_return) * side * side - 1.0

    @classmethod
    def from_config(cls, cfg: Config) -> CostModel:
        costs = cfg.section("backtest.costs")
        return cls(
            taker_fee_pct=float(costs.get("taker_fee_pct", 0.26)),
            slippage_pct=float(costs.get("slippage_pct", 0.05)),
            spread_pct=float(costs.get("spread_pct", 0.03)),
        )


@dataclass(frozen=True)
class ExitRules:
    """Reglas de salida. Son una decisión del backtest, no de la señal.

    La especificación define cuándo se emite una señal pero no cuándo se cierra
    la posición. Se elige lo más simple que sigue siendo realista: stop en la
    invalidación de la señal, objetivo a un múltiplo del riesgo y cierre por
    tiempo. Nada de esto se optimiza; ajustar las salidas para mejorar el
    resultado convertiría el backtest en un ejercicio de sobreajuste.
    """

    target_r: float = 2.0
    max_bars: int = 30

    @classmethod
    def from_config(cls, cfg: Config) -> ExitRules:
        exits = cfg.section("backtest.exits")
        return cls(
            target_r=float(exits.get("target_r", 2.0)),
            max_bars=int(exits.get("max_bars", 30)),
        )


@dataclass(frozen=True)
class Trade:
    """Una operación simulada, con su resultado bruto y neto de costes."""

    symbol: str
    direction: str
    entry_index: int
    entry_time: pd.Timestamp
    entry_price: float
    stop_price: float
    target_price: float
    exit_index: int
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: str
    gross_return: float
    net_return: float

    @property
    def bars_held(self) -> int:
        return self.exit_index - self.entry_index

    @property
    def won(self) -> bool:
        return self.net_return > 0

    def __str__(self) -> str:
        return (
            f"{self.symbol} {self.direction} {self.entry_time:%Y-%m-%d %H:%M} → "
            f"{self.exit_time:%Y-%m-%d %H:%M} [{self.exit_reason}] "
            f"bruto {self.gross_return:+.2%} neto {self.net_return:+.2%}"
        )


class SkipReason:
    """Motivos por los que una señal no llega a convertirse en operación."""

    NO_NEXT_BAR = "sin vela siguiente"
    STOP_WRONG_SIDE = "invalidación del lado equivocado"
    ZERO_RISK = "riesgo nulo"


def simulate_trade(
    frame: pd.DataFrame,
    *,
    symbol: str,
    signal_index: int,
    direction: str,
    stop_price: float,
    rules: ExitRules,
    costs: CostModel,
) -> Trade | str:
    """Simula una operación. Devuelve el `Trade` o el motivo del descarte."""
    entry_index = signal_index + 1
    if entry_index >= len(frame):
        return SkipReason.NO_NEXT_BAR

    opens = frame["open"].to_numpy(dtype="float64")
    highs = frame["high"].to_numpy(dtype="float64")
    lows = frame["low"].to_numpy(dtype="float64")
    closes = frame["close"].to_numpy(dtype="float64")

    entry_price = float(opens[entry_index])
    long = direction == BULLISH

    # El stop tiene que quedar al otro lado de la entrada. Si no, la señal y su
    # invalidación son incoherentes y la operación no se puede plantear.
    if (long and stop_price >= entry_price) or (not long and stop_price <= entry_price):
        return SkipReason.STOP_WRONG_SIDE

    risk = abs(entry_price - stop_price)
    if risk <= 0:
        return SkipReason.ZERO_RISK

    target_price = entry_price + rules.target_r * risk * (1 if long else -1)

    last_index = min(entry_index + rules.max_bars, len(frame) - 1)
    exit_index, exit_price, exit_reason = last_index, float(closes[last_index]), EXIT_TIMEOUT

    for i in range(entry_index, last_index + 1):
        hit_stop = lows[i] <= stop_price if long else highs[i] >= stop_price
        hit_target = highs[i] >= target_price if long else lows[i] <= target_price
        # Ante la duda, el stop. No conocemos el orden dentro de la vela.
        if hit_stop:
            exit_index, exit_price, exit_reason = i, stop_price, EXIT_STOP
            break
        if hit_target:
            exit_index, exit_price, exit_reason = i, target_price, EXIT_TARGET
            break

    sign = 1.0 if long else -1.0
    gross = sign * (exit_price / entry_price - 1.0)
    net = costs.apply(gross)

    return Trade(
        symbol=symbol,
        direction=direction,
        entry_index=entry_index,
        entry_time=frame.index[entry_index],
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        exit_index=exit_index,
        exit_time=frame.index[exit_index],
        exit_price=exit_price,
        exit_reason=exit_reason,
        gross_return=gross,
        net_return=net,
    )


def run_signals(
    frame: pd.DataFrame,
    signals: Sequence[ConfluenceResult],
    *,
    rules: ExitRules,
    costs: CostModel,
    allow_overlap: bool = False,
) -> tuple[list[Trade], dict[str, int]]:
    """Convierte señales en operaciones sobre una serie.

    Con `allow_overlap=False` se ignora una señal si todavía hay una posición
    abierta. Es lo realista con capital finito y además evita contar varias
    veces el mismo movimiento.
    """
    trades: list[Trade] = []
    skipped: dict[str, int] = {}
    busy_until = -1

    for signal in signals:
        signal_index = int(frame.index.get_loc(signal.timestamp))
        if not allow_overlap and signal_index <= busy_until:
            skipped["solapada"] = skipped.get("solapada", 0) + 1
            continue

        outcome = simulate_trade(
            frame,
            symbol=signal.symbol,
            signal_index=signal_index,
            direction=signal.signal_direction,
            stop_price=signal.signal_invalidation,
            rules=rules,
            costs=costs,
        )
        if isinstance(outcome, str):
            skipped[outcome] = skipped.get(outcome, 0) + 1
            continue

        trades.append(outcome)
        busy_until = outcome.exit_index

    return trades, skipped


def trades_to_frame(trades: Sequence[Trade]) -> pd.DataFrame:
    """Vuelca las operaciones a un DataFrame ordenado por salida."""
    columns = [
        "symbol",
        "direction",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "stop_price",
        "target_price",
        "exit_reason",
        "bars_held",
        "gross_return",
        "net_return",
    ]
    if not trades:
        return pd.DataFrame(columns=columns)
    rows = [
        {
            "symbol": t.symbol,
            "direction": t.direction,
            "entry_time": t.entry_time,
            "exit_time": t.exit_time,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "stop_price": t.stop_price,
            "target_price": t.target_price,
            "exit_reason": t.exit_reason,
            "bars_held": t.bars_held,
            "gross_return": t.gross_return,
            "net_return": t.net_return,
        }
        for t in trades
    ]
    return pd.DataFrame(rows, columns=columns).sort_values("exit_time").reset_index(drop=True)
