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
    assert "Zona de venta · objetivo 2R" in page
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
    assert "no hay señal de compra activa" in page
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


def test_hay_boton_de_actualizacion_de_precios_y_enlace_a_reanalisis():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert 'id="btn-live"' in page
    assert "Actualizar precios" in page
    assert "actions/workflows/daily-scan.yml" in page  # re-análisis completo


def test_con_overview_se_embebe_el_refresco_en_vivo():
    overview = [
        {
            "base": "BTC",
            "symbol": "BTC/USDT",
            "price": 64810.0,
            "state": "radar",
            "cls": "rad",
            "link": True,
        }
    ]
    page = render_html([], [], cfg=make_config(), now=NOW, overview=overview)

    assert "EHS_LIVE" in page
    assert "data-api.binance.vision" in page
    assert '"sym":"BTC/USDT"' in page


def test_explica_que_los_precios_son_dolares():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert "USDT" in page and "dólar" in page


def test_las_monedas_en_observacion_tienen_tarjeta_con_diagnostico():
    watch = {
        "ETH": {
            "base": "ETH",
            "symbol": "ETH/USDT",
            "price": 1915.0,
            "res": 1981.0,
            "sup": 1822.0,
            "label": "lectura bajista",
            "cls": "bear",
            "text": "La mejor lectura de Elliott ahora es <b>bajista</b>. "
            "Se anula si supera <b>1,981</b>.",
            "anula": 1981.0,
        }
    }
    page = render_html([], [], cfg=make_config(), now=NOW, watch=watch)

    assert "En observación (1)" in page
    assert "lectura bajista" in page
    assert "Soporte clave" in page and "1,822" in page
    assert "Resistencia clave" in page and "1,981" in page
    assert "Se anula lo bajista" in page


def test_sin_watch_no_hay_seccion_de_observacion():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert "En observación" not in page


def test_redondeo_respeta_monedas_diminutas():
    """El bug de PEPE: redondear a 6 decimales fijos aplana el gráfico entero."""
    from ehs.report.web import _round_price

    assert _round_price(0.0000020534267, 9) == 0.00000205343
    assert _round_price(0.0000021198, 9) != _round_price(0.0000020534, 9)
    assert _round_price(64810.1234, 0) == 64810.1234  # las grandes no pierden nada


def test_la_tarjeta_dice_que_hacer_ahora():
    # Señal con el precio (63,000) por encima de la zona (60,000–61,000).
    señal = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([señal], [], cfg=make_config(), now=NOW)
    assert "Qué hacer ahora" in page
    assert "no comprar persiguiendo el precio" in page
    assert "orden límite" in page

    # Radar: aún no es señal.
    radar = make_entry([0.9, 0.8, 0.1, 0.1, 0.1], is_signal=False)
    page = render_html([radar], [], cfg=make_config(), now=NOW)
    assert "todavía no es señal (2 de 5" in page


def test_la_proyeccion_muestra_frecuencias_historicas():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([entry], [], cfg=make_config(), now=NOW)

    assert "Posible siguiente movimiento" in page
    assert "195 operaciones" in page
    assert "llegó a la venta objetivo (+2R)" in page
    assert "tocó el stop" in page
    assert "No es una predicción" in page


def test_la_proyeccion_se_embebe_para_los_graficos():
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([entry], [], cfg=make_config(), now=NOW, chart_data=CHART)
    assert "EHS_PROJ" in page
    assert '"target_pct":21.5' in page


def test_la_navegacion_por_secciones_existe():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert 'href="#sec-senales"' in page
    assert 'id="sec-forward"' in page
    assert 'id="sec-guia"' in page


def test_watch_bajista_tambien_dice_que_hacer():
    watch = {
        "ETH": {
            "base": "ETH",
            "symbol": "ETH/USDT",
            "price": 1915.0,
            "res": 1981.0,
            "sup": 1822.0,
            "label": "lectura bajista",
            "cls": "bear",
            "text": "texto",
            "anula": 1981.0,
        }
    }
    page = render_html([], [], cfg=make_config(), now=NOW, watch=watch)
    assert "esperar fuera del mercado" in page


