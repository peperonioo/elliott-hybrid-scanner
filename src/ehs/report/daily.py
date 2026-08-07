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
from ehs.confluence.scorer import ConfluenceResult, score_confluence
from ehs.data.cache import ParquetCache
from ehs.elliott.validator import scan_recent
from ehs.pipeline import PipelineParams, generate_signals
from ehs.structure.swings import detect_swings

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
    params = PipelineParams.from_config(cfg)
    filters = TradeFilters.from_config(cfg)

    entries: list[ReportEntry] = []
    warnings: list[str] = []

    for base in cfg.bases:
        symbol, structure, context = _read_pair(cfg, cache, base, params)
        if structure.empty or context.empty:
            warnings.append(f"{base}: sin datos en caché (ni primario ni fallback)")
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

        # Radar: la mejor estructura vigente del par, re-evaluada al precio de
        # AHORA. No es una señal causal —eso solo lo decide el bloque
        # anterior— pero es lo que un lector humano quiere vigilar: qué niveles
        # tiene delante cada par hoy.
        watch = _best_current_read(structure, context, symbol, params, filters)
        if watch is not None and not any(e.result.symbol == symbol for e in entries):
            entries.append(watch)

    # Señales causales: todas. Radar: una sola lectura por par, la mejor.
    signals = [e for e in entries if e.is_signal]
    radar: dict[str, ReportEntry] = {}
    for e in entries:
        if e.is_signal:
            continue
        current = radar.get(e.result.symbol)
        if current is None or e.result.score > current.result.score:
            radar[e.result.symbol] = e

    entries = signals + list(radar.values())
    entries.sort(key=lambda e: (not e.is_signal, -e.result.score))
    return entries, warnings


def _read_pair(cfg: Config, cache: ParquetCache, base: str, params: PipelineParams):
    """Series del par desde la caché, respetando el orden de fallback.

    El fetcher guarda bajo el exchange que realmente sirvió los datos: si el
    primario estaba caído (o geo-bloqueado, como Binance en los runners de CI)
    los datos viven bajo el fallback, y el informe tiene que saber mirarlo.
    """
    for role in ("primary", "fallback"):
        exchange_id = cfg.get(f"exchanges.{role}.id", None)
        if not exchange_id:
            continue
        symbol = cfg.symbol_for(base, role)
        structure = cache.read(str(exchange_id), symbol, params.structure_timeframe)
        context = cache.read(str(exchange_id), symbol, params.context_timeframe)
        if not structure.empty and not context.empty:
            return symbol, structure, context
    return cfg.symbol_for(base, "primary"), structure, context


def _best_current_read(
    structure: pd.DataFrame,
    context: pd.DataFrame,
    symbol: str,
    params: PipelineParams,
    filters: TradeFilters,
) -> ReportEntry | None:
    """La mejor lectura alcista del par evaluada en la última vela cerrada.

    Solo se acepta si su geometría es operable: la invalidación tiene que
    quedar por debajo de la zona de compra. Devuelve None si no hay ninguna.
    """
    pivots = detect_swings(structure, **params.swing)
    best: ConfluenceResult | None = None
    for count in scan_recent(pivots, params.elliott):
        try:
            result = score_confluence(
                count,
                structure=structure,
                context=context,
                symbol=symbol,
                structure_timeframe=params.structure_timeframe,
                context_timeframe=params.context_timeframe,
                params=params.confluence,
            )
        except ValueError:
            continue
        if not filters.allows_direction(result.signal_direction):
            continue
        if result.zone is None or result.signal_invalidation >= result.zone[0]:
            continue
        if best is None or result.score > best.score:
            best = result
    if best is None:
        return None
    return ReportEntry(result=best, is_signal=False, bars_ago=0)


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
    near = [e for e in entries if not e.is_signal]

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
        lines.append(
            "La mejor estructura alcista vigente de cada par, re-evaluada al precio "
            "actual. NO son señales (les faltan factores): son los niveles a vigilar."
        )
        lines.append("")
        lines.append("| par | hipótesis | score | factores activos | zona de compra | stop |")
        lines.append("|---|---|---|---|---|---|")
        for entry in near:
            r = entry.result
            activos = ", ".join(f.name for f in r.active_factors) or "—"
            zona = f"{_fmt_price(r.zone[0])}–{_fmt_price(r.zone[1])}" if r.zone else "—"
            lines.append(
                f"| {r.symbol} | `{r.count.hypothesis}` | {r.score:.3f} | {activos} "
                f"| {zona} | {_fmt_price(r.signal_invalidation)} |"
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
