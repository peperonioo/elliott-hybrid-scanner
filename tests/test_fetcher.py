"""Tests del fetcher: paginación, caché incremental, fallback y vela en curso."""

from __future__ import annotations

import pandas as pd
import pytest

from ehs.config import Config
from ehs.data.cache import ParquetCache
from ehs.data.fetcher import OHLCVFetcher, drop_incomplete_candles
from ehs.data.gateway import ExchangeGateway, RetryPolicy, SymbolUnavailable
from ehs.data.schema import assert_valid, timeframe_to_ms
from helpers import FakeExchange, make_frame, make_rows, to_ms

NO_RETRY = RetryPolicy(max_attempts=2, base_delay_s=0.0, backoff_factor=1.0, jitter=False)
TF = "4h"
TF_MS = timeframe_to_ms(TF)
START = "2024-01-01"


def gateway_for(exchange: FakeExchange, exchange_id: str = "binance") -> ExchangeGateway:
    return ExchangeGateway(exchange_id, exchange=exchange, retry=NO_RETRY, sleep=lambda _: None)


def build_fetcher(
    config_dict,
    tmp_path,
    *,
    primary: FakeExchange,
    fallback: FakeExchange | None = None,
    now: int,
) -> OHLCVFetcher:
    gateways = {"primary": gateway_for(primary, "binance")}
    if fallback is not None:
        gateways["fallback"] = gateway_for(fallback, "kraken")
    return OHLCVFetcher(
        Config(config_dict),
        cache=ParquetCache(tmp_path),
        gateways=gateways,
        now_ms=lambda: now,
    )


def closed_at(count: int) -> int:
    """Instante en el que la vela número `count` ya ha cerrado."""
    return to_ms(START) + count * TF_MS


# --------------------------------------------------------------------------
# Descarga básica
# --------------------------------------------------------------------------


def test_descarga_desde_cero_y_cumple_el_esquema(config_dict, tmp_path):
    exchange = FakeExchange(make_rows(START, TF, 40))
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(40))

    result = fetcher.fetch("BTC", TF)

    assert_valid(result.frame)
    assert len(result.frame) == 40
    assert result.symbol == "BTC/USDT"
    assert result.exchange_id == "binance"
    assert result.exchange_role == "primary"
    assert result.new_candles == 40
    assert result.ok


def test_pagina_hasta_agotar_el_historico(config_dict, tmp_path):
    config_dict["history"]["page_limit"] = 100
    exchange = FakeExchange(make_rows(START, TF, 250), max_per_page=100)
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(250))

    result = fetcher.fetch("BTC", TF)

    assert len(result.frame) == 250
    assert len(exchange.calls) == 3  # 100 + 100 + 50
    assert exchange.calls[0][2] == to_ms(START)
    assert exchange.calls[1][2] == to_ms(START) + 100 * TF_MS


def test_la_serie_se_persiste_en_la_cache(config_dict, tmp_path):
    exchange = FakeExchange(make_rows(START, TF, 30))
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(30))
    fetcher.fetch("BTC", TF)

    cached = ParquetCache(tmp_path).read("binance", "BTC/USDT", TF)
    assert len(cached) == 30
    assert_valid(cached)


# --------------------------------------------------------------------------
# Ausencia de velas sin cerrar
# --------------------------------------------------------------------------


def test_descarta_la_vela_en_curso(config_dict, tmp_path):
    """Con la vela 30 aún abierta, la serie debe terminar en la 29.

    Es el equivalente en la fase 1 del test anti-lookahead de la fase 2: un
    `close` que todavía se mueve no puede entrar en la caché.
    """
    exchange = FakeExchange(make_rows(START, TF, 30))
    mid_candle = closed_at(29) + TF_MS // 2  # la vela 30 lleva media vida
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=mid_candle)

    result = fetcher.fetch("BTC", TF)

    assert len(result.frame) == 29
    assert result.frame.index.max() == pd.Timestamp(START, tz="UTC") + pd.Timedelta(
        28 * TF_MS, unit="ms"
    )
    assert (
        ParquetCache(tmp_path).read("binance", "BTC/USDT", TF).index.max()
        == result.frame.index.max()
    )


def test_la_vela_en_curso_se_incorpora_cuando_cierra(config_dict, tmp_path):
    rows = make_rows(START, TF, 30)
    exchange = FakeExchange(rows)
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(29) + TF_MS // 2)
    assert len(fetcher.fetch("BTC", TF).frame) == 29

    fetcher.now_ms = lambda: closed_at(30)
    assert len(fetcher.fetch("BTC", TF).frame) == 30


def test_se_puede_desactivar_el_descarte_por_configuracion(config_dict, tmp_path):
    config_dict["history"]["drop_incomplete_candle"] = False
    exchange = FakeExchange(make_rows(START, TF, 30))
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(29) + TF_MS // 2)
    assert len(fetcher.fetch("BTC", TF).frame) == 30


def test_drop_incomplete_candles_es_puro():
    frame = make_frame(START, TF, 10)
    assert len(drop_incomplete_candles(frame, TF, closed_at(10))) == 10
    assert len(drop_incomplete_candles(frame, TF, closed_at(10) - 1)) == 9
    assert drop_incomplete_candles(frame, TF, to_ms(START)).empty


# --------------------------------------------------------------------------
# Descarga incremental
# --------------------------------------------------------------------------


def test_la_segunda_pasada_no_rebaja_el_historico(config_dict, tmp_path):
    config_dict["history"]["overlap_candles"] = 2
    exchange = FakeExchange(make_rows(START, TF, 50))
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(50))
    fetcher.fetch("BTC", TF)
    first_pass_calls = len(exchange.calls)

    exchange.rows = make_rows(START, TF, 55)
    fetcher.now_ms = lambda: closed_at(55)
    result = fetcher.fetch("BTC", TF)

    since_second_pass = exchange.calls[first_pass_calls][2]
    expected = to_ms(START) + (49 - 2) * TF_MS  # última cacheada menos el solape
    assert since_second_pass == expected
    assert len(result.frame) == 55
    assert result.new_candles == 5


