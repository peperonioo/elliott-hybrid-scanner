"""Tests del dashboard HTML."""

from __future__ import annotations

from ehs.report.web import render_html
from tests_report_fixtures import NOW, make_config, make_entry


def test_una_senal_se_renderiza_con_niveles_y_factores():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([entry], [], cfg=make_config(), now=NOW)

    assert "<!doctype html>" in page
    assert "Señales de compra activas (1)" in page
    assert "COMPRA" in page
    assert "Zona de compra" in page and "60,000.00" in page
    assert "Invalidación (stop)" in page and "58,000.00" in page
    assert "no ejecuta órdenes" in page
    assert "Cómo leer esta página" in page


def test_sin_senales_muestra_el_estado_vacio():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert "Hoy no hay señal de compra" in page
    assert "Señales de compra activas (0)" in page


def test_los_cercanos_van_al_radar():
    cerca = make_entry([0.9, 0.8, 0.1, 0.1, 0.1], is_signal=False)
    page = render_html([cerca], [], cfg=make_config(), now=NOW)

    assert "En el radar (1)" in page
    assert "fibonacci, rsi_divergence" in page


def test_el_html_escapa_el_contenido():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True, detail="<script>x</script>")
    page = render_html([entry], [], cfg=make_config(), now=NOW)
    assert "<script>x</script>" not in page
    assert "&lt;script&gt;" in page


def test_los_avisos_aparecen():
    page = render_html([], ["ETH/USDT: sin datos"], cfg=make_config(), now=NOW)
    assert "Avisos" in page and "ETH/USDT: sin datos" in page
