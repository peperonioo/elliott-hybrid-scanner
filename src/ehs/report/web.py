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
from ehs.data.cache import ParquetCache
from ehs.pipeline import PipelineParams
from ehs.report.daily import ReportEntry, _read_pair, collect_entries
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
  --bg:#f6f8fa; --fg:#1f2328; --muted:#656d76; --card:#ffffff;
  --border:#d0d7de; --accent:#0969da; --green:#1a7f37; --red:#d1242f;
  --amber:#9a6700; --zone:rgba(9,105,218,.10);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg:#0d1117; --fg:#e6edf3; --muted:#8b949e; --card:#161b22;
    --border:#30363d; --accent:#4493f8; --green:#3fb950; --red:#f85149;
    --amber:#d29922; --zone:rgba(68,147,248,.12);
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:24px 16px 56px}
h1{font-size:1.45rem;margin:0}
.updated{color:var(--muted);font-size:.9rem;margin:4px 0 14px}
.disclaimer{color:var(--muted);font-size:.82rem;margin-bottom:22px}
h2{font-size:1.12rem;margin:30px 0 10px;border-bottom:1px solid var(--border);
  padding-bottom:6px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:14px 16px;margin:14px 0}
.card.signal{border-color:var(--green);border-width:2px}
.card h3{margin:0 0 6px;font-size:1rem;display:flex;flex-wrap:wrap;gap:8px;
  align-items:center}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;
  font-size:.75rem;font-weight:700}
.badge.long{background:var(--green);color:#fff}
.badge.score{background:var(--zone);color:var(--accent)}
.card .meta{color:var(--muted);font-size:.82rem;margin:0 0 8px}
.tvchart{height:300px;margin:6px 0 2px}
.tvlink{font-size:.8rem;margin:2px 0 6px}
.tvlink a{color:var(--accent);text-decoration:none}
.levels{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:8px;margin:10px 0 2px}
.level{background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:6px 10px}
.level .lab{font-size:.7rem;color:var(--muted);text-transform:uppercase;
  letter-spacing:.03em}
.level .val{font-weight:700;font-size:.95rem}
.level.buy .val{color:var(--accent)}
.level.stop .val{color:var(--red)}
.level.target .val{color:var(--green)}
table{border-collapse:collapse;width:100%;font-size:.84rem;margin:8px 0}
th,td{border:1px solid var(--border);padding:5px 9px;text-align:left}
th{background:var(--bg)}
.ok{color:var(--green);font-weight:700}
.empty{background:var(--card);border:1px dashed var(--border);border-radius:12px;
  padding:18px;text-align:center;color:var(--muted)}
.empty b{color:var(--fg)}
details{margin-top:6px}
summary{cursor:pointer;color:var(--accent);font-size:.88rem}
details ul{margin:8px 0;padding-left:18px;color:var(--muted);font-size:.86rem}
.legend{font-size:.9rem}
.legend dt{font-weight:700;margin-top:10px}
.legend dd{margin:2px 0 0 0;color:var(--muted)}
footer{margin-top:36px;color:var(--muted);font-size:.82rem;
  border-top:1px solid var(--border);padding-top:12px}
footer a{color:var(--accent)}
.ovgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
  gap:8px;margin:8px 0 4px}
.chip{background:var(--card);border:1px solid var(--border);border-radius:10px;
  padding:8px 10px;display:flex;gap:8px;align-items:center;text-decoration:none;
  color:var(--fg)}
.chip:hover{border-color:var(--accent)}
.mono{width:30px;height:30px;border-radius:50%;color:#fff;font-weight:800;
  font-size:.78rem;display:flex;align-items:center;justify-content:center;flex:none}
.chip .nm{font-weight:700;font-size:.85rem;line-height:1.2}
.chip .pr{font-size:.78rem;color:var(--muted)}
.st{font-size:.66rem;font-weight:700;border-radius:999px;padding:2px 7px;
  margin-left:auto;white-space:nowrap}