def test_sin_velas_nuevas_la_serie_no_cambia(config_dict, tmp_path):
    exchange = FakeExchange(make_rows(START, TF, 40))
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(40))
    first = fetcher.fetch("BTC", TF)
    second = fetcher.fetch("BTC", TF)

    pd.testing.assert_frame_equal(first.frame, second.frame)
    assert second.new_candles == 0


def test_el_solape_refresca_las_ultimas_velas(config_dict, tmp_path):
    """Si el exchange corrige una vela ya cacheada, el solape la actualiza."""
    exchange = FakeExchange(make_rows(START, TF, 20))
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(20))
    fetcher.fetch("BTC", TF)

    corrected = make_rows(START, TF, 20)
    corrected[19][4] = 12345.0  # el exchange revisa el close de la última vela
    exchange.rows = corrected
    result = fetcher.fetch("BTC", TF)

    assert result.frame["close"].iloc[-1] == 12345.0


def test_force_full_ignora_la_cache(config_dict, tmp_path):
    exchange = FakeExchange(make_rows(START, TF, 30))
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(30))
    fetcher.fetch("BTC", TF)
    calls_before = len(exchange.calls)

    result = fetcher.fetch("BTC", TF, force_full=True)

    assert exchange.calls[calls_before][2] == to_ms(START)
    assert len(result.frame) == 30


# --------------------------------------------------------------------------
# Fallback entre exchanges
# --------------------------------------------------------------------------


def test_cae_al_fallback_si_el_primario_no_lista_el_simbolo(config_dict, tmp_path):
    primary = FakeExchange(markets={"ETH/USDT": {"active": True}})
    fallback = FakeExchange(make_rows(START, TF, 25), markets={"BTC/USD": {"active": True}})
    fetcher = build_fetcher(
        config_dict, tmp_path, primary=primary, fallback=fallback, now=closed_at(25)
    )

    result = fetcher.fetch("BTC", TF)

    assert result.exchange_role == "fallback"
    assert result.exchange_id == "kraken"
    assert result.symbol == "BTC/USD"
    assert len(result.frame) == 25


def test_cae_al_fallback_si_el_primario_no_soporta_el_timeframe(config_dict, tmp_path):
    primary = FakeExchange(make_rows(START, TF, 25), timeframes={"1h": "1h"})
    fallback = FakeExchange(make_rows(START, TF, 25), markets={"BTC/USD": {"active": True}})
    fetcher = build_fetcher(
        config_dict, tmp_path, primary=primary, fallback=fallback, now=closed_at(25)
    )

    assert fetcher.fetch("BTC", TF).exchange_role == "fallback"


def test_sin_ninguna_fuente_disponible_lanza(config_dict, tmp_path):
    empty = FakeExchange(markets={})
    fetcher = build_fetcher(
        config_dict, tmp_path, primary=empty, fallback=FakeExchange(markets={}), now=closed_at(10)
    )

    with pytest.raises(SymbolUnavailable, match="no disponible en ningún exchange"):
        fetcher.fetch("BTC", TF)


# --------------------------------------------------------------------------
# Robustez de la paginación
# --------------------------------------------------------------------------


def test_un_exchange_que_ignora_since_no_provoca_bucle_infinito(config_dict, tmp_path):
    """Kraken devuelve siempre las últimas N velas ignorando `since`.

    La paginación debe detectar que no avanza y cortar, quedándose con lo que
    el exchange sí puede dar.
    """
    config_dict["history"]["page_limit"] = 50
    exchange = FakeExchange(make_rows(START, TF, 500), ignores_since=True, max_per_page=50)
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(500))

    result = fetcher.fetch("BTC", TF)

    assert len(exchange.calls) <= 3
    assert len(result.frame) == 50
    assert_valid(result.frame)


def test_un_exchange_sin_datos_devuelve_serie_vacia(config_dict, tmp_path):
    fetcher = build_fetcher(config_dict, tmp_path, primary=FakeExchange([]), now=closed_at(10))
    result = fetcher.fetch("BTC", TF)

    assert result.frame.empty
    assert not result.ok


# --------------------------------------------------------------------------
# Recorrido del universo
# --------------------------------------------------------------------------


def test_fetch_all_recorre_bases_y_timeframes(config_dict, tmp_path):
    config_dict["universe"]["bases"] = ["BTC", "ETH"]
    config_dict["timeframes"] = {"structure": "4h", "timing": "1h"}
    markets = {"BTC/USDT": {"active": True}, "ETH/USDT": {"active": True}}
    exchange = FakeExchange(make_rows(START, "1h", 400), markets=markets)
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(100))

    results = fetcher.fetch_all()

    assert len(results) == 4
    assert {(r.base, r.timeframe) for r in results} == {
        ("BTC", "4h"),
        ("BTC", "1h"),
        ("ETH", "4h"),
        ("ETH", "1h"),
    }


def test_fetch_all_continua_aunque_un_par_falle(config_dict, tmp_path):
    config_dict["universe"]["bases"] = ["BTC", "NOEXISTE"]
    config_dict["timeframes"] = {"structure": "4h"}
    exchange = FakeExchange(make_rows(START, TF, 30), markets={"BTC/USDT": {"active": True}})
    fetcher = build_fetcher(config_dict, tmp_path, primary=exchange, now=closed_at(30))

    results = fetcher.fetch_all()

    assert [r.base for r in results] == ["BTC"]
