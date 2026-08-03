"""Ingesta de OHLCV multi-timeframe con caché incremental en Parquet.

Punto de entrada de la fase 1. Responsabilidades:

  1. Resolver el símbolo de cada base en el exchange primario, con fallback.
  2. Descargar paginando desde la última vela cacheada (no el histórico entero).
  3. Descartar la vela en curso antes de persistir.
  4. Validar la integridad de la serie y devolver el informe junto a los datos.

El punto 3 no es cosmético: una vela sin cerrar tiene un `close` que aún se
mueve. Si entra en la caché, el ATR de la fase 2 y los indicadores de la fase 4
se calculan sobre un valor que en producción todavía no se conocía — es
lookahead bias colado por la puerta de atrás.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import pandas as pd

from ehs.config import Config
from ehs.data.cache import ParquetCache, merge_frames
from ehs.data.gateway import ExchangeGateway, FetchError, RetryPolicy, SymbolUnavailable
from ehs.data.schema import empty_frame, frame_from_ccxt, normalise, timeframe_to_ms
from ehs.data.validation import ValidationReport, validate

LOGGER = logging.getLogger(__name__)

EXCHANGE_ROLES: tuple[str, ...] = ("primary", "fallback")


@dataclass
class FetchResult:
    """Resultado de descargar un (base, timeframe)."""

    base: str
    symbol: str
    exchange_id: str
    exchange_role: str
    timeframe: str
    frame: pd.DataFrame
    report: ValidationReport
    new_candles: int

    @property
    def ok(self) -> bool:
        return self.report.ok

    def __str__(self) -> str:
        origin = f"{self.exchange_id}:{self.symbol}"
        return f"{origin} (+{self.new_candles}) {self.report.summary()}"


class OHLCVFetcher:
    """Orquesta descarga, caché y validación para el universo configurado."""

    def __init__(
        self,
        cfg: Config,
        *,
        cache: ParquetCache | None = None,
        gateways: dict[str, ExchangeGateway] | None = None,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self.cfg = cfg
        self.cache = cache or ParquetCache(cfg.path("paths.cache_dir"))
        # `now_ms` es inyectable para poder testear el descarte de la vela en
        # curso sin depender del reloj real.
        self.now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._gateways: dict[str, ExchangeGateway] = dict(gateways or {})

        self.page_limit = int(cfg.get("history.page_limit"))
        self.overlap_candles = int(cfg.get("history.overlap_candles", 0))
        self.drop_incomplete = bool(cfg.get("history.drop_incomplete_candle", True))
        self.start_ms = _to_ms(str(cfg.get("history.start_date")))

    # -- exchanges ----------------------------------------------------------

    def gateway(self, role: str) -> ExchangeGateway:
        """Gateway perezoso por rol ("primary" / "fallback")."""
        if role not in self._gateways:
            exchange_id = str(self.cfg.get(f"exchanges.{role}.id"))
            rate_limit = self.cfg.section("exchanges.rate_limit")
            self._gateways[role] = ExchangeGateway(
                exchange_id,
                enable_throttle=bool(rate_limit.get("enable_throttle", True)),
                extra_sleep_ms=int(rate_limit.get("extra_sleep_ms", 0)),
                retry=RetryPolicy.from_config(self.cfg.section("exchanges.retry")),
            )
        return self._gateways[role]

    def _roles(self) -> list[str]:
        return [role for role in EXCHANGE_ROLES if self.cfg.get(f"exchanges.{role}.id", None)]

    def resolve_source(self, base: str, timeframe: str) -> tuple[str, ExchangeGateway, str]:
        """Elige el primer exchange que liste el símbolo y soporte el timeframe."""
        problems: list[str] = []
        for role in self._roles():
            symbol = self.cfg.symbol_for(base, role)
            try:
                gw = self.gateway(role)
                if not gw.has_symbol(symbol):
                    problems.append(f"{role}: {symbol} no listado")
                    continue
                if not gw.supports_timeframe(timeframe):
                    problems.append(f"{role}: timeframe {timeframe} no soportado")
                    continue
                if role != "primary":
                    LOGGER.warning("%s: usando fallback %s (%s)", base, gw.exchange_id, symbol)
                return role, gw, symbol
            except FetchError as exc:
                problems.append(f"{role}: {exc}")
        raise SymbolUnavailable(f"{base} no disponible en ningún exchange — {'; '.join(problems)}")

    # -- descarga -----------------------------------------------------------

    def fetch(self, base: str, timeframe: str, *, force_full: bool = False) -> FetchResult:
        """Descarga (incrementalmente) un par y timeframe, y lo valida."""
        role, gw, symbol = self.resolve_source(base, timeframe)
        tf_ms = timeframe_to_ms(timeframe)

        cached = empty_frame() if force_full else self.cache.read(gw.exchange_id, symbol, timeframe)
        since_ms = self._resume_point(cached, tf_ms)
        until_ms = self.now_ms()

        fresh = self._download(gw, symbol, timeframe, since_ms, until_ms)
        merged = merge_frames(cached, fresh)

        if self.drop_incomplete:
            merged = drop_incomplete_candles(merged, timeframe, until_ms)

        new_candles = len(merged) - len(cached)
        if not merged.empty:
            self.cache.write(gw.exchange_id, symbol, timeframe, merged)

        merged, report = validate(
            merged,
            symbol=symbol,
            timeframe=timeframe,
            policies=self.cfg.section("validation"),
            max_gap_ratio=float(self.cfg.get("validation.max_gap_ratio", 1.0)),
            min_candles=int(self.cfg.get("validation.min_candles", 0)),
        )

        return FetchResult(
            base=base,
            symbol=symbol,
            exchange_id=gw.exchange_id,
            exchange_role=role,
            timeframe=timeframe,
            frame=merged,
            report=report,
            new_candles=max(new_candles, 0),
        )

    def fetch_all(
        self,
        bases: Sequence[str] | None = None,
        timeframes: Sequence[str] | None = None,
        *,
        force_full: bool = False,
    ) -> list[FetchResult]:
        """Descarga el producto cartesiano bases x timeframes.

        Un par que falle no aborta el resto: se registra y se continúa.
        """
        bases = list(bases if bases is not None else self.cfg.bases)
        timeframes = list(timeframes if timeframes is not None else self.cfg.timeframes)

        results: list[FetchResult] = []
        for base in bases:
            for timeframe in timeframes:
                try:
                    result = self.fetch(base, timeframe, force_full=force_full)
                except FetchError as exc:
                    LOGGER.error("%s %s: %s", base, timeframe, exc)
                    continue
                LOGGER.info("%s", result)
                results.append(result)
        return results

    def _resume_point(self, cached: pd.DataFrame, tf_ms: int) -> int:
        """Desde dónde reanudar: última vela cacheada menos el solape."""
        if cached.empty:
            return self.start_ms
        last_ms = int(cached.index.max().timestamp() * 1000)
        resume = last_ms - self.overlap_candles * tf_ms
        return max(resume, self.start_ms)

    def _download(
        self, gw: ExchangeGateway, symbol: str, timeframe: str, since_ms: int, until_ms: int
    ) -> pd.DataFrame:
        """Pagina hacia adelante desde `since_ms` hasta alcanzar `until_ms`."""
        if since_ms >= until_ms:
            return empty_frame()

        tf_ms = timeframe_to_ms(timeframe)
        max_pages = _page_budget(since_ms, until_ms, tf_ms, self.page_limit)

        pages: list[list[list[float]]] = []
        cursor = since_ms
        for page_no in range(1, max_pages + 1):
            page = gw.fetch_page(symbol, timeframe, cursor, self.page_limit)
            if not page:
                break
            pages.append(page)

            next_cursor = int(page[-1][0]) + tf_ms
            if next_cursor <= cursor:
                # Sin avance: el exchange devuelve siempre lo mismo. Cortar aquí
                # es lo que impide un bucle infinito.
                LOGGER.debug("%s %s: la paginación no avanza, se corta", symbol, timeframe)
                break
            cursor = next_cursor

            if len(page) < self.page_limit:
                # Página incompleta: no hay más histórico disponible.
                # Es también el caso de Kraken, que devuelve ~720 velas fijas
                # e ignora `since`.
                break
            if cursor >= until_ms:
                break
            if page_no == max_pages:
                LOGGER.warning(
                    "%s %s: alcanzado el límite de %d páginas, descarga truncada",
                    symbol,
                    timeframe,
                    max_pages,
                )

        if not pages:
            return empty_frame()
        return normalise(frame_from_ccxt([row for page in pages for row in page]))


def drop_incomplete_candles(frame: pd.DataFrame, timeframe: str, now_ms: int) -> pd.DataFrame:
    """Elimina las velas que aún no han cerrado.

    Una vela con apertura en `t` cierra en `t + tf`; solo es definitiva cuando
    `now >= t + tf`.
    """
    if frame.empty:
        return frame
    tf_ms = timeframe_to_ms(timeframe)
    open_ms = frame.index.astype("int64") // 1_000_000
    return frame[open_ms + tf_ms <= now_ms]


def _page_budget(since_ms: int, until_ms: int, tf_ms: int, page_limit: int) -> int:
    """Cota superior de páginas necesarias, con margen para solapes."""
    candles = max(math.ceil((until_ms - since_ms) / tf_ms), 1)
    return max(math.ceil(candles / max(page_limit, 1)) * 2 + 5, 5)


def _to_ms(date_str: str) -> int:
    return int(pd.Timestamp(date_str, tz="UTC").timestamp() * 1000)


def summarise(results: Iterable[FetchResult]) -> str:
    """Resumen legible de una tanda de descargas."""
    results = list(results)
    ok = sum(1 for r in results if r.ok)
    lines = [f"{ok}/{len(results)} series aptas", ""]
    lines += [f"  {r}" for r in results]
    return "\n".join(lines)
