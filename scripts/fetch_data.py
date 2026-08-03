#!/usr/bin/env python3
"""CLI de la fase 1: descarga y valida el universo configurado.

Ejemplos:
    python scripts/fetch_data.py                       # todo el universo
    python scripts/fetch_data.py --bases BTC ETH       # solo dos pares
    python scripts/fetch_data.py --timeframes 4h       # solo estructura
    python scripts/fetch_data.py --show BTC --rows 10  # inspeccionar un frame
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from ehs.config import Config, setup_logging
from ehs.data.fetcher import OHLCVFetcher, summarise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga OHLCV pública y la cachea en Parquet.")
    parser.add_argument("--config", default=None, help="Ruta a config.yaml")
    parser.add_argument(
        "--bases", nargs="*", default=None, help="Bases a descargar (por defecto: todas)"
    )
    parser.add_argument(
        "--timeframes", nargs="*", default=None, help="Timeframes (por defecto: todos)"
    )
    parser.add_argument(
        "--force-full", action="store_true", help="Ignora la caché y re-descarga todo"
    )
    parser.add_argument("--show", default=None, help="Muestra el DataFrame resultante de esta base")
    parser.add_argument("--rows", type=int, default=8, help="Filas a mostrar con --show")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = Config.load(args.config)
    setup_logging(cfg)

    fetcher = OHLCVFetcher(cfg)
    results = fetcher.fetch_all(args.bases, args.timeframes, force_full=args.force_full)

    print()
    print(summarise(results))

    if args.show:
        pd.set_option("display.width", 140)
        pd.set_option("display.float_format", lambda v: f"{v:,.6g}")
        for result in (r for r in results if r.base == args.show):
            frame = result.frame
            print(
                f"\n=== {result.base} {result.timeframe} ({result.exchange_id}:{result.symbol}) ==="
            )
            print(f"velas: {len(frame)} | rango: {frame.index.min()} .. {frame.index.max()}")
            print(f"dtypes:\n{frame.dtypes.to_string()}")
            print(f"\nhead({args.rows}):\n{result.frame.head(args.rows)}")
            print(f"\ntail({args.rows}):\n{result.frame.tail(args.rows)}")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
