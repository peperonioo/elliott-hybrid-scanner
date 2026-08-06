"""Página web del scanner: el informe diario como dashboard HTML.

Genera un `index.html` autocontenido (sin dependencias externas, tema claro y
oscuro) pensado para GitHub Pages y para leerse desde el móvil. Usa las mismas
entradas que el informe Markdown —`collect_entries`—, así que la web y el
informe no pueden contar cosas distintas.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path

import pandas as pd

from ehs.config import Config
from ehs.report.daily import ReportEntry, collect_entries

LOGGER = logging.getLogger(__name__)

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
.wrap{max-width:820px;margin:0 auto;padding:24px 16px 56px}
h1{font-size:1.45rem;margin:0}
.updated{color:var(--muted);font-size:.9rem;margin:4px 0 18px}
.disclaimer{border-left:4px solid var(--amber);background:var(--card);
  padding:10px 14px;border-radius:0 8px 8px 0;color:var(--muted);
  font-size:.88rem;margin-bottom:26px}
h2{font-size:1.12rem;margin:34px 0 12px;border-bottom:1px solid var(--border);
  padding-bottom:6px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:16px 18px;margin:14px 0}
.card h3{margin:0 0 8px;font-size:1rem}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;
  font-size:.78rem;font-weight:700;vertical-align:middle}
.badge.long{background:var(--green);color:#fff}
.badge.score{background:var(--zone);color:var(--accent)}
.levels{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:10px;margin:12px 0}
.level{background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:8px 12px}
.level .lab{font-size:.75rem;color:var(--muted);text-transform:uppercase;
  letter-spacing:.03em}
.level .val{font-weight:700;font-size:1.02rem}
.level.buy .val{color:var(--accent)}
.level.stop .val{color:var(--red)}
table{border-collapse:collapse;width:100%;font-size:.86rem;margin:8px 0}
th,td{border:1px solid var(--border);padding:6px 9px;text-align:left}
th{background:var(--bg)}
.ok{color:var(--green);font-weight:700}
.empty{background:var(--card);border:1px dashed var(--border);border-radius:12px;
  padding:22px;text-align:center;color:var(--muted)}
.empty b{color:var(--fg)}
details{margin-top:8px}
summary{cursor:pointer;color:var(--accent);font-size:.9rem}
details ul{margin:8px 0;padding-left:18px;color:var(--muted);font-size:.88rem}
.scroll{overflow-x:auto}
.legend{font-size:.92rem}
.legend dt{font-weight:700;margin-top:12px}
.legend dd{margin:2px 0 0 0;color:var(--muted)}
footer{margin-top:40px;color:var(--muted);font-size:.85rem;
  border-top:1px solid var(--border);padding-top:14px}
footer a{color:var(--accent)}
"""


def _fmt(value: float) -> str:
    return f"{value:,.4f}" if value < 100 else f"{value:,.2f}"


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _signal_card(entry: ReportEntry) -> str:
    r = entry.result
    factores = "".join(
        f"<tr><td>{_esc(f.name)}</td><td>{f.score:.2f}</td>"
        f"<td>{f.threshold:.2f}</td><td>{'<span class=ok>✅</span>' if f.active else '—'}</td></tr>"
        for f in r.factors
    )
    detalles = "".join(f"<li><b>{_esc(f.name)}</b>: {_esc(f.detail)}</li>" for f in r.factors)
    zona = (
        f'<div class="level buy"><div class="lab">Zona de compra</div>'
        f'<div class="val">{_fmt(r.zone[0])} – {_fmt(r.zone[1])}</div></div>'
        if r.zone
        else ""
    )
    ambiguo = (
        f'<p style="color:var(--muted);font-size:.88rem">⚠️ Conteo ambiguo; lectura '
        f"alternativa: {_esc(', '.join(r.count.ambiguous_with))}</p>"
        if r.count.is_ambiguous
        else ""
    )
    return f"""
<div class="card">
  <h3>{_esc(r.symbol)}
    <span class="badge long">COMPRA</span>
    <span class="badge score">{len(r.active_factors)}/{len(r.factors)} factores
      · score {r.score:.2f}</span>
  </h3>
  <p style="margin:4px 0;color:var(--muted);font-size:.9rem">
    Estructura: <code>{_esc(r.count.hypothesis)}</code> ·
    confirmada {r.timestamp:%d-%m-%Y %H:%M} UTC ({entry.bars_ago} velas de 4h atrás) ·
    precio en la señal {_fmt(r.price)}
  </p>
  <div class="levels">
    {zona}
    <div class="level stop"><div class="lab">Invalidación (stop)</div>
      <div class="val">{_fmt(r.signal_invalidation)}</div></div>
  </div>
  {ambiguo}
  <div class="scroll">
  <table>
    <tr><th>factor</th><th>score</th><th>umbral</th><th>activo</th></tr>
    {factores}
  </table>
  </div>
  <details><summary>por qué puntúa así</summary><ul>{detalles}</ul></details>
</div>"""


