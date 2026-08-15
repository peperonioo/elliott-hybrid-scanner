"""Tests del backtest: costes, salidas, métricas, baselines y walk-forward.

Los costes se verifican contra números calculados a mano, no contra la propia
implementación. Es la parte que decide si el sistema tiene ventaja o no, así
que no puede validarse consigo misma.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from ehs.backtest.baselines import buy_and_hold, direction_mix, random_baseline, random_trades
from ehs.backtest.engine import (
    EXIT_STOP,
    EXIT_TARGET,
    EXIT_TIMEOUT,
    CostModel,
    ExitRules,
    SkipReason,
    run_signals,
    simulate_trade,
    trades_to_frame,
)
from ehs.backtest.metrics import annualised_sharpe, compute_metrics, equity_curve, max_drawdown
from ehs.backtest.walkforward import make_folds, trades_for, walk_forward
from ehs.config import Config, project_root
from ehs.elliott.validator import BEARISH, BULLISH
from helpers import frame_from_closes, path_closes

COSTS = CostModel(taker_fee_pct=0.26, slippage_pct=0.05, spread_pct=0.03)
FREE = CostModel(taker_fee_pct=0.0, slippage_pct=0.0, spread_pct=0.0)
RULES = ExitRules(target_r=2.0, max_bars=30)


def flat_frame(closes, *, wick=0.0, start="2024-01-01"):
    return frame_from_closes(closes, start=start, timeframe="4h", wick=wick)


# --------------------------------------------------------------------------
# Modelo de costes
# --------------------------------------------------------------------------


def test_el_coste_por_lado_suma_comision_slippage_y_spread():
    assert COSTS.per_side_pct == pytest.approx(0.34)
    assert COSTS.round_trip_pct == pytest.approx(0.68)


def test_una_operacion_plana_pierde_exactamente_el_coste_de_ida_y_vuelta():
    """Entrar y salir al mismo precio debe costar el viaje completo."""
    frame = flat_frame(np.full(10, 100.0))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=90.0,
        rules=ExitRules(target_r=2.0, max_bars=5),
        costs=COSTS,
    )

    assert trade.gross_return == pytest.approx(0.0)
    # (1 - 0.0034)² - 1: se paga 0.34% al entrar y otro 0.34% al salir.
    esperado = 0.9966**2 - 1
    assert trade.net_return == pytest.approx(esperado)
    assert trade.net_return == pytest.approx(-0.006788, abs=1e-5)
    # Aproximadamente el coste de ida y vuelta anunciado.
    assert abs(trade.net_return) == pytest.approx(COSTS.round_trip_pct / 100, abs=2e-5)


def test_los_costes_penalizan_igual_en_corto():
    frame = flat_frame(np.full(10, 100.0))
    corto = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BEARISH,
        stop_price=110.0,
        rules=ExitRules(target_r=2.0, max_bars=5),
        costs=COSTS,
    )
    assert corto.gross_return == pytest.approx(0.0)
    # Idéntico al largo: el modelo no puede penalizar más a un lado que a otro.
    assert corto.net_return == pytest.approx(0.9966**2 - 1)


def test_sin_costes_bruto_y_neto_coinciden():
    frame = flat_frame(path_closes([(0, 100.0), (9, 110.0)]))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=95.0,
        rules=ExitRules(target_r=99.0, max_bars=8),
        costs=FREE,
    )
    assert trade.net_return == pytest.approx(trade.gross_return)


def test_los_costes_se_leen_del_yaml():
    cfg = Config.load(project_root() / "config.yaml")
    costs = CostModel.from_config(cfg)
    assert costs.taker_fee_pct == 0.26
    assert costs.round_trip_pct == pytest.approx(0.68)


# --------------------------------------------------------------------------
# Reglas de salida
# --------------------------------------------------------------------------


def test_la_entrada_ocurre_en_la_apertura_de_la_vela_siguiente():
    """Nunca al cierre de la vela que generó la señal: no era operable."""
    frame = flat_frame(path_closes([(0, 100.0), (9, 130.0)]))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=3,
        direction=BULLISH,
        stop_price=95.0,
        rules=ExitRules(target_r=2.0, max_bars=5),  # horizonte dentro de los datos
        costs=FREE,
    )
    assert trade.entry_index == 4
    assert trade.entry_price == pytest.approx(frame["open"].iloc[4])


def test_el_stop_corta_la_operacion():
    frame = flat_frame(path_closes([(0, 100.0), (10, 80.0), (20, 100.0)]))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=95.0,
        rules=RULES,
        costs=FREE,
    )
    assert trade.exit_reason == EXIT_STOP
    assert trade.exit_price == 95.0
    assert trade.gross_return < 0


def test_el_objetivo_se_calcula_como_multiplo_del_riesgo():
    frame = flat_frame(path_closes([(0, 100.0), (20, 140.0)]))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=90.0,
        rules=ExitRules(target_r=2.0, max_bars=25),
        costs=FREE,
    )
    riesgo = trade.entry_price - 90.0
    assert trade.target_price == pytest.approx(trade.entry_price + 2 * riesgo)
    assert trade.exit_reason == EXIT_TARGET


def test_el_cierre_por_tiempo_usa_el_cierre_de_la_ultima_vela():
    frame = flat_frame(path_closes([(0, 100.0), (40, 103.0)]))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=90.0,
        rules=ExitRules(target_r=10.0, max_bars=5),
        costs=FREE,
    )
    assert trade.exit_reason == EXIT_TIMEOUT
    assert trade.bars_held == 5
    assert trade.exit_price == pytest.approx(frame["close"].iloc[trade.exit_index])


def test_ante_stop_y_objetivo_en_la_misma_vela_gana_el_stop():
    """No conocemos el orden intrabar; suponer lo contrario sería regalarse el
    resultado favorable."""
    frame = flat_frame(np.full(10, 100.0))
    # Vela que toca ambos extremos.
    frame.iloc[2, frame.columns.get_loc("high")] = 130.0
    frame.iloc[2, frame.columns.get_loc("low")] = 80.0

    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=90.0,
        rules=ExitRules(target_r=2.0, max_bars=5),
        costs=FREE,
    )
    assert trade.exit_reason == EXIT_STOP


def test_un_corto_se_resuelve_en_espejo():
    frame = flat_frame(path_closes([(0, 100.0), (20, 60.0)]))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BEARISH,
        stop_price=110.0,
        rules=ExitRules(target_r=2.0, max_bars=25),
        costs=FREE,
    )
    assert trade.exit_reason == EXIT_TARGET
    assert trade.gross_return > 0


# --------------------------------------------------------------------------
# Descartes
# --------------------------------------------------------------------------


def test_una_invalidacion_del_lado_equivocado_descarta_la_operacion():
    """Un largo no puede tener el stop por encima de la entrada."""
    frame = flat_frame(np.full(10, 100.0))
    resultado = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=110.0,
        rules=RULES,
        costs=FREE,
    )
    assert resultado == SkipReason.STOP_WRONG_SIDE


def test_sin_vela_siguiente_no_hay_entrada():
    frame = flat_frame(np.full(5, 100.0))
    resultado = simulate_trade(
        frame,
        symbol="X",
        signal_index=4,
        direction=BULLISH,
        stop_price=90.0,
        rules=RULES,
        costs=FREE,
    )
    assert resultado == SkipReason.NO_NEXT_BAR


# --------------------------------------------------------------------------
# Métricas
# --------------------------------------------------------------------------


class FakeTrade:
    """Operación mínima para probar las métricas sin simular precios."""

    def __init__(self, net, *, bars=5, reason=EXIT_TARGET, direction=BULLISH, day=1):
        self.net_return = net
        self.gross_return = net
        self.exit_reason = reason
        self.direction = direction
        self.symbol = "X"
        self.entry_time = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(day, unit="D")
        self.exit_time = self.entry_time + pd.Timedelta(bars, unit="D")
        self.entry_index = 0
        self.exit_index = bars
        self.bars_held = bars


def test_metricas_sobre_un_conjunto_conocido():
    trades = [
        FakeTrade(0.10, day=1),
        FakeTrade(-0.05, day=10),
        FakeTrade(0.20, day=20),
        FakeTrade(-0.05, day=30),
    ]
    m = compute_metrics(trades)

    assert m.n_trades == 4
    assert m.win_rate == pytest.approx(0.5)
    assert m.profit_factor == pytest.approx(0.30 / 0.10)
    assert m.expectancy == pytest.approx(0.05)
    assert m.best == pytest.approx(0.20)
    assert m.worst == pytest.approx(-0.05)


def test_el_profit_factor_es_infinito_sin_perdidas():
    assert compute_metrics([FakeTrade(0.1), FakeTrade(0.2)]).profit_factor == np.inf


def test_la_curva_de_capital_compone():
    curva = equity_curve([FakeTrade(0.10, day=1), FakeTrade(0.10, day=5)])
    assert curva.iloc[-1] == pytest.approx(1.21)


def test_el_drawdown_maximo():
    curva = pd.Series([1.0, 1.5, 0.9, 1.2])
    assert max_drawdown(curva) == pytest.approx(0.4)


def test_sin_operaciones_las_metricas_no_fallan():
    m = compute_metrics([])
    assert m.n_trades == 0
    assert m.summary() == "sin operaciones"


def test_el_sharpe_se_anualiza_con_la_frecuencia_observada():
    """Dos sistemas con los mismos retornos pero distinta frecuencia no pueden
    tener el mismo Sharpe."""
    frecuente = [FakeTrade(0.02 * (-1) ** i, day=i) for i in range(1, 40)]
    esporadico = [FakeTrade(0.02 * (-1) ** i, day=i * 30) for i in range(1, 40)]

    assert abs(annualised_sharpe(frecuente)) > abs(annualised_sharpe(esporadico))


def test_la_distribucion_se_reporta_ademas_de_la_media():
    m = compute_metrics([FakeTrade(v, day=i) for i, v in enumerate([0.5, -0.02, -0.02, -0.02], 1)])
    assert m.expectancy > 0  # la media la escribe un único resultado
    assert m.median_return < 0  # la mediana lo desmiente
    assert set(m.percentiles) == {5, 25, 50, 75, 95}


# --------------------------------------------------------------------------
# Baselines
# --------------------------------------------------------------------------


def test_buy_and_hold_paga_costes():
    frame = flat_frame(path_closes([(0, 100.0), (50, 200.0)]))
    resultado = buy_and_hold(frame, "X", COSTS)

    assert resultado.gross_return == pytest.approx(1.0, abs=0.02)
    assert resultado.net_return < resultado.gross_return


def test_las_senales_aleatorias_replican_par_y_direccion():
    frame = flat_frame(path_closes([(0, 100.0), (300, 150.0)]))
    plantilla = [
        simulate_trade(
            frame,
            symbol="X",
            signal_index=10,
            direction=BULLISH,
            stop_price=95.0,
            rules=RULES,
            costs=FREE,
        )
    ]
    aleatorias = random_trades(
        {"X": frame}, plantilla, rules=RULES, costs=FREE, rng=np.random.default_rng(0)
    )

    assert len(aleatorias) == 1
    assert aleatorias[0].direction == BULLISH
    assert aleatorias[0].symbol == "X"


def test_el_baseline_aleatorio_produce_p_valor_y_veredicto():
    frame = flat_frame(path_closes([(0, 100.0), (400, 160.0)]))
    plantilla, _ = run_signals(frame, [], rules=RULES, costs=FREE)
    plantilla = [
        simulate_trade(
            frame,
            symbol="X",
            signal_index=i,
            direction=BULLISH,
            stop_price=frame["open"].iloc[i + 1] * 0.95,
            rules=RULES,
            costs=FREE,
        )
        for i in (10, 60, 110, 160, 210)
    ]
    resultado = random_baseline({"X": frame}, plantilla, rules=RULES, costs=FREE, trials=50, seed=1)

    assert resultado.trials == 50
    assert 0.0 < resultado.p_value_expectancy <= 1.0
    assert 0.0 <= resultado.percentile <= 100.0
    assert "azar" in resultado.verdict()


def test_el_p_valor_nunca_es_cero():
    """Con simulaciones finitas, un p-valor de 0 sería engañoso."""
    frame = flat_frame(path_closes([(0, 100.0), (400, 160.0)]))
    plantilla = [
        simulate_trade(
            frame,
            symbol="X",
            signal_index=10,
            direction=BULLISH,
            stop_price=frame["open"].iloc[11] * 0.99,
            rules=RULES,
            costs=FREE,
        )
    ]
    resultado = random_baseline({"X": frame}, plantilla, rules=RULES, costs=FREE, trials=20, seed=3)
    assert resultado.p_value_expectancy >= 1 / 21


def test_sin_operaciones_no_hay_baseline_aleatorio():
    assert random_baseline({}, [], rules=RULES, costs=FREE, trials=10) is None


def test_la_mezcla_de_direcciones():
    trades = [FakeTrade(0.1, direction=BULLISH), FakeTrade(0.1, direction=BEARISH)]
    assert direction_mix(trades) == {BULLISH: 1, BEARISH: 1}


# --------------------------------------------------------------------------
# Walk-forward
# --------------------------------------------------------------------------


def test_los_folds_ruedan_sin_solapar_entrenamiento_y_prueba():
    folds = make_folds(
        pd.Timestamp("2022-01-01", tz="UTC"),
        pd.Timestamp("2024-01-01", tz="UTC"),
        train_months=12,
        test_months=3,
    )

    assert len(folds) == 4
    for fold in folds:
        assert fold.train_end == fold.test_start
        assert fold.train_start < fold.train_end < fold.test_end
    # Cada tramo de prueba empieza donde acabó el anterior.
    for anterior, siguiente in pairwise(folds):
        assert siguiente.test_start == anterior.test_end


def test_no_se_generan_folds_sin_histórico_suficiente():
    folds = make_folds(
        pd.Timestamp("2023-01-01", tz="UTC"),
        pd.Timestamp("2023-06-01", tz="UTC"),
        train_months=12,
        test_months=3,
    )
    assert folds == []


class FakeSignal:
    """Señal mínima: lo único que mira el walk-forward es cuándo y cuántos
    factores tenía activos."""

    def __init__(self, timestamp, n_active, direction=BULLISH, invalidation=95.0):
        self.timestamp = timestamp
        self.symbol = "X"
        self.signal_direction = direction
        self.signal_invalidation = invalidation
        self.active_factors = tuple(range(n_active))
        self.score = 0.5


def test_trades_for_filtra_por_ventana_y_por_factores():
    frame = flat_frame(path_closes([(0, 100.0), (400, 160.0)]))
    señales = [
        FakeSignal(frame.index[10], 2),
        FakeSignal(frame.index[100], 4),
        FakeSignal(frame.index[200], 4),
    ]

    todas = trades_for(
        {"X": señales},
        {"X": frame},
        min_active=2,
        start=frame.index[0],
        end=frame.index[-1],
        rules=RULES,
        costs=FREE,
    )
    exigente = trades_for(
        {"X": señales},
        {"X": frame},
        min_active=4,
        start=frame.index[0],
        end=frame.index[-1],
        rules=RULES,
        costs=FREE,
    )
    ventana = trades_for(
        {"X": señales},
        {"X": frame},
        min_active=2,
        start=frame.index[0],
        end=frame.index[50],
        rules=RULES,
        costs=FREE,
    )

    assert len(todas) == 3
    assert len(exigente) == 2
    assert len(ventana) == 1


def test_el_walk_forward_solo_reporta_los_tramos_de_prueba():
    # 4001 velas de 4h ≈ 666 días: da para un par de folds de 12+3 meses.
    frame = flat_frame(path_closes([(0, 100.0), (4000, 300.0)]), start="2022-01-01")
    señales = [FakeSignal(frame.index[i], 3) for i in range(20, 3900, 40)]
    folds = make_folds(frame.index[0], frame.index[-1], train_months=12, test_months=3)
    assert folds

    resultado = walk_forward(
        {"X": señales},
        {"X": frame},
        folds=folds,
        grid=[2, 3, 4],
        rules=RULES,
        costs=FREE,
        default_min_active=3,
        min_train_trades=3,
    )

    assert len(resultado.folds) == len(folds)
    for fold_result in resultado.folds:
        for trade in fold_result.test_trades:
            assert trade.entry_time >= fold_result.fold.test_start
    assert resultado.metrics.n_trades == len(resultado.test_trades)


def test_sin_entrenamiento_suficiente_se_usa_el_valor_por_defecto():
    frame = flat_frame(path_closes([(0, 100.0), (4000, 300.0)]), start="2022-01-01")
    folds = make_folds(frame.index[0], frame.index[-1], train_months=12, test_months=3)

    resultado = walk_forward(
        {"X": []},
        {"X": frame},
        folds=folds,
        grid=[2, 3, 4],
        rules=RULES,
        costs=FREE,
        default_min_active=3,
        min_train_trades=10,
    )

    assert all(f.chosen_min_active == 3 for f in resultado.folds)
    assert all(f.chosen_by == "por defecto" for f in resultado.folds)


# --------------------------------------------------------------------------
# Solapamiento y volcado
# --------------------------------------------------------------------------


def test_no_se_abren_operaciones_solapadas_por_defecto():
    frame = flat_frame(path_closes([(0, 100.0), (400, 160.0)]))
    señales = [FakeSignal(frame.index[i], 3) for i in (10, 11, 12)]

    trades, descartes = run_signals(frame, señales, rules=RULES, costs=FREE)

    assert len(trades) == 1
    assert descartes["solapada"] == 2


def test_con_allow_overlap_se_permiten():
    frame = flat_frame(path_closes([(0, 100.0), (400, 160.0)]))
    señales = [FakeSignal(frame.index[i], 3) for i in (10, 11, 12)]

    trades, _ = run_signals(frame, señales, rules=RULES, costs=FREE, allow_overlap=True)
    assert len(trades) == 3


def test_volcado_a_dataframe():
    frame = flat_frame(path_closes([(0, 100.0), (400, 160.0)]))
    trades, _ = run_signals(frame, [FakeSignal(frame.index[10], 3)], rules=RULES, costs=FREE)
    salida = trades_to_frame(trades)

    assert len(salida) == 1
    assert "net_return" in salida.columns
    assert trades_to_frame([]).empty


def test_las_reglas_de_salida_se_leen_del_yaml():
    cfg = Config.load(project_root() / "config.yaml")
    rules = ExitRules.from_config(cfg)
    assert rules.target_r == 2.0
    assert rules.max_bars == 30


# --------------------------------------------------------------------------
# Entrada limitada, filtros y costes maker/taker
# --------------------------------------------------------------------------

from ehs.backtest.engine import ENTRY_LIMIT_ZONE, EntryRules, TradeFilters  # noqa: E402

LIMIT = EntryRules(mode=ENTRY_LIMIT_ZONE, limit_valid_bars=10)


def test_la_limitada_solo_se_ejecuta_si_el_precio_visita_la_zona():
    # El precio sube sin retroceder: la limitada por debajo nunca se toca.
    frame = flat_frame(path_closes([(0, 100.0), (30, 150.0)]))
    resultado = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=80.0,
        rules=RULES,
        costs=FREE,
        entry=LIMIT,
        limit_price=95.0,
    )
    assert resultado == SkipReason.NOT_FILLED


def test_la_limitada_entra_al_precio_de_la_zona_cuando_el_precio_la_visita():
    # Retrocede hasta 94 en la vela 5 y luego sube.
    frame = flat_frame(path_closes([(0, 100.0), (5, 94.0), (30, 150.0)]))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=80.0,
        rules=ExitRules(target_r=2.0, max_bars=28),
        costs=FREE,
        entry=LIMIT,
        limit_price=95.0,
    )
    assert not isinstance(trade, str)
    assert trade.entry_price == pytest.approx(95.0)
    assert trade.entry_index <= 5


def test_una_limitada_marketable_se_ejecuta_al_abrir_pagando_taker():
    """Si el precio ya está por debajo del nivel, la orden cruza el libro."""
    frame = flat_frame(path_closes([(0, 90.0), (30, 150.0)]))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=70.0,
        rules=ExitRules(target_r=2.0, max_bars=28),
        costs=COSTS,
        entry=LIMIT,
        limit_price=95.0,
    )
    assert not isinstance(trade, str)
    assert trade.entry_price == pytest.approx(frame["open"].iloc[1])
    # Entrada agresiva (0.34) aunque la orden fuese limitada.
    assert trade.cost_pct >= COSTS.aggressive_pct


def test_sin_zona_la_entrada_limitada_no_puede_operar():
    frame = flat_frame(np.full(20, 100.0))
    resultado = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=90.0,
        rules=RULES,
        costs=FREE,
        entry=LIMIT,
        limit_price=None,
    )
    assert resultado == SkipReason.NO_ZONE


def test_la_entrada_maker_y_salida_en_objetivo_pagan_el_coste_reducido():
    """Limitada + objetivo: 0.16 + 0.16 = 0.32% frente al 0.68% agresivo."""
    frame = flat_frame(path_closes([(0, 100.0), (5, 94.0), (30, 160.0)]))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=85.0,
        rules=ExitRules(target_r=2.0, max_bars=28),
        costs=COSTS,
        entry=LIMIT,
        limit_price=95.0,
    )
    assert not isinstance(trade, str)
    assert trade.exit_reason == EXIT_TARGET
    assert trade.cost_pct == pytest.approx(2 * COSTS.maker_fee_pct)


def test_el_stop_paga_salida_agresiva_aunque_la_entrada_fuese_maker():
    frame = flat_frame(path_closes([(0, 100.0), (5, 94.0), (15, 70.0)]))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=88.0,
        rules=ExitRules(target_r=5.0, max_bars=28),
        costs=COSTS,
        entry=LIMIT,
        limit_price=95.0,
    )
    assert not isinstance(trade, str)
    assert trade.exit_reason == EXIT_STOP
    assert trade.cost_pct == pytest.approx(COSTS.maker_fee_pct + COSTS.aggressive_pct)


def test_el_filtro_de_direccion_descarta_cortos():
    frame = flat_frame(np.full(20, 100.0))
    solo_largos = TradeFilters(directions=("bullish",))
    resultado = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BEARISH,
        stop_price=110.0,
        rules=RULES,
        costs=FREE,
        filters=solo_largos,
    )
    assert resultado == SkipReason.DIRECTION_FILTERED


def test_el_filtro_recompensa_coste_descarta_objetivos_pequenos():
    """Stop pegado -> objetivo pegado -> el recorrido no cubre el peaje."""
    frame = flat_frame(np.full(20, 100.0), wick=0.0)
    exigente = TradeFilters(min_reward_cost_ratio=4.0)
    resultado = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=99.7,  # riesgo 0.3% -> objetivo 0.6% < 4×0.68%
        rules=ExitRules(target_r=2.0, max_bars=10),
        costs=COSTS,
        filters=exigente,
    )
    assert resultado == SkipReason.REWARD_TOO_SMALL


def test_el_filtro_recompensa_coste_deja_pasar_objetivos_suficientes():
    frame = flat_frame(path_closes([(0, 100.0), (19, 120.0)]))
    exigente = TradeFilters(min_reward_cost_ratio=4.0)
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=95.0,  # riesgo ~5% -> objetivo ~10% > 2.72%
        rules=ExitRules(target_r=2.0, max_bars=18),
        costs=COSTS,
        filters=exigente,
    )
    assert not isinstance(trade, str)


# --------------------------------------------------------------------------
# Fixes de la auditoría matemática (2026-08-15)
# --------------------------------------------------------------------------


def test_el_drawdown_cuenta_desde_el_capital_inicial():
    """[-5%, +10%] tiene un drawdown real del 5% aunque la curva acabe en positivo."""
    curva = pd.Series([0.95, 1.045])
    assert max_drawdown(curva) == pytest.approx(0.05)


def test_sin_desenlace_dentro_de_los_datos_no_hay_operacion():
    """Si la serie acaba antes del horizonte sin tocar stop ni objetivo, el
    desenlace es desconocido: contarlo como 'tiempo' censuraría la operación."""
    frame = flat_frame(path_closes([(0, 100.0), (9, 101.0)]))  # 10 velas, sin movimiento
    resultado = simulate_trade(
        frame,
        symbol="X",
        signal_index=3,
        direction=BULLISH,
        stop_price=95.0,
        rules=RULES,  # max_bars=30 > velas disponibles
        costs=FREE,
    )
    assert resultado == SkipReason.UNRESOLVED


def test_si_el_stop_se_toca_antes_del_fin_de_datos_si_hay_operacion():
    frame = flat_frame(path_closes([(0, 100.0), (5, 90.0), (9, 90.0)]))
    trade = simulate_trade(
        frame,
        symbol="X",
        signal_index=0,
        direction=BULLISH,
        stop_price=95.0,
        rules=RULES,
        costs=FREE,
    )
    assert trade.exit_reason == "stop"
