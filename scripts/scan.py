#!/usr/bin/env python3
"""CLI de la fase 4: recorre el universo y puntúa la confluencia.

Es una herramienta de diagnóstico, no el informe de la fase 6. Sirve para ver
qué está encontrando el sistema y con qué factores.

Ejemplos:
    python scripts/scan.py
    python scripts/scan.py --bases BTC ETH --all
    python scripts/scan.py --explain
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ehs.config import Config, setup_logging
from ehs.confluence.scorer import ConfluenceParams, ConfluenceResult, score_confluence
from ehs.data.cache import ParquetCache
from ehs.elliott.validator import ElliottParams, scan_recent
from ehs.structure.swings import detect_swings_from_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Escanea el universo y puntúa la confluencia.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--bases", nargs="*", default=None)
    parser.add_argument("--all", action="store_true", help="Muestra también lo que no emite señal")
    parser.add_argument("--explain", action="store_true", help="Detalla cada factor")
    parser.add_argument("--top", type=int, default=10)
    return parser.parse_args()


def evaluate(cfg: Config, base: str, cache: ParquetCache, params: ConfluenceParams):
    exchange_id = str(cfg.get("exchanges.primary.id"))
    symbol = cfg.symbol_for(base, "primary")
    tf_structure = str(cfg.get("timeframes.structure"))
    tf_context = str(cfg.get("timeframes.context"))

    structure = cache.read(exchange_id, symbol, tf_structure)
    context = cache.read(exchange_id, symbol, tf_context)
    if structure.empty or context.empty:
        return []

    pivots = detect_swings_from_config(structure, cfg)
    counts = scan_recent(pivots, ElliottParams.from_config(cfg))

    swing_kwargs = {
        "atr_period": int(cfg.get("swings.atr_period")),
        "atr_threshold": float(cfg.get("swings.atr_threshold")),
        "confirmation_bars": int(cfg.get("swings.confirmation_bars")),
        "atr_reference": str(cfg.get("swings.atr_reference")),
    }

    results: list[ConfluenceResult] = []
    for count in counts:
        try:
            results.append(
                score_confluence(
                    count,
                    structure=structure,
                    context=context,
                    symbol=symbol,
                    structure_timeframe=tf_structure,
                    context_timeframe=tf_context,
                    params=params,
                    swing_kwargs=swing_kwargs,
                )
            )
        except ValueError as exc:  # conteo aún no confirmado o serie corta
            print(f"  {symbol}: {exc}")
    return results


def main() -> int:
    args = parse_args()
    cfg = Config.load(args.config)
    setup_logging(cfg)

    cache = ParquetCache(cfg.path("paths.cache_dir"))
    params = ConfluenceParams.from_config(cfg)

    todos: list[ConfluenceResult] = []
    for base in args.bases if args.bases else cfg.bases:
        todos.extend(evaluate(cfg, base, cache, params))

    con_senal = [r for r in todos if r.emits_signal]
    mostrar = todos if args.all else con_senal
    mostrar = sorted(mostrar, key=lambda r: r.score, reverse=True)[: args.top]

    print(
        f"\n{len(todos)} conteos evaluados, {len(con_senal)} emiten señal "
        f"(≥{params.min_active_factors} factores sobre umbral)\n"
    )
    for resultado in mostrar:
        print(resultado.summary())
        if resultado.zone:
            print(
                f"    zona de interés {resultado.zone[0]:,.2f}–{resultado.zone[1]:,.2f} | "
                f"invalidación de señal {resultado.signal_invalidation:,.2f}"
                if resultado.signal_invalidation is not None
                else f"    zona de interés {resultado.zone[0]:,.2f}–{resultado.zone[1]:,.2f}"
            )
        if resultado.count.is_ambiguous:
            print(f"    hipótesis alternativas: {', '.join(resultado.count.ambiguous_with)}")
        if args.explain:
            for factor in resultado.factors:
                print(f"      {factor}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