def _near_table(near: list[ReportEntry]) -> str:
    filas = "".join(
        (
            f"<tr><td>{_esc(e.result.symbol)}</td>"
            f"<td><code>{_esc(e.result.count.hypothesis)}</code></td>"
            f"<td>{e.result.score:.2f}</td>"
            f"<td>{_esc(', '.join(f.name for f in e.result.active_factors) or '—')}</td>"
            f"<td>{_fmt(e.result.zone[0])} – {_fmt(e.result.zone[1])}</td></tr>"
            if e.result.zone
            else f"<tr><td>{_esc(e.result.symbol)}</td>"
            f"<td><code>{_esc(e.result.count.hypothesis)}</code></td>"
            f"<td>{e.result.score:.2f}</td>"
            f"<td>{_esc(', '.join(f.name for f in e.result.active_factors) or '—')}</td>"
            f"<td>—</td></tr>"
        )
        for e in near
    )
    return f"""
<div class="scroll">
<table>
  <tr><th>par</th><th>estructura</th><th>score</th><th>factores activos</th>
    <th>zona a vigilar</th></tr>
  {filas}
</table>
</div>
<p style="color:var(--muted);font-size:.88rem">Les falta un factor para emitir señal.
Si el precio visita la zona o aparece la ruptura que falta, pueden dispararse.</p>"""


LEGEND = """
<dl class="legend">
  <dt>COMPRA sobre corrective_abc / impulse / impulse_1_2_3</dt>
  <dd><b>corrective_abc</b>: una corrección en 3 tramos parece terminada; la tesis es que
  la subida anterior se reanuda. <b>impulse</b>: cinco ondas completas.
  <b>impulse_1_2_3</b>: impulso a medias, se espera el retroceso (onda 4) y luego la
  onda 5 al alza. El sistema solo emite compras: las ventas en corto se eliminaron
  porque perdían dinero en el backtest.</dd>
  <dt>Zona de compra</dt>
  <dd>Banda alrededor del nivel de Fibonacci relevante. Si el precio vuelve ahí, es la
  entrada teóricamente favorable. Si ya se ha ido muy por encima, la señal ha escapado:
  se deja pasar.</dd>
  <dt>Invalidación (stop)</dt>
  <dd>Si el precio cae a este nivel, la tesis está rota. Si se operara, ahí iría el
  stop-loss. El objetivo de referencia del sistema es 2R: entrada + 2 × (entrada −
  invalidación).</dd>
  <dt>Factores (mínimo 3 de 5)</dt>
  <dd>fibonacci (precio en nivel clave), rsi_divergence (el RSI contradice al precio),
  market_structure (ruptura reciente en el gráfico diario), volume_profile (el volumen
  acompaña a la estructura), higher_timeframe_trend (la tendencia diaria va a favor).</dd>
</dl>"""


def render_html(
    entries: list[ReportEntry],
    warnings: list[str],
    *,
    cfg: Config,
    now: pd.Timestamp,
) -> str:
    signals = [e for e in entries if e.is_signal]
    near = [e for e in entries if not e.is_signal and len(e.result.active_factors) >= 2]

    if signals:
        cuerpo_senales = "".join(_signal_card(e) for e in signals)
    else:
        cuerpo_senales = """
<div class="empty">
  <b>Hoy no hay señal de compra.</b><br>
  Es lo normal: el sistema solo habla cuando 3 de sus 5 comprobaciones están a favor,
  unas 4 veces al mes en todo el universo. Un scanner que dispara a diario no filtra nada.
</div>"""

    cuerpo_cerca = (
        _near_table(near)
        if near
        else (
            '<p style="color:var(--muted)">Ningún par está a un factor de disparar ahora mismo.</p>'
        )
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
    universo: {_esc(', '.join(cfg.bases))} · timeframe 4h</div>

  <div class="disclaimer">Informe generado automáticamente con datos públicos de Binance.
  <b>No es asesoramiento financiero y el sistema no ejecuta órdenes</b>: son hipótesis
  técnicas para validar a mano antes de decidir nada. Backtest: prometedor pero no
  probado (holdout de solo 20 operaciones); en fase de forward test.</div>

  <h2>🎯 Señales de compra activas ({len(signals)})</h2>
  {cuerpo_senales}

  <h2>👀 En el radar ({len(near)})</h2>
  {cuerpo_cerca}

  {avisos}

  <h2>📖 Cómo leer esta página</h2>
  {LEGEND}

  <footer>
    <a href="https://github.com/peperonioo/elliott-hybrid-scanner">Código y metodología</a> ·
    <a href="https://github.com/peperonioo/elliott-hybrid-scanner/tree/main/reports">
    Historial de informes</a>
    (el registro del forward test: cada informe queda commiteado con fecha, imposible de
    reescribir).
  </footer>
</div>
</body>
</html>
"""


def write_web(cfg: Config, *, now: pd.Timestamp | None = None) -> Path:
    """Genera `docs/index.html` para GitHub Pages."""
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    entries, warnings = collect_entries(cfg)
    content = render_html(entries, warnings, cfg=cfg, now=now)

    web_dir = cfg.path("paths.web_dir")
    web_dir.mkdir(parents=True, exist_ok=True)
    path = web_dir / "index.html"
    path.write_text(content, encoding="utf-8")
    LOGGER.info("Web escrita en %s", path)
    return path
