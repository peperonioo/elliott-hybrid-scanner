"""Generación causal de señales: swings → conteos → confluencia.

Es el pegamento entre las fases 2, 3 y 4, y lo comparten el backtest y el
informe diario. Que sea el mismo código en ambos casos es lo que impide que el
backtest mida algo distinto de lo que el informe publica.

## Por qué se pueden detectar los swings una sola vez

Detectar los pivotes sobre la serie completa y filtrarlos por `confirmed_index`
da **exactamente** el mismo resultado que recorrer la serie vela a vela. No es
una aproximación por eficiencia: es el invariante que demuestra
`tests/test_swings.py::test_no_hay_lookahead_bias_invariancia_ante_prefijos`.
Sin esa garantía habría que recalcular los swings en cada vela, y un backtest
de 4 años sobre 9 pares dejaría de ser viable.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from ehs.config import Config
from ehs.confluence.scorer import ConfluenceParams, ConfluenceResult, score_confluence
from ehs.elliott.validator import ElliottParams, SequenceError, validate_sequence
from ehs.structure.swings import Pivot, detect_swings

LOGGER = logging.getLogger(__name__)

# Ventanas de pivotes que el validador sabe interpretar: cinco tramos y tres.
WINDOW_SIZES: tuple[int, ...] = (6, 4)


@dataclass(frozen=True)
class PipelineParams:
    """Todo lo que necesita el pipeline, resuelto desde el `config.yaml`."""

    swing: dict[str, Any]
    elliott: ElliottParams
    confluence: ConfluenceParams
    structure_timeframe: str
    context_timeframe: str

    @classmethod
    def from_config(cls, cfg: Config) -> PipelineParams:
        return cls(
            swing={
                "atr_period": int(cfg.get("swings.atr_period")),
                "atr_threshold": float(cfg.get("swings.atr_threshold")),
                "confirmation_bars": int(cfg.get("swings.confirmation_bars")),
                "atr_reference": str(cfg.get("swings.atr_reference")),
            },
            elliott=ElliottParams.from_config(cfg),
            confluence=ConfluenceParams.from_config(cfg),
            structure_timeframe=str(cfg.get("timeframes.structure")),
            context_timeframe=str(cfg.get("timeframes.context")),
        )


def generate_signals(
    structure: pd.DataFrame,
    context: pd.DataFrame,
    *,
    symbol: str,
    params: PipelineParams,
    only_emitting: bool = True,
    deduplicate: bool = True,
    pivots: Sequence[Pivot] | None = None,
) -> list[ConfluenceResult]:
    """Recorre el histórico y evalúa cada conteo en el momento en que se supo.

    Cada evaluación usa como instante el `confirmed_index` del último pivote de
    la ventana, que es la primera vela en la que ese conteo era conocible.

    `only_emitting=False` devuelve también los conteos que no llegan al mínimo
    de factores. El backtest lo necesita: el walk-forward reajusta ese mínimo
    por tramo y no puede hacerlo si ya se han filtrado.
    """
    if structure.empty or context.empty:
        return []

    if pivots is None:
        pivots = detect_swings(structure, **params.swing)
    results: list[ConfluenceResult] = []

    for size in WINDOW_SIZES:
        for start in range(len(pivots) - size + 1):
            window = pivots[start : start + size]
            at = window[-1].confirmed_index
            if at >= len(structure):
                continue
            try:
                counts = validate_sequence(window, params.elliott)
            except SequenceError:
                continue
            for count in counts:
                try:
                    results.append(
                        score_confluence(
                            count,
                            structure=structure,
                            context=context,
                            symbol=symbol,
                            structure_timeframe=params.structure_timeframe,
                            context_timeframe=params.context_timeframe,
                            params=params.confluence,
                            at=at,
                        )
                    )
                except ValueError as exc:  # serie corta o conteo no confirmado
                    LOGGER.debug("%s en la vela %d: %s", symbol, at, exc)

    if only_emitting:
        results = [r for r in results if r.emits_signal]
    if deduplicate:
        results = deduplicate_by_bar(results)
    return sorted(results, key=lambda r: r.timestamp)


def deduplicate_by_bar(results: Sequence[ConfluenceResult]) -> list[ConfluenceResult]:
    """Un conteo por vela: el de mayor score.

    Varias ventanas de pivotes pueden confirmarse en la misma vela y producir
    conteos distintos. Contarlos todos inflaría artificialmente el número de
    operaciones del backtest.
    """
    best: dict[pd.Timestamp, ConfluenceResult] = {}
    for result in results:
        current = best.get(result.timestamp)
        if current is None or result.score > current.score:
            best[result.timestamp] = result
    return sorted(best.values(), key=lambda r: r.timestamp)