def test_la_zona_dca_se_muestra_como_estrategia_separada():
    dca = [
        {
            "base": "BTC",
            "lower": 39081.0,
            "upper": 57373.0,
            "price": 64900.0,
            "estado": "13% por encima — esperar",
            "cls": "flat",
        }
    ]
    page = render_html([], [], cfg=make_config(), now=NOW, dca=dca)

    assert "Zona DCA" in page
    assert "39,081" in page and "57,373" in page
    assert "por encima — esperar" in page
    assert "No está validada por el backtest" in page


def test_una_senal_con_el_stop_tocado_se_declara_anulada():
    """Si el precio actual ya está bajo el stop, la tarjeta no puede sugerir comprar."""
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    chart = {
        "BTC/USDT": {
            "candles": [
                {"time": 1, "open": 60000.0, "high": 60500.0, "low": 57000.0, "close": 57500.0}
            ],
            "pivots": [],
            "zone": [60000.0, 61000.0],
            "stop": 58000.0,
            "target": 66500.0,
        }
    }
    page = render_html([entry], [], cfg=make_config(), now=NOW, chart_data=chart)
    assert "anulada" in page
    assert "el plan ha muerto" in page


def test_el_boton_de_actualizar_tiene_estado_de_carga():
    overview = [
        {
            "base": "BTC",
            "symbol": "BTC/USDT",
            "price": 64810.0,
            "state": "radar",
            "cls": "rad",
            "link": True,
        }
    ]
    page = render_html([], [], cfg=make_config(), now=NOW, overview=overview)
    assert "spinner" in page  # animación mientras actualiza
    assert "Actualizando…" in page
    assert "monedas actualizadas a las" in page  # confirmación al terminar
    assert "sin conexión con Binance" in page  # y aviso si todo falla


def test_la_proyeccion_incluye_el_aviso_fuera_de_muestra():
    """La regla de la casa: si fuera de muestra no batió costes, se dice."""
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([entry], [], cfg=make_config(), now=NOW)
    assert "Aviso honesto" in page
    assert "no cubrió" in page
    assert "-0.18%" in page or "−0.18%" in page or "-0.18" in page


def test_la_tarjeta_ofrece_venta_rapida_en_la_resistencia():
    # Señal: precio 63,000, objetivo 65,500. Resistencia entre medias → venta rápida.
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)
    page = render_html([entry], [], cfg=make_config(), now=NOW, levels={"BTC": {"res": 64200.0}})
    assert "Venta rápida · resistencia" in page and "64,200" in page

    # Resistencia por debajo del precio actual: no se ofrece.
    page = render_html([entry], [], cfg=make_config(), now=NOW, levels={"BTC": {"res": 62000.0}})
    assert "Venta rápida" not in page


def test_el_resumen_ejecutivo_y_los_bloques_ordenan_la_pagina():
    from ehs.report.direction import DirectionStats

    rows = [
        {
            "base": "TRX",
            "stats": DirectionStats(
                trend_up=True,
                momentum_up=False,
                rsi_zone="débil",
                p_up=0.54,
                avg_move=0.001,
                n=1378,
                reliable=True,
            ),
        }
    ]
    page = render_html([], [], cfg=make_config(), now=NOW, direction=rows)

    assert "señales activas: <b>0</b>" in page
    assert "mejor apuesta 24h: <b>TRX ▲ 54%</b>" in page
    assert "Para operar — el plan validado" in page
    assert "Contexto y apuestas" in page
    assert "Registro y ayuda" in page


def test_la_observacion_va_plegada_con_resumen():
    watch = {
        "ETH": {
            "base": "ETH",
            "symbol": "ETH/USDT",
            "price": 1915.0,
            "res": 1981.0,
            "sup": 1822.0,
            "label": "lectura bajista",
            "cls": "bear",
            "text": "texto",
            "anula": 1981.0,
        }
    }
    page = render_html([], [], cfg=make_config(), now=NOW, watch=watch)
    assert '<details class="wdet">' in page
    assert "sup 1,822 · res 1,981" in page


def test_el_branding_de_app_esta_presente():
    page = render_html([], [], cfg=make_config(), now=NOW)
    assert '<header class="appbar">' in page  # logo + wordmark
    assert 'class="tabbar"' in page  # barra de pestañas móvil
    assert "prefers-color-scheme: light" in page  # oscuro por defecto, claro automático
    assert "#0ecb81" in page  # verde de la marca (velas/estados)
