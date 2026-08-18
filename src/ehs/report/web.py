"""Página web del scanner: dashboard con gráficos interactivos.

Genera un `index.html` para GitHub Pages con un gráfico de velas real por
moneda, usando Lightweight Charts (la librería open-source de TradingView,
cargada por CDN). Sobre cada gráfico se dibujan la zona de compra, el stop y
el objetivo 2R, y la estructura de ondas detectada. Los datos de las velas
van embebidos en la propia página como JSON: no hay peticiones a exchanges
desde el navegador.

Usa las mismas entradas que el informe Markdown —`collect_entries`—, así que
la web y el informe no pueden contar cosas distintas.
"""

from __future__ import annotations

import html
import json
import logging
import math
from pathlib import Path
from typing import Any

import pandas as pd

from ehs.config import Config
from ehs.confluence.scorer import score_confluence
from ehs.data.cache import ParquetCache
from ehs.elliott.validator import scan_recent
from ehs.pipeline import PipelineParams
from ehs.report.daily import ReportEntry, _read_pair, collect_entries
from ehs.report.direction import compute_direction_stats
from ehs.report.signals_log import LoggedSignal, summary_stats, update_log
from ehs.structure.swings import detect_swings

LOGGER = logging.getLogger(__name__)

CHART_BARS = 240  # ~40 días de velas de 4h
LIGHTWEIGHT_CHARTS_CDN = (
    "https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"
)

# Traducciones a lenguaje llano. La web es la cara del sistema para un lector
# no técnico: los nombres internos se quedan en el código y en el Markdown.
FACTOR_LABELS = {
    "fibonacci": "precio en nivel Fibonacci",
    "rsi_divergence": "divergencia del RSI",
    "market_structure": "ruptura en el gráfico diario",
    "volume_profile": "volumen coherente",
    "higher_timeframe_trend": "tendencia diaria a favor",
}

HYPOTHESIS_LABELS = {
    "corrective_abc": "corrección terminada → posible subida",
    "impulse": "ciclo de 5 ondas completo",
    "impulse_1_2_3": "impulso en construcción",
    "diagonal_contracting": "cuña terminal completa",
    "diagonal_expanding": "cuña expansiva completa",
}


def _factor_label(name: str) -> str:
    return FACTOR_LABELS.get(name, name)


def _hypothesis_label(name: str) -> str:
    return HYPOTHESIS_LABELS.get(name, name)


CSS = """
:root {
  --bg:#0b0e14; --fg:#e9edf5; --muted:#8a93a6; --card:#131926;
  --card2:#0f141f; --border:#222b3c; --accent:#4c8dff; --accent2:#7c5cff;
  --green:#0ecb81; --red:#f6465d; --amber:#f0b90b;
  --zone:rgba(76,141,255,.14); --glow:rgba(76,141,255,.35);
}
@media (prefers-color-scheme: light) {
  :root {
    --bg:#f4f6fa; --fg:#141a24; --muted:#5d6a80; --card:#ffffff;
    --card2:#eef1f7; --border:#dfe5ef; --accent:#2563eb; --accent2:#6d4fd8;
    --green:#059f68; --red:#dc2f4e; --amber:#b45309;
    --zone:rgba(37,99,235,.10); --glow:rgba(37,99,235,.25);
  }
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:920px;margin:0 auto;padding:18px 16px 56px}
.appbar{display:flex;align-items:center;gap:12px;margin:0 0 4px}
.logo{width:38px;height:38px;flex:none;border-radius:11px;
  filter:drop-shadow(0 2px 8px var(--glow))}
h1{font-size:1.3rem;margin:0;letter-spacing:-.02em;font-weight:800;line-height:1.15}
h1 .thin{font-weight:500;color:var(--muted)}
.bsub{display:block;font-size:.72rem;font-weight:600;color:var(--muted);
  letter-spacing:.08em;text-transform:uppercase}
.updated{color:var(--muted);font-size:.82rem;margin:8px 0 10px}
.disclaimer{color:var(--muted);font-size:.78rem;margin-bottom:16px;
  border-left:2px solid var(--border);padding-left:10px}
h2{font-size:1.05rem;margin:30px 0 10px;padding-bottom:8px;font-weight:800;
  letter-spacing:-.01em;border-bottom:1px solid var(--border)}
.ghdr{margin:44px 0 -16px;font-size:.68rem;font-weight:800;letter-spacing:.16em;
  text-transform:uppercase;color:var(--accent);display:flex;align-items:center;gap:10px}
.ghdr::after{content:"";flex:1;height:1px;
  background:linear-gradient(90deg,var(--border),transparent)}
.hero{display:flex;gap:6px 22px;flex-wrap:wrap;align-items:center;margin:14px 0 18px;
  padding:14px 18px;border-radius:16px;font-size:.9rem;color:var(--muted);
  background:linear-gradient(135deg,var(--card),var(--card2));
  border:1px solid var(--border)}
.hero b{font-size:1.06rem;color:var(--fg);font-variant-numeric:tabular-nums}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;
  padding:16px 18px;margin:14px 0;scroll-margin-top:56px;
  transition:border-color .15s ease,box-shadow .15s ease}
.card:hover{border-color:var(--accent);box-shadow:0 6px 24px rgba(0,0,0,.25)}
.card.signal{border-color:var(--green);
  box-shadow:0 0 0 1px var(--green),0 6px 28px rgba(14,203,129,.15)}
.card h3{margin:0 0 6px;font-size:1rem;display:flex;flex-wrap:wrap;gap:8px;
  align-items:center;letter-spacing:-.01em}
.badge{display:inline-block;padding:3px 11px;border-radius:999px;
  font-size:.72rem;font-weight:800;letter-spacing:.02em}
.badge.long{background:var(--green);color:#04140d}
.badge.score{background:var(--zone);color:var(--accent)}
.badge.hot{background:var(--amber);color:#221600}
.card .meta{color:var(--muted);font-size:.82rem;margin:0 0 8px}
.tvchart{height:300px;margin:8px 0 2px;border-radius:10px;overflow:hidden}
.tvlink{font-size:.78rem;margin:4px 0 6px}
.tvlink a{color:var(--accent);text-decoration:none}
.levels{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));
  gap:8px;margin:12px 0 2px}
.level{background:var(--card2);border:1px solid var(--border);border-radius:10px;
  padding:8px 12px;border-left-width:3px}
.level .lab{font-size:.64rem;color:var(--muted);text-transform:uppercase;
  letter-spacing:.05em;font-weight:700}
.level .val{font-weight:800;font-size:.98rem;font-variant-numeric:tabular-nums}
.level.buy{border-left-color:var(--accent)}
.level.buy .val{color:var(--accent)}
.level.stop{border-left-color:var(--red)}
.level.stop .val{color:var(--red)}
.level.target{border-left-color:var(--green)}
.level.target .val{color:var(--green)}
table{border-collapse:collapse;width:100%;font-size:.84rem;margin:8px 0;
  font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--border);padding:8px 10px;text-align:left}
th{color:var(--muted);font-size:.7rem;text-transform:uppercase;
  letter-spacing:.05em;font-weight:700}
tr:hover td{background:var(--card2)}
.ok{color:var(--green);font-weight:700}
.empty{background:var(--card);border:1px dashed var(--border);border-radius:16px;
  padding:20px;text-align:center;color:var(--muted)}
.empty b{color:var(--fg)}
details{margin-top:6px}
summary{cursor:pointer;color:var(--accent);font-size:.88rem}
details ul{margin:8px 0;padding-left:18px;color:var(--muted);font-size:.86rem}
.legend{font-size:.9rem}
.legend dt{font-weight:700;margin-top:12px}
.legend dd{margin:2px 0 0 0;color:var(--muted)}
footer{margin-top:40px;color:var(--muted);font-size:.8rem;
  border-top:1px solid var(--border);padding-top:14px}
footer a{color:var(--accent)}
.ovgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
  gap:8px;margin:8px 0 4px}
.chip{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:9px 11px;display:flex;gap:9px;align-items:center;text-decoration:none;
  color:var(--fg);transition:border-color .15s ease,transform .15s ease}
.chip:hover{border-color:var(--accent);transform:translateY(-1px)}
.mono{width:30px;height:30px;border-radius:9px;color:#fff;font-weight:800;
  font-size:.78rem;display:flex;align-items:center;justify-content:center;flex:none}
.chip .nm{font-weight:800;font-size:.85rem;line-height:1.2}
.chip .pr{font-size:.78rem;color:var(--muted);font-variant-numeric:tabular-nums}
.st{font-size:.62rem;font-weight:800;border-radius:999px;padding:3px 8px;
  margin-left:auto;white-space:nowrap;flex-shrink:0;letter-spacing:.03em}
@media (max-width: 560px){
  .chip{flex-wrap:wrap;row-gap:4px}
}
.st.sig{background:var(--green);color:#04140d}
.st.rad{background:var(--zone);color:var(--accent)}
.st.non{background:var(--card2);color:var(--muted);border:1px solid var(--border)}
.st.bear{background:rgba(246,70,93,.14);color:var(--red)}
.meta2{font-size:.86rem;margin:0 0 6px}
.inzone{color:var(--green);font-weight:700}
.btnrow{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 14px}
.btn{display:inline-flex;align-items:center;gap:7px;border:0;cursor:pointer;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  color:#fff;font-weight:700;font-size:.85rem;padding:9px 16px;border-radius:10px;
  text-decoration:none;box-shadow:0 2px 10px var(--glow)}
.btn.sec{background:var(--card);color:var(--accent);border:1px solid var(--border);
  box-shadow:none}
.btnhint{color:var(--muted);font-size:.74rem;align-self:center}
.res{font-weight:700;border-radius:7px;padding:2px 9px;font-size:.78rem;
  white-space:nowrap}
.res.win{background:rgba(14,203,129,.16);color:var(--green)}
.res.loss{background:rgba(246,70,93,.14);color:var(--red)}
.res.open{background:var(--zone);color:var(--accent)}
.res.flat{background:var(--card2);color:var(--muted);border:1px solid var(--border)}
.ftstats{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);
  font-size:.88rem;margin:6px 0 10px}
.ftstats b{color:var(--fg);font-variant-numeric:tabular-nums}
.nav{position:sticky;top:0;z-index:20;display:flex;gap:6px;overflow-x:auto;
  padding:10px 16px;margin:0 -16px 6px;
  background:color-mix(in srgb,var(--bg) 86%,transparent);
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
  border-bottom:1px solid var(--border);scrollbar-width:none}
.nav::-webkit-scrollbar{display:none}
.nav a{flex:none;font-size:.78rem;font-weight:700;color:var(--muted);
  text-decoration:none;padding:6px 12px;border-radius:999px;
  border:1px solid var(--border);background:var(--card)}
.nav a:hover{color:var(--accent);border-color:var(--accent)}
h2{scroll-margin-top:56px}
.action{background:var(--zone);border-left:3px solid var(--accent);
  border-radius:0 10px 10px 0;padding:9px 13px;font-size:.87rem;margin:8px 0}
.action.go{background:rgba(14,203,129,.10);border-left-color:var(--green)}
.action.warn{background:rgba(246,70,93,.09);border-left-color:var(--red)}
.proj{background:var(--card2);border:1px solid var(--border);border-radius:12px;
  padding:11px 13px;margin:10px 0 2px}
.proj-t{font-size:.8rem;font-weight:800;margin-bottom:8px}
.probbar{display:flex;height:9px;border-radius:999px;overflow:hidden;gap:2px}
.pb{display:block;height:100%;border-radius:2px}
.pb.win{background:var(--green)}
.pb.flat{background:var(--muted);opacity:.4}
.pb.loss{background:var(--red)}
.proj-leg{display:flex;gap:12px;flex-wrap:wrap;font-size:.77rem;
  color:var(--muted);margin:8px 0 4px}
.c-green{color:var(--green)}.c-red{color:var(--red)}.c-mut{color:var(--muted)}
.proj-note{font-size:.74rem;color:var(--muted)}
.chg{font-size:.7rem;font-weight:800;margin-left:5px;
  font-variant-numeric:tabular-nums}
.chg.up{color:var(--green)}
.chg.dn{color:var(--red)}
.wdet{margin:10px 0}
.wdet>summary{cursor:pointer;display:flex;gap:10px;align-items:center;
  background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:11px 14px;list-style:none;color:var(--fg);
  transition:border-color .15s ease}
.wdet>summary::-webkit-details-marker{display:none}
.wdet>summary::after{content:"▾";margin-left:auto;color:var(--muted)}
.wdet[open]>summary::after{content:"▴"}
.wdet>summary:hover{border-color:var(--accent)}
.wsum{color:var(--muted);font-size:.8rem;font-variant-numeric:tabular-nums}
.wdet .card{margin-top:6px}
.btn:disabled,.btn[disabled]{opacity:.75;cursor:default}
.spinner{width:13px;height:13px;border:2px solid rgba(255,255,255,.35);
  border-top-color:#fff;border-radius:50%;display:inline-block;flex:none;
  animation:ehsspin .7s linear infinite}
@keyframes ehsspin{to{transform:rotate(360deg)}}
.flash{animation:ehsflash 1s ease}
@keyframes ehsflash{0%{background:var(--zone);border-radius:4px}100%{background:transparent}}
.tabbar{display:none}
@media (max-width: 720px){
  .nav{display:none}
  body{padding-bottom:72px}
  .tabbar{position:fixed;bottom:0;left:0;right:0;z-index:30;display:flex;
    justify-content:space-around;gap:2px;padding:6px 4px
      calc(6px + env(safe-area-inset-bottom));
    background:color-mix(in srgb,var(--card) 92%,transparent);
    backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
    border-top:1px solid var(--border)}
  .tabbar a{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;
    text-decoration:none;color:var(--muted);font-size:1.05rem;padding:4px 2px;
    border-radius:10px}
  .tabbar a span{font-size:.6rem;font-weight:700;letter-spacing:.02em}
  .tabbar a:active{color:var(--accent);background:var(--zone)}
}
"""


