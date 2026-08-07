"""Registro persistente de señales emitidas: el forward test, automatizado.

Cada ejecución añade a `reports/signals.json` las señales nuevas (una sola vez
cada una) y evalúa el desenlace de las anteriores con las mismas reglas que el
backtest: entrada en la apertura de la vela siguiente, stop en la invalidación,
objetivo a 2R y cierre por tiempo a las 30 velas. Si stop y objetivo se tocan
en la misma vela, cuenta el stop.

El fichero se commitea con el informe, así que el registro queda fechado en el
historial de git: imposible de reescribir a posteriori. Es exactamente la
libreta que el tutorial pedía llevar a mano, sin la mano.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ehs.config import Config
from ehs.report.daily import ReportEntry

LOGGER = logging.getLogger(__name__)

OUTCOME_TARGET = "objetivo"
OUTCOME_STOP = "stop"
OUTCOME_TIMEOUT = "tiempo"
OUTCOME_OPEN = "en curso"
OUTCOME_PENDING = "sin vela de entrada"

MAX_BARS = 30
TARGET_R = 2.0


@dataclass
class LoggedSignal:
    """Una señal registrada, con su desenlace si ya se conoce."""

    symbol: str
    timestamp: str  # ISO, vela de confirmación
    hypothesis: str
    price: float
    zone_low: float | None
    zone_high: float | None
    stop: float
    score: float
    factors: list[str]
    recorded_at: str
    # Calculados al evaluar:
    entry: float | None = None
    target: float | None = None
    outcome: str = OUTCOME_OPEN
    result_r: float | None = None
    result_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoggedSignal:
        known = {k: data.get(k) for k in cls.__dataclass_fields__}
        return cls(**known)


def log_path(cfg: Config) -> Path:
    return cfg.path("paths.reports_dir") / "signals.json"


def load_log(cfg: Config) -> list[LoggedSignal]:
    path = log_path(cfg)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [LoggedSignal.from_dict(item) for item in raw]
    except (json.JSONDecodeError, TypeError) as exc:
        LOGGER.warning("Registro de señales ilegible (%s); se conserva aparte", exc)
        path.rename(path.with_suffix(".json.bak"))
        return []


def save_log(cfg: Config, signals: list[LoggedSignal]) -> Path:
    path = log_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([s.to_dict() for s in signals], indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def append_new(log: list[LoggedSignal], entries: list[ReportEntry], *, now: pd.Timestamp) -> int:
    """Añade al registro las señales emitidas que aún no estaban. Devuelve cuántas."""
    seen = {(s.symbol, s.timestamp) for s in log}
    added = 0
    for entry in entries:
        if not entry.is_signal:
            continue
        r = entry.result
        key = (r.symbol, r.timestamp.isoformat())
        if key in seen:
            continue
        log.append(
            LoggedSignal(
                symbol=r.symbol,
                timestamp=r.timestamp.isoformat(),
                hypothesis=r.count.hypothesis,
                price=float(r.price),
                zone_low=float(r.zone[0]) if r.zone else None,
                zone_high=float(r.zone[1]) if r.zone else None,
                stop=float(r.signal_invalidation),
                score=float(r.score),
                factors=[f.name for f in r.active_factors],
                recorded_at=now.isoformat(),
            )
        )
        seen.add(key)
        added += 1
    return added


def evaluate(signal: LoggedSignal, frame: pd.DataFrame) -> None:
    """Evalúa el desenlace con las reglas del backtest. Muta el registro."""
    ts = pd.Timestamp(signal.timestamp)
    try:
        position = int(frame.index.get_loc(ts))
    except KeyError:
        return

    entry_index = position + 1
    if entry_index >= len(frame):
        signal.outcome = OUTCOME_PENDING
        return

    entry = float(frame["open"].iloc[entry_index])
    risk = entry - signal.stop
    if risk <= 0:
        signal.outcome = OUTCOME_STOP
        signal.entry = entry
        signal.result_r = -1.0
        signal.result_pct = signal.stop / entry - 1
        return
    target = entry + TARGET_R * risk
    signal.entry, signal.target = entry, target

    highs = frame["high"].to_numpy()
    lows = frame["low"].to_numpy()
    closes = frame["close"].to_numpy()
    last = min(entry_index + MAX_BARS, len(frame) - 1)

    for i in range(entry_index, last + 1):
        if lows[i] <= signal.stop:  # ante la duda, el stop
            signal.outcome = OUTCOME_STOP
            signal.result_r = -1.0
            signal.result_pct = signal.stop / entry - 1
            return
        if highs[i] >= target:
            signal.outcome = OUTCOME_TARGET
            signal.result_r = TARGET_R
            signal.result_pct = target / entry - 1
            return

    final = float(closes[last])
    pct = final / entry - 1
    if entry_index + MAX_BARS <= len(frame) - 1:
        signal.outcome = OUTCOME_TIMEOUT
    else:
        signal.outcome = OUTCOME_OPEN
    signal.result_r = (final - entry) / risk
    signal.result_pct = pct


def update_log(
    cfg: Config,
    entries: list[ReportEntry],
    frames: dict[str, pd.DataFrame],
    *,
    now: pd.Timestamp,
) -> list[LoggedSignal]:
    """Carga, añade señales nuevas, re-evalúa desenlaces y persiste."""
    log = load_log(cfg)
    added = append_new(log, entries, now=now)
    for signal in log:
        frame = frames.get(signal.symbol)
        if frame is not None and not frame.empty:
            evaluate(signal, frame)
    save_log(cfg, log)
    if added:
        LOGGER.info("Forward test: %d señal(es) nueva(s) registrada(s)", added)
    return sorted(log, key=lambda s: s.timestamp, reverse=True)


def summary_stats(log: list[LoggedSignal]) -> dict[str, Any]:
    """Recuento del forward test: cerradas, ganadas, perdidas y R acumulado."""
    closed = [s for s in log if s.outcome in (OUTCOME_TARGET, OUTCOME_STOP, OUTCOME_TIMEOUT)]
    wins = sum(1 for s in closed if (s.result_r or 0) > 0)
    total_r = sum(s.result_r or 0.0 for s in closed)
    return {
        "total": len(log),
        "closed": len(closed),
        "open": sum(1 for s in log if s.outcome == OUTCOME_OPEN),
        "wins": wins,
        "losses": len(closed) - wins,
        "total_r": total_r,
    }
