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

ENTRY_MARKET = "market"
ENTRY_LIMIT_ZONE = "limit_zone"


@dataclass(frozen=True)
class CostModel:
    """Costes por lado, en porcentaje del nominal.

    El coste depende de **cómo** se cruza el mercado, no solo de cuántas veces:

      - Orden agresiva (market, stop, cierre por tiempo): comisión taker más
        slippage más media horquilla. Se cruza el spread y se paga por ello.
      - Orden limitada que espera (entrada en zona, objetivo): comisión maker y
        nada más. No hay slippage —o se ejecuta a tu precio o no se ejecuta— ni
        se cruza la horquilla, porque la estás poniendo tú.

    Modelarlo así no es optimismo: es que un sistema cuya tesis es "el precio
    vuelve a la zona de Fibonacci" se opera naturalmente con limitadas, y
    cobrarle taker en ambos lados le imputa un coste que no tendría.
    """

    taker_fee_pct: float = 0.26
    maker_fee_pct: float = 0.16
    slippage_pct: float = 0.05
    spread_pct: float = 0.03

    @property
    def aggressive_pct(self) -> float:
        """Coste de un lado ejecutado contra el libro."""
        return self.taker_fee_pct + self.slippage_pct + self.spread_pct

    @property
    def passive_pct(self) -> float:
        """Coste de un lado ejecutado con orden limitada."""
        return self.maker_fee_pct

    @property
    def per_side_pct(self) -> float:
        """Compatibilidad: el lado agresivo, que es el caso por defecto."""
        return self.aggressive_pct

    @property
    def round_trip_pct(self) -> float:
        """Viaje completo agresivo: el peor caso y el que se usa de referencia."""
        return 2 * self.aggressive_pct

    def entry_cost_pct(self, mode: str, *, filled_aggressively: bool = False) -> float:
        if mode == ENTRY_LIMIT_ZONE and not filled_aggressively:
            return self.passive_pct
        return self.aggressive_pct

    def exit_cost_pct(self, reason: str) -> float:
        # El objetivo se coloca como limitada; el stop y el cierre por tiempo
        # salen contra el libro.
        return self.passive_pct if reason == EXIT_TARGET else self.aggressive_pct

    def apply(
        self,
        gross_return: float,
        *,
        entry_cost_pct: float | None = None,
        exit_cost_pct: float | None = None,
    ) -> float:
        """Aplica el coste a un retorno bruto.

        El capital se multiplica por `(1 + bruto)` y por `(1 - c)` una vez al
        entrar y otra al salir, pagando el coste sobre el nominal movido en cada
        lado. La formulación es idéntica para largos y cortos, cosa que no
        ocurre si se ajustan los precios de entrada y salida por separado: ahí
        el nominal desplegado difiere y el coste sale asimétrico por un artefacto
        del modelo, no por nada real.
        """
        entrada = self.aggressive_pct if entry_cost_pct is None else entry_cost_pct
        salida = self.aggressive_pct if exit_cost_pct is None else exit_cost_pct
        return (1.0 + gross_return) * (1 - entrada / 100) * (1 - salida / 100) - 1.0

    @classmethod
    def from_config(cls, cfg: Config) -> CostModel:
        costs = cfg.section("backtest.costs")
        return cls(
            taker_fee_pct=float(costs.get("taker_fee_pct", 0.26)),
            maker_fee_pct=float(costs.get("maker_fee_pct", 0.16)),
            slippage_pct=float(costs.get("slippage_pct", 0.05)),
            spread_pct=float(costs.get("spread_pct", 0.03)),
        )


@dataclass(frozen=True)
class EntryRules:
    """Cómo se entra tras una señal.

    `market` entra a la apertura de la vela siguiente, sin condiciones.
    `limit_zone` coloca una limitada en la zona de Fibonacci que la propia
    señal ya calcula y espera a que el precio la visite. Si no la visita en
    `limit_valid_bars`, **no hay operación**: es la diferencia entre perseguir
    el precio y esperarlo.
    """

    mode: str = ENTRY_MARKET
    limit_valid_bars: int = 10

    @classmethod
    def from_config(cls, cfg: Config) -> EntryRules:
        entry = cfg.section("backtest.entry")
        return cls(
            mode=str(entry.get("mode", ENTRY_MARKET)),
            limit_valid_bars=int(entry.get("limit_valid_bars", 10)),
        )


