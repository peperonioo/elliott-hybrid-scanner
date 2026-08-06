#!/usr/bin/env python3
"""CLI de la fase 6: descarga las velas nuevas y genera el informe diario.

python scripts/daily_report.py            # actualiza datos + informe
python scripts/daily_report.py --no-fetch # solo el informe, con la caché
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ehs.config import Config, setup_logging
from ehs.data.fetcher import OHLCVFetcher
from ehs.report.daily import write_report
from ehs.report.web import write_web


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera el informe diario de señales.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--no-fetch", action="store_true", help="No actualiza la caché")
    args = parser.parse_args()

    cfg = Config.load(args.config)
    setup_logging(cfg)

    if not args.no_fetch:
        results = OHLCVFetcher(cfg).fetch_all()
        no_aptas = [r for r in results if not r.ok]
        for resultado in no_aptas:
            print(f"AVISO: {resultado.report.summary()}")

    path = write_report(cfg)
    web = write_web(cfg)
    print(f"Informe: {path}")
    print(f"Web: {web}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
