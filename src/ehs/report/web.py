"""Página web del scanner: dashboard HTML con gráficos.

Genera un `index.html` autocontenido (sin librerías externas, tema claro y
oscuro, apto para móvil) pensado para GitHub Pages. Cada par se presenta como
una tarjeta con un gráfico SVG generado aquí mismo: precio reciente, ZigZag de
la estructura, zona de compra sombreada y líneas de stop y objetivo.

Usa las mismas entradas que el informe Markdown —`collect_entries`—, así que
la web y el informe no pueden contar cosas distintas.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path

import pandas as pd

from ehs.config import Config
from ehs.data.cache import ParquetCache
from ehs.pipeline import PipelineParams
from ehs.report.daily import ReportEntry, _read_pair, collect_entries
from ehs.structure.swings import detect_swings

LOGGER = logging.getLogger(__name__)

CHART_BARS = 180  # ~30 días de velas de 4h

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
  --amber:#9a6700; --zone:rgba(9,105,218,.10); --zonefill:rgba(9,105,218,.16);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg:#0d1117; --fg:#e6edf3; --muted:#8b949e; --card:#161b22;
    --border:#30363d; --accent:#4493f8; --green:#3fb950; --red:#f85149;
    --amber:#d29922; --zone:rgba(68,147,248,.12); --zonefill:rgba(68,147,248,.20);
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:24px 16px 56px}
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
.chart{margin:4px 0}
.chart svg{width:100%;height:auto;display:block}
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
"""


def _fmt(value: float) -> str:
    return f"{value:,.4f}" if value < 100 else f"{value:,.0f}"


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


# ---------------------------------------------------------------------------
# Gráfico SVG
# ---------------------------------------------------------------------------


