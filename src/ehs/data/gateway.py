"""Acceso a exchanges vía ccxt: **solo endpoints públicos**.

Este módulo nunca construye un exchange con credenciales y nunca llama a un
método privado. El sistema lee precios y nada más; no existe ninguna ruta de
código capaz de tocar una cuenta.

Encapsula además el rate limiting (el throttle propio de ccxt más un margen
opcional) y los reintentos con backoff exponencial ante errores transitorios.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import ccxt

LOGGER = logging.getLogger(__name__)

# Errores transitorios: merecen reintento. En ccxt, DDoSProtection,
# RateLimitExceeded, RequestTimeout y ExchangeNotAvailable heredan de
# NetworkError; se listan igualmente para dejar la intención explícita.
RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    ccxt.NetworkError,
    ccxt.RequestTimeout,
    ccxt.ExchangeNotAvailable,
    ccxt.DDoSProtection,
    ccxt.RateLimitExceeded,
)

# Errores permanentes: reintentar solo gasta cuota.
FATAL_ERRORS: tuple[type[Exception], ...] = (
    ccxt.BadSymbol,
    ccxt.AuthenticationError,
    ccxt.NotSupported,
)


class FetchError(Exception):
    """La descarga ha fallado de forma definitiva."""


class SymbolUnavailable(FetchError):
    """El exchange no lista ese símbolo (o no está activo)."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_s: float = 1.0
    backoff_factor: float = 2.0
    max_delay_s: float = 60.0
    jitter: bool = True

    def delay_for(self, attempt: int) -> float:
        """Espera antes del intento `attempt` (1-indexado)."""
        delay = min(self.base_delay_s * (self.backoff_factor ** (attempt - 1)), self.max_delay_s)
        if self.jitter:
            # Jitter completo: reparte los reintentos y evita que varios pares
            # rebotando a la vez vuelvan a golpear el exchange sincronizados.
            delay *= random.random()
        return delay

    @classmethod
    def from_config(cls, section: dict[str, Any]) -> RetryPolicy:
        return cls(
            max_attempts=int(section.get("max_attempts", 5)),
            base_delay_s=float(section.get("base_delay_s", 1.0)),
            backoff_factor=float(section.get("backoff_factor", 2.0)),
            max_delay_s=float(section.get("max_delay_s", 60.0)),
            jitter=bool(section.get("jitter", True)),
        )


class ExchangeGateway:
    """Envoltorio de un exchange ccxt restringido a datos públicos."""

    def __init__(
        self,
        exchange_id: str,
        *,
        enable_throttle: bool = True,
        extra_sleep_ms: int = 0,
        retry: RetryPolicy | None = None,
        exchange: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        public_api_url: str | None = None,
        ccxt_options: dict[str, Any] | None = None,
    ) -> None:
        self.exchange_id = exchange_id
        self.retry = retry or RetryPolicy()
        self.extra_sleep_s = max(extra_sleep_ms, 0) / 1000
        self._sleep = sleep
        self._exchange = exchange if exchange is not None else self._build(enable_throttle)
        self._markets_loaded = False

        # Opciones de ccxt inyectadas desde la configuración. El caso que lo
        # motiva: `load_markets` de Binance consulta por defecto también los
        # mercados de futuros (fapi/dapi), que están geo-bloqueados en CI y no
        # pasan por el override de URL. Restringirlo a spot lo evita.
        if ccxt_options:
            options = getattr(self._exchange, "options", None)
            if isinstance(options, dict):
                options.update(ccxt_options)

        # Endpoint alternativo para los datos públicos. El caso que lo motiva:
        # Binance geo-bloquea las IPs de los runners de GitHub (EE.UU.), pero
        # su endpoint oficial solo-datos (data-api.binance.vision) no. Solo se
        # toca la ruta `public`: este sistema no usa ninguna otra.
        if public_api_url:
            urls = getattr(self._exchange, "urls", None)
            if isinstance(urls, dict) and "api" in urls and isinstance(urls["api"], dict):
                urls["api"]["public"] = public_api_url

    def _build(self, enable_throttle: bool) -> Any:
        if not hasattr(ccxt, self.exchange_id):
            raise FetchError(f"ccxt no conoce el exchange {self.exchange_id!r}")
        # Sin apiKey ni secret: el objeto resultante no puede firmar peticiones.
        return getattr(ccxt, self.exchange_id)({"enableRateLimit": enable_throttle})

    # -- mercados -----------------------------------------------------------

    def load_markets(self) -> dict[str, Any]:
        if not self._markets_loaded:
            self._call("load_markets", lambda: self._exchange.load_markets())
            self._markets_loaded = True
        return self._exchange.markets

    def has_symbol(self, symbol: str) -> bool:
        markets = self.load_markets()
        market = markets.get(symbol)
        # `active` es None en exchanges que no informan del estado: se acepta.
        return market is not None and market.get("active") is not False

    def supports_timeframe(self, timeframe: str) -> bool:
        timeframes = getattr(self._exchange, "timeframes", None)
        return True if not timeframes else timeframe in timeframes

    # -- OHLCV --------------------------------------------------------------

    def fetch_page(
        self, symbol: str, timeframe: str, since_ms: int | None, limit: int
    ) -> list[list[float]]:
        """Una página de velas. Devuelve la lista cruda de ccxt."""
        rows = self._call(
            f"fetch_ohlcv({symbol},{timeframe},since={since_ms})",
            lambda: self._exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit),
        )
        if self.extra_sleep_s:
            self._sleep(self.extra_sleep_s)
        return rows or []

    # -- reintentos ---------------------------------------------------------

    def _call(self, label: str, fn: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.retry.max_attempts + 1):
            try:
                return fn()
            except FATAL_ERRORS as exc:
                raise SymbolUnavailable(f"{self.exchange_id} {label}: {exc}") from exc
            except RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt == self.retry.max_attempts:
                    break
                delay = self.retry.delay_for(attempt)
                LOGGER.warning(
                    "%s %s falló (intento %d/%d): %s. Reintento en %.1fs",
                    self.exchange_id,
                    label,
                    attempt,
                    self.retry.max_attempts,
                    type(exc).__name__,
                    delay,
                )
                self._sleep(delay)
            except ccxt.ExchangeError as exc:
                raise FetchError(f"{self.exchange_id} {label}: {exc}") from exc

        raise FetchError(
            f"{self.exchange_id} {label}: agotados {self.retry.max_attempts} intentos "
            f"({type(last_error).__name__}: {last_error})"
        ) from last_error

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"ExchangeGateway({self.exchange_id})"
