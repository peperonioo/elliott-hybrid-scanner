"""Tests del dashboard HTML."""

from __future__ import annotations

from ehs.report.web import price_chart_svg, render_html
from tests_report_fixtures import NOW, make_config, make_entry


def test_una_senal_se_renderiza_con_niveles_y_lenguaje_llano():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([entry], [], cfg=make_config(), now=NOW)

    assert "<!doctype html>" in page
    assert "Señales de compra activas (1)" in page
    assert "COMPRA" in page
    assert "3 de 5 comprobaciones a favor" in page
    assert "Zona de compra" in page and "60,000" in page
    assert "Stop" in page and "58,000" in page
    assert "Objetivo 2R" in page
    assert "ni ejecuta órdenes" in page
    assert "Cómo leer esta página" in page
    # Lenguaje llano, no jerga interna.
    assert "precio en nivel Fibonacci" in page
    assert "corrective_abc" not in page.replace("corrective_abc", "", 0)  # placeholder
    assert "Lectura:" in page


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


def test_el_grafico_se_incrusta_cuando_se_proporciona():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    svg = price_chart_svg(
        [100.0, 105.0, 103.0, 108.0],
        [(0, 100.0), (3, 108.0)],
        zone=(101.0, 102.0),
        stop=99.0,
        target=106.0,
    )
    page = render_html([entry], [], cfg=make_config(), now=NOW, charts={"BTC/USDT": svg})

    assert "<svg" in page
    assert "compra 101" in page  # etiqueta de la banda
    assert "stop 99" in page
    assert "2R 106" in page


def test_el_svg_dibuja_precio_zigzag_y_niveles():
    svg = price_chart_svg(
        [100.0, 110.0, 105.0, 120.0, 115.0],
        [(1, 110.0), (2, 105.0)],
        zone=(102.0, 104.0),
        stop=98.0,
        target=130.0,
    )
    assert svg.count("<polyline") == 2  # precio + zigzag
    assert "<rect" in svg  # banda de compra
    assert svg.count("stroke-dasharray") == 2  # stop y objetivo


def test_el_svg_sin_datos_suficientes_devuelve_vacio():
    assert price_chart_svg([100.0], [], zone=None, stop=None, target=None) == ""


def test_el_html_escapa_el_contenido():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True, detail="<script>x</script>")
    page = render_html([entry], [], cfg=make_config(), now=NOW)
    assert "<script>x</script>" not in page
    assert "&lt;script&gt;" in page


def test_los_avisos_aparecen():
    page = render_html([], ["ETH: sin datos"], cfg=make_config(), now=NOW)
    assert "Avisos" in page and "ETH: sin datos" in page


def test_explica_que_los_precios_son_dolares():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert "USDT" in page and "dólar" in page