def _mono_style(base: str) -> str:
    hue = sum(ord(c) * 47 for c in base) % 360
    return f"background:hsl({hue},62%,45%)"


def _fmt(value: float) -> str:
    """Formato con dígitos significativos: sirve igual para BTC que para PEPE."""
    v = float(value)
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:.2f}"
    if v <= 0:
        return f"{v:.2f}"
    decimals = min(10, -math.floor(math.log10(v)) + 3)
    return f"{v:.{decimals}f}"


def _price_precision(value: float) -> int:
    """Decimales que necesita el eje del gráfico para este precio."""
    v = float(value)
    if v >= 1000:
        return 0
    if v >= 1:
        return 3
    if v <= 0:
        return 2
    return min(10, -math.floor(math.log10(v)) + 3)


def _round_price(value: float, precision: int) -> float:
    """Redondeo que respeta la escala de la moneda.

    Un redondeo fijo a 6 decimales aplasta monedas como PEPE (2e-6): todas las
    velas colapsan al mismo valor y el gráfico sale plano. Se redondea con
    margen sobre la precisión del eje.
    """
    return round(float(value), max(6, precision + 2))


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _target_for(entry: ReportEntry) -> float | None:
    r = entry.result
    if r.zone is None:
        return None
    mid = (r.zone[0] + r.zone[1]) / 2
    if r.signal_invalidation >= mid:
        return None
    return mid + 2 * (mid - r.signal_invalidation)


def _chart_id(symbol: str) -> str:
    return "chart-" + symbol.replace("/", "-")


def _tradingview_url(symbol: str) -> str:
    return "https://www.tradingview.com/chart/?symbol=BINANCE:" + symbol.replace("/", "")


# ---------------------------------------------------------------------------
# Datos para los gráficos
# ---------------------------------------------------------------------------


