"""Tests del esquema canónico de series OHLCV."""

from __future__ import annotations

import pandas as pd
import pytest

from ehs.data.schema import (
    OHLCV_COLUMNS,
    SchemaError,
    assert_valid,
    empty_frame,
    frame_from_ccxt,
    normalise,
    timeframe_to_ms,
)
from helpers import make_rows


@pytest.mark.parametrize(
    ("timeframe", "expected_ms"),
    [("1m", 60_000), ("15m", 900_000), ("1h", 3_600_000), ("4h", 14_400_000), ("1d", 86_400_000)],
)
def test_conversion_de_timeframe(timeframe, expected_ms):
    assert timeframe_to_ms(timeframe) == expected_ms


@pytest.mark.parametrize("bad", ["", "h", "0h", "-1h", "4y", "cuatro-horas"])
def test_timeframe_invalido_lanza(bad):
    with pytest.raises(ValueError):
        timeframe_to_ms(bad)


def test_frame_desde_ccxt_cumple_el_esquema():
    frame = frame_from_ccxt(make_rows("2024-01-01", "4h", 5))
    assert_valid(frame)
    assert list(frame.columns) == list(OHLCV_COLUMNS)
    assert frame.index.tz is not None
    assert len(frame) == 5


def test_frame_vacio_es_valido():
    assert_valid(empty_frame())
    assert empty_frame().empty


def test_normalise_ordena_y_deduplica_quedandose_con_lo_ultimo():
    rows = make_rows("2024-01-01", "1h", 3)
    duplicate = list(rows[1])
    duplicate[4] = 999.0  # misma vela, close revisado por el exchange
    frame = frame_from_ccxt([rows[2], rows[0], rows[1], duplicate])

    out = normalise(frame)

    assert_valid(out)
    assert len(out) == 3
    assert out["close"].iloc[1] == 999.0


def test_normalise_localiza_indices_naive_a_utc():
    frame = frame_from_ccxt(make_rows("2024-01-01", "1h", 3))
    naive = frame.tz_localize(None)
    assert normalise(naive).index.tz is not None


def test_assert_valid_detecta_duplicados():
    frame = frame_from_ccxt(make_rows("2024-01-01", "1h", 2))
    roto = pd.concat([frame, frame.iloc[[0]]])
    with pytest.raises(SchemaError, match="duplicados"):
        assert_valid(roto)


def test_normalise_falla_si_faltan_columnas():
    frame = frame_from_ccxt(make_rows("2024-01-01", "1h", 2)).drop(columns=["volume"])
    with pytest.raises(SchemaError, match="Faltan columnas"):
        normalise(frame)
