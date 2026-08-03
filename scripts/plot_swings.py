#!/usr/bin/env python3
"""CLI de la fase 2: detecta swings sobre la caché local y los dibuja.

Ejemplos:
    python scripts/plot_swings.py --bases BTC ETH
    python scripts/plot_swings.py --bases BTC --threshold 3.0
    python scripts/plot_swings.py --bases BTC --compare 1.5 2.5 3.5 4.5
    python scripts/plot_swings.py --bases BTC --lookback 0        # serie entera
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ehs.config import Config, setup_logging
from ehs.data.cache import ParquetCache
from ehs.structure.plotting import plot_swings, plot_threshold_comparison
from ehs.structure.swings import detect_swings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dibuja los swings detectados sobre el precio.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--bases", nargs="*", default=None, help="Bases a dibujar")
    parser.add_argument("--timeframe", default=None, help="Por defecto, timeframes.structure")
    parser.add_argument("--threshold", type=float, default=None, help="Sobrescribe atr_threshold")
    parser.add_argument("--lookback", type=int, default=None, help="Velas a mostrar; 0 = todas")
    parser.add_argument(
        "--compare", nargs="*", type=float, default=None, help="Compara varios umbrales"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = Config.load(args.config)
    setup_logging(cfg)

    cache = ParquetCache(cfg.path("paths.cache_dir"))
    plots_dir = cfg.path("paths.plots_dir")
    exchange_id = str(cfg.get("exchanges.primary.id"))
    timeframe = args.timeframe or str(cfg.get("timeframes.structure"))

    atr_period = int(cfg.get("swings.atr_period"))
    threshold = (
        args.threshold if args.threshold is not None else float(cfg.get("swings.atr_threshold"))
    )
    confirmation_bars = int(cfg.get("swings.confirmation_bars"))
    atr_reference = str(cfg.get("swings.atr_reference"))

    lookback = (
        args.lookback if args.lookback is not None else int(cfg.get("plots.lookback_candles"))
    )
    figsize = tuple(cfg.get("plots.figsize"))
    dpi = int(cfg.get("plots.dpi"))

    bases = args.bases if args.bases else cfg.bases
    written: list[Path] = []

    for base in bases:
        symbol = cfg.symbol_for(base, "primary")
        frame = cache.read(exchange_id, symbol, timeframe)
        if frame.empty:
            print(f"{base}: sin caché para {symbol} {timeframe}; ejecuta antes fetch_data.py")
            continue

        window = frame.iloc[-lookback:] if lookback and lookback > 0 else frame
        span = f"{window.index.min():%Y-%m-%d} .. {window.index.max():%Y-%m-%d}"

        if args.compare:
            output = plots_dir / f"swings_compare_{base}_{timeframe}.png"
            written.append(
                plot_threshold_comparison(
                    window,
                    list(args.compare),
                    title=f"{symbol} {timeframe} — comparación de umbrales — {span}",
                    output=output,
                    atr_period=atr_period,
                    confirmation_bars=confirmation_bars,
                    atr_reference=atr_reference,
                    figsize=figsize,
                    dpi=dpi,
                )
            )
            continue

        pivots = detect_swings(
            window,
            atr_period=atr_period,
            atr_threshold=threshold,
            confirmation_bars=confirmation_bars,
            atr_reference=atr_reference,
        )
        lags = [p.confirmation_lag for p in pivots]
        media_lag = sum(lags) / len(lags) if lags else 0.0
        print(
            f"{symbol} {timeframe}: {len(window)} velas, {len(pivots)} pivotes, "
            f"retardo medio de confirmación {media_lag:.1f} velas"
        )
        for pivot in pivots[-6:]:
            print(f"    {pivot}")

        output = plots_dir / f"swings_{base}_{timeframe}.png"
        written.append(
            plot_swings(
                window,
                pivots,
                title=(
                    f"{symbol} {timeframe} — {threshold}×ATR{atr_period}, "
                    f"confirmación +{confirmation_bars} velas — {span}"
                ),
                output=output,
                atr_period=atr_period,
                atr_threshold=threshold,
                figsize=figsize,
                dpi=dpi,
            )
        )

    for path in written:
        print(f"→ {path}")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
