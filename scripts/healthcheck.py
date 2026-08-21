#!/usr/bin/env python3
"""Chequeo de salud: ¿está la web diciendo la verdad ahora mismo?

Compara la página publicada con el mercado en vivo y con la caché local, y
avisa de lo único que puede estropearse en silencio: que los niveles se hayan
quedado viejos, que el análisis lleve horas sin renovarse, o que los datos
tengan huecos. Pensado para ejecutarlo cuando el mercado se mueve rápido.

    python scripts/healthcheck.py
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from ehs.config import Config
from ehs.data.cache import ParquetCache

WEB = "https://peperonioo.github.io/elliott-hybrid-scanner/"
BINANCE = "https://data-api.binance.vision/api/v3/klines"
DERIVA_AVISO = 2.0  # % de deriva a partir del cual la web ya avisa sola
ANALISIS_MAX_H = 6.0  # el análisis se rehace cada 4 h


def _get(url: str, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode()


def main() -> int:
    cfg = Config.load()
    problemas: list[str] = []

    print("== web publicada ==")
    try:
        html = _get(WEB)
    except Exception as exc:  # el diagnóstico no debe romperse por un fallo de red
        print(f"  ✖ no se pudo leer la web: {exc}")
        return 1

    gen = re.search(r"var EHS_GEN = (\d+);", html)
    if gen:
        edad = (dt.datetime.now(dt.UTC).timestamp() - int(gen.group(1))) / 3600
        marca = "✔" if edad <= ANALISIS_MAX_H else "✖"
        print(f"  {marca} análisis de hace {edad:.1f} h")
        if edad > ANALISIS_MAX_H:
            problemas.append(f"el análisis lleva {edad:.1f} h sin renovarse")
    else:
        problemas.append("la web no declara cuándo se generó")

    live = re.search(r"var EHS_LIVE = (\[.*?\]);", html, re.S)
    if not live:
        print("  ✖ la web no lleva datos en vivo")
        return 1
    payload = {o["base"]: o for o in json.loads(live.group(1))}

    print("\n== deriva del mercado desde el análisis ==")
    derivas: list[float] = []
    for base, o in payload.items():
        if not o.get("px0"):
            continue
        try:
            rows = json.loads(_get(f"{BINANCE}?symbol={base}USDT&interval=4h&limit=1", 15))
        except Exception:  # una moneda caída no invalida el resto
            print(f"  {base:6} sin precio en vivo")
            continue
        deriva = (float(rows[-1][4]) / o["px0"] - 1) * 100
        derivas.append(deriva)
        aviso = "  ← recalculado en vivo" if abs(deriva) >= DERIVA_AVISO else ""
        print(f"  {base:6} {deriva:+6.1f}%{aviso}")

    if derivas:
        mediana = sorted(derivas)[len(derivas) // 2]
        print(f"\n  mediana: {mediana:+.1f}%")
        if abs(mediana) >= DERIVA_AVISO:
            tiene_aviso = 'id="drift-warn"' in html
            print(
                f"  {'✔' if tiene_aviso else '✖'} la web "
                f"{'avisa' if tiene_aviso else 'NO avisa'} de la deriva"
            )
            if not tiene_aviso:
                problemas.append("deriva alta y la web no la avisa")

    print("\n== caché local ==")
    cache = ParquetCache(cfg.path("paths.cache_dir"))
    exchange = str(cfg.get("exchanges.primary.id"))
    for base in cfg.bases:
        frame = cache.read(exchange, cfg.symbol_for(base, "primary"), "4h")
        if frame.empty:
            problemas.append(f"{base}: sin caché")
            print(f"  ✖ {base:6} sin datos")
            continue
        huecos = int((frame.index.to_series().diff().dropna() > pd.Timedelta(hours=4)).sum())
        dups = int(frame.index.duplicated().sum())
        atraso = (pd.Timestamp.now(tz="UTC") - frame.index[-1]).total_seconds() / 3600
        if huecos or dups:
            problemas.append(f"{base}: {huecos} huecos, {dups} duplicados")
        print(
            f"  {'✖' if huecos or dups else '✔'} {base:6} {len(frame):6} velas · "
            f"última hace {atraso:4.1f} h · huecos {huecos} · dups {dups}"
        )

    print("\n== veredicto ==")
    if problemas:
        for p in problemas:
            print(f"  ✖ {p}")
        print("\n  (la caché local se queda vieja entre sesiones; el workflow de")
        print("   GitHub es el que mantiene la web al día — mira Actions si falla)")
        return 1
    print("  ✔ todo en orden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
