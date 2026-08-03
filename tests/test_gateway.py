"""Tests del gateway: rate limit, reintentos y errores permanentes."""

from __future__ import annotations

import ccxt
import pytest

from ehs.data.gateway import ExchangeGateway, FetchError, RetryPolicy, SymbolUnavailable
from helpers import FakeExchange, FlakyExchange, make_rows

NO_RETRY = RetryPolicy(max_attempts=3, base_delay_s=0.0, backoff_factor=1.0, jitter=False)


def build(exchange, retry: RetryPolicy = NO_RETRY, **kwargs):
    slept: list[float] = []
    gw = ExchangeGateway("binance", exchange=exchange, retry=retry, sleep=slept.append, **kwargs)
    return gw, slept


def test_detecta_simbolos_listados():
    gw, _ = build(FakeExchange(markets={"BTC/USDT": {"active": True}}))
    assert gw.has_symbol("BTC/USDT")
    assert not gw.has_symbol("DOGE/USDT")


def test_un_mercado_inactivo_no_cuenta_como_disponible():
    gw, _ = build(FakeExchange(markets={"LUNA/USDT": {"active": False}}))
    assert not gw.has_symbol("LUNA/USDT")


def test_soporte_de_timeframes():
    gw, _ = build(FakeExchange(timeframes={"1h": "1h", "4h": "4h"}))
    assert gw.supports_timeframe("4h")
    assert not gw.supports_timeframe("3h")


def test_los_mercados_se_cargan_una_sola_vez():
    exchange = FakeExchange()
    calls = {"n": 0}
    original = exchange.load_markets

    def counting():
        calls["n"] += 1
        return original()

    exchange.load_markets = counting
    gw, _ = build(exchange)
    gw.has_symbol("BTC/USDT")
    gw.has_symbol("ETH/USDT")
    assert calls["n"] == 1


def test_reintenta_ante_error_transitorio_y_acaba_devolviendo_datos():
    exchange = FlakyExchange(
        make_rows("2024-01-01", "1h", 5),
        error=ccxt.NetworkError("caída temporal"),
        fail_times=2,
    )
    gw, slept = build(
        exchange, RetryPolicy(max_attempts=3, base_delay_s=1.0, backoff_factor=2.0, jitter=False)
    )

    rows = gw.fetch_page("BTC/USDT", "1h", None, 100)

    assert len(rows) == 5
    assert exchange.attempts == 3
    assert slept == [1.0, 2.0]  # backoff exponencial


def test_agotar_los_reintentos_lanza_fetch_error():
    exchange = FlakyExchange(
        make_rows("2024-01-01", "1h", 5),
        error=ccxt.RateLimitExceeded("429"),
        fail_times=99,
    )
    gw, _ = build(exchange)

    with pytest.raises(FetchError, match="agotados 3 intentos"):
        gw.fetch_page("BTC/USDT", "1h", None, 100)
    assert exchange.attempts == 3


def test_un_simbolo_invalido_no_se_reintenta():
    exchange = FlakyExchange([], error=ccxt.BadSymbol("símbolo inexistente"), fail_times=99)
    gw, _ = build(exchange)

    with pytest.raises(SymbolUnavailable):
        gw.fetch_page("NOPE/USDT", "1h", None, 100)
    assert exchange.attempts == 1  # un único intento


def test_el_backoff_respeta_el_tope():
    policy = RetryPolicy(base_delay_s=1.0, backoff_factor=10.0, max_delay_s=5.0, jitter=False)
    assert policy.delay_for(1) == 1.0
    assert policy.delay_for(2) == 5.0
    assert policy.delay_for(9) == 5.0


def test_el_jitter_no_supera_nunca_el_backoff_nominal():
    policy = RetryPolicy(base_delay_s=4.0, backoff_factor=2.0, max_delay_s=60.0, jitter=True)
    assert all(0.0 <= policy.delay_for(3) <= 16.0 for _ in range(200))


def test_extra_sleep_se_aplica_tras_cada_pagina():
    gw, slept = build(FakeExchange(make_rows("2024-01-01", "1h", 3)), extra_sleep_ms=250)
    gw.fetch_page("BTC/USDT", "1h", None, 100)
    assert slept == [0.25]


def test_exchange_desconocido():
    with pytest.raises(FetchError, match="no conoce el exchange"):
        ExchangeGateway("no_existe_este_exchange")


def test_el_gateway_no_lleva_credenciales():
    """El objeto ccxt se construye sin claves: no puede firmar peticiones."""
    gw = ExchangeGateway("kraken")
    assert not gw._exchange.apiKey
    assert not gw._exchange.secret
