#!/usr/bin/env python3
"""CLI de la fase 5: walk-forward, costes reales y contraste contra baselines.

Ejemplos:
    python scripts/backtest.py
    python scripts/backtest.py --bases BTC ETH --trials 200
    python scripts/backtest.py --trades trades.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from ehs.backtest.baselines import (
    buy_and_hold,
    direction_mix,
    random_baseline,
    summarise_buy_and_hold,
)
from ehs.backtest.engine import CostModel, ExitRules, trades_to_frame
from ehs.backtest.metrics import compute_metrics
from ehs.backtest.walkforward import make_folds, walk_forward
from ehs.config import Config, setup_logging
from ehs.data.cache import ParquetCache
from ehs.pipeline import PipelineParams, generate_signals


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest walk-forward con costes reales.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--bases", nargs="*", default=None)
    parser.add_argument("--trials", type=int, default=None, help="Simulaciones aleatorias")
    parser.add_argument("--trades", default=None, help="Vuelca las operaciones a este CSV")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = Config.load(args.config)
    setup_logging(cfg)

    cache = ParquetCache(cfg.path("paths.cache_dir"))
    exchange_id = str(cfg.get("exchanges.primary.id"))
    params = PipelineParams.from_config(cfg)
    costs = CostModel.from_config(cfg)
    rules = ExitRules.from_config(cfg)

    bases = args.bases if args.bases else cfg.bases
    frames: dict[str, pd.DataFrame] = {}
    signals: dict[str, list] = {}

    print("Generando señales…")
    for base in bases:
        symbol = cfg.symbol_for(base, "primary")
        structure = cache.read(exchange_id, symbol, params.structure_timeframe)
        context = cache.read(exchange_id, symbol, params.context_timeframe)
        if structure.empty or context.empty:
            print(f"  {symbol}: sin caché, se omite")
            continue
        frames[symbol] = structure
        # `only_emitting=False`: el walk-forward reajusta el mínimo de factores
        # por tramo y necesita ver también los conteos que hoy no emiten.
        signals[symbol] = generate_signals(
            structure, context, symbol=symbol, params=params, only_emitting=False
        )
        emiten = sum(1 for s in signals[symbol] if s.emits_signal)
        print(f"  {symbol}: {len(signals[symbol])} conteos, {emiten} emiten con el umbral actual")

    if not frames:
        print("No hay datos. Ejecuta antes scripts/fetch_data.py")
        return 1

    start = min(f.index[0] for f in frames.values())
    end = max(f.index[-1] for f in frames.values())
    years = (end - start).days / 365.25
    minimo = float(cfg.get("backtest.min_history_years", 2))
    print(f"\nPeriodo: {start:%Y-%m-%d} → {end:%Y-%m-%d} ({years:.1f} años)")
    if years < minimo:
        print(f"AVISO: menos de {minimo} años de histórico; los resultados no son concluyentes.")

    folds = make_folds(
        start,
        end,
        train_months=int(cfg.get("backtest.walk_forward.train_months")),
        test_months=int(cfg.get("backtest.walk_forward.test_months")),
    )
    resultado = walk_forward(
        signals,
        frames,
        folds=folds,
        grid=[int(k) for k in cfg.get("backtest.walk_forward.min_active_grid")],
        rules=rules,
        costs=costs,
        default_min_active=int(cfg.get("confluence.min_active_factors")),
        min_train_trades=int(cfg.get("backtest.walk_forward.min_train_trades", 10)),
        allow_overlap=bool(cfg.get("backtest.allow_overlap", False)),
    )

    print("\n" + "=" * 78)
    print("WALK-FORWARD (solo tramos de prueba)")
    print("=" * 78)
    print(resultado.summary())

    trades = resultado.test_trades
    metrics = compute_metrics(trades)
    print("\n" + "-" * 78)
    print(f"AGREGADO  (costes: {costs.round_trip_pct:.2f}% ida y vuelta)")
    print("-" * 78)
    print(metrics.detail() if trades else "sin operaciones fuera de muestra")

    print("\n" + "-" * 78)
    print("BASELINE 1 — buy & hold")
    print("-" * 78)
    holds = [buy_and_hold(frame, symbol, costs) for symbol, frame in frames.items()]
    print(summarise_buy_and_hold(holds))

    print("\n" + "-" * 78)
    print("BASELINE 2 — señales aleatorias con la misma frecuencia")
    print("-" * 78)
    if not trades:
        print("sin operaciones que contrastar")
    else:
        trials = args.trials or int(cfg.get("backtest.baselines.random_trials", 1000))
        print(f"mezcla de direcciones replicada: {direction_mix(trades)}")
        baseline = random_baseline(
            frames,
            trades,
            rules=rules,
            costs=costs,
            trials=trials,
            seed=int(cfg.get("backtest.baselines.seed", 20240101)),
        )
        print(baseline.summary())
        print()
        print(baseline.verdict(alpha=float(cfg.get("backtest.baselines.alpha", 0.05))))

    if args.trades and trades:
        path = Path(args.trades)
        trades_to_frame(trades).to_csv(path, index=False)
        print(f"\nOperaciones volcadas en {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