def build_chart_data(
    cfg: Config,
    entries: list[ReportEntry],
    watch: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Velas, pivotes y niveles de cada par, listos para embeber como JSON."""
    cache = ParquetCache(cfg.path("paths.cache_dir"))
    params = PipelineParams.from_config(cfg)
    data: dict[str, dict[str, Any]] = {}

    for entry in entries:
        r = entry.result
        if r.symbol in data:
            continue
        base = r.symbol.split("/")[0]
        _, structure, _ = _read_pair(cfg, cache, base, params)
        if structure.empty:
            continue

        window = structure.iloc[-CHART_BARS:]
        precision = _price_precision(float(window["close"].iloc[-1]))
        candles = [
            {
                "time": int(ts.timestamp()),
                "open": _round_price(row["open"], precision),
                "high": _round_price(row["high"], precision),
                "low": _round_price(row["low"], precision),
                "close": _round_price(row["close"], precision),
            }
            for ts, row in window.iterrows()
        ]

        first_ts = int(window.index[0].timestamp())
        # Etiquetas de las ondas del conteo (1-5 o A-B-C) sobre sus pivotes.
        labels = [
            {
                "time": int(wave.end.timestamp.timestamp()),
                "pos": "aboveBar" if wave.end.kind == "H" else "belowBar",
                "text": wave.label,
            }
            for wave in r.count.waves
            if int(wave.end.timestamp.timestamp()) >= first_ts
        ]
        pivots = [
            {"time": int(p.timestamp.timestamp()), "value": _round_price(p.price, precision)}
            for p in detect_swings(structure, **params.swing)
            if int(p.timestamp.timestamp()) >= first_ts
        ]

        target = _target_for(entry)
        data[r.symbol] = {
            "precision": precision,
            "minMove": round(10**-precision, 12),
            "candles": candles,
            "pivots": pivots,
            "labels": labels,
            "zone": (
                [_round_price(r.zone[0], precision), _round_price(r.zone[1], precision)]
                if r.zone
                else None
            ),
            "stop": _round_price(r.signal_invalidation, precision),
            "target": _round_price(target, precision) if target is not None else None,
        }

    # Monedas en observación: velas + ondas + soporte/resistencia/anulación.
    for info in (watch or {}).values():
        symbol = info["symbol"]
        if symbol in data:
            continue
        base = info["base"]
        _, structure, _ = _read_pair(cfg, cache, base, params)
        if structure.empty:
            continue
        window = structure.iloc[-CHART_BARS:]
        precision = _price_precision(float(window["close"].iloc[-1]))
        candles = [
            {
                "time": int(ts.timestamp()),
                "open": _round_price(row["open"], precision),
                "high": _round_price(row["high"], precision),
                "low": _round_price(row["low"], precision),
                "close": _round_price(row["close"], precision),
            }
            for ts, row in window.iterrows()
        ]
        first_ts = int(window.index[0].timestamp())
        pivots = [
            {"time": int(p.timestamp.timestamp()), "value": _round_price(p.price, precision)}
            for p in detect_swings(structure, **params.swing)
            if int(p.timestamp.timestamp()) >= first_ts
        ]
        hlines = []
        if info.get("sup") is not None:
            hlines.append(
                {"p": _round_price(info["sup"], precision), "label": "soporte", "c": "--green"}
            )
        if info.get("res") is not None:
            hlines.append(
                {"p": _round_price(info["res"], precision), "label": "resistencia", "c": "--red"}
            )
        if info.get("anula") is not None and info.get("anula") != info.get("res"):
            hlines.append(
                {
                    "p": _round_price(info["anula"], precision),
                    "label": "anula bajista",
                    "c": "--amber",
                }
            )
        data[symbol] = {
            "precision": precision,
            "minMove": round(10**-precision, 12),
            "candles": candles,
            "pivots": pivots,
            "labels": [],
            "zone": None,
            "stop": None,
            "target": None,
            "hlines": hlines,
        }
    return data


def build_overview(
    cfg: Config,
    entries: list[ReportEntry],
    watch: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Estado de TODAS las monedas del universo, tengan o no estructura.

    Es lo que responde de un vistazo "¿y ETH?": aunque una moneda no tenga
    tarjeta, aquí aparece con su precio y su estado.
    """
    cache = ParquetCache(cfg.path("paths.cache_dir"))
    params = PipelineParams.from_config(cfg)
    by_symbol: dict[str, ReportEntry] = {}
    for e in entries:
        by_symbol.setdefault(e.result.symbol, e)

    out: list[dict[str, Any]] = []
    for base in cfg.bases:
        symbol, structure, _ = _read_pair(cfg, cache, base, params)
        if structure.empty:
            out.append(
                {"base": base, "price": None, "state": "sin datos", "cls": "non", "link": False}
            )
            continue
        price = float(structure["close"].iloc[-1])
        entry = by_symbol.get(symbol)
        info = (watch or {}).get(base)
        if entry and entry.is_signal:
            state, cls = "SEÑAL", "sig"
        elif entry:
            state, cls = "radar", "rad"
        elif info:
            state, cls = info["label"], info["cls"]
        else:
            state, cls = "sin datos", "non"
        out.append(
            {
                "base": base,
                "symbol": symbol,
                "price": price,
                "state": state,
                "cls": cls,
                "link": entry is not None or info is not None,
            }
        )
    return out


def _overview_html(overview: list[dict[str, Any]]) -> str:
    chips = []
    for o in overview:
        precio = _fmt(o["price"]) if o["price"] is not None else "—"
        inner = (
            f'<span class="mono" style="{_mono_style(o["base"])}">{_esc(o["base"][:1])}</span>'
            f'<span><span class="nm">{_esc(o["base"])}'
            f'<span class="chg" id="chg-{_esc(o["base"])}"></span></span><br>'
            f'<span class="pr" id="ov-{_esc(o["base"])}">{precio}</span></span>'
            f'<span class="st {o["cls"]}">{_esc(o["state"])}</span>'
        )
        if o["link"]:
            chips.append(f'<a class="chip" href="#card-{_esc(o["base"])}">{inner}</a>')
        else:
            chips.append(f'<div class="chip">{inner}</div>')
    return '<div class="ovgrid">' + "".join(chips) + "</div>"


def build_watch(cfg: Config, entries: list[ReportEntry]) -> dict[str, dict[str, Any]]:
    """Diagnóstico de las monedas SIN jugada alcista operable.

    "Sin estructura" era un callejón sin salida informativo. El sistema sabe
    más: si la mejor lectura es bajista (y dónde se anularía), si la lectura
    alcista existe pero su geometría no es operable, o si simplemente es un
    lateral. Y los pivotes del ZigZag dan siempre soporte y resistencia
    objetivos. Nada de esto toca la lógica de señales: es solo diagnóstico.
    """
    cache = ParquetCache(cfg.path("paths.cache_dir"))
    params = PipelineParams.from_config(cfg)
    have = {e.result.symbol.split("/")[0] for e in entries}

    out: dict[str, dict[str, Any]] = {}
    for base in cfg.bases:
        if base in have:
            continue
        symbol, structure, context = _read_pair(cfg, cache, base, params)
        if structure.empty:
            continue

        pivots = detect_swings(structure, **params.swing)
        highs = [p for p in pivots if p.kind == "H"]
        lows = [p for p in pivots if p.kind == "L"]
        res = highs[-1].price if highs else None
        sup = lows[-1].price if lows else None

        best_bear = None
        bull_incoherente = False
        for count in scan_recent(pivots, params.elliott):
            try:
                r = score_confluence(
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
            if r.signal_direction == "bearish":
                if best_bear is None or r.score > best_bear.score:
                    best_bear = r
            elif r.zone and r.signal_invalidation >= r.zone[0]:
                bull_incoherente = True

        if best_bear is not None:
            anula = best_bear.signal_invalidation
            info = {
                "label": "lectura bajista",
                "cls": "bear",
                "text": (
                    f"La mejor lectura de Elliott ahora es <b>bajista</b> "
                    f"({_esc(_hypothesis_label(best_bear.count.hypothesis))} al alza que "
                    f"parece agotada) — y este sistema solo compra, así que toca esperar. "
                    f"La lectura bajista <b>se anula si el precio supera "
                    f"{_fmt(anula)}</b>: ahí el mapa se redibujaría al alza."
                ),
                "anula": anula,
            }
        elif bull_incoherente:
            info = {
                "label": "no operable",
                "cls": "non",
                "text": (
                    "Hay una lectura alcista, pero su zona de compra queda por encima de "
                    "su propio stop: <b>geometría no operable</b> (comprar ahí ya "
                    "invalidaría el conteo). Se espera a que se forme una estructura "
                    "nueva."
                ),
                "anula": None,
            }
        else:
            info = {
                "label": "lateral",
                "cls": "non",
                "text": (
                    "Sin patrón de Elliott válido ahora mismo: movimiento lateral o "
                    "ruido. Los niveles del último swing marcan el rango a vigilar."
                ),
                "anula": None,
            }

        price = float(structure["close"].iloc[-1])
        out[base] = {
            "base": base,
            "symbol": symbol,
            "price": price,
            "res": res,
            "sup": sup,
            **info,
        }
    return out


def build_levels(cfg: Config) -> dict[str, dict[str, float]]:
    """Soporte y resistencia del último swing, para TODAS las monedas.

    La resistencia es la «zona de venta rápida»: el techo técnico más cercano
    donde tiene sentido recoger beneficios si no se quiere esperar al 2R.
    """
    cache = ParquetCache(cfg.path("paths.cache_dir"))
    params = PipelineParams.from_config(cfg)
    out: dict[str, dict[str, float]] = {}
    for base in cfg.bases:
        _, structure, _ = _read_pair(cfg, cache, base, params)
        if structure.empty:
            continue
        pivots = detect_swings(structure, **params.swing)
        highs = [p.price for p in pivots if p.kind == "H"]
        lows = [p.price for p in pivots if p.kind == "L"]
        info: dict[str, float] = {}
        if highs:
            info["res"] = highs[-1]
        if lows:
            info["sup"] = lows[-1]
        if info:
            out[base] = info
    return out


def build_direction(cfg: Config) -> list[dict[str, Any]]:
    """Panel «¿sube o baja?»: estado actual + frecuencias históricas a 24h."""
    cache = ParquetCache(cfg.path("paths.cache_dir"))
    params = PipelineParams.from_config(cfg)
    rows: list[dict[str, Any]] = []
    for base in cfg.bases:
        _, structure, _ = _read_pair(cfg, cache, base, params)
        if structure.empty:
            continue
        stats = compute_direction_stats(structure)
        if stats is None:
            continue
        rows.append({"base": base, "stats": stats})
    # Primero lo más decidido: donde el histórico más se aleja del 50/50.
    rows.sort(key=lambda r: -abs(r["stats"].p_up - 0.5))
    return rows


def _direction_html(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    filas = []
    for r in rows:
        s = r["stats"]
        if not s.reliable:
            veredicto = f'<span class="res flat">muestra insuficiente (n={s.n})</span>'
        elif s.p_up >= 0.52:
            veredicto = f'<span class="res win">▲ subió el {s.p_up:.0%}</span>'
        elif s.p_up <= 0.48:
            veredicto = f'<span class="res loss">▼ bajó el {1 - s.p_up:.0%}</span>'
        else:
            veredicto = '<span class="res flat">≈ 50% — moneda al aire</span>'
        filas.append(
            f"<tr><td><b>{_esc(r['base'])}</b></td>"
            f"<td>{_esc(s.estado_txt)}</td>"
            f"<td>{veredicto}</td>"
            f"<td>{s.avg_move * 100:+.2f}%</td>"
            f"<td>{s.n}</td></tr>"
        )
    return f"""
<h2 id="sec-dir">⚡ ¿Sube o baja? — histórico a 24 h</h2>
<p style="color:var(--muted);font-size:.88rem">Cada moneda se clasifica por su estado
actual (tendencia larga, momentum de 24 h y zona de RSI) y se busca <b>ese mismo
estado en todo su histórico de velas de 4 h</b>: el porcentaje dice cuántas veces el
precio estaba más alto 24 horas después. Es <b>frecuencia histórica, no predicción</b>
— nadie sabe la próxima vela; un ≈50% significa literalmente moneda al aire, y los
casos se solapan entre sí, así que la muestra efectiva es menor que n. Ordenado de
más a menos decidido. Para niveles concretos, mira la tarjeta de cada moneda.</p>
<div class="scroll" style="overflow-x:auto">
<table>
  <tr><th>moneda</th><th>estado actual</th><th>¿24 h después?</th>
    <th>media 24 h</th><th>casos (n)</th></tr>
  {"".join(filas)}
</table>
</div>"""


DCA_RETR = (0.618, 0.786)  # retroceso profundo del ciclo completo


def build_dca(cfg: Config) -> list[dict[str, Any]]:
    """Zona DCA por moneda: banda 0.618-0.786 de retroceso del ciclo completo.

    Marco técnico clásico de acumulación a LARGO plazo (meses/años), calculado
    sobre el gráfico diario entre el mínimo y el máximo de todo el histórico
    disponible. NO está validado por el backtest — es contexto para la
    estrategia de acumulación, deliberadamente separada del swing.
    """
    cache = ParquetCache(cfg.path("paths.cache_dir"))
    params = PipelineParams.from_config(cfg)
    rows: list[dict[str, Any]] = []

    for base in cfg.bases:
        _, structure, context = _read_pair(cfg, cache, base, params)
        if context.empty or structure.empty:
            continue
        high = float(context["high"].max())
        low = float(context["low"].min())
        span = high - low
        if span <= 0:
            continue
        upper = high - span * DCA_RETR[0]
        lower = high - span * DCA_RETR[1]
        price = float(structure["close"].iloc[-1])

        if price > upper:
            estado, cls = f"{(price / upper - 1) * 100:.0f}% por encima — esperar", "flat"
        elif price >= lower:
            estado, cls = "DENTRO de la zona", "win"
        else:
            estado, cls = f"{(1 - price / lower) * 100:.0f}% por debajo", "open"

        rows.append(
            {
                "base": base,
                "lower": lower,
                "upper": upper,
                "price": price,
                "estado": estado,
                "cls": cls,
            }
        )
    return rows


def _dca_html(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    filas = "".join(
        f"<tr><td><b>{_esc(r['base'])}</b></td>"
        f"<td>{_fmt(r['lower'])} – {_fmt(r['upper'])}</td>"
        f"<td>{_fmt(r['price'])}</td>"
        f'<td><span class="res {r["cls"]}">{_esc(r["estado"])}</span></td></tr>'
        for r in rows
    )
    return f"""
<h2 id="sec-dca">🐢 Zona DCA — acumulación a largo plazo (meses/años)</h2>
<p style="color:var(--muted);font-size:.88rem">Estrategia <b>separada</b> del swing de
arriba: banda de retroceso profundo (0.618–0.786) de todo el ciclo, donde
históricamente se acumula <b>por tramos</b> pensando en años, sin stop y solo si se
cree en el activo a largo. <b>No está validada por el backtest</b> — es un marco
técnico clásico, no una señal. Regla de higiene: dinero y decisiones aparte del
swing; nunca convertir un swing fallido en "DCA".</p>
<div class="scroll" style="overflow-x:auto">
<table>
  <tr><th>moneda</th><th>zona DCA</th><th>precio ahora</th><th>estado</th></tr>
  {filas}
</table>
</div>"""


# ---------------------------------------------------------------------------
# Tarjetas
# ---------------------------------------------------------------------------


def _projection_html(proj: dict[str, Any] | None) -> str:
    """Escenarios históricos del plan: frecuencias del backtest, no predicción."""
    if not proj:
        return ""
    t, s, o = float(proj["target_pct"]), float(proj["stop_pct"]), float(proj["timeout_pct"])
    n = int(proj["n_trades"])
    media_tiempo = f"{float(proj['timeout_avg_pct']):+.1f}"
    return f"""
<div class="proj">
  <div class="proj-t">🔮 Posible siguiente movimiento (histórico de {n} operaciones)</div>
  <div class="probbar">
    <span class="pb win" style="width:{t:.1f}%"></span>
    <span class="pb flat" style="width:{o:.1f}%"></span>
    <span class="pb loss" style="width:{s:.1f}%"></span>
  </div>
  <div class="proj-leg">
    <span><b class="c-green">▲ {t:.0f}%</b> llegó a la venta objetivo (+2R)</span>
    <span><b class="c-mut">◼ {o:.0f}%</b> cerró por tiempo (media {media_tiempo}%)</span>
    <span><b class="c-red">▼ {s:.0f}%</b> tocó el stop (−1R)</span>
  </div>
  <div class="proj-note">Ese reparto ganó de media {float(proj["expectancy_pct"]):+.1f}% por
  operación <b>en el periodo de desarrollo (2022–2025)</b>. No es una predicción del
  precio. El gráfico dibuja los dos caminos en línea discontinua.{_oos_note(proj)}</div>
</div>"""


def _oos_note(proj: dict[str, Any]) -> str:
    """La letra NO pequeña: qué hizo el sistema fuera de muestra."""
    oos = proj.get("out_of_sample")
    if not oos:
        return ""
    return (
        f' <b class="c-red">Aviso honesto:</b> fuera de muestra ({_esc(oos["window"])}, '
        f"{int(oos['n_trades'])} operaciones) la media fue "
        f"<b>{float(oos['expectancy_pct']):+.2f}% por operación</b> — el sistema no cubrió "
        "sus costes en ese tramo, mayormente bajista y siendo un sistema que solo compra. "
        "El 📒 forward test de abajo es el juez final."
    )


def _action_html(entry: ReportEntry, price_now: float, target: float | None) -> str:
    """La pregunta que responde la tarjeta: ¿y yo qué hago AHORA MISMO?"""
    r = entry.result
    n = len(r.active_factors)
    if not entry.is_signal:
        return (
            '<p class="action"><b>Qué hacer ahora:</b> nada — todavía no es señal '
            f"({n} de 5 comprobaciones). Si la estructura se confirma con 3 de 5, "
            "pasará a «Señales activas» y se abrirá el aviso automático.</p>"
        )
    if r.zone is None:
        return ""
    lo, hi = r.zone
    if price_now <= r.signal_invalidation:
        return (
            '<p class="action warn"><b>Qué hacer ahora:</b> nada — esta señal ya está '
            f"<b>anulada</b>: el precio ha caído hasta su stop ({_fmt(r.signal_invalidation)}) "
            "y el plan ha muerto. No comprar «porque está más barato»: el forward test la "
            "apuntará como perdida y el siguiente análisis dirá si nace un plan nuevo.</p>"
        )
    if lo <= price_now <= hi:
        objetivo = f" y la venta objetivo en <b>{_fmt(target)}</b>" if target else ""
        return (
            '<p class="action go"><b>Qué hacer ahora:</b> el plan está activo — se puede '
            f"comprar dentro de la zona, con el stop en <b>{_fmt(r.signal_invalidation)}</b>"
            f"{objetivo}. Nunca sin stop.</p>"
        )
    if price_now > hi:
        return (
            '<p class="action"><b>Qué hacer ahora:</b> no comprar persiguiendo el precio. '
            f"Dos opciones sanas: dejar una <b>orden límite</b> dentro de la zona "
            f"({_fmt(lo)} – {_fmt(hi)}) por si el precio la visita, o dejarla pasar — "
            "cada 4 h se recalculan planes nuevos.</p>"
        )
    return (
        '<p class="action warn"><b>Qué hacer ahora:</b> nada — el precio está entre la zona '
        f"y el stop. Si pierde <b>{_fmt(r.signal_invalidation)}</b> la señal queda anulada; "
        "comprar aquí es arriesgar sin plan.</p>"
    )


def _card(
    entry: ReportEntry,
    has_chart: bool,
    current_price: float | None = None,
    proj: dict[str, Any] | None = None,
    res: float | None = None,
) -> str:
    r = entry.result
    base = r.symbol.split("/")[0]
    target = _target_for(entry)
    price_now = current_price if current_price is not None else r.price

    levels = [
        f'<div class="level"><div class="lab">Precio ahora</div>'
        f'<div class="val" id="now-{_esc(base)}">{_fmt(price_now)}</div></div>'
    ]

    # Distancia del precio a la zona de compra, en cristiano.
    zona_txt = ""
    if r.zone:
        lo, hi = r.zone
        if lo <= price_now <= hi:
            zona_txt = '<span class="inzone">✅ El precio está DENTRO de la zona de compra</span>'
        elif price_now > hi:
            pct = (price_now / hi - 1) * 100
            zona_txt = (
                f"El precio está un <b>{pct:.1f}% por encima</b> de la zona de compra "
                "— tocaría esperar a que baje"
            )
        else:
            pct = (1 - price_now / lo) * 100
            zona_txt = (
                f"⚠️ El precio está un <b>{pct:.1f}% por debajo</b> de la zona "
                "— cerca del stop, prudencia"
            )
    if r.zone:
        levels.append(
            f'<div class="level buy"><div class="lab">Zona de compra · swing</div>'
            f'<div class="val">{_fmt(r.zone[0])} – {_fmt(r.zone[1])}</div></div>'
        )
    if target is not None:
        levels.append(
            f'<div class="level target"><div class="lab">Zona de venta · objetivo 2R</div>'
            f'<div class="val">{_fmt(target)}</div></div>'
        )
    # Venta rápida: la resistencia del último swing, para quien no quiera
    # esperar al 2R. Solo tiene sentido si queda por encima del precio.
    if res is not None and res > price_now and (target is None or res < target):
        levels.append(
            f'<div class="level target"><div class="lab">Venta rápida · resistencia</div>'
            f'<div class="val">{_fmt(res)}</div></div>'
        )
    levels.append(
        f'<div class="level stop"><div class="lab">Stop</div>'
        f'<div class="val">{_fmt(r.signal_invalidation)}</div></div>'
    )

    if entry.is_signal:
        badge = '<span class="badge long">COMPRA</span>'
        card_class = "card signal"
    elif len(r.active_factors) >= r.min_active_factors:
        # Cumple el mínimo AHORA (re-evaluado al precio actual), pero la señal
        # validada solo se emite cuando una estructura se CONFIRMA cumpliéndolo.
        badge = '<span class="badge hot">⚡ cumple 3/5 ahora</span>'
        card_class = "card"
    else:
        badge = ""
        card_class = "card"

    n_activos = len(r.active_factors)
    activos = ", ".join(_factor_label(f.name) for f in r.active_factors) or "ninguna"
    detalles = "".join(
        f"<li><b>{_esc(_factor_label(f.name))}</b>: {_esc(f.detail)}</li>" for f in r.factors
    )
    factores_tabla = "".join(
        f"<tr><td>{_esc(_factor_label(f.name))}</td><td>{f.score:.2f}</td>"
        f"<td>{'<span class=ok>✅</span>' if f.active else '—'}</td></tr>"
        for f in r.factors
    )
    ambiguo = " · la estructura admite otra lectura (ver detalle)" if r.count.is_ambiguous else ""
    confirmada = f" · señal confirmada el {r.timestamp:%d-%m %H:%M} UTC" if entry.is_signal else ""

    chart_html = (
        f'<div class="tvchart" id="{_chart_id(r.symbol)}"></div>'
        f'<p class="tvlink"><a href="{_tradingview_url(r.symbol)}" target="_blank" '
        f'rel="noopener">ver {_esc(base)} en TradingView ↗</a></p>'
        if has_chart
        else ""
    )

    zona_html = f'<p class="meta2" id="zt-{_esc(base)}">{zona_txt}</p>' if zona_txt else ""
    accion_html = _action_html(entry, price_now, target)
    proj_html = _projection_html(proj) if target is not None else ""

    return f"""
<div class="{card_class}" id="card-{_esc(base)}">
  <h3><span class="mono" style="{_mono_style(base)}">{_esc(base[:1])}</span> {_esc(base)} {badge}
    <span class="badge score">{n_activos} de 5 comprobaciones a favor</span>
  </h3>
  <p class="meta">Lectura: <b>{_esc(_hypothesis_label(r.count.hypothesis))}</b>
    · a favor: {_esc(activos)}
    · se necesitan 3 de 5 para señal de compra{confirmada}{ambiguo}</p>
  {zona_html}
  {accion_html}
  {chart_html}
  <div class="levels">{"".join(levels)}</div>
  {proj_html}
  <details><summary>ver las 5 comprobaciones</summary>
    <table><tr><th>comprobación</th><th>puntuación (0–1)</th><th>a favor</th></tr>
    {factores_tabla}</table>
    <ul>{detalles}</ul>
  </details>
</div>"""


def _watch_card(info: dict[str, Any], has_chart: bool) -> str:
    base = info["base"]
    chart_html = (
        f'<div class="tvchart" id="{_chart_id(info["symbol"])}"></div>'
        f'<p class="tvlink"><a href="{_tradingview_url(info["symbol"])}" target="_blank" '
        f'rel="noopener">ver {_esc(base)} en TradingView ↗</a></p>'
        if has_chart
        else ""
    )
    levels = [
        f'<div class="level"><div class="lab">Precio ahora</div>'
        f'<div class="val" id="now-{_esc(base)}">{_fmt(info["price"])}</div></div>'
    ]
    if info.get("sup") is not None:
        levels.append(
            f'<div class="level target"><div class="lab">Soporte clave</div>'
            f'<div class="val">{_fmt(info["sup"])}</div></div>'
        )
    if info.get("res") is not None:
        levels.append(
            f'<div class="level stop"><div class="lab">Resistencia clave</div>'
            f'<div class="val">{_fmt(info["res"])}</div></div>'
        )
    if info.get("anula") is not None:
        levels.append(
            f'<div class="level buy"><div class="lab">Se anula lo bajista ↑</div>'
            f'<div class="val">{_fmt(info["anula"])}</div></div>'
        )
    if info["cls"] == "bear":
        accion = (
            '<p class="action warn"><b>Qué hacer ahora:</b> esperar fuera del mercado — '
            "ni comprar (sería contra la lectura) ni ponerse corto (perdía en las "
            f"pruebas). Solo vigilar <b>{_fmt(info['anula'])}</b>: si lo supera, el mapa "
            "se redibuja al alza.</p>"
        )
    else:
        accion = (
            '<p class="action"><b>Qué hacer ahora:</b> nada — no hay estructura operable. '
            "El escáner revisa cada 4 h y esta tarjeta cambiará sola cuando la haya.</p>"
        )
    return f"""
<div class="card" id="card-{_esc(base)}">
  <h3><span class="mono" style="{_mono_style(base)}">{_esc(base[:1])}</span> {_esc(base)}
    <span class="badge {"hot" if info["cls"] == "bear" else "score"}">{_esc(info["label"])}</span>
  </h3>
  <p class="meta2">{info["text"]}</p>
  {accion}
  {chart_html}
  <div class="levels">{"".join(levels)}</div>
</div>"""


LEGEND = """
<details><summary>📖 Cómo leer esta página</summary>
<dl class="legend">
  <dt>Los precios están en dólares</dt>
  <dd>Cotizaciones de Binance contra USDT, un "dólar digital" que vale lo mismo que
  un dólar estadounidense. Cuando pone BTC 64.665, son ~64.665 $.</dd>
  <dt>El gráfico (interactivo)</dt>
  <dd>Velas de 4 horas del último mes y medio: arrastra para moverte y usa la rueda o
  el gesto de pellizcar para hacer zoom. La línea azul es la estructura de ondas de
  Elliott detectada. Las líneas horizontales marcan la <b>zona de compra</b> (azul),
  el <b>stop</b> (rojo: si el precio cae ahí, la idea ha fallado) y el
  <b>objetivo</b> (verde: gana el doble de lo que arriesga el stop, "2R"). El enlace
  de debajo abre la misma moneda en TradingView.</dd>
  <dt>¿Qué tipo de operativa es?</dt>
  <dd><b>Compra al contado (spot)</b>: comprar la moneda y ya está. Sin apalancamiento,
  sin margin y sin futuros. Cuando aparece una señal, las dos formas razonables de
  ejecutarla a mano son: comprar a mercado en ese momento (así se validó el sistema
  en el backtest) o dejar una orden límite dentro de la zona de compra por si el
  precio la visita. El stop se coloca como orden stop-loss de venta. El sistema
  nunca toca tu exchange: todas las órdenes las pones tú.</dd>
  <dt>¿Qué es el objetivo "2× riesgo" (2R)?</dt>
  <dd>R = lo que arriesgas, la distancia entre tu entrada y el stop. Ejemplo: compras
  a 100 con stop en 95 → arriesgas 5 por unidad (eso es 1R). El objetivo está al
  doble: 100 + 2×5 = <b>110</b>. Si sale mal pierdes 5; si sale bien ganas 10. Con
  esa relación basta acertar algo más de 1 de cada 3 veces para no perder dinero —
  es la regla de salida con la que se validó el sistema.</dd>
  <dt>¿Y la zona DCA?</dt>
  <dd>Es la <b>otra</b> estrategia: acumulación a meses/años. La banda es el retroceso
  profundo (0.618–0.786) de todo el ciclo en el gráfico diario — donde históricamente
  se compra por tramos, sin stop, solo si crees en el activo a años vista. No está
  validada por el backtest: es un marco técnico clásico, no una señal. Nunca mezclar
  con el swing: dinero y decisiones separados.</dd>
  <dt>¿A qué plazo son las señales?</dt>
  <dd><b>Corto plazo: swing de 2 a 5 días.</b> Así se validó el sistema: la operación
  se cierra al tocar el objetivo (2R), el stop, o como máximo a los 5 días (30 velas
  de 4h); la duración media del backtest fue ~3 días. Las zonas de compra caducan:
  se recalculan en cada análisis. Esto NO es inversión a largo plazo — acumular
  pensando en meses o años es otra estrategia, con otros niveles y otro dinero, y
  conviene no mezclarlas (convertir una señal que tocó su stop en "inversión a
  largo" es la forma clásica de arruinar ambas).</dd>
  <dt>¿Qué hago si el precio NO está en la zona de compra?</dt>
  <dd>Cada tarjeta lo dice en su caja "Qué hacer ahora", pero la regla general es:
  <b>si está por encima de la zona, no perseguir</b> — o dejas una orden límite dentro
  de la zona por si el precio la visita, o la dejas pasar (cada 4 h salen planes
  nuevos). <b>Si está entre la zona y el stop, nada</b>: demasiado tarde para el plan.
  Comprar fuera de la zona rompe la relación riesgo/beneficio con la que se validó
  el sistema.</dd>
  <dt>¿Dónde vendo? ¿Qué es la "venta rápida"?</dt>
  <dd>Cada tarjeta con plan muestra hasta dos niveles de venta: la <b>zona de venta ·
  objetivo 2R</b> (la salida con la que se validó el sistema, gana el doble de lo que
  arriesga) y la <b>venta rápida · resistencia</b>, el techo técnico más cercano — el
  último máximo del swing. Para trading más ágil se puede vender ahí (o parcial: la
  mitad en la resistencia y el resto al 2R), sabiendo que salir antes del 2R
  <b>reduce la esperanza con la que se validó el sistema</b>: es un intercambio de
  beneficio por velocidad, no una mejora gratis. El stop no se negocia en ninguna de
  las dos variantes.</dd>
  <dt>¿Qué es el panel "¿Sube o baja?"</dt>
  <dd>Una tabla pensada para responder rápido: clasifica el estado actual de cada
  moneda con tres variables clásicas (tendencia larga, momentum de 24 h, zona de RSI)
  y cuenta, en todo su histórico, qué pasó 24 horas después en ese mismo estado.
  <b>Es frecuencia histórica, no una predicción</b>: 55% significa "ventaja pequeña",
  no certeza; ≈50% es moneda al aire, y conviene decirlo: la mayoría del tiempo el
  mercado a 24 h es casi moneda al aire. Este panel es descriptivo y NO forma parte
  del sistema de señales validado.</dd>
  <dt>¿Qué es "posible siguiente movimiento"?</dt>
  <dd>No es una predicción — nadie sabe el siguiente movimiento. Es la <b>frecuencia
  histórica</b>: de las operaciones del backtest (2022–2025), qué porcentaje llegó al
  objetivo, cuál tocó el stop y cuál cerró por tiempo. El gráfico dibuja los dos
  caminos (a objetivo y a stop) en línea discontinua con esos porcentajes. Sirve
  para calibrar expectativas: incluso haciéndolo todo bien, el stop salta 1 de cada
  3 veces — por eso el objetivo gana el doble de lo que arriesga el stop.</dd>
  <dt>¿Qué hago con una moneda en "lectura bajista"?</dt>
  <dd><b>Esperar.</b> Ni comprar (sería contra la lectura) ni vender en corto (los
  cortos perdían en las pruebas). Solo vigilar el nivel "se anula lo bajista": si el
  precio lo supera, el mapa se redibuja y con el tiempo puede aparecer una jugada
  alcista. Esa vigilancia la hace la web sola cada 4 horas.</dd>
  <dt>Los estados de cada moneda</dt>
  <dd><b>SEÑAL</b>: compra activa validada. <b>radar</b>: estructura alcista con sus
  niveles, pero faltan comprobaciones. <b>lectura bajista</b>: la mejor lectura de
  Elliott apunta abajo — su tarjeta dice en qué nivel se anularía. <b>no operable</b>:
  hay lectura alcista pero su geometría no permite un trade sano. <b>lateral</b>: sin
  patrón claro; se muestran soporte y resistencia del último swing.</dd>
  <dt>Señal de compra vs radar</dt>
  <dd>El sistema hace 5 comprobaciones sobre cada moneda (precio en nivel Fibonacci,
  divergencia del RSI, ruptura en el gráfico diario, volumen coherente y tendencia
  diaria a favor). Con <b>3 o más a favor</b> se convierte en <b>señal de compra</b>
  (tarjeta de borde verde) — es la regla que se validó en el backtest. Con menos, la
  moneda queda <b>en el radar</b>: se ven sus niveles pero aún no es momento. Solo
  hay compras: las apuestas a la baja perdían dinero en las pruebas.</dd>
  <dt>Las lecturas</dt>
  <dd><b>corrección terminada</b>: el precio bajó en 3 tramos y parece haber acabado;
  lo esperable sería que la subida se reanude. <b>ciclo de 5 ondas completo</b>: un
  movimiento entero según Elliott, se espera giro. <b>impulso en construcción</b>: una
  subida a medio hacer.</dd>
</dl>
</details>"""


CHART_SCRIPT = """
<script>
(function () {
  if (typeof LightweightCharts === "undefined") return;
  var css = getComputedStyle(document.documentElement);
  var v = function (name) { return css.getPropertyValue(name).trim(); };

  Object.keys(EHS_DATA).forEach(function (symbol) {
    var d = EHS_DATA[symbol];
    var el = document.getElementById("chart-" + symbol.replace("/", "-"));
    if (!el || !d.candles || d.candles.length < 2) return;

    var chart = LightweightCharts.createChart(el, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: v("--muted") },
      grid: {
        vertLines: { color: v("--border") },
        horzLines: { color: v("--border") },
      },
      rightPriceScale: { borderColor: v("--border") },
      timeScale: { borderColor: v("--border"), timeVisible: true },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });

    var candles = chart.addCandlestickSeries({
      upColor: v("--green"), downColor: v("--red"),
      wickUpColor: v("--green"), wickDownColor: v("--red"),
      borderVisible: false,
      priceFormat: { type: "price", precision: d.precision || 2,
                     minMove: d.minMove || 0.01 },
    });
    candles.setData(d.candles);
    window.EHS_SERIES = window.EHS_SERIES || {};
    window.EHS_SERIES[symbol] = candles;
    window.EHS_LAST = window.EHS_LAST || {};
    window.EHS_LAST[symbol] = d.candles[d.candles.length - 1].time;

    if (d.labels && d.labels.length) {
      candles.setMarkers(d.labels.slice().sort(function (a, b) {
        return a.time - b.time;
      }).map(function (m) {
        return { time: m.time, position: m.pos, color: v("--accent"),
                 shape: "circle", size: 0.1, text: m.text };
      }));
    }

    if (d.pivots && d.pivots.length >= 2) {
      var zigzag = chart.addLineSeries({
        color: v("--accent"), lineWidth: 2,
        priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      zigzag.setData(d.pivots);
    }

    var line = function (price, color, title, style, axisLabel) {
      if (price === null || price === undefined) return;
      candles.createPriceLine({
        price: price, color: color, lineWidth: 1,
        lineStyle: style, axisLabelVisible: axisLabel !== false, title: title,
      });
    };
    var dashed = LightweightCharts.LineStyle.Dashed;
    var solid = LightweightCharts.LineStyle.Solid;
    var proj = (typeof EHS_PROJ !== "undefined") ? EHS_PROJ : null;
    var pct = function (x) { return " · " + Math.round(x) + "% histórico"; };
    if (d.zone) {
      line(d.zone[0], v("--accent"), "zona compra", solid);
      line(d.zone[1], v("--accent"), "", solid, false);
    }
    line(d.stop, v("--red"),
         proj && d.target ? "stop" + pct(proj.stop_pct) : "stop", dashed);
    line(d.target, v("--green"),
         proj ? "objetivo 2R" + pct(proj.target_pct) : "objetivo 2R", dashed);
    if (d.hlines) {
      d.hlines.forEach(function (h) { line(h.p, v(h.c), h.label, dashed); });
    }

    // Proyección: los dos caminos posibles del plan, dibujados hacia delante
    // desde la última vela (duración típica del backtest, ~15 velas de 4h).
    var hasProj = proj && d.target !== null && d.stop !== null && d.candles.length;
    if (hasProj) {
      var lastC = d.candles[d.candles.length - 1];
      var horizon = lastC.time + 15 * 14400;
      [[d.target, "--green"], [d.stop, "--red"]].forEach(function (p) {
        var s = chart.addLineSeries({
          color: v(p[1]), lineWidth: 1,
          lineStyle: LightweightCharts.LineStyle.Dashed,
          priceLineVisible: false, lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        s.setData([{ time: lastC.time, value: lastC.close },
                   { time: horizon, value: p[0] }]);
      });
    }

    // Vista inicial: las últimas ~90 velas (15 días); el resto, con scroll.
    var n = d.candles.length;
    if (n > 95) {
      chart.timeScale().setVisibleLogicalRange({ from: n - 90, to: n + (hasProj ? 17 : 3) });
    } else {
      chart.timeScale().fitContent();
    }
  });
})();
</script>"""


LIVE_SCRIPT = """
<script>
(function () {
  if (typeof EHS_LIVE === "undefined") return;
  function fmt(v) {
    if (v >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
    if (v >= 1 || v <= 0) return v.toFixed(2);
    var d = Math.min(10, -Math.floor(Math.log10(v)) + 3);
    return v.toFixed(d);
  }
  function zoneText(px, zone) {
    var lo = zone[0], hi = zone[1];
    if (px >= lo && px <= hi)
      return '<span class="inzone">✅ El precio está DENTRO de la zona de compra</span>';
    if (px > hi)
      return "El precio está un <b>" + ((px / hi - 1) * 100).toFixed(1) +
        "% por encima</b> de la zona de compra — tocaría esperar a que baje";
    return "⚠️ El precio está un <b>" + ((1 - px / lo) * 100).toFixed(1) +
      "% por debajo</b> de la zona — cerca del stop, prudencia";
  }
  function setText(el, text) {
    // Devuelve true si el valor cambió, y lo resalta un instante.
    if (!el) return false;
    if (el.textContent === text) return false;
    el.textContent = text;
    el.classList.remove("flash");
    void el.offsetWidth;
    el.classList.add("flash");
    return true;
  }
  function refresh() {
    var jobs = EHS_LIVE.map(function (o) {
      var pair = o.sym.replace("/", "");
      return fetch("https://data-api.binance.vision/api/v3/klines?symbol=" + pair +
            "&interval=4h&limit=7")
        .then(function (r) { return r.json(); })
        .then(function (rows) {
          if (!rows || !rows.length) return false;
          var px = parseFloat(rows[rows.length - 1][4]);
          setText(document.getElementById("now-" + o.base), fmt(px));
          setText(document.getElementById("ov-" + o.base), fmt(px));
          if (rows.length >= 7) {
            var prev = parseFloat(rows[rows.length - 7][4]);
            var chg = document.getElementById("chg-" + o.base);
            if (chg && prev > 0) {
              var p = (px / prev - 1) * 100;
              chg.textContent = (p >= 0 ? "▲" : "▼") + Math.abs(p).toFixed(1) + "%";
              chg.className = "chg " + (p >= 0 ? "up" : "dn");
              chg.title = "variación en 24 h";
            }
          }
          var zt = document.getElementById("zt-" + o.base);
          if (zt && o.zone) zt.innerHTML = zoneText(px, o.zone);
          if (window.EHS_SERIES && window.EHS_SERIES[o.sym]) {
            rows.forEach(function (k) {
              var t = Math.floor(k[0] / 1000);
              if (t >= window.EHS_LAST[o.sym]) {
                window.EHS_SERIES[o.sym].update(
                  { time: t, open: +k[1], high: +k[2], low: +k[3], close: +k[4] });
                window.EHS_LAST[o.sym] = t;
              }
            });
          }
          return true;
        })
        .catch(function () { return false; });
    });
    return Promise.all(jobs);
  }
  var btn = document.getElementById("btn-live");
  function setLoading(on) {
    if (!btn) return;
    btn.disabled = on;
    btn.innerHTML = on
      ? '<span class="spinner"></span> Actualizando…'
      : "🔄 Actualizar precios";
  }
  function run() {
    if (btn && btn.disabled) return;
    setLoading(true);
    // Mínimo ~0.6 s de spinner: si no, con buena conexión ni se ve.
    var minimo = new Promise(function (r) { setTimeout(r, 600); });
    Promise.all([refresh(), minimo]).then(function (res) {
      setLoading(false);
      var ok = res[0].filter(Boolean).length;
      var st = document.getElementById("live-stamp");
      if (!st) return;
      if (ok === 0) {
        st.textContent = "⚠ sin conexión con Binance — precios no actualizados";
      } else {
        st.textContent = "✓ " + ok + " monedas actualizadas a las " +
          new Date().toTimeString().slice(0, 5) +
          " · el análisis completo se rehace solo cada 4 h";
      }
    });
  }
  var age = document.getElementById("an-age");
  if (age && typeof EHS_GEN !== "undefined") {
    var horas = (Date.now() / 1000 - EHS_GEN) / 3600;
    if (horas >= 1) age.textContent = " (hace " + horas.toFixed(0) + " h)";
    if (horas > 6) {
      age.innerHTML = ' <b style="color:var(--red)">⚠ el análisis lleva ' +
        horas.toFixed(0) + ' h sin renovarse</b>';
    }
  }

  if (btn) btn.addEventListener("click", run);
  run();
})();
</script>"""


def _forward_test_html(log: list[LoggedSignal]) -> str:
    """El registro del forward test: la libreta que ya no hay que llevar a mano."""
    if not log:
        return (
            '<p style="color:var(--muted)">Aún no se ha emitido ninguna señal desde que '
            "el registro está activo. Cada señal futura quedará apuntada aquí "
            "automáticamente, con su desenlace calculado con las reglas del backtest "
            "(entrada en la vela siguiente, stop, objetivo 2R, 30 velas máximo).</p>"
        )

    stats = summary_stats(log)
    cerr = stats["closed"]
    resumen = (
        f'<div class="ftstats">'
        f'<span>señales: <b>{stats["total"]}</b></span>'
        f"<span>cerradas: <b>{cerr}</b></span>"
        f'<span>ganadas: <b>{stats["wins"]}</b> · perdidas: <b>{stats["losses"]}</b></span>'
        f'<span>resultado acumulado: <b>{stats["total_r"]:+.1f}R</b></span>'
        f"</div>"
    )

    filas = []
    for sig in log[:40]:
        fecha = pd.Timestamp(sig.timestamp).strftime("%d-%m-%Y %H:%M")
        base = sig.symbol.split("/")[0]
        if sig.outcome == "objetivo":
            res = '<span class="res win">✅ objetivo +2R</span>'
        elif sig.outcome == "stop":
            res = '<span class="res loss">✖ stop −1R</span>'
        elif sig.outcome == "tiempo":
            pct = f"{(sig.result_pct or 0) * 100:+.1f}%"
            res = f'<span class="res flat">tiempo {pct}</span>'
        elif sig.outcome == "no operable":
            res = '<span class="res flat">no operable — descartada</span>'
        else:
            pct = f"{(sig.result_pct or 0) * 100:+.1f}%"
            res = f'<span class="res open">en curso {pct}</span>'
        filas.append(
            f"<tr><td>{fecha}</td><td><b>{_esc(base)}</b></td>"
            f"<td>{_fmt(sig.entry) if sig.entry else _fmt(sig.price)}</td>"
            f"<td>{_fmt(sig.stop)}</td>"
            f"<td>{_fmt(sig.target) if sig.target else '—'}</td>"
            f"<td>{res}</td></tr>"
        )

    return f"""{resumen}
<div class="scroll" style="overflow-x:auto">
<table>
  <tr><th>señal</th><th>moneda</th><th>entrada</th><th>stop</th>
    <th>objetivo</th><th>resultado</th></tr>
  {"".join(filas)}
</table>
</div>
<p style="color:var(--muted);font-size:.82rem">Desenlaces calculados con las mismas
reglas que el backtest. El fichero de registro se guarda en el historial de git con
fecha: no se puede reescribir a posteriori.</p>"""


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------


def render_html(
    entries: list[ReportEntry],
    warnings: list[str],
    *,
    cfg: Config,
    now: pd.Timestamp,
    chart_data: dict[str, dict[str, Any]] | None = None,
    overview: list[dict[str, Any]] | None = None,
    signals_log: list[LoggedSignal] | None = None,
    watch: dict[str, dict[str, Any]] | None = None,
    dca: list[dict[str, Any]] | None = None,
    direction: list[dict[str, Any]] | None = None,
    levels: dict[str, dict[str, float]] | None = None,
) -> str:
    chart_data = chart_data or {}
    signals = [e for e in entries if e.is_signal]
    proj = cfg.get("report.projection") if cfg.has("report.projection") else None

    def _near_rank(e: ReportEntry) -> tuple:
        """Primero lo más cercano a disparar; luego, lo más cercano a su zona."""
        r = e.result
        if r.zone:
            mid = (r.zone[0] + r.zone[1]) / 2
            distance = abs(r.price - mid) / mid if mid else 9.9
        else:
            distance = 9.9
        return (-len(r.active_factors), distance)

    near = sorted((e for e in entries if not e.is_signal), key=_near_rank)

    # Resumen ejecutivo: lo primero que responde la página en una línea.
    mejor_24h = ""
    for fila in direction or []:
        s = fila["stats"]
        if s.reliable and (s.p_up >= 0.52 or s.p_up <= 0.48):
            flecha, pct = ("▲", s.p_up) if s.p_up >= 0.52 else ("▼", 1 - s.p_up)
            mejor_24h = (
                f"<span>⚡ mejor apuesta 24h: <b>{_esc(fila['base'])} {flecha} {pct:.0%}</b></span>"
            )
            break
    hero = (
        '<div class="hero">'
        f"<span>🎯 señales activas: <b>{len(signals)}</b></span>"
        f"<span>👀 en radar: <b>{len(near)}</b></span>"
        f"{mejor_24h}"
        "</div>"
    )
    vistazo = (
        '<h2 id="sec-vistazo">🧭 El mercado de un vistazo</h2>' + _overview_html(overview)
        if overview
        else ""
    )
    title = ("🎯 " + str(len(signals)) + " señal · " if signals else "") + "Elliott Hybrid Scanner"

    def last_close(symbol: str) -> float | None:
        candles = chart_data.get(symbol, {}).get("candles")
        return float(candles[-1]["close"]) if candles else None

    levels = levels or {}

    def card(e: ReportEntry) -> str:
        base = e.result.symbol.split("/")[0]
        return _card(
            e,
            e.result.symbol in chart_data,
            last_close(e.result.symbol),
            proj,
            levels.get(base, {}).get("res"),
        )

    if signals:
        cuerpo_senales = "".join(card(e) for e in signals)
    else:
        cuerpo_senales = """
<div class="empty"><b>Ahora mismo no hay señal de compra activa.</b><br>
El sistema solo dispara cuando una estructura se <b>confirma</b> con 3 de 5
comprobaciones a favor — pocas veces al mes. El radar muestra lo más cercano.</div>"""

    cuerpo_radar = (
        "".join(card(e) for e in near)
        if near
        else '<p style="color:var(--muted)">Ningún par tiene ahora mismo una estructura '
        "alcista operable.</p>"
    )

    avisos = (
        "<h2>Avisos</h2><ul>" + "".join(f"<li>{_esc(w)}</li>" for w in warnings) + "</ul>"
        if warnings
        else ""
    )

    watch = watch or {}
    if watch:
        plegadas = []
        for info in watch.values():
            resumen_niveles = " · ".join(
                f"{lab} {_fmt(info[k])}"
                for k, lab in (("sup", "sup"), ("res", "res"))
                if info.get(k) is not None
            )
            plegadas.append(
                f'<details class="wdet"><summary><b>{_esc(info["base"])}</b> '
                f'<span class="st {info["cls"]}">{_esc(info["label"])}</span> '
                f'<span class="wsum">{_esc(resumen_niveles)}</span></summary>'
                f"{_watch_card(info, info['symbol'] in chart_data)}</details>"
            )
        cuerpo_watch = (
            f'<h2 id="sec-watch">🔎 En observación ({len(watch)}) — sin jugada alcista ahora</h2>'
            '<p style="color:var(--muted);font-size:.85rem">Toca una moneda para ver su '
            "diagnóstico completo, niveles y gráfico.</p>" + "".join(plegadas)
        )
    else:
        cuerpo_watch = ""

    # Lista de símbolos para el refresco en vivo, con su zona si la tienen.
    zone_by_base: dict[str, list[float]] = {}
    for e in entries:
        b = e.result.symbol.split("/")[0]
        if b not in zone_by_base and e.result.zone:
            zone_by_base[b] = [round(e.result.zone[0], 10), round(e.result.zone[1], 10)]
    live_payload = [
        {"sym": o["symbol"], "base": o["base"], "zone": zone_by_base.get(o["base"])}
        for o in (overview or [])
        if o.get("symbol")
    ]
    if not live_payload and chart_data:
        live_payload = [
            {"sym": sym, "base": sym.split("/")[0], "zone": zone_by_base.get(sym.split("/")[0])}
            for sym in chart_data
        ]

    scripts = ""
    if chart_data:
        payload = json.dumps(chart_data, separators=(",", ":"))
        proj_js = f"var EHS_PROJ = {json.dumps(proj, separators=(',', ':'))};" if proj else ""
        scripts += (
            f"<script>var EHS_DATA = {payload};{proj_js}</script>\n"
            f'<script src="{LIGHTWEIGHT_CHARTS_CDN}"></script>\n'
            f"{CHART_SCRIPT}\n"
        )
    if live_payload:
        live_json = json.dumps(live_payload, separators=(",", ":"))
        scripts += (
            f"<script>var EHS_LIVE = {live_json};"
            f"var EHS_GEN = {int(now.timestamp())};</script>\n{LIVE_SCRIPT}"
        )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="icon" href="icon.svg" type="image/svg+xml">
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#0b0e14">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="appbar">
    <svg class="logo" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#4c8dff"/><stop offset="1" stop-color="#7c5cff"/>
      </linearGradient></defs>
      <rect width="40" height="40" rx="11" fill="url(#lg)"/>
      <path d="M7 28 L14 17 L18 22 L27 9 L30 13" fill="none" stroke="#fff"
        stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="32" cy="10.5" r="2.6" fill="#0ecb81"/>
    </svg>
    <h1>Elliott <span class="thin">Hybrid Scanner</span>
      <span class="bsub">ondas de elliott · spot · se rehace cada 4 h</span></h1>
  </header>
  <div class="updated">Análisis: {now:%d-%m-%Y %H:%M} UTC
    <span id="an-age"></span> · se rehace solo cada 4 h ·
    {_esc(", ".join(cfg.bases))} · velas de 4h</div>
  <div class="disclaimer">Herramienta informativa generada automáticamente — no es
  asesoramiento financiero ni ejecuta órdenes. Operativa de referencia: compra al
  contado (spot), sin apalancamiento. Sistema en fase de validación (forward test).</div>

  <div class="btnrow">
    <button class="btn" id="btn-live" type="button">🔄 Actualizar precios</button>
    <a class="btn sec" target="_blank" rel="noopener"
       href="https://github.com/peperonioo/elliott-hybrid-scanner/actions/workflows/daily-scan.yml">
       re-análisis completo ↗</a>
    <span class="btnhint" id="live-stamp">un toque: precios al instante desde Binance
    · el análisis completo se rehace solo cada 4 h</span>
  </div>

  <nav class="nav">
    <a href="#sec-vistazo">🧭 Vistazo</a>
    {'<a href="#sec-dir">⚡ ¿Sube o baja?</a>' if direction else ""}
    <a href="#sec-senales">🎯 Señales</a>
    <a href="#sec-radar">👀 Radar</a>
    {'<a href="#sec-watch">🔎 Observación</a>' if watch else ""}
    <a href="#sec-dca">🐢 DCA</a>
    <a href="#sec-forward">📒 Forward test</a>
    <a href="#sec-guia">📖 Guía</a>
  </nav>

  {hero}

  {vistazo}

  <div class="ghdr">🟢 Para operar — el plan validado</div>

  <h2 id="sec-senales">🎯 Señales de compra activas ({len(signals)})</h2>
  {cuerpo_senales}

  <h2 id="sec-radar">👀 En el radar ({len(near)})</h2>
  {cuerpo_radar}

  <div class="ghdr">🧠 Contexto y apuestas</div>

  {_direction_html(direction or [])}

  {cuerpo_watch}

  {_dca_html(dca or [])}

  <div class="ghdr">📚 Registro y ayuda</div>

  <h2 id="sec-forward">📒 Forward test — registro de señales</h2>
  {_forward_test_html(signals_log or [])}

  {avisos}

  <div id="sec-guia">{LEGEND}</div>

  <footer>
    <a href="https://github.com/peperonioo/elliott-hybrid-scanner">Código y metodología</a> ·
    <a href="https://github.com/peperonioo/elliott-hybrid-scanner/tree/main/reports">
    Historial de informes</a> (registro del forward test)
  </footer>

  <nav class="tabbar">
    <a href="#sec-vistazo">🧭<span>Mercado</span></a>
    <a href="#sec-senales">🎯<span>Señales</span></a>
    <a href="#sec-dir">⚡<span>24h</span></a>
    <a href="#sec-forward">📒<span>Registro</span></a>
    <a href="#sec-guia">📖<span>Guía</span></a>
  </nav>
</div>
{scripts}
</body>
</html>
"""


def write_web(cfg: Config, *, now: pd.Timestamp | None = None) -> Path:
    """Genera `docs/index.html` para GitHub Pages."""
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    entries, warnings = collect_entries(cfg)
    watch = build_watch(cfg, entries)
    dca = build_dca(cfg)
    direction = build_direction(cfg)
    levels = build_levels(cfg)
    chart_data = build_chart_data(cfg, entries, watch)
    overview = build_overview(cfg, entries, watch)

    # Forward test: registrar señales nuevas y re-evaluar desenlaces.
    cache = ParquetCache(cfg.path("paths.cache_dir"))
    params = PipelineParams.from_config(cfg)
    frames: dict[str, pd.DataFrame] = {}
    for o in overview:
        sym = o.get("symbol")
        if sym:
            _, structure, _ = _read_pair(cfg, cache, o["base"], params)
            frames[sym] = structure
    log = update_log(cfg, entries, frames, now=now)

    content = render_html(
        entries,
        warnings,
        cfg=cfg,
        now=now,
        chart_data=chart_data,
        overview=overview,
        signals_log=log,
        watch=watch,
        dca=dca,
        direction=direction,
        levels=levels,
    )

    web_dir = cfg.path("paths.web_dir")
    web_dir.mkdir(parents=True, exist_ok=True)
    path = web_dir / "index.html"
    path.write_text(content, encoding="utf-8")
    LOGGER.info("Web escrita en %s", path)
    return path