def price_chart_svg(
    closes: list[float],
    pivots_rel: list[tuple[int, float]],
    *,
    zone: tuple[float, float] | None,
    stop: float | None,
    target: float | None,
) -> str:
    """Gráfico de línea con la zona de compra, el stop y el objetivo.

    Todo son coordenadas calculadas aquí: sin JavaScript ni librerías, así que
    funciona en cualquier navegador y pesa poco.
    """
    if len(closes) < 2:
        return ""

    width, height = 680.0, 240.0
    left, right, top, bottom = 6.0, 74.0, 12.0, 12.0
    plot_w, plot_h = width - left - right, height - top - bottom

    candidates = list(closes)
    if zone:
        candidates += [zone[0], zone[1]]
    if stop is not None:
        candidates.append(stop)
    if target is not None:
        candidates.append(target)
    lo, hi = min(candidates), max(candidates)
    span = (hi - lo) or abs(hi) or 1.0
    lo, hi = lo - span * 0.05, hi + span * 0.05

    def x(i: int) -> float:
        return left + plot_w * i / (len(closes) - 1)

    def y(price: float) -> float:
        return top + plot_h * (1 - (price - lo) / (hi - lo))

    parts: list[str] = [
        f'<svg viewBox="0 0 {width:.0f} {height:.0f}" role="img" '
        f'xmlns="http://www.w3.org/2000/svg">'
    ]

    # Banda de la zona de compra, de lado a lado.
    if zone:
        z_top, z_bot = y(zone[1]), y(zone[0])
        parts.append(
            f'<rect x="{left}" y="{z_top:.1f}" width="{plot_w:.1f}" '
            f'height="{max(z_bot - z_top, 2):.1f}" fill="var(--zonefill)"/>'
        )
        parts.append(
            f'<text x="{left + 4}" y="{z_top - 4:.1f}" font-size="11" '
            f'fill="var(--accent)">compra {_fmt(zone[0])}–{_fmt(zone[1])}</text>'
        )

    # Líneas de stop y objetivo, con etiqueta en el margen derecho.
    def hline(price: float, color: str, label: str, dy: float) -> None:
        yy = y(price)
        parts.append(
            f'<line x1="{left}" y1="{yy:.1f}" x2="{left + plot_w:.1f}" y2="{yy:.1f}" '
            f'stroke="{color}" stroke-width="1.3" stroke-dasharray="6 4"/>'
        )
        parts.append(
            f'<text x="{left + plot_w + 4:.1f}" y="{yy + dy:.1f}" font-size="11" '
            f'fill="{color}">{label}</text>'
        )

    if stop is not None:
        hline(stop, "var(--red)", f"stop {_fmt(stop)}", 4)
    if target is not None:
        hline(target, "var(--green)", f"2R {_fmt(target)}", 4)

    # Precio.
    line = " ".join(f"{x(i):.1f},{y(c):.1f}" for i, c in enumerate(closes))
    parts.append(
        f'<polyline points="{line}" fill="none" stroke="var(--muted)" '
        f'stroke-width="1.4" stroke-linejoin="round"/>'
    )

    # ZigZag de la estructura por encima del precio.
    visible = [(i, p) for i, p in pivots_rel if 0 <= i < len(closes)]
    if len(visible) >= 2:
        zigzag = " ".join(f"{x(i):.1f},{y(p):.1f}" for i, p in visible)
        parts.append(
            f'<polyline points="{zigzag}" fill="none" stroke="var(--accent)" '
            f'stroke-width="1.8" stroke-linejoin="round"/>'
        )
        for i, p in visible:
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(p):.1f}" r="3" fill="var(--accent)"/>')

    # Último precio.
    last_x, last_y = x(len(closes) - 1), y(closes[-1])
    parts.append(f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3.5" fill="var(--fg)"/>')
    parts.append(
        f'<text x="{left + plot_w + 4:.1f}" y="{last_y - 6:.1f}" font-size="11" '
        f'font-weight="700" fill="var(--fg)">{_fmt(closes[-1])}</text>'
    )

    parts.append("</svg>")
    return "".join(parts)


def _target_for(entry: ReportEntry) -> float | None:
    r = entry.result
    if r.zone is None:
        return None
    mid = (r.zone[0] + r.zone[1]) / 2
    if r.signal_invalidation >= mid:
        return None
    return mid + 2 * (mid - r.signal_invalidation)


# ---------------------------------------------------------------------------
# Tarjetas
# ---------------------------------------------------------------------------


def _card(entry: ReportEntry, chart: str) -> str:
    r = entry.result
    target = _target_for(entry)

    levels = []
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
            f'<div class="level target"><div class="lab">Objetivo 2R</div>'
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

    chart_html = f'<div class="chart">{chart}</div>' if chart else ""

    return f"""
<div class="{card_class}">
  <h3>{_esc(base)} {badge}
    <span class="badge score">{n_activos} de 5 comprobaciones a favor</span>
  </h3>
  <p class="meta">Lectura: <b>{_esc(_hypothesis_label(r.count.hypothesis))}</b>
    · a favor: {_esc(activos)}
    · se necesitan 3 de 5 para señal de compra{confirmada}{ambiguo}</p>
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
  <dt>El gráfico</dt>
  <dd>Línea gris: el precio (velas de 4 horas, último mes). Línea azul: la estructura
  de ondas de Elliott que el sistema ha detectado. Banda azul: la zona donde comprar
  sería técnicamente favorable. Línea roja: el stop (si el precio cae ahí, la idea ha
  fallado y se sale). Línea verde: el objetivo, que gana el doble de lo que arriesga
  el stop ("2R").</dd>
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


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------


def render_html(
    entries: list[ReportEntry],
    warnings: list[str],
    *,
    cfg: Config,
    now: pd.Timestamp,
    charts: dict[str, str] | None = None,
) -> str:
    charts = charts or {}
    signals = [e for e in entries if e.is_signal]
    near = [e for e in entries if not e.is_signal]

    if signals:
        cuerpo_senales = "".join(_card(e, charts.get(e.result.symbol, "")) for e in signals)
    else:
        cuerpo_senales = """
<div class="empty"><b>Hoy no hay señal de compra.</b><br>
Es lo normal (~4 señales al mes en todo el universo): el sistema solo dispara con
3 de 5 factores a favor.</div>"""

    cuerpo_radar = (
        "".join(_card(e, charts.get(e.result.symbol, "")) for e in near)
        if near
        else '<p style="color:var(--muted)">Ningún par tiene ahora mismo una estructura '
        "alcista operable.</p>"
    )

    avisos = (
        "<h2>Avisos</h2><ul>" + "".join(f"<li>{_esc(w)}</li>" for w in warnings) + "</ul>"
        if warnings
        else ""
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
  asesoramiento financiero ni ejecuta órdenes. Sistema en fase de validación
  (forward test).</div>

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
</body>
</html>
"""


def build_charts(cfg: Config, entries: list[ReportEntry]) -> dict[str, str]:
    """Genera el SVG de cada par presente en las entradas."""
    cache = ParquetCache(cfg.path("paths.cache_dir"))
    params = PipelineParams.from_config(cfg)
    charts: dict[str, str] = {}

    for entry in entries:
        r = entry.result
        if r.symbol in charts:
            continue
        base = r.symbol.split("/")[0]
        _, structure, _ = _read_pair(cfg, cache, base, params)
        if structure.empty:
            continue

        window = structure.iloc[-CHART_BARS:]
        offset = len(structure) - len(window)
        closes = [float(v) for v in window["close"]]
        pivots_rel = [
            (p.index - offset, p.price)
            for p in detect_swings(structure, **params.swing)
            if p.index >= offset
        ]
        charts[r.symbol] = price_chart_svg(
            closes,
            pivots_rel,
            zone=r.zone,
            stop=r.signal_invalidation,
            target=_target_for(entry),
        )
    return charts


def write_web(cfg: Config, *, now: pd.Timestamp | None = None) -> Path:
    """Genera `docs/index.html` para GitHub Pages."""
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    entries, warnings = collect_entries(cfg)
    charts = build_charts(cfg, entries)
    content = render_html(entries, warnings, cfg=cfg, now=now, charts=charts)

    web_dir = cfg.path("paths.web_dir")
    web_dir.mkdir(parents=True, exist_ok=True)
    path = web_dir / "index.html"
    path.write_text(content, encoding="utf-8")
    LOGGER.info("Web escrita en %s", path)
    return path
