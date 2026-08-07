"""Tests del dashboard HTML con gráficos interactivos."""

from __future__ import annotations

from ehs.report.web import render_html
from tests_report_fixtures import NOW, make_config, make_entry

CHART = {
    "BTC/USDT": {
        "candles": [
            {"time": 1, "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0},
            {"time": 2, "open": 105.0, "high": 112.0, "low": 101.0, "close": 63500.0},
        ],
        "pivots": [{"time": 1, "value": 100.0}, {"time": 2, "value": 110.0}],
        "zone": [60000.0, 61000.0],
        "stop": 58000.0,
        "target": 66500.0,
    }
}


def test_una_senal_se_renderiza_con_niveles_y_lenguaje_llano():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([entry], [], cfg=make_config(), now=NOW)

    assert "<!doctype html>" in page
    assert "Señales de compra activas (1)" in page
    assert "COMPRA" in page
    assert "3 de 5 comprobaciones a favor" in page
    assert "Precio ahora" in page
    assert "Zona de compra" in page and "60,000" in page
    assert "Stop" in page and "58,000" in page
    assert "Objetivo (2× riesgo)" in page
    assert "ni ejecuta órdenes" in page
    assert "Cómo leer esta página" in page
    assert "precio en nivel Fibonacci" in page
    assert "Lectura:" in page


def test_sin_grafico_el_precio_actual_es_el_de_la_senal():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([entry], [], cfg=make_config(), now=NOW)
    assert "63,000" in page  # r.price del fixture


def test_con_grafico_el_precio_actual_es_el_ultimo_cierre():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([entry], [], cfg=make_config(), now=NOW, chart_data=CHART)
    assert "63,500" in page  # último cierre de las velas embebidas


def test_sin_senales_muestra_el_estado_vacio():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert "Hoy no hay señal de compra" in page
    assert "Señales de compra activas (0)" in page


def test_el_radar_muestra_tarjetas_con_niveles():
    cerca = make_entry([0.9, 0.8, 0.1, 0.1, 0.1], is_signal=False)
    page = render_html([cerca], [], cfg=make_config(), now=NOW)

    assert "En el radar (1)" in page
    assert "2 de 5 comprobaciones a favor" in page
    assert "precio en nivel Fibonacci, divergencia del RSI" in page
    assert "60,000 – 61,000" in page


def test_con_datos_se_embebe_el_grafico_interactivo():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([entry], [], cfg=make_config(), now=NOW, chart_data=CHART)

    assert "lightweight-charts" in page  # CDN de la librería de TradingView
    assert 'id="chart-BTC-USDT"' in page
    assert "EHS_DATA" in page
    assert '"stop":58000.0' in page
    assert "ver BTC en TradingView" in page
    assert "tradingview.com/chart/?symbol=BINANCE:BTCUSDT" in page


def test_sin_datos_no_se_carga_ninguna_libreria():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([entry], [], cfg=make_config(), now=NOW)
    assert "lightweight-charts" not in page
    assert "<script" not in page


def test_el_html_escapa_el_contenido():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True, detail="<script>x</script>")
    page = render_html([entry], [], cfg=make_config(), now=NOW)
    assert "<script>x</script>" not in page
    assert "&lt;script&gt;" in page


def test_los_avisos_aparecen():
    page = render_html([], ["ETH: sin datos"], cfg=make_config(), now=NOW)
    assert "Avisos" in page and "ETH: sin datos" in page


def test_formato_para_precios_diminutos():
    """PEPE cotiza a 0.00001: el formato debe enseñar dígitos significativos."""
    from ehs.report.web import _fmt

    assert _fmt(0.00001053) == "0.00001053"
    assert _fmt(0.8330) == "0.8330"
    assert _fmt(64810.0) == "64,810"
    assert _fmt(1.05) == "1.05"


def test_el_resumen_del_mercado_muestra_todas_las_monedas():
    overview = [
        {"base": "BTC", "price": 64810.0, "state": "radar", "cls": "rad", "link": True},
        {"base": "ETH", "price": 1909.0, "state": "sin estructura", "cls": "non", "link": False},
        {"base": "PEPE", "price": 0.00001053, "state": "SEÑAL", "cls": "sig", "link": True},
    ]
    page = render_html([], [], cfg=make_config(), now=NOW, overview=overview)

    assert "El mercado de un vistazo" in page
    assert "ETH" in page and "sin estructura" in page
    assert "0.00001053" in page
    assert 'href="#card-BTC"' in page


def test_la_leyenda_explica_operativa_y_objetivo():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert "spot" in page
    assert "sin apalancamiento" in page
    assert "margin" in page
    assert "100 + 2×5" in page  # el ejemplo numérico del 2R


def test_hay_boton_de_actualizacion_manual():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert "Actualizar ahora" in page
    assert "actions/workflows/daily-scan.yml" in page


def test_explica_que_los_precios_son_dolares():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert "USDT" in page and "dólar" in page
