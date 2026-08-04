"""Walk-forward: elegir el parámetro en el pasado y medirlo en el futuro.

## Qué es out-of-sample aquí y qué no

Conviene ser preciso, porque "walk-forward" se usa a veces como sello de
respetabilidad sin que signifique nada. La mayoría de los parámetros de este
sistema —el umbral del ZigZag, los pesos de la confluencia, los objetivos de
Fibonacci— se fijaron por criterio, no ajustándolos a los datos. Sobre esos, el
walk-forward no aporta: el sesgo que pueda haber es el de quien los eligió
mirando el mercado, y ninguna partición de la muestra lo corrige.

Lo que sí se elige aquí con datos es `min_active_factors`, que es una decisión
genuina y sensible. Se escoge en cada tramo de entrenamiento y se aplica al
tramo de prueba siguiente, sin volver a mirarlo. Las métricas que se reportan
son **solo las de los tramos de prueba**.

Las operaciones abiertas al final de un tramo se dejan cerrar, aunque salgan
fuera de la ventana. Truncarlas eliminaría sistemáticamente las que van
perdiendo, que son las que más tardan en cerrar.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from ehs.backtest.engine import CostModel, ExitRules, Trade, run_signals
from ehs.backtest.metrics import Metrics, compute_metrics
from ehs.confluence.scorer import ConfluenceResult

LOGGER = logging.getLogger(__name__)

SignalsBySymbol = dict[str, list[ConfluenceResult]]
FramesBySymbol = dict[str, pd.DataFrame]


@dataclass(frozen=True)
class Fold:
    """Un tramo de entrenamiento seguido de su tramo de prueba."""

    index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    def __str__(self) -> str:
        return (
            f"fold {self.index}: entrena {self.train_start:%Y-%m-%d}→{self.train_end:%Y-%m-%d}, "
            f"prueba {self.test_start:%Y-%m-%d}→{self.test_end:%Y-%m-%d}"
        )


@dataclass(frozen=True)
class FoldResult:
    fold: Fold
    chosen_min_active: int
    chosen_by: str
    train_metrics: Metrics
    test_metrics: Metrics
    test_trades: list[Trade]


@dataclass(frozen=True)
class WalkForwardResult:
    folds: list[FoldResult]

    @property
    def test_trades(self) -> list[Trade]:
        return [trade for fold in self.folds for trade in fold.test_trades]

    @property
    def metrics(self) -> Metrics:
        return compute_metrics(self.test_trades)

    def summary(self) -> str:
        lineas = [f"{len(self.folds)} tramos de prueba", ""]
        for resultado in self.folds:
            lineas.append(
                f"  {resultado.fold} | min_factores={resultado.chosen_min_active} "
                f"({resultado.chosen_by}) | {resultado.test_metrics.summary()}"
            )
        return "\n".join(lineas)


def make_folds(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    train_months: int,
    test_months: int,
) -> list[Fold]:
    """Divide el periodo en tramos rodantes de entrenamiento y prueba."""
    folds: list[Fold] = []
    train_offset = pd.DateOffset(months=train_months)
    test_offset = pd.DateOffset(months=test_months)

    train_start = pd.Timestamp(start)
    index = 0
    while True:
        train_end = train_start + train_offset
        test_end = train_end + test_offset
        if test_end > end:
            break
        folds.append(
            Fold(
                index=index,
                train_start=train_start,
                train_end=train_end,
                test_start=train_end,
                test_end=test_end,
            )
        )
        train_start = train_start + test_offset
        index += 1

    return folds


def _in_window(
    signals: Sequence[ConfluenceResult], start: pd.Timestamp, end: pd.Timestamp
) -> list[ConfluenceResult]:
    return [s for s in signals if start <= s.timestamp < end]


def trades_for(
    signals: SignalsBySymbol,
    frames: FramesBySymbol,
    *,
    min_active: int,
    start: pd.Timestamp,
    end: pd.Timestamp,
    rules: ExitRules,
    costs: CostModel,
    allow_overlap: bool = False,
) -> list[Trade]:
    """Operaciones de una ventana temporal con un mínimo de factores dado."""
    trades: list[Trade] = []
    for symbol, symbol_signals in signals.items():
        frame = frames.get(symbol)
        if frame is None or frame.empty:
            continue
        seleccion = [
            s for s in _in_window(symbol_signals, start, end) if len(s.active_factors) >= min_active
        ]
        if not seleccion:
            continue
        symbol_trades, _ = run_signals(
            frame, seleccion, rules=rules, costs=costs, allow_overlap=allow_overlap
        )
        trades.extend(symbol_trades)
    return trades


def walk_forward(
    signals: SignalsBySymbol,
    frames: FramesBySymbol,
    *,
    folds: Sequence[Fold],
    grid: Sequence[int],
    rules: ExitRules,
    costs: CostModel,
    default_min_active: int,
    min_train_trades: int = 10,
    allow_overlap: bool = False,
) -> WalkForwardResult:
    """Elige `min_active_factors` en cada tramo de entrenamiento y lo aplica al
    de prueba."""
    resultados: list[FoldResult] = []

    for fold in folds:
        mejor_k, mejor_metrics, motivo = default_min_active, None, "por defecto"
        mejor_expectancy = float("-inf")

        for k in grid:
            train_trades = trades_for(
                signals,
                frames,
                min_active=k,
                start=fold.train_start,
                end=fold.train_end,
                rules=rules,
                costs=costs,
                allow_overlap=allow_overlap,
            )
            if len(train_trades) < min_train_trades:
                continue
            metrics = compute_metrics(train_trades)
            if metrics.expectancy > mejor_expectancy:
                mejor_k, mejor_expectancy, mejor_metrics = k, metrics.expectancy, metrics
                motivo = "elegido en entrenamiento"

        if mejor_metrics is None:
            # Sin operaciones suficientes para elegir nada, se usa el valor de
            # la configuración. Registrarlo importa: significa que ese tramo no
            # aporta evidencia sobre el parámetro.
            LOGGER.info("%s: entrenamiento insuficiente, se usa el valor por defecto", fold)
            mejor_metrics = compute_metrics([])

        test_trades = trades_for(
            signals,
            frames,
            min_active=mejor_k,
            start=fold.test_start,
            end=fold.test_end,
            rules=rules,
            costs=costs,
            allow_overlap=allow_overlap,
        )

        resultados.append(
            FoldResult(
                fold=fold,
                chosen_min_active=mejor_k,
                chosen_by=motivo,
                train_metrics=mejor_metrics,
                test_metrics=compute_metrics(test_trades),
                test_trades=test_trades,
            )
        )

    return WalkForwardResult(folds=resultados)
