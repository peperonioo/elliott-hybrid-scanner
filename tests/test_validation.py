"""Tests de la validación de integridad de series."""

from __future__ import annotations

import pandas as pd
import pytest

from ehs.data.schema import frame_from_ccxt
from ehs.data.validation import ValidationFailure, count_ohlc_inconsistencies, find_gaps, validate
from helpers import make_frame, make_rows


def test_serie_limpia_no_reporta_anomalias():
    frame = make_frame("2024-01-01", "4h", 50)
    out, report = validate(frame, symbol="BTC/USDT", timeframe="4h")

    assert report.ok
    assert report.duplicates == 0
    assert report.gaps == []
    assert report.zero_volume == 0
    assert report.gap_ratio == 0.0
    assert len(out) == 50


def test_detecta_hueco_y_cuenta_las_velas_ausentes():
    rows = make_rows("2024-01-01", "4h", 10)
    del rows[4:7]  # faltan 3 velas
    frame = frame_from_ccxt(rows)

    _, report = validate(frame, symbol="BTC/USDT", timeframe="4h")

    assert len(report.gaps) == 1
    assert report.gaps[0].missing == 3
    assert report.missing_candles == 3
    assert report.ok  # política por defecto: warn


def test_el_ratio_de_huecos_por_encima_del_maximo_invalida_la_serie():
    rows = make_rows("2024-01-01", "4h", 10)
    del rows[4:7]
    frame = frame_from_ccxt(rows)

    _, report = validate(frame, symbol="BTC/USDT", timeframe="4h", max_gap_ratio=0.01)

    assert not report.ok
    assert any("ratio de huecos" in err for err in report.errors)


def test_politica_raise_ante_hueco():
    rows = make_rows("2024-01-01", "4h", 10)
    del rows[4]
    with pytest.raises(ValidationFailure, match="huecos"):
        validate(
            frame_from_ccxt(rows),
            symbol="BTC/USDT",
            timeframe="4h",
            policies={"on_gap": "raise"},
        )


def test_duplicados_se_corrigen_por_defecto():
    rows = make_rows("2024-01-01", "1h", 5)
    frame = pd.concat([frame_from_ccxt(rows), frame_from_ccxt(rows[2:3])])

    out, report = validate(frame, symbol="BTC/USDT", timeframe="1h")

    assert report.duplicates == 1
    assert len(out) == 5
    assert not out.index.has_duplicates


def test_volumen_cero_se_reporta_y_opcionalmente_se_elimina():
    rows = make_rows("2024-01-01", "1h", 6)
    rows[2][5] = 0.0
    frame = frame_from_ccxt(rows)

    _, report = validate(frame, symbol="BTC/USDT", timeframe="1h")
    assert report.zero_volume == 1
    assert report.ok  # se informa, no invalida

    out, _ = validate(frame, symbol="BTC/USDT", timeframe="1h", policies={"on_zero_volume": "drop"})
    assert len(out) == 5


def test_detecta_ohlc_incoherente():
    rows = make_rows("2024-01-01", "1h", 4)
    rows[1][2] = rows[1][3] - 1  # high por debajo de low
    frame = frame_from_ccxt(rows)

    assert count_ohlc_inconsistencies(frame) == 1
    _, report = validate(frame, symbol="BTC/USDT", timeframe="1h")
    assert report.ohlc_inconsistent == 1


def test_los_nan_invalidan_la_serie():
    rows = make_rows("2024-01-01", "1h", 4)
    rows[2][4] = float("nan")
    _, report = validate(frame_from_ccxt(rows), symbol="BTC/USDT", timeframe="1h")

    assert report.nan_rows == 1
    assert not report.ok


def test_serie_demasiado_corta_no_es_apta():
    _, report = validate(
        make_frame("2024-01-01", "4h", 10), symbol="BTC/USDT", timeframe="4h", min_candles=200
    )
    assert not report.ok
    assert "al menos 200" in report.errors[0]


def test_serie_vacia_no_es_apta():
    from ehs.data.schema import empty_frame

    _, report = validate(empty_frame(), symbol="BTC/USDT", timeframe="4h")
    assert not report.ok
    assert report.errors == ["serie vacía"]


def test_find_gaps_con_menos_de_dos_velas():
    assert find_gaps(make_frame("2024-01-01", "1h", 1).index, "1h") == []


def test_el_resumen_es_legible():
    frame = make_frame("2024-01-01", "4h", 30)
    _, report = validate(frame, symbol="BTC/USDT", timeframe="4h")
    assert "OK" in report.summary()
    assert "sin anomalías" in report.summary()
