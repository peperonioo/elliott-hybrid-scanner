"""Tests de carga y validación de la configuración."""

from __future__ import annotations

import textwrap

import pytest
import yaml

from ehs.config import Config, ConfigError, project_root


def write_config(tmp_path, data) -> str:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(path)


def test_carga_el_config_real_del_repo():
    cfg = Config.load(project_root() / "config.yaml")
    assert cfg.bases
    assert cfg.get("exchanges.primary.id") == "binance"


def test_falla_si_faltan_claves_obligatorias(tmp_path):
    path = write_config(tmp_path, {"universe": {"bases": ["BTC"]}})
    with pytest.raises(ConfigError, match="Faltan claves obligatorias"):
        Config.load(path)


def test_falla_si_el_universo_esta_vacio(tmp_path, config_dict):
    config_dict["universe"]["bases"] = []
    with pytest.raises(ConfigError, match="lista no vacía"):
        Config.load(write_config(tmp_path, config_dict))


def test_falla_si_el_fichero_no_existe(tmp_path):
    with pytest.raises(ConfigError, match="No se encuentra"):
        Config.load(tmp_path / "no-existe.yaml")


def test_falla_con_yaml_invalido(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        textwrap.dedent("""\
        exchanges:
          primary:
           - a
          : mal
        """),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        Config.load(path)


def test_get_con_ruta_punteada(config_dict):
    cfg = Config(config_dict)
    assert cfg.get("exchanges.primary.quote") == "USDT"
    assert cfg.get("no.existe", "por-defecto") == "por-defecto"
    with pytest.raises(ConfigError, match="ausente"):
        cfg.get("no.existe")


def test_construccion_de_simbolos(config_dict):
    cfg = Config(config_dict)
    assert cfg.symbol_for("BTC", "primary") == "BTC/USDT"
    assert cfg.symbol_for("BTC", "fallback") == "BTC/USD"


def test_los_overrides_de_simbolo_ganan(config_dict):
    config_dict["exchanges"]["symbol_overrides"] = {"binance": {"BTC": "BTC/FDUSD"}}
    cfg = Config(config_dict)
    assert cfg.symbol_for("BTC", "primary") == "BTC/FDUSD"
    assert cfg.symbol_for("ETH", "primary") == "ETH/USDT"


def test_timeframes_deduplicados_y_en_orden(config_dict):
    config_dict["timeframes"] = {"context": "1d", "structure": "4h", "timing": "4h"}
    assert Config(config_dict).timeframes == ["1d", "4h"]
