"""Caché local de OHLCV en Parquet.

Un fichero por (exchange, símbolo, timeframe). Las escrituras son atómicas
—fichero temporal y `replace`— para que una interrupción a mitad de descarga
no deje un Parquet corrupto que envenene la siguiente ejecución.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ehs.data.schema import empty_frame, normalise

LOGGER = logging.getLogger(__name__)


def safe_symbol(symbol: str) -> str:
    """`BTC/USDT` -> `BTC-USDT`, apto como nombre de directorio."""
    return symbol.replace("/", "-").replace(":", "_")


class ParquetCache:
    """Almacén de series OHLCV bajo `<root>/<exchange>/<símbolo>/<tf>.parquet`."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, exchange_id: str, symbol: str, timeframe: str) -> Path:
        return self.root / exchange_id / safe_symbol(symbol) / f"{timeframe}.parquet"

    def exists(self, exchange_id: str, symbol: str, timeframe: str) -> bool:
        return self.path_for(exchange_id, symbol, timeframe).is_file()

    def read(self, exchange_id: str, symbol: str, timeframe: str) -> pd.DataFrame:
        """Lee la serie cacheada. Devuelve un frame vacío si no existe.

        Un Parquet ilegible se trata como caché ausente: se registra y se
        vuelve a descargar, en lugar de tumbar toda la ingesta.
        """
        path = self.path_for(exchange_id, symbol, timeframe)
        if not path.is_file():
            return empty_frame()
        try:
            return normalise(pd.read_parquet(path))
        except Exception as exc:
            LOGGER.warning("Caché ilegible en %s (%s); se re-descargará", path, exc)
            return empty_frame()

    def write(self, exchange_id: str, symbol: str, timeframe: str, frame: pd.DataFrame) -> Path:
        path = self.path_for(exchange_id, symbol, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".parquet.tmp")
        normalise(frame).to_parquet(tmp, engine="pyarrow", compression="snappy")
        tmp.replace(path)
        LOGGER.debug("Caché escrita: %s (%d velas)", path, len(frame))
        return path

    def last_timestamp(self, exchange_id: str, symbol: str, timeframe: str) -> pd.Timestamp | None:
        cached = self.read(exchange_id, symbol, timeframe)
        return None if cached.empty else cached.index.max()


def merge_frames(cached: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    """Fusiona lo cacheado con lo recién descargado.

    Ante un mismo timestamp gana la descarga nueva: el exchange puede corregir
    una vela reciente y su última lectura es la buena.
    """
    if cached.empty:
        return normalise(fresh)
    if fresh.empty:
        return normalise(cached)
    return normalise(pd.concat([cached, fresh]))
