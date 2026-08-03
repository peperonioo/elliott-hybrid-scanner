"""Tests de la caché Parquet."""

from __future__ import annotations

import pandas as pd

from ehs.data.cache import ParquetCache, merge_frames, safe_symbol
from ehs.data.schema import assert_valid, empty_frame
from helpers import make_frame


def test_symbol_seguro_como_nombre_de_directorio():
    assert safe_symbol("BTC/USDT") == "BTC-USDT"
    assert "/" not in safe_symbol("BTC/USDT:USDT")


def test_ida_y_vuelta_conserva_el_esquema(tmp_path):
    cache = ParquetCache(tmp_path)
    frame = make_frame("2024-01-01", "4h", 20)

    cache.write("binance", "BTC/USDT", "4h", frame)
    out = cache.read("binance", "BTC/USDT", "4h")

    assert_valid(out)
    pd.testing.assert_frame_equal(out, frame)
    assert cache.exists("binance", "BTC/USDT", "4h")


def test_leer_una_cache_inexistente_devuelve_frame_vacio(tmp_path):
    cache = ParquetCache(tmp_path)
    assert cache.read("binance", "BTC/USDT", "4h").empty
    assert cache.last_timestamp("binance", "BTC/USDT", "4h") is None


def test_una_cache_corrupta_se_trata_como_ausente(tmp_path):
    cache = ParquetCache(tmp_path)
    path = cache.path_for("binance", "BTC/USDT", "4h")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"esto no es un parquet")

    assert cache.read("binance", "BTC/USDT", "4h").empty


def test_la_escritura_no_deja_ficheros_temporales(tmp_path):
    cache = ParquetCache(tmp_path)
    cache.write("binance", "BTC/USDT", "4h", make_frame("2024-01-01", "4h", 5))
    assert list(tmp_path.rglob("*.tmp")) == []


def test_last_timestamp(tmp_path):
    cache = ParquetCache(tmp_path)
    frame = make_frame("2024-01-01", "4h", 10)
    cache.write("binance", "BTC/USDT", "4h", frame)
    assert cache.last_timestamp("binance", "BTC/USDT", "4h") == frame.index.max()


def test_merge_da_prioridad_a_lo_recien_descargado():
    cached = make_frame("2024-01-01", "4h", 10)
    fresh = make_frame("2024-01-01", "4h", 10, price=500.0).iloc[8:]

    merged = merge_frames(cached, fresh)

    assert_valid(merged)
    assert len(merged) == 10
    assert merged["open"].iloc[8] == fresh["open"].iloc[0]
    assert merged["open"].iloc[0] == cached["open"].iloc[0]


def test_merge_con_operandos_vacios():
    frame = make_frame("2024-01-01", "4h", 5)
    assert len(merge_frames(empty_frame(), frame)) == 5
    assert len(merge_frames(frame, empty_frame())) == 5
    assert merge_frames(empty_frame(), empty_frame()).empty
