"""Capa de confluencia: cinco factores independientes sobre un conteo de Elliott.

Aquí está el valor real del sistema. La fase 3 dice qué es estructuralmente
posible —y sobre datos reales eso todavía deja un 9% de las ventanas—, así que
la decisión la toma esta capa.

## Regla de emisión

El score final es la media ponderada de los cinco factores, pero **no es la
condición de emisión**. Se exige que al menos `min_active_factors` superen su
propio umbral. Un solo factor muy fuerte no emite señal por muy alto que
puntúe: la idea es confluencia, no un máximo aislado.

## Dirección de la señal

Un detalle que la especificación no fijaba y que cambia el signo de todo: la
dirección de la señal **no** es la dirección del conteo.

  - Cinco ondas completas (impulso o diagonal): el movimiento ha terminado, así
    que lo que se espera es el giro. Señal contraria al conteo.
  - Corrección A-B-C completa: la corrección ha terminado y se espera que se
    reanude la tendencia previa. También contraria a la dirección del A-B-C.
  - Impulso parcial 1-2-3: la estructura sigue viva; se espera la onda 4 contra
    y después la 5 a favor. Señal **a favor** del conteo (comprar el retroceso).

## Ausencia de lookahead bias

Cada factor recibe únicamente velas ya cerradas en el instante evaluado. El
punto delicado no son los swings —eso ya lo resuelve la fase 2— sino el desfase
entre timeframes: al evaluar la vela de 4h de las 08:00, la vela diaria de hoy
todavía no ha cerrado. `ehs.data.schema.closed_candles` es lo que lo impide, y
hay un test dedicado a ello.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ehs.config import Config
from ehs.data.schema import close_time_ms, closed_candles
from ehs.elliott.validator import (
    BEARISH,
    BULLISH,
    CORRECTIVE_ABC,
    DIAGONAL_HYPOTHESES,
    IMPULSE,
    IMPULSE_PARTIAL,
    Wave,
    WaveCount,
)
from ehs.structure.indicators import ema, wilder_atr, wilder_rsi
from ehs.structure.swings import HIGH, Pivot, detect_swings

LOGGER = logging.getLogger(__name__)

FIBONACCI = "fibonacci"
RSI_DIVERGENCE = "rsi_divergence"
MARKET_STRUCTURE = "market_structure"
VOLUME_PROFILE = "volume_profile"
HIGHER_TIMEFRAME_TREND = "higher_timeframe_trend"

FACTOR_NAMES: tuple[str, ...] = (
    FIBONACCI,
    RSI_DIVERGENCE,
    MARKET_STRUCTURE,
    VOLUME_PROFILE,
    HIGHER_TIMEFRAME_TREND,
)

# Conteos de cinco ondas: completados, anticipan giro.
COMPLETED_FIVE = (IMPULSE, *DIAGONAL_HYPOTHESES)


# ---------------------------------------------------------------------------
# Parámetros
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfluenceParams:
    """Parámetros de la capa, normalmente cargados del `config.yaml`."""

    weights: dict[str, float] = field(
        default_factory=lambda: {
            FIBONACCI: 0.25,
            RSI_DIVERGENCE: 0.20,
            MARKET_STRUCTURE: 0.20,
            VOLUME_PROFILE: 0.15,
            HIGHER_TIMEFRAME_TREND: 0.20,
        }
    )
    thresholds: dict[str, float] = field(default_factory=lambda: dict.fromkeys(FACTOR_NAMES, 0.6))
    min_active_factors: int = 3
    rsi_period: int = 14
    atr_period: int = 14

    fib_retracements: tuple[float, ...] = (0.618, 0.786)
    fib_extensions: tuple[float, ...] = (1.618,)
    fib_tolerance_atr: float = 0.75
    fib_clusters: bool = False
    fib_cluster_bonus: float = 0.15

    divergence_full_scale: float = 10.0

    structure_lookback_bars: int = 20
    # El ZigZag del timeframe de contexto necesita su propio umbral: el de la
    # fase 2 está calibrado en 4h y aplicado al diario deja pivotes tan
    # escasos que la estructura casi nunca se rompe.
    context_swing_atr_period: int = 14
    context_swing_atr_threshold: float = 2.0
    context_swing_confirmation_bars: int = 2

    volume_expansion_target: float = 1.5
    volume_contraction_target: float = 0.7

    trend_ema_period: int = 50
    trend_atr_period: int = 14
    trend_strength_atr: float = 2.0

    @classmethod
    def from_config(cls, cfg: Config) -> ConfluenceParams:
        fib = cfg.section("confluence.fibonacci")
        div = cfg.section("confluence.rsi_divergence")
        struct = cfg.section("confluence.market_structure")
        vol = cfg.section("confluence.volume_profile")
        trend = cfg.section("confluence.higher_timeframe_trend")
        return cls(
            weights={k: float(v) for k, v in cfg.section("confluence.weights").items()},
            thresholds={k: float(v) for k, v in cfg.section("confluence.thresholds").items()},
            min_active_factors=int(cfg.get("confluence.min_active_factors", 3)),
            rsi_period=int(cfg.get("confluence.rsi_period", 14)),
            atr_period=int(cfg.get("swings.atr_period", 14)),
            fib_retracements=tuple(float(r) for r in fib.get("retracements", [0.618, 0.786])),
            fib_extensions=tuple(float(e) for e in fib.get("extensions", [1.618])),
            fib_tolerance_atr=float(fib.get("tolerance_atr", 0.75)),
            fib_clusters=bool(fib.get("clusters", False)),
            fib_cluster_bonus=float(fib.get("cluster_bonus", 0.15)),
            divergence_full_scale=float(div.get("full_scale_points", 10.0)),
            structure_lookback_bars=int(struct.get("lookback_bars", 20)),
            context_swing_atr_period=int(struct.get("swing_atr_period", 14)),
            context_swing_atr_threshold=float(struct.get("swing_atr_threshold", 2.0)),
            context_swing_confirmation_bars=int(struct.get("swing_confirmation_bars", 2)),
            volume_expansion_target=float(vol.get("expansion_target", 1.5)),
            volume_contraction_target=float(vol.get("contraction_target", 0.7)),
            trend_ema_period=int(trend.get("ema_period", 50)),
            trend_atr_period=int(trend.get("atr_period", 14)),
            trend_strength_atr=float(trend.get("strength_atr", 2.0)),
        )


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FactorScore:
    """Puntuación de un factor, normalizada 0-1 e independiente del resto."""

    name: str
    score: float
    threshold: float
    weight: float
    detail: str

    @property
    def active(self) -> bool:
        return self.score >= self.threshold

    def __str__(self) -> str:
        marca = "✔" if self.active else "·"
        return (
            f"{marca} {self.name}: {self.score:.3f} (umbral {self.threshold:.2f}) — {self.detail}"
        )


@dataclass(frozen=True)
class ConfluenceResult:
    """Evaluación completa de un conteo en un instante concreto."""

    symbol: str
    timeframe: str
    timestamp: pd.Timestamp
    price: float
    count: WaveCount
    signal_direction: str
    factors: tuple[FactorScore, ...]
    min_active_factors: int
    zone: tuple[float, float] | None
    # Dos niveles distintos y fáciles de confundir: uno mata el conteo, el otro
    # mata la señal. El stop de una operación es siempre el segundo.
    count_invalidation: float | None
    signal_invalidation: float

    @property
    def active_factors(self) -> tuple[FactorScore, ...]:
        return tuple(factor for factor in self.factors if factor.active)

    @property
    def score(self) -> float:
        total = sum(factor.weight for factor in self.factors)
        if total <= 0:
            return 0.0
        return sum(f.score * f.weight for f in self.factors) / total

    @property
    def emits_signal(self) -> bool:
        """Confluencia, no un máximo aislado: N factores por encima de umbral."""
        return len(self.active_factors) >= self.min_active_factors

    def summary(self) -> str:
        estado = "SEÑAL" if self.emits_signal else "sin señal"
        return (
            f"[{estado}] {self.symbol} {self.timeframe} {self.timestamp:%Y-%m-%d %H:%M} "
            f"{self.signal_direction} sobre {self.count.hypothesis} "
            f"— score {self.score:.3f}, {len(self.active_factors)}/{len(self.factors)} factores"
        )


# ---------------------------------------------------------------------------
# Dirección de la señal
# ---------------------------------------------------------------------------


def signal_direction(count: WaveCount) -> str:
    """Sesgo direccional que sugiere el conteo.

    No coincide con `count.direction`: un impulso alcista **completado** no es
    una señal alcista, es la antesala de una corrección.
    """
    opposite = BEARISH if count.direction == BULLISH else BULLISH
    if count.hypothesis in COMPLETED_FIVE or count.hypothesis == CORRECTIVE_ABC:
        return opposite
    # Impulso 1-2-3 en curso: se espera la 4 contra y la 5 a favor.
    return count.direction


def signal_invalidation(count: WaveCount) -> float:
    """Precio que, de alcanzarse, deja sin sentido la señal.

    No es lo mismo que `WaveCount.invalidation_level()`, que es el nivel que
    invalida el **conteo**. Para un impulso alcista completado el conteo muere
    por debajo del origen de la onda 1, pero la señal —bajista, esperando la
    corrección— muere por encima del final de la onda 5. Confundirlos pondría
    el stop de un corto por debajo de la entrada.

      - Cinco ondas o A-B-C completos: la señal es de giro desde el pivote
        terminal, así que se invalida al superarlo.
      - Impulso 1-2-3 en curso: la señal va a favor y el nivel que la sostiene
        es el final de la onda 1, que la onda 4 no puede solapar.
    """
    if count.hypothesis == IMPULSE_PARTIAL:
        return count.waves[0].end.price
    return count.pivots[-1].price


# ---------------------------------------------------------------------------
# Utilidades de puntuación
# ---------------------------------------------------------------------------


def _distance_score(distance: float, tolerance: float) -> float:
    """1.0 en el nivel, cayendo linealmente hasta 0 a `tolerance` de distancia."""
    if tolerance <= 0:
        return 0.0
    return max(0.0, 1.0 - distance / tolerance)


def _ratio_score(value: float, target: float, *, higher_is_better: bool) -> float:
    """Rampa lineal entre 1.0 y `target`, saturando en los extremos."""
    if target == 1.0:
        return 0.0
    if higher_is_better:
        return float(np.clip((value - 1.0) / (target - 1.0), 0.0, 1.0))
    return float(np.clip((1.0 - value) / (1.0 - target), 0.0, 1.0))


def _mean_volume(frame: pd.DataFrame, wave: Wave) -> float:
    segment = frame["volume"].iloc[wave.start.index : wave.end.index + 1]
    return float(segment.mean()) if len(segment) else 0.0


# ---------------------------------------------------------------------------
# Factores
# ---------------------------------------------------------------------------


def fibonacci_levels(count: WaveCount, params: ConfluenceParams) -> list[tuple[str, float]]:
    """Niveles de Fibonacci relevantes para el conteo.

    Además de los retrocesos y extensiones de la última onda, se añaden las
    relaciones **entre ondas** que la teoría considera significativas: la
    igualdad C=A en correcciones (el zigzag tiende a C≈A medido desde el final
    de B) y los retrocesos de la estructura completa cuando las cinco ondas han
    terminado. Cuando varios de estos niveles caen juntos forman un *cluster*,
    y esa confluencia es más significativa que cualquier nivel aislado.
    """
    last = count.waves[-1]
    levels: list[tuple[str, float]] = []

    span = last.end.price - last.start.price
    for ratio in params.fib_retracements:
        levels.append((f"retroceso {ratio}", last.end.price - span * ratio))
    for ratio in params.fib_extensions:
        levels.append((f"extensión {ratio}", last.start.price + span * ratio))

    if not params.fib_clusters:
        return levels

    if count.hypothesis == CORRECTIVE_ABC:
        # Proyección de igualdad: C = A medida desde el final de B.
        wave_a, wave_b = count.waves[0], count.waves[1]
        direction = 1.0 if wave_a.end.price > wave_a.start.price else -1.0
        levels.append(("igualdad C=A", wave_b.end.price + direction * wave_a.length))
        levels.append(("C=1.618·A", wave_b.end.price + direction * wave_a.length * 1.618))
    elif count.hypothesis in COMPLETED_FIVE:
        # Retrocesos de la estructura completa: los imanes clásicos tras un
        # impulso terminado (la zona de la onda 4 previa suele coincidir).
        origin, end = count.pivots[0].price, count.pivots[-1].price
        total = end - origin
        for ratio in (0.382, 0.5, 0.618):
            levels.append((f"retroceso {ratio} del impulso", end - total * ratio))

    return levels


def factor_fibonacci(
    count: WaveCount, price: float, atr: float, params: ConfluenceParams
) -> FactorScore:
    """Proximidad del precio a los niveles de Fibonacci del conteo.

    Con `fib_clusters` activo, la coincidencia de dos o más niveles distintos
    dentro de la tolerancia suma una bonificación: la confluencia de niveles
    independientes es la lectura fuerte, no un ratio suelto.
    """
    levels = fibonacci_levels(count, params)
    tolerance = params.fib_tolerance_atr * atr

    best_name, best_level, best_score = "", float("nan"), 0.0
    in_reach = 0
    for name, level in levels:
        score = _distance_score(abs(price - level), tolerance)
        if score > 0:
            in_reach += 1
        if score > best_score:
            best_name, best_level, best_score = name, level, score

    cluster_note = ""
    if params.fib_clusters and best_score > 0 and in_reach >= 2:
        bonus = params.fib_cluster_bonus * (in_reach - 1)
        best_score = min(1.0, best_score + bonus)
        cluster_note = f" — cluster de {in_reach} niveles (+{bonus:.2f})"

    if best_score == 0.0:
        cercano = min(levels, key=lambda item: abs(price - item[1]))
        detalle = (
            f"precio {price:,.4f} lejos de todo nivel; el más próximo es "
            f"{cercano[0]} en {cercano[1]:,.4f} "
            f"({abs(price - cercano[1]) / atr:.2f} ATR)"
        )
    else:
        detalle = f"precio {price:,.4f} sobre {best_name} en {best_level:,.4f}{cluster_note}"

    return FactorScore(
        name=FIBONACCI,
        score=best_score,
        threshold=params.thresholds.get(FIBONACCI, 0.6),
        weight=params.weights.get(FIBONACCI, 0.0),
        detail=detalle,
    )


def factor_rsi_divergence(
    count: WaveCount, frame: pd.DataFrame, params: ConfluenceParams
) -> FactorScore:
    """Divergencia bajista en la supuesta onda 5, alcista al final de la correctiva.

    Compara los dos extremos relevantes del conteo: en cinco ondas, el final de
    la 3 contra el de la 5; en un A-B-C, el final de A contra el de C.
    """
    threshold = params.thresholds.get(RSI_DIVERGENCE, 0.6)
    weight = params.weights.get(RSI_DIVERGENCE, 0.0)

    if count.hypothesis in COMPLETED_FIVE:
        first, second = count.waves[2].end, count.waves[4].end
    elif count.hypothesis == CORRECTIVE_ABC:
        first, second = count.waves[0].end, count.waves[2].end
    else:
        return FactorScore(
            name=RSI_DIVERGENCE,
            score=0.0,
            threshold=threshold,
            weight=weight,
            detail="un impulso 1-2-3 no tiene todavía dos extremos comparables",
        )

    rsi = wilder_rsi(frame, params.rsi_period)
    rsi_first, rsi_second = rsi.iloc[first.index], rsi.iloc[second.index]
    if np.isnan(rsi_first) or np.isnan(rsi_second):
        return FactorScore(
            name=RSI_DIVERGENCE,
            score=0.0,
            threshold=threshold,
            weight=weight,
            detail="RSI aún sin definir en alguno de los dos extremos",
        )

    higher_high = second.price > first.price
    # Divergencia bajista: precio hace máximo superior y el RSI no lo acompaña.
    if second.kind == HIGH:
        diverges = higher_high and rsi_second < rsi_first
        tipo = "bajista"
    else:
        diverges = second.price < first.price and rsi_second > rsi_first
        tipo = "alcista"

    gap = abs(float(rsi_second) - float(rsi_first))
    score = min(1.0, gap / params.divergence_full_scale) if diverges else 0.0
    detalle = (
        f"divergencia {tipo}: precio {first.price:,.4f}→{second.price:,.4f}, "
        f"RSI {rsi_first:.1f}→{rsi_second:.1f}"
        if diverges
        else (
            f"sin divergencia {tipo}: precio {first.price:,.4f}→{second.price:,.4f}, "
            f"RSI {rsi_first:.1f}→{rsi_second:.1f}"
        )
    )

    return FactorScore(
        name=RSI_DIVERGENCE, score=score, threshold=threshold, weight=weight, detail=detalle
    )


def factor_market_structure(
    direction: str,
    context: pd.DataFrame,
    context_pivots: Sequence[Pivot],
    params: ConfluenceParams,
) -> FactorScore:
    """BOS o CHoCH reciente en el timeframe superior, alineado con la señal.

    BOS (Break of Structure) es la ruptura del último extremo en el sentido de
    la estructura vigente; CHoCH (Change of Character) es la ruptura en sentido
    contrario, que anuncia un posible giro. Para una señal de reversión, el
    CHoCH a favor es la confirmación más valiosa.
    """
    threshold = params.thresholds.get(MARKET_STRUCTURE, 0.6)
    weight = params.weights.get(MARKET_STRUCTURE, 0.0)

    highs = [p for p in context_pivots if p.kind == HIGH]
    lows = [p for p in context_pivots if p.kind != HIGH]
    if len(highs) < 2 or len(lows) < 2 or context.empty:
        return FactorScore(
            name=MARKET_STRUCTURE,
            score=0.0,
            threshold=threshold,
            weight=weight,
            detail="pivotes insuficientes en el timeframe superior",
        )

    last_close = float(context["close"].iloc[-1])
    last_bar = len(context) - 1

    bullish_structure = highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price
    bearish_structure = highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price

    broke_up = last_close > highs[-1].price
    broke_down = last_close < lows[-1].price

    if direction == BULLISH:
        broke = broke_up
        evento = "CHoCH alcista" if bearish_structure else "BOS alcista"
        referencia = highs[-1]
    else:
        broke = broke_down
        evento = "CHoCH bajista" if bullish_structure else "BOS bajista"
        referencia = lows[-1]

    if not broke:
        return FactorScore(
            name=MARKET_STRUCTURE,
            score=0.0,
            threshold=threshold,
            weight=weight,
            detail=(
                f"sin ruptura a favor de {direction}: cierre {last_close:,.4f} "
                f"contra referencia {referencia.price:,.4f}"
            ),
        )

    # La antigüedad se mide desde que ocurrió la ruptura, no desde que se formó
    # el extremo roto. Un BOS es un evento: "reciente" se refiere al momento en
    # que el precio atravesó el nivel, que puede ser meses después de que ese
    # nivel quedara marcado.
    closes = context["close"].to_numpy(dtype="float64")[referencia.index + 1 :]
    crossed = closes > referencia.price if direction == BULLISH else closes < referencia.price
    positions = np.flatnonzero(crossed)
    # `positions` nunca puede venir vacío aquí: `broke` ya lo garantiza.
    break_index = referencia.index + 1 + int(positions[0])

    age = last_bar - break_index
    score = max(0.0, 1.0 - age / max(params.structure_lookback_bars, 1))

    return FactorScore(
        name=MARKET_STRUCTURE,
        score=score,
        threshold=threshold,
        weight=weight,
        detail=(
            f"{evento} sobre {referencia.price:,.4f}, cierre {last_close:,.4f}, "
            f"ruptura hace {age} velas"
        ),
    )


def factor_volume_profile(
    count: WaveCount, frame: pd.DataFrame, params: ConfluenceParams
) -> FactorScore:
    """Perfil de volumen coherente con la fase: expansión en 3, contracción en 4."""
    threshold = params.thresholds.get(VOLUME_PROFILE, 0.6)
    weight = params.weights.get(VOLUME_PROFILE, 0.0)

    if count.hypothesis in COMPLETED_FIVE:
        vol1 = _mean_volume(frame, count.waves[0])
        vol3 = _mean_volume(frame, count.waves[2])
        vol4 = _mean_volume(frame, count.waves[3])
        if vol1 <= 0 or vol3 <= 0:
            score, detalle = 0.0, "volumen nulo en las ondas impulsivas"
        else:
            expansion = _ratio_score(
                vol3 / vol1, params.volume_expansion_target, higher_is_better=True
            )
            contraction = _ratio_score(
                vol4 / vol3, params.volume_contraction_target, higher_is_better=False
            )
            score = (expansion + contraction) / 2
            detalle = (
                f"vol 3/1 = {vol3 / vol1:.2f} (expansión {expansion:.2f}), "
                f"vol 4/3 = {vol4 / vol3:.2f} (contracción {contraction:.2f})"
            )
    elif count.hypothesis == IMPULSE_PARTIAL:
        vol1 = _mean_volume(frame, count.waves[0])
        vol3 = _mean_volume(frame, count.waves[2])
        if vol1 <= 0:
            score, detalle = 0.0, "volumen nulo en la onda 1"
        else:
            score = _ratio_score(vol3 / vol1, params.volume_expansion_target, higher_is_better=True)
            detalle = f"vol 3/1 = {vol3 / vol1:.2f}; la onda 4 aún no existe"
    else:
        vol_a = _mean_volume(frame, count.waves[0])
        vol_b = _mean_volume(frame, count.waves[1])
        if vol_a <= 0:
            score, detalle = 0.0, "volumen nulo en la onda A"
        else:
            score = _ratio_score(
                vol_b / vol_a, params.volume_contraction_target, higher_is_better=False
            )
            detalle = f"vol B/A = {vol_b / vol_a:.2f}; en un zigzag la B se seca"

    return FactorScore(
        name=VOLUME_PROFILE, score=score, threshold=threshold, weight=weight, detail=detalle
    )


def factor_higher_timeframe_trend(
    direction: str, context: pd.DataFrame, params: ConfluenceParams
) -> FactorScore:
    """Alineación de la señal con la tendencia del timeframe de contexto.

    Muchas señales de este sistema son de giro y por tanto contra-tendencia; el
    factor las penaliza a propósito, que es justo su función.
    """
    threshold = params.thresholds.get(HIGHER_TIMEFRAME_TREND, 0.6)
    weight = params.weights.get(HIGHER_TIMEFRAME_TREND, 0.0)

    if len(context) < max(params.trend_ema_period, params.trend_atr_period) + 1:
        return FactorScore(
            name=HIGHER_TIMEFRAME_TREND,
            score=0.0,
            threshold=threshold,
            weight=weight,
            detail="histórico insuficiente en el timeframe de contexto",
        )

    trend_ema = ema(context["close"], params.trend_ema_period)
    trend_atr = wilder_atr(context, params.trend_atr_period)
    close = float(context["close"].iloc[-1])
    reference = float(trend_ema.iloc[-1])
    volatility = float(trend_atr.iloc[-1])

    if np.isnan(reference) or np.isnan(volatility) or volatility <= 0:
        return FactorScore(
            name=HIGHER_TIMEFRAME_TREND,
            score=0.0,
            threshold=threshold,
            weight=weight,
            detail="EMA o ATR sin definir en el timeframe de contexto",
        )

    # Fuerza con signo en [-1, 1]: cuánto se aleja el precio de su EMA, en ATR.
    strength = float(
        np.clip((close - reference) / (volatility * params.trend_strength_atr), -1.0, 1.0)
    )
    sign = 1.0 if direction == BULLISH else -1.0
    score = (1.0 + strength * sign) / 2.0

    return FactorScore(
        name=HIGHER_TIMEFRAME_TREND,
        score=score,
        threshold=threshold,
        weight=weight,
        detail=(
            f"cierre {close:,.4f} contra EMA{params.trend_ema_period} {reference:,.4f} "
            f"(fuerza {strength:+.2f}); señal {direction}"
        ),
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def score_confluence(
    count: WaveCount,
    *,
    structure: pd.DataFrame,
    context: pd.DataFrame,
    symbol: str,
    structure_timeframe: str,
    context_timeframe: str,
    params: ConfluenceParams,
    at: int | None = None,
    swing_kwargs: dict | None = None,
) -> ConfluenceResult:
    """Evalúa los cinco factores sobre un conteo.

    `structure` debe llegar ya recortado a las velas conocidas, o indicarse
    `at` para recortarlo aquí. El frame de contexto se recorta siempre a las
    velas que ya habían cerrado en ese instante.
    """
    if at is not None:
        structure = structure.iloc[: at + 1]
    if structure.empty:
        raise ValueError("el frame de estructura está vacío")

    # Un conteo cuyo último pivote todavía no estaba confirmado en este
    # instante no se conocía: evaluarlo sería leer el futuro. Se falla en vez
    # de puntuar cero, para que el error del llamante no pase desapercibido.
    known_at = count.pivots[-1].confirmed_index
    if known_at > len(structure) - 1:
        raise ValueError(
            f"el conteo no se confirma hasta la vela {known_at}, pero solo se conocen "
            f"{len(structure)}: evaluarlo aquí sería leer el futuro"
        )

    evaluated_at = structure.index[-1]
    now_ms = close_time_ms(evaluated_at, structure_timeframe)
    visible_context = closed_candles(context, context_timeframe, now_ms)

    price = float(structure["close"].iloc[-1])
    atr_series = wilder_atr(structure, params.atr_period)
    atr = float(atr_series.iloc[-1])
    if np.isnan(atr) or atr <= 0:
        raise ValueError("ATR sin definir: la serie de estructura es demasiado corta")

    direction = signal_direction(count)
    swing_kwargs = swing_kwargs or {
        "atr_period": params.context_swing_atr_period,
        "atr_threshold": params.context_swing_atr_threshold,
        "confirmation_bars": params.context_swing_confirmation_bars,
    }
    context_pivots = (
        detect_swings(visible_context, **swing_kwargs) if not visible_context.empty else []
    )

    factors = (
        factor_fibonacci(count, price, atr, params),
        factor_rsi_divergence(count, structure, params),
        factor_market_structure(direction, visible_context, context_pivots, params),
        factor_volume_profile(count, structure, params),
        factor_higher_timeframe_trend(direction, visible_context, params),
    )

    zone = _interest_zone(count, price, atr, params)

    return ConfluenceResult(
        symbol=symbol,
        timeframe=structure_timeframe,
        timestamp=evaluated_at,
        price=price,
        count=count,
        signal_direction=direction,
        factors=factors,
        min_active_factors=params.min_active_factors,
        zone=zone,
        count_invalidation=count.invalidation_level(),
        signal_invalidation=signal_invalidation(count),
    )


def _interest_zone(
    count: WaveCount, price: float, atr: float, params: ConfluenceParams
) -> tuple[float, float] | None:
    """Banda de precio alrededor del nivel de Fibonacci más cercano."""
    last = count.waves[-1]
    span = last.end.price - last.start.price
    levels = [last.end.price - span * r for r in params.fib_retracements]
    levels += [last.start.price + span * e for e in params.fib_extensions]
    if not levels:
        return None
    nearest = min(levels, key=lambda level: abs(price - level))
    margin = params.fib_tolerance_atr * atr
    return (nearest - margin, nearest + margin)