@dataclass(frozen=True)
class TradeFilters:
    """Filtros aplicables antes de abrir, con información ya conocida.

    `min_reward_cost_ratio` es la respuesta directa al diagnóstico del primer
    backtest: la ventaja bruta era del 0.50% por operación y el peaje del
    0.68%. Exigir que el objetivo cubra el coste un número de veces descarta
    las operaciones que no pueden pagarlo ni saliendo bien.
    """

    min_reward_cost_ratio: float = 0.0
    directions: tuple[str, ...] = ()

    def allows_direction(self, direction: str) -> bool:
        return not self.directions or direction in self.directions

    @classmethod
    def from_config(cls, cfg: Config) -> TradeFilters:
        filters = cfg.section("backtest.filters")
        return cls(
            min_reward_cost_ratio=float(filters.get("min_reward_cost_ratio", 0.0)),
            directions=tuple(filters.get("directions", []) or ()),
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
    cost_pct: float = 0.68  # coste total imputado, por transparencia

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
    NOT_FILLED = "la limitada no llegó a ejecutarse"
    NO_ZONE = "sin zona de entrada"
    REWARD_TOO_SMALL = "objetivo insuficiente para cubrir el coste"
    DIRECTION_FILTERED = "dirección excluida"
    UNRESOLVED = "sin desenlace dentro de los datos disponibles"


def _fill(
    frame_arrays: tuple,
    *,
    signal_index: int,
    long: bool,
    entry: EntryRules,
    limit_price: float | None,
) -> tuple[int, float, bool] | str:
    """Determina en qué vela y a qué precio se entra.

    Devuelve `(índice, precio, ejecutada_agresivamente)` o el motivo del
    descarte.
    """
    opens, highs, lows, _ = frame_arrays
    first = signal_index + 1
    if first >= len(opens):
        return SkipReason.NO_NEXT_BAR

    if entry.mode == ENTRY_MARKET:
        return first, float(opens[first]), True

    if limit_price is None:
        return SkipReason.NO_ZONE

    # Si al colocar la orden el precio ya ha atravesado el nivel, la limitada es
    # marketable y se ejecuta contra el libro: mejor precio, pero pagando taker.
    open_first = float(opens[first])
    if (long and open_first <= limit_price) or (not long and open_first >= limit_price):
        return first, open_first, True

    last = min(first + entry.limit_valid_bars - 1, len(opens) - 1)
    for i in range(first, last + 1):
        touched = lows[i] <= limit_price if long else highs[i] >= limit_price
        if touched:
            return i, float(limit_price), False

    # El precio nunca visitó la zona. No perseguirlo es parte de la estrategia.
    return SkipReason.NOT_FILLED


def simulate_trade(
    frame: pd.DataFrame,
    *,
    symbol: str,
    signal_index: int,
    direction: str,
    stop_price: float,
    rules: ExitRules,
    costs: CostModel,
    entry: EntryRules | None = None,
    filters: TradeFilters | None = None,
    limit_price: float | None = None,
) -> Trade | str:
    """Simula una operación. Devuelve el `Trade` o el motivo del descarte."""
    entry = entry or EntryRules()
    filters = filters or TradeFilters()

    if not filters.allows_direction(direction):
        return SkipReason.DIRECTION_FILTERED

    arrays = (
        frame["open"].to_numpy(dtype="float64"),
        frame["high"].to_numpy(dtype="float64"),
        frame["low"].to_numpy(dtype="float64"),
        frame["close"].to_numpy(dtype="float64"),
    )
    _, highs, lows, closes = arrays
    long = direction == BULLISH

    filled = _fill(
        arrays, signal_index=signal_index, long=long, entry=entry, limit_price=limit_price
    )
    if isinstance(filled, str):
        return filled
    entry_index, entry_price, aggressive_entry = filled

    # El stop tiene que quedar al otro lado de la entrada. Si no, la señal y su
    # invalidación son incoherentes y la operación no se puede plantear.
    if (long and stop_price >= entry_price) or (not long and stop_price <= entry_price):
        return SkipReason.STOP_WRONG_SIDE

    risk = abs(entry_price - stop_price)
    if risk <= 0:
        return SkipReason.ZERO_RISK

    target_price = entry_price + rules.target_r * risk * (1 if long else -1)

    # ¿Compensa siquiera si sale bien? El recorrido hasta el objetivo tiene que
    # cubrir el peaje varias veces; si no, la operación pierde por construcción.
    if filters.min_reward_cost_ratio > 0:
        reward = abs(target_price - entry_price) / entry_price
        if reward < filters.min_reward_cost_ratio * costs.round_trip_pct / 100:
            return SkipReason.REWARD_TOO_SMALL

    last_index = min(entry_index + rules.max_bars, len(closes) - 1)
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

    # Si la serie se acaba antes del horizonte y ni el stop ni el objetivo
    # llegaron a tocarse, el desenlace es DESCONOCIDO, no "cierre por tiempo":
    # contarlo como timeout censura la operación en la frontera del frame y
    # distorsiona la distribución de salidas.
    if exit_reason == EXIT_TIMEOUT and entry_index + rules.max_bars > len(closes) - 1:
        return SkipReason.UNRESOLVED

    sign = 1.0 if long else -1.0
    gross = sign * (exit_price / entry_price - 1.0)
    entry_cost = costs.entry_cost_pct(entry.mode, filled_aggressively=aggressive_entry)
    exit_cost = costs.exit_cost_pct(exit_reason)
    net = costs.apply(gross, entry_cost_pct=entry_cost, exit_cost_pct=exit_cost)

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
        cost_pct=entry_cost + exit_cost,
    )


def run_signals(
    frame: pd.DataFrame,
    signals: Sequence[ConfluenceResult],
    *,
    rules: ExitRules,
    costs: CostModel,
    entry: EntryRules | None = None,
    filters: TradeFilters | None = None,
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

        # La zona de interés de la señal es donde se coloca la limitada. Para
        # un largo interesa el borde bajo de la zona; para un corto, el alto.
        zone = getattr(signal, "zone", None)
        if zone is not None:
            limit_price = zone[0] if signal.signal_direction == BULLISH else zone[1]
        else:
            limit_price = None

        outcome = simulate_trade(
            frame,
            symbol=signal.symbol,
            signal_index=signal_index,
            direction=signal.signal_direction,
            stop_price=signal.signal_invalidation,
            rules=rules,
            costs=costs,
            entry=entry,
            filters=filters,
            limit_price=limit_price,
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
        "cost_pct",
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
            "cost_pct": t.cost_pct,
        }
        for t in trades
    ]
    return pd.DataFrame(rows, columns=columns).sort_values("exit_time").reset_index(drop=True)
