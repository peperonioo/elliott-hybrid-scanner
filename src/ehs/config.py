"""Carga y acceso a la configuración única del sistema (`config.yaml`).

Todo parámetro ajustable del scanner vive en el YAML. Este módulo se limita a
leerlo, validar que las claves imprescindibles existen y ofrecer acceso por
ruta punteada. No define valores por defecto de negocio a propósito: si falta
una clave es un error de configuración, no algo que el código deba inventar.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

LOGGER = logging.getLogger(__name__)

DEFAULT_CONFIG_FILENAME = "config.yaml"

# Claves sin las cuales la ingesta no puede funcionar.
REQUIRED_KEYS: tuple[str, ...] = (
    "paths.cache_dir",
    "exchanges.primary.id",
    "exchanges.primary.quote",
    "exchanges.retry.max_attempts",
    "universe.bases",
    "timeframes.structure",
    "history.start_date",
    "history.page_limit",
)

_MISSING = object()


class ConfigError(Exception):
    """La configuración no existe, no parsea, o le faltan claves."""


def project_root() -> Path:
    """Raíz del repo, deducida desde la ubicación de este fichero."""
    return Path(__file__).resolve().parents[2]


class Config:
    """Wrapper de solo lectura sobre el árbol del YAML."""

    def __init__(self, data: dict[str, Any], source: Path | None = None) -> None:
        self._data = data
        self.source = source
        self.root = source.parent if source is not None else project_root()

    # -- construcción -------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        cfg_path = Path(path) if path is not None else project_root() / DEFAULT_CONFIG_FILENAME
        if not cfg_path.is_file():
            raise ConfigError(f"No se encuentra el fichero de configuración: {cfg_path}")

        try:
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigError(f"YAML inválido en {cfg_path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise ConfigError(f"La raíz de {cfg_path} debe ser un mapa, no {type(raw).__name__}")

        cfg = cls(raw, source=cfg_path)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        missing = [key for key in REQUIRED_KEYS if not self.has(key)]
        if missing:
            raise ConfigError(
                "Faltan claves obligatorias en la configuración: " + ", ".join(missing)
            )

        bases = self.get("universe.bases")
        if not isinstance(bases, list) or not bases:
            raise ConfigError("`universe.bases` debe ser una lista no vacía")

    # -- acceso -------------------------------------------------------------

    def has(self, dotted_key: str) -> bool:
        """True si la clave existe, sea cual sea su valor (incluido `None`)."""
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return False
            node = node[part]
        return True

    def get(self, dotted_key: str, default: Any = _MISSING) -> Any:
        """Devuelve el valor en `a.b.c`, o `default`. Sin default, lanza."""
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                if default is _MISSING:
                    raise ConfigError(f"Clave de configuración ausente: {dotted_key}")
                return default
            node = node[part]
        return node

    def section(self, dotted_key: str) -> dict[str, Any]:
        value = self.get(dotted_key, {})
        if not isinstance(value, dict):
            raise ConfigError(f"`{dotted_key}` debería ser un mapa, es {type(value).__name__}")
        return value

    def path(self, dotted_key: str) -> Path:
        """Resuelve una ruta del YAML contra la raíz del proyecto."""
        return (self.root / str(self.get(dotted_key))).resolve()

    # -- ayudas de dominio --------------------------------------------------

    @property
    def bases(self) -> list[str]:
        return [str(b) for b in self.get("universe.bases")]

    @property
    def timeframes(self) -> list[str]:
        """Timeframes a descargar, deduplicados y en orden de declaración."""
        declared = self.section("timeframes").values()
        seen: dict[str, None] = {}
        for tf in declared:
            seen.setdefault(str(tf), None)
        return list(seen)

    def symbol_for(self, base: str, exchange_role: str) -> str:
        """Construye el símbolo de un `base` en el exchange indicado.

        `exchange_role` es "primary" o "fallback". Se respeta cualquier
        override declarado en `exchanges.symbol_overrides.<exchange_id>`.
        """
        exchange_id = str(self.get(f"exchanges.{exchange_role}.id"))
        overrides = self.section("exchanges.symbol_overrides").get(exchange_id) or {}
        if base in overrides:
            return str(overrides[base])
        quote = str(self.get(f"exchanges.{exchange_role}.quote"))
        return f"{base}/{quote}"

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"Config(source={self.source}, bases={len(self.bases)})"


def setup_logging(cfg: Config) -> None:
    """Configura el logging raíz según el YAML."""
    logging.basicConfig(
        level=str(cfg.get("logging.level", "INFO")).upper(),
        format=str(cfg.get("logging.format", "%(asctime)s | %(levelname)s | %(message)s")),
    )