.st.sig{background:var(--green);color:#fff}
.st.rad{background:var(--zone);color:var(--accent)}
.st.non{background:var(--bg);color:var(--muted);border:1px solid var(--border)}
.meta2{font-size:.86rem;margin:0 0 6px}
.inzone{color:var(--green);font-weight:700}
.btnrow{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px}
.btn{display:inline-flex;align-items:center;gap:6px;background:var(--accent);
  color:#fff;font-weight:700;font-size:.85rem;padding:7px 14px;border-radius:8px;
  text-decoration:none}
.btn.sec{background:var(--card);color:var(--accent);border:1px solid var(--border)}
.btnhint{color:var(--muted);font-size:.75rem;align-self:center}
.card{transition:box-shadow .15s ease}
.card:hover{box-shadow:0 3px 14px rgba(0,0,0,.10)}
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
        return 2
    if v >= 1:
        return 3
    if v <= 0:
        return 2
    return min(10, -math.floor(math.log10(v)) + 3)


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


def build_chart_data(cfg: Config, entries: list[ReportEntry]) -> dict[str, dict[str, Any]]:
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
        candles = [
            {
                "time": int(ts.timestamp()),
                "open": round(float(row["open"]), 6),
                "high": round(float(row["high"]), 6),
                "low": round(float(row["low"]), 6),
                "close": round(float(row["close"]), 6),
            }
            for ts, row in window.iterrows()
        ]

        first_ts = int(window.index[0].timestamp())
        pivots = [
            {"time": int(p.timestamp.timestamp()), "value": round(p.price, 6)}
            for p in detect_swings(structure, **params.swing)
            if int(p.timestamp.timestamp()) >= first_ts
        ]

        precision = _price_precision(candles[-1]["close"]) if candles else 2
        data[r.symbol] = {
            "precision": precision,
            "minMove": round(10**-precision, 12),
            "candles": candles,
            "pivots": pivots,
            "zone": [round(r.zone[0], 6), round(r.zone[1], 6)] if r.zone else None,
            "stop": round(r.signal_invalidation, 6),
            "target": (round(_target_for(entry), 6) if _target_for(entry) is not None else None),
        }
    return data


def build_overview(cfg: Config, entries: list[ReportEntry]) -> list[dict[str, Any]]:
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
        if entry and entry.is_signal:
            state, cls = "SEÑAL", "sig"
        elif entry:
            state, cls = "radar", "rad"
        else:
            state, cls = "sin estructura", "non"
        out.append(
            {"base": base, "price": price, "state": state, "cls": cls, "link": entry is not None}
        )
    return out


def _overview_html(overview: list[dict[str, Any]]) -> str:
    chips = []
    for o in overview:
        precio = _fmt(o["price"]) if o["price"] is not None else "—"
        inner = (
            f'<span class="mono" style="{_mono_style(o["base"])}">{_esc(o["base"][:1])}</span>'
            f'<span><span class="nm">{_esc(o["base"])}</span><br>'
            f'<span class="pr">{precio}</span></span>'
            f'<span class="st {o["cls"]}">{_esc(o["state"])}</span>'
        )
        if o["link"]:
            chips.append(f'<a class="chip" href="#card-{_esc(o["base"])}">{inner}</a>')
        else:
            chips.append(f'<div class="chip">{inner}</div>')
    return '<div class="ovgrid">' + "".join(chips) + "</div>"


# ---------------------------------------------------------------------------
# Tarjetas
# ---------------------------------------------------------------------------


def _card(entry: ReportEntry, has_chart: bool, current_price: float | None = None) -> str:
    r = entry.result
    target = _target_for(entry)
    price_now = current_price if current_price is not None else r.price

    levels = [
        f'<div class="level"><div class="lab">Precio ahora</div>'
        f'<div class="val">{_fmt(price_now)}</div></div>'
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
            f'<div class="level buy"><div class="lab">Zona de compra</div>'
            f'<div class="val">{_fmt(r.zone[0])} – {_fmt(r.zone[1])}</div></div>'
        )
    levels.append(
        f'<div class="level stop"><div class="lab">Stop</div>'
        f'<div class="val">{_fmt(r.signal_invalidation)}</div></div>'
    )
    if target is not None:
        levels.append(
            f'<div class="level target"><div class="lab">Objetivo (2× riesgo)</div>'
            f'<div class="val">{_fmt(target)}</div></div>'
        )

    if entry.is_signal:
        badge = '<span class="badge long">COMPRA</span>'
        card_class = "card signal"
    else:
        badge = ""
        card_class = "card"

    base = r.symbol.split("/")[0]
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

    zona_html = f'<p class="meta2">{zona_txt}</p>' if zona_txt else ""

    return f"""
<div class="{card_class}" id="card-{_esc(base)}">
  <h3><span class="mono" style="{_mono_style(base)}">{_esc(base[:1])}</span> {_esc(base)} {badge}
    <span class="badge score">{n_activos} de 5 comprobaciones a favor</span>
  </h3>
  <p class="meta">Lectura: <b>{_esc(_hypothesis_label(r.count.hypothesis))}</b>
    · a favor: {_esc(activos)}
    · se necesitan 3 de 5 para señal de compra{confirmada}{ambiguo}</p>
  {zona_html}
  {chart_html}
  <div class="levels">{"".join(levels)}</div>
  <details><summary>ver las 5 comprobaciones</summary>
    <table><tr><th>comprobación</th><th>puntuación (0–1)</th><th>a favor</th></tr>
    {factores_tabla}</table>
    <ul>{detalles}</ul>
  </details>
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

    if (d.pivots && d.pivots.length >= 2) {
      var zigzag = chart.addLineSeries({
        color: v("--accent"), lineWidth: 2,
        priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      zigzag.setData(d.pivots);
    }

    var line = function (price, color, title, style) {
      if (price === null || price === undefined) return;
      candles.createPriceLine({
        price: price, color: color, lineWidth: 1,
        lineStyle: style, axisLabelVisible: true, title: title,
      });
    };
    var dashed = LightweightCharts.LineStyle.Dashed;
    var solid = LightweightCharts.LineStyle.Solid;
    if (d.zone) {
      line(d.zone[0], v("--accent"), "zona compra", solid);
      line(d.zone[1], v("--accent"), "", solid);
    }
    line(d.stop, v("--red"), "stop", dashed);
    line(d.target, v("--green"), "objetivo 2R", dashed);

    chart.timeScale().fitContent();
  });
})();
</script>"""


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
) -> str:
    chart_data = chart_data or {}
    signals = [e for e in entries if e.is_signal]
    near = [e for e in entries if not e.is_signal]

    def last_close(symbol: str) -> float | None:
        candles = chart_data.get(symbol, {}).get("candles")
        return float(candles[-1]["close"]) if candles else None

    def card(e: ReportEntry) -> str:
        return _card(e, e.result.symbol in chart_data, last_close(e.result.symbol))

    if signals:
        cuerpo_senales = "".join(card(e) for e in signals)
    else:
        cuerpo_senales = """
<div class="empty"><b>Hoy no hay señal de compra.</b><br>
Es lo normal (~4 señales al mes en todo el universo): el sistema solo dispara con
3 de 5 comprobaciones a favor.</div>"""

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

    scripts = ""
    if chart_data:
        payload = json.dumps(chart_data, separators=(",", ":"))
        scripts = (
            f"<script>var EHS_DATA = {payload};</script>\n"
            f'<script src="{LIGHTWEIGHT_CHARTS_CDN}"></script>\n'
            f"{CHART_SCRIPT}"
        )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Elliott Hybrid Scanner</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>📡 Elliott Hybrid Scanner</h1>
  <div class="updated">Actualizado: {now:%d-%m-%Y %H:%M} UTC · se regenera cada noche ·
    {_esc(", ".join(cfg.bases))} · 4h</div>
  <div class="disclaimer">Herramienta informativa generada automáticamente — no es
  asesoramiento financiero ni ejecuta órdenes. Operativa de referencia: compra al
  contado (spot), sin apalancamiento. Sistema en fase de validación (forward test).</div>

  <div class="btnrow">
    <a class="btn" target="_blank" rel="noopener"
       href="https://github.com/peperonioo/elliott-hybrid-scanner/actions/workflows/daily-scan.yml">
       🔄 Actualizar ahora</a>
    <span class="btnhint">se abre GitHub → botón "Run workflow" → espera ~4 min →
    recarga esta página (necesita tu sesión de GitHub)</span>
  </div>

  {"<h2>🧭 El mercado de un vistazo</h2>" + _overview_html(overview) if overview else ""}

  <h2>🎯 Señales de compra activas ({len(signals)})</h2>
  {cuerpo_senales}

  <h2>👀 En el radar ({len(near)})</h2>
  {cuerpo_radar}

  {avisos}

  {LEGEND}

  <footer>
    <a href="https://github.com/peperonioo/elliott-hybrid-scanner">Código y metodología</a> ·
    <a href="https://github.com/peperonioo/elliott-hybrid-scanner/tree/main/reports">
    Historial de informes</a> (registro del forward test)
  </footer>
</div>
{scripts}
</body>
</html>
"""


def write_web(cfg: Config, *, now: pd.Timestamp | None = None) -> Path:
    """Genera `docs/index.html` para GitHub Pages."""
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    entries, warnings = collect_entries(cfg)
    chart_data = build_chart_data(cfg, entries)
    overview = build_overview(cfg, entries)
    content = render_html(
        entries, warnings, cfg=cfg, now=now, chart_data=chart_data, overview=overview
    )

    web_dir = cfg.path("paths.web_dir")
    web_dir.mkdir(parents=True, exist_ok=True)
    path = web_dir / "index.html"
    path.write_text(content, encoding="utf-8")
    LOGGER.info("Web escrita en %s", path)
    return path
