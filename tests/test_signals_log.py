"""Tests del registro automático del forward test."""

from __future__ import annotations

from ehs.config import Config
from ehs.report.signals_log import (
    OUTCOME_OPEN,
    OUTCOME_STOP,
    OUTCOME_TARGET,
    LoggedSignal,
    append_new,
    evaluate,
    load_log,
    save_log,
    summary_stats,
    update_log,
)
from helpers import frame_from_closes, path_closes
from tests_report_fixtures import NOW, make_entry


def make_signal(frame, *, stop: float) -> LoggedSignal:
    return LoggedSignal(
        symbol="X/USDT",
        timestamp=frame.index[5].isoformat(),
        hypothesis="corrective_abc",
        price=float(frame["close"].iloc[5]),
        zone_low=None,
        zone_high=None,
        stop=stop,
        score=0.7,
        factors=["fibonacci"],
        recorded_at=NOW.isoformat(),
    )


def test_una_senal_que_alcanza_el_objetivo_marca_mas_dos_r():
    # Entrada ~106 con stop 95 → objetivo ~128. El precio sube hasta 140.
    frame = frame_from_closes(path_closes([(0, 100.0), (20, 140.0)]), timeframe="4h")
    signal = make_signal(frame, stop=95.0)

    evaluate(signal, frame)

    assert signal.outcome == OUTCOME_TARGET
    assert signal.result_r == 2.0
    assert signal.entry is not None and signal.target is not None


def test_una_senal_que_toca_el_stop_marca_menos_un_r():
    frame = frame_from_closes(path_closes([(0, 100.0), (20, 80.0)]), timeframe="4h")
    signal = make_signal(frame, stop=95.0)

    evaluate(signal, frame)

    assert signal.outcome == OUTCOME_STOP
    assert signal.result_r == -1.0


def test_una_senal_reciente_queda_en_curso():
    closes = path_closes([(0, 100.0), (10, 102.0)])
    frame = frame_from_closes(closes, timeframe="4h")
    signal = make_signal(frame, stop=90.0)

    evaluate(signal, frame)

    assert signal.outcome == OUTCOME_OPEN
    assert signal.result_r is not None  # resultado provisional


def test_append_no_duplica_senales():
    log: list[LoggedSignal] = []
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)

    assert append_new(log, [entry], now=NOW) == 1
    assert append_new(log, [entry], now=NOW) == 0
    assert len(log) == 1
    assert log[0].symbol == "BTC/USDT"
    assert log[0].stop == 58000.0


def test_los_no_senal_no_se_registran():
    log: list[LoggedSignal] = []
    radar = make_entry([0.9, 0.8, 0.1, 0.1, 0.1], is_signal=False)
    assert append_new(log, [radar], now=NOW) == 0


def test_persistencia_ida_y_vuelta(tmp_path):
    cfg = Config(
        {
            "paths": {"cache_dir": "data/cache", "reports_dir": str(tmp_path)},
            "exchanges": {"primary": {"id": "binance", "quote": "USDT"}},
            "universe": {"bases": ["BTC"]},
            "timeframes": {"context": "1d", "structure": "4h", "timing": "1h"},
            "history": {"start_date": "2022-01-01", "page_limit": 1000},
        }
    )
    entry = make_entry([0.9, 0.8, 0.7, 0.1, 0.1], is_signal=True)

    log = update_log(cfg, [entry], {}, now=NOW)
    assert len(log) == 1
    assert (tmp_path / "signals.json").is_file()

    # Segunda pasada: no duplica y conserva.
    log2 = update_log(cfg, [entry], {}, now=NOW)
    assert len(log2) == 1

    reloaded = load_log(cfg)
    assert reloaded[0].symbol == "BTC/USDT"
    save_log(cfg, reloaded)  # idempotente


def test_summary_stats():
    frame_win = frame_from_closes(path_closes([(0, 100.0), (20, 140.0)]), timeframe="4h")
    frame_loss = frame_from_closes(path_closes([(0, 100.0), (20, 80.0)]), timeframe="4h")
    win = make_signal(frame_win, stop=95.0)
    loss = make_signal(frame_loss, stop=95.0)
    evaluate(win, frame_win)
    evaluate(loss, frame_loss)

    stats = summary_stats([win, loss])

    assert stats["closed"] == 2
    assert stats["wins"] == 1 and stats["losses"] == 1
    assert stats["total_r"] == 1.0  # +2R −1R


def test_la_seccion_del_forward_test_aparece_en_la_web():
    from ehs.report.web import render_html
    from tests_report_fixtures import make_config

    frame = frame_from_closes(path_closes([(0, 100.0), (20, 140.0)]), timeframe="4h")
    signal = make_signal(frame, stop=95.0)
    evaluate(signal, frame)

    page = render_html([], [], cfg=make_config(), now=NOW, signals_log=[signal])

    assert "Forward test" in page
    assert "objetivo +2R" in page
    assert "resultado acumulado" in page


def test_la_seccion_vacia_explica_que_es():
    from ehs.report.web import render_html
    from tests_report_fixtures import make_config

    page = render_html([], [], cfg=make_config(), now=NOW, signals_log=[])
    assert "Forward test" in page
    assert "quedará apuntada aquí" in page
