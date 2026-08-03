"""Validación de integridad de las series OHLCV.

Filosofía: la validación **informa**, y solo aborta cuando la configuración lo
pide explícitamente. Una serie con un hueco de hace dos años sigue siendo útil
para el conteo de ondas de hoy; tirarla entera sería peor que anotarlo.

Anomalías cubiertas:
  - timestamps duplicados
  - huecos en la rejilla temporal (velas ausentes)
  - velas con volumen cero
  - incoherencias OHLC (high < low, high por debajo de open/close, etc.)
  - NaN e infinitos
  - serie demasiado corta para ser utilizable
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ehs.data.schema import OHLCV_COLUMNS, timeframe_to_timedelta

LOGGER = logging.getLogger(__name__)


class ValidationFailure(Exception):
    """Una anomalía cuya política configurada es `raise`."""


@dataclass(frozen=True)
class Gap:
    """Tramo de velas ausentes entre dos velas consecutivas presentes."""

    start: pd.Timestamp  # última vela presente antes del hueco
    end: pd.Timestamp  # primera vela presente tras el hueco
    missing: int  # número de velas que faltan

    def __str__(self) -> str:
        return f"{self.start:%Y-%m-%d %H:%M} -> {self.end:%Y-%m-%d %H:%M} ({self.missing} velas)"


@dataclass
class ValidationReport:
    """Resultado de validar una serie. `ok` resume si es apta para usarse."""

    symbol: str
    timeframe: str
    rows: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    duplicates: int = 0
    gaps: list[Gap] = field(default_factory=list)
    zero_volume: int = 0
    ohlc_inconsistent: int = 0
    nan_rows: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def missing_candles(self) -> int:
        return sum(gap.missing for gap in self.gaps)

    @property
    def gap_ratio(self) -> float:
        """Velas ausentes sobre el total esperado en el rango cubierto."""
        expected = self.rows + self.missing_candles
        return self.missing_candles / expected if expected else 0.0

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        head = f"{self.symbol} {self.timeframe}: {self.rows} velas " f"[{self.start} .. {self.end}]"
        bits = []
        if self.duplicates:
            bits.append(f"{self.duplicates} duplicadas")
        if self.gaps:
            bits.append(
                f"{len(self.gaps)} huecos / {self.missing_candles} velas ({self.gap_ratio:.3%})"
            )
        if self.zero_volume:
            bits.append(f"{self.zero_volume} con volumen 0")
        if self.ohlc_inconsistent:
            bits.append(f"{self.ohlc_inconsistent} OHLC incoherentes")
        if self.nan_rows:
            bits.append(f"{self.nan_rows} con NaN")
        detail = "; ".join(bits) if bits else "sin anomalías"
        status = "OK" if self.ok else "NO APTA"
        return f"[{status}] {head} — {detail}"


def find_gaps(index: pd.DatetimeIndex, timeframe: str, *, max_report: int = 50) -> list[Gap]:
    """Localiza tramos de velas ausentes asumiendo rejilla regular.

    `max_report` acota la lista devuelta para no generar informes gigantes en
    series muy rotas; el recuento total sigue siendo correcto en los devueltos.
    """
    if len(index) < 2:
        return []

    step = timeframe_to_timedelta(timeframe)
    deltas = index[1:] - index[:-1]
    over = np.flatnonzero(deltas > step)

    gaps: list[Gap] = []
    for position in over[:max_report]:
        missing = int(deltas[position] / step) - 1
        gaps.append(Gap(start=index[position], end=index[position + 1], missing=missing))
    if len(over) > max_report:
        LOGGER.debug(
            "Se han encontrado %d huecos; se reportan los primeros %d", len(over), max_report
        )
    return gaps


def count_ohlc_inconsistencies(frame: pd.DataFrame) -> int:
    """Velas donde el rango high/low no envuelve a open/close."""
    if frame.empty:
        return 0
    highest = frame[["open", "close"]].max(axis=1)
    lowest = frame[["open", "close"]].min(axis=1)
    bad = (
        (frame["high"] < frame["low"])
        | (frame["high"] < highest)
        | (frame["low"] > lowest)
        | (frame[list(OHLCV_COLUMNS)] < 0).any(axis=1)
    )
    return int(bad.sum())


def validate(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    policies: dict[str, str] | None = None,
    max_gap_ratio: float = 1.0,
    min_candles: int = 0,
) -> tuple[pd.DataFrame, ValidationReport]:
    """Valida y (según política) repara una serie.

    Devuelve la serie resultante y el informe. Las políticas admitidas son
    `warn`, `raise`, y además `fix` para duplicados y `drop` para volumen cero.
    """
    policies = policies or {}
    working = frame

    report = ValidationReport(
        symbol=symbol,
        timeframe=timeframe,
        rows=len(working),
        start=working.index.min() if len(working) else None,
        end=working.index.max() if len(working) else None,
    )

    if working.empty:
        report.errors.append("serie vacía")
        return working, report

    # --- duplicados --------------------------------------------------------
    duplicated = working.index.duplicated(keep="last")
    report.duplicates = int(duplicated.sum())
    if report.duplicates:
        _apply_policy(
            report,
            policies.get("on_duplicate", "fix"),
            f"{report.duplicates} timestamps duplicados",
        )
        if policies.get("on_duplicate", "fix") == "fix":
            working = working[~duplicated]

    if not working.index.is_monotonic_increasing:
        working = working.sort_index()
        report.warnings.append("índice desordenado, reordenado")

    # --- huecos ------------------------------------------------------------
    report.gaps = find_gaps(pd.DatetimeIndex(working.index), timeframe)
    if report.gaps:
        message = (
            f"{len(report.gaps)} huecos, {report.missing_candles} velas ausentes "
            f"({report.gap_ratio:.3%}); primero: {report.gaps[0]}"
        )
        _apply_policy(report, policies.get("on_gap", "warn"), message)
        if report.gap_ratio > max_gap_ratio:
            report.errors.append(
                f"ratio de huecos {report.gap_ratio:.3%} por encima del máximo {max_gap_ratio:.3%}"
            )

    # --- volumen cero ------------------------------------------------------
    zero_mask = working["volume"] <= 0
    report.zero_volume = int(zero_mask.sum())
    if report.zero_volume:
        _apply_policy(
            report,
            policies.get("on_zero_volume", "warn"),
            f"{report.zero_volume} velas con volumen 0",
        )
        if policies.get("on_zero_volume", "warn") == "drop":
            working = working[~zero_mask]

    # --- coherencia OHLC y NaN --------------------------------------------
    report.ohlc_inconsistent = count_ohlc_inconsistencies(working)
    if report.ohlc_inconsistent:
        _apply_policy(
            report,
            policies.get("on_ohlc_inconsistency", "warn"),
            f"{report.ohlc_inconsistent} velas con OHLC incoherente",
        )

    finite = np.isfinite(working[list(OHLCV_COLUMNS)].to_numpy(dtype="float64"))
    report.nan_rows = int((~finite).any(axis=1).sum())
    if report.nan_rows:
        report.errors.append(f"{report.nan_rows} velas con NaN o infinitos")

    # --- longitud mínima ---------------------------------------------------
    report.rows = len(working)
    if report.rows < min_candles:
        report.errors.append(f"solo {report.rows} velas, se requieren al menos {min_candles}")

    return working, report


def _apply_policy(report: ValidationReport, policy: str, message: str) -> None:
    if policy == "raise":
        raise ValidationFailure(f"{report.symbol} {report.timeframe}: {message}")
    report.warnings.append(message)
