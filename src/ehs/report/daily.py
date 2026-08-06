"""Informe diario en Markdown: pares rankeados por score de confluencia.

Publica únicamente lo que el backtest validó: señales del pipeline compartido
(`ehs.pipeline`), con la configuración de filtros del `config.yaml`. Además de
las señales emitidas incluye los conteos que se quedaron cerca, porque para
validar a mano en TradingView interesa también lo que casi dispara.

Todo el output es informativo. El sistema no ejecuta órdenes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ehs.backtest.engine import TradeFilters
from ehs.config import Config
from ehs.confluence.scorer import ConfluenceResult
from ehs.data.cache import ParquetCache
from ehs.pipeline import PipelineParams, generate_signals

LOGGER = logging.getLogger(__name__)

# Un conteo solo aparece en el informe si su confirmación cae dentro de las
# últimas N velas de estructura: lo más viejo ya no es accionable.
DEFAULT_FRESHNESS_BARS = 12


@dataclass(frozen=True)
class ReportEntry:
    result: ConfluenceResult
    is_signal: bool
    bars_ago: int


def collect_entries(
    cfg: Config,
    *,
    freshness_bars: int = DEFAULT_FRESHNESS_BARS,
) -> tuple[list[ReportEntry], list[str]]:
    """Evalúa el universo y devuelve las entradas recientes, más avisos."""
    cache = ParquetCache(cfg.path("paths.cache_dir"))
    exchange_id = str(cfg.get("exchanges.primary.id"))
    params = PipelineParams.from_config(cfg)
    filters = TradeFilters.from_config(cfg)

    entries: list[ReportEntry] = []
    warnings: list[str] = []

    for base in cfg.bases:
        symbol = cfg.symbol_for(base, "primary")
        structure = cache.read(exchange_id, symbol, params.structure_timeframe)
        context = cache.read(exchange_id, symbol, params.context_timeframe)
        if structure.empty or context.empty:
            warnings.append(f"{symbol}: sin datos en caché")
            continue

        results = generate_signals(
            structure, context, symbol=symbol, params=params, only_emitting=False
        )
        last_index = len(structure) - 1
        for result in results:
            bars_ago = last_index - int(structure.index.get_loc(result.timestamp))
            if bars_ago > freshness_bars:
                continue
            # El filtro de dirección del backtest también gobierna el informe:
            # no se publica lo que no se operaría.
            if not filters.allows_direction(result.signal_direction):
                continue
            entries.append(
                ReportEntry(result=result, is_signal=result.emits_signal, bars_ago=bars_ago)
            )

    entries.sort(key=lambda e: (not e.is_signal, -e.result.score))
    return entries, warnings


def _fmt_price(value: float) -> str:
    return f"{value:,.4f}" if value < 100 else f"{value:,.2f}"


def _entry_block(entry: ReportEntry) -> list[str]:
    r = entry.result
    hypothesis = r.count.hypothesis
    direction = "largo" if r.signal_direction == "bullish" else "corto"
    lines = [
        f"### {r.symbol} — {direction} sobre `{hypothesis}` "
        f"(score {r.score:.3f}, {len(r.active_factors)}/{len(r.factors)} factores)",
        "",
        f"- **Timeframe**: {r.timeframe}, señal confirmada el {r.timestamp:%Y-%m-%d %H:%M} UTC "
        f"({entry.bars_ago} velas atrás)",
        f"- **Precio en la señal**: {_fmt_price(r.price)}",
    ]
    if r.zone:
        lines.append(f"- **Zona de interés**: {_fmt_price(r.zone[0])} – {_fmt_price(r.zone[1])}")
    lines.append(f"- **Invalidación de la señal**: {_fmt_price(r.signal_invalidation)}")
    if r.count_invalidation is not None:
        lines.append(f"- **Invalidación del conteo**: {_fmt_price(r.count_invalidation)}")
    if r.count.is_ambiguous:
        alternativas = ", ".join(f"`{a}`" for a in r.count.ambiguous_with)
        lines.append(f"- **Hipótesis alternativas**: {alternativas} — el conteo es ambiguo")

    lines.append("")
    lines.append("| factor | score | umbral | activo |")
    lines.append("|---|---|---|---|")
    for factor in r.factors:
        marca = "✅" if factor.active else "—"
        lines.append(f"| {factor.name} | {factor.score:.3f} | {factor.threshold:.2f} | {marca} |")

    lines.append("")
    lines.append("<details><summary>detalle de factores</summary>")
    lines.append("")
    for factor in r.factors:
        lines.append(f"- **{factor.name}**: {factor.detail}")
    if r.count.notes:
        lines.append("")
        for nota in r.count.notes:
            lines.append(f"> {nota}")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    return lines


def render_markdown(
    entries: list[ReportEntry],
    warnings: list[str],
    *,
    cfg: Config,
    now: pd.Timestamp,
) -> str:
    """Construye el documento Markdown completo."""
    signals = [e for e in entries if e.is_signal]
    near = [e for e in entries if not e.is_signal and len(e.result.active_factors) >= 2]

    lines = [
        f"# Elliott Hybrid Scanner — {now:%Y-%m-%d %H:%M} UTC",
        "",
        "> Informe generado automáticamente. **No es asesoramiento financiero y el",
        "> sistema no ejecuta órdenes**: las señales están pensadas para validarse",
        "> a mano (por ejemplo en TradingView) antes de decidir nada.",
        "",
        f"Universo: {', '.join(cfg.bases)} | timeframe de estructura: "
        f"{cfg.get('timeframes.structure')} | mínimo de factores: "
        f"{cfg.get('confluence.min_active_factors')}",
        "",
        f"## Señales activas ({len(signals)})",
        "",
    ]

    if signals:
        for entry in signals:
            lines.extend(_entry_block(entry))
    else:
        lines.extend(
            [
                "Hoy no hay ninguna señal que supere el umbral de confluencia. Es el",
                "comportamiento esperado la mayoría de los días: el sistema emite unas",
                "cuatro señales al mes en todo el universo.",
                "",
            ]
        )

    if near:
        lines.append(f"## Cerca del umbral ({len(near)})")
        lines.append("")
        lines.append("Conteos válidos con 2 factores activos, a uno de emitir señal:")
        lines.append("")
        lines.append("| par | dirección | hipótesis | score | factores activos |")
        lines.append("|---|---|---|---|---|")
        for entry in near:
            r = entry.result
            activos = ", ".join(f.name for f in r.active_factors) or "—"
            lines.append(
                f"| {r.symbol} | {r.signal_direction} | `{r.count.hypothesis}` "
                f"| {r.score:.3f} | {activos} |"
            )
        lines.append("")

    if warnings:
        lines.append("## Avisos")
        lines.append("")
        lines.extend(f"- {w}" for w in warnings)
        lines.append("")

    lines.append("---")
    lines.append(
        "*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra "
        "azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no "
        "probado. Ver README.*"
    )
    lines.append("")
    return "\n".join(lines)


def write_report(cfg: Config, *, now: pd.Timestamp | None = None) -> Path:
    """Genera el informe del día y lo escribe en `paths.reports_dir`."""
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    entries, warnings = collect_entries(cfg)
    content = render_markdown(entries, warnings, cfg=cfg, now=now)

    reports_dir = cfg.path("paths.reports_dir")
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"scan_{now:%Y-%m-%d}.md"
    path.write_text(content, encoding="utf-8")

    latest = reports_dir / "latest.md"
    latest.write_text(content, encoding="utf-8")
    LOGGER.info("Informe escrito en %s (y latest.md)", path)
    return path
