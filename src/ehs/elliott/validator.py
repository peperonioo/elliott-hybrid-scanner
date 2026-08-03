"""Validador de conteos de Elliott. Enfoque **descartador**, no predictivo.

La pregunta que responde este módulo es "¿es este conteo estructuralmente
posible?", nunca "¿cuál es el conteo correcto?". Recibe una secuencia de
pivotes y devuelve todas las hipótesis compatibles con ella, cada una con su
score. Si la secuencia admite varias lecturas, se devuelven todas marcadas como
ambiguas: inventar una resolución determinista para algo genuinamente ambiguo
sería el error más caro que podría cometer el sistema.

## Nota sobre el número de pivotes

Cinco ondas necesitan **seis** pivotes: el origen más el final de cada onda.
La especificación hablaba de "una secuencia de 5 pivotes"; con cinco pivotes
solo se pueden expresar cuatro tramos, y las reglas duras 2 y 3 —que comparan
las ondas 1, 3 y 5 y el solape de la 4 con la 1— no serían formulables. Se
implementa por tanto sobre longitudes de tramo:

  - 3 tramos (4 pivotes): ambiguo entre corrección A-B-C e impulso incompleto
    1-2-3. Se devuelven las dos hipótesis.
  - 5 tramos (6 pivotes): impulso y/o diagonal.

## Reglas duras (invalidan el conteo)

1. La onda 2 no retrocede más del 100% de la onda 1.
2. La onda 3 nunca es la más corta de las impulsivas (1, 3, 5).
3. La onda 4 no solapa el territorio de precio de la onda 1.

La tercera no se aplica a las diagonales, que se tratan como hipótesis aparte
en lugar de meterlas como excepción dentro de la regla general.

Hay además una condición de forma previa a las reglas —los pivotes deben
alternar máximo y mínimo, y la onda 3 debe superar el final de la onda 1— sin
la cual la secuencia no es un impulso en absoluto. No es una de las tres reglas
nombradas: es lo que hace que hablar de "onda 3" signifique algo.

## Guías blandas (puntúan, no invalidan)

  - La onda 2 suele retroceder entre 0.5 y 0.786 de la onda 1.
  - La onda 3 se extiende con frecuencia hasta 1.618 de la onda 1.
  - Alternancia entre las ondas 2 y 4.

La alternancia se mide con un **proxy**: a este grado no conocemos las subondas,
así que no podemos saber si una corrección es simple o compleja en el sentido
clásico. Se aproxima por la diferencia de profundidad y duración entre ambas.
Está declarado como aproximación en el detalle de cada score, no disimulado.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from ehs.config import Config
from ehs.structure.swings import HIGH, LOW, Pivot

LOGGER = logging.getLogger(__name__)

BULLISH = "bullish"
BEARISH = "bearish"

IMPULSE = "impulse"
DIAGONAL = "diagonal"
CORRECTIVE_ABC = "corrective_abc"
IMPULSE_PARTIAL = "impulse_1_2_3"

IMPULSE_LABELS = ("1", "2", "3", "4", "5")
PARTIAL_LABELS = ("1", "2", "3")
ABC_LABELS = ("A", "B", "C")


class SequenceError(ValueError):
    """La secuencia recibida no tiene la forma mínima para ser analizada."""


# ---------------------------------------------------------------------------
# Estructuras de salida
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Wave:
    """Un tramo entre dos pivotes consecutivos."""

    label: str
    start: Pivot
    end: Pivot

    @property
    def length(self) -> float:
        """Recorrido en precio, siempre positivo."""
        return abs(self.end.price - self.start.price)

    @property
    def direction(self) -> int:
        return 1 if self.end.price > self.start.price else -1

    @property
    def bars(self) -> int:
        return self.end.index - self.start.index

    def __str__(self) -> str:
        return (
            f"onda {self.label}: {self.start.price:,.4f} → {self.end.price:,.4f} "
            f"({self.bars} velas)"
        )


@dataclass(frozen=True)
class RuleResult:
    """Veredicto de una regla dura."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GuideScore:
    """Puntuación de una guía blanda, normalizada 0-1."""

    name: str
    score: float
    weight: float
    detail: str


@dataclass
class WaveCount:
    """Una hipótesis de conteo sobre una secuencia de pivotes."""

    hypothesis: str
    direction: str
    pivots: tuple[Pivot, ...]
    waves: tuple[Wave, ...]
    rules: tuple[RuleResult, ...]
    guides: tuple[GuideScore, ...]
    ambiguous_with: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def valid(self) -> bool:
        """Un conteo es válido si ninguna regla dura lo invalida."""
        return all(rule.passed for rule in self.rules)

    @property
    def violations(self) -> tuple[RuleResult, ...]:
        return tuple(rule for rule in self.rules if not rule.passed)

    @property
    def score(self) -> float:
        """Media ponderada de las guías blandas. 0 si el conteo es inválido."""
        if not self.valid or not self.guides:
            return 0.0
        total_weight = sum(guide.weight for guide in self.guides)
        if total_weight <= 0:
            return 0.0
        return sum(g.score * g.weight for g in self.guides) / total_weight

    @property
    def is_ambiguous(self) -> bool:
        return bool(self.ambiguous_with)

    @property
    def start(self) -> Pivot:
        return self.pivots[0]

    @property
    def end(self) -> Pivot:
        return self.pivots[-1]

    def invalidation_level(self) -> float | None:
        """Precio que, de perderse, invalida este conteo.

        Para un impulso es el origen de la onda 1: si el precio lo atraviesa,
        la regla de la onda 2 queda rota y el conteo deja de ser posible.
        """
        if self.hypothesis in (IMPULSE, DIAGONAL, IMPULSE_PARTIAL):
            return self.pivots[0].price
        return None

    def summary(self) -> str:
        estado = "válido" if self.valid else "INVÁLIDO"
        etiquetas = "-".join(w.label for w in self.waves)
        linea = (
            f"[{estado}] {self.hypothesis} {self.direction} ({etiquetas}) "
            f"score={self.score:.3f}"
        )
        if self.is_ambiguous:
            linea += f" — ambiguo con: {', '.join(self.ambiguous_with)}"
        return linea


# ---------------------------------------------------------------------------
# Funciones de puntuación
# ---------------------------------------------------------------------------


def proximity_score(value: float, target: float, tolerance: float) -> float:
    """1.0 si `value` está a menos de `tolerance` relativo de `target`.

    Decae linealmente hasta 0 a cuatro veces esa distancia. Se prefiere una
    rampa explícita a una gaussiana: es más fácil de razonar al calibrar.
    """
    if target == 0:
        return 0.0
    relative = abs(value - target) / abs(target)
    if relative <= tolerance:
        return 1.0
    span = tolerance * 4
    return max(0.0, 1.0 - (relative - tolerance) / (span - tolerance))


def range_score(value: float, low: float, high: float) -> float:
    """1.0 dentro de [low, high], decayendo hasta 0 a una anchura de distancia."""
    if low <= value <= high:
        return 1.0
    width = high - low
    if width <= 0:
        return 0.0
    distance = (low - value) if value < low else (value - high)
    return max(0.0, 1.0 - distance / width)


# ---------------------------------------------------------------------------
# Forma de la secuencia
# ---------------------------------------------------------------------------


def _sequence_direction(pivots: Sequence[Pivot]) -> str:
    """Un tramo que arranca en un mínimo es alcista, y viceversa."""
    return BULLISH if pivots[0].kind == LOW else BEARISH


def _check_shape(pivots: Sequence[Pivot], expected_legs: int) -> None:
    """Comprueba lo mínimo para que hablar de ondas tenga sentido."""
    if len(pivots) != expected_legs + 1:
        raise SequenceError(
            f"{expected_legs} tramos necesitan {expected_legs + 1} pivotes, "
            f"se han recibido {len(pivots)}"
        )
    if any(a.kind == b.kind for a, b in pairwise(pivots)):
        raise SequenceError("los pivotes deben alternar máximo y mínimo")
    if any(a.index >= b.index for a, b in pairwise(pivots)):
        raise SequenceError("los pivotes deben estar ordenados en el tiempo")
    if any(p.kind not in (HIGH, LOW) for p in pivots):
        raise SequenceError("tipo de pivote desconocido")


def _build_waves(pivots: Sequence[Pivot], labels: Sequence[str]) -> tuple[Wave, ...]:
    return tuple(
        Wave(label=label, start=pivots[i], end=pivots[i + 1]) for i, label in enumerate(labels)
    )


# ---------------------------------------------------------------------------
# Reglas duras
# ---------------------------------------------------------------------------


def _rule_wave2_retracement(waves: tuple[Wave, ...], max_retrace: float) -> RuleResult:
    wave1, wave2 = waves[0], waves[1]
    ratio = wave2.length / wave1.length if wave1.length else float("inf")
    return RuleResult(
        name="onda2_no_retrocede_mas_del_100",
        passed=ratio <= max_retrace,
        detail=f"la onda 2 retrocede {ratio:.3f} de la onda 1 (máximo {max_retrace})",
    )


def _rule_wave3_not_shortest(waves: tuple[Wave, ...]) -> RuleResult:
    len1, len3, len5 = waves[0].length, waves[2].length, waves[4].length
    # "La más corta" significa estrictamente menor que las otras dos.
    is_shortest = len3 < len1 and len3 < len5
    return RuleResult(
        name="onda3_nunca_la_mas_corta",
        passed=not is_shortest,
        detail=f"longitudes 1={len1:,.4f} 3={len3:,.4f} 5={len5:,.4f}",
    )


def _rule_wave4_no_overlap(waves: tuple[Wave, ...], direction: str) -> RuleResult:
    end_wave1 = waves[0].end.price
    end_wave4 = waves[3].end.price
    # Alcista: el mínimo de la onda 4 debe quedar por encima del máximo de la 1.
    passed = end_wave4 > end_wave1 if direction == BULLISH else end_wave4 < end_wave1
    return RuleResult(
        name="onda4_no_solapa_onda1",
        passed=passed,
        detail=(
            f"la onda 4 termina en {end_wave4:,.4f} y la onda 1 en {end_wave1:,.4f} "
            f"(tendencia {direction})"
        ),
    )


def _rule_wave3_exceeds_wave1(waves: tuple[Wave, ...], direction: str) -> RuleResult:
    """Condición de forma: sin esto la secuencia no es un impulso."""
    end_wave1 = waves[0].end.price
    end_wave3 = waves[2].end.price
    passed = end_wave3 > end_wave1 if direction == BULLISH else end_wave3 < end_wave1
    return RuleResult(
        name="onda3_supera_el_final_de_la_onda1",
        passed=passed,
        detail=f"la onda 3 termina en {end_wave3:,.4f} y la onda 1 en {end_wave1:,.4f}",
    )


# ---------------------------------------------------------------------------
# Guías blandas
# ---------------------------------------------------------------------------


def _guide_wave2_retracement(
    waves: tuple[Wave, ...], low: float, high: float, weight: float
) -> GuideScore:
    ratio = waves[1].length / waves[0].length if waves[0].length else 0.0
    return GuideScore(
        name="retroceso_onda2",
        score=range_score(ratio, low, high),
        weight=weight,
        detail=f"retroceso {ratio:.3f}, rango típico {low}-{high}",
    )


def _guide_wave3_extension(
    waves: tuple[Wave, ...], target: float, tolerance: float, weight: float
) -> GuideScore:
    ratio = waves[2].length / waves[0].length if waves[0].length else 0.0
    return GuideScore(
        name="extension_onda3",
        score=proximity_score(ratio, target, tolerance),
        weight=weight,
        detail=f"la onda 3 mide {ratio:.3f} de la onda 1, objetivo {target}",
    )


def _guide_alternation(waves: tuple[Wave, ...], weight: float) -> GuideScore:
    """Proxy de alternancia entre las ondas 2 y 4.

    La alternancia clásica compara si una corrección es simple y la otra
    compleja, y eso exige conocer las subondas. A este grado no las tenemos, así
    que se aproxima por cuánto difieren en profundidad relativa y en duración:
    dos correcciones de carácter distinto tienden a separarse en ambas.
    """
    retrace2 = waves[1].length / waves[0].length if waves[0].length else 0.0
    retrace4 = waves[3].length / waves[2].length if waves[2].length else 0.0
    bars2, bars4 = max(waves[1].bars, 1), max(waves[3].bars, 1)

    depth_gap = abs(retrace2 - retrace4) / max(retrace2, retrace4, 1e-9)
    time_gap = abs(bars2 - bars4) / max(bars2, bars4)
    score = min(1.0, (depth_gap + time_gap) / 2)

    return GuideScore(
        name="alternancia_2_4",
        score=score,
        weight=weight,
        detail=(
            f"proxy: retrocesos {retrace2:.3f} vs {retrace4:.3f}, "
            f"duraciones {bars2} vs {bars4} velas "
            "(aproximación: no conocemos las subondas a este grado)"
        ),
    )


# ---------------------------------------------------------------------------
# Parámetros
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ElliottParams:
    """Parámetros del validador, normalmente cargados del `config.yaml`."""

    wave2_max_retrace: float = 1.0
    wave3_never_shortest: bool = True
    wave4_no_overlap_wave1: bool = True
    allow_diagonals: bool = True
    wave2_retrace_range: tuple[float, float] = (0.5, 0.786)
    wave3_extension_target: float = 1.618
    ratio_tolerance: float = 0.05
    weight_wave2_retracement: float = 0.35
    weight_wave3_extension: float = 0.40
    weight_alternation: float = 0.25

    @classmethod
    def from_config(cls, cfg: Config) -> ElliottParams:
        hard = cfg.section("elliott.hard_rules")
        soft = cfg.section("elliott.soft_guides")
        weights = cfg.section("elliott.guide_weights")
        low, high = soft.get("wave2_retrace_range", [0.5, 0.786])
        return cls(
            wave2_max_retrace=float(hard.get("wave2_max_retrace", 1.0)),
            wave3_never_shortest=bool(hard.get("wave3_never_shortest", True)),
            wave4_no_overlap_wave1=bool(hard.get("wave4_no_overlap_wave1", True)),
            allow_diagonals=bool(hard.get("allow_diagonals", True)),
            wave2_retrace_range=(float(low), float(high)),
            wave3_extension_target=float(soft.get("wave3_extension_target", 1.618)),
            ratio_tolerance=float(cfg.get("elliott.ratio_tolerance", 0.05)),
            weight_wave2_retracement=float(weights.get("wave2_retracement", 0.35)),
            weight_wave3_extension=float(weights.get("wave3_extension", 0.40)),
            weight_alternation=float(weights.get("alternation", 0.25)),
        )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def validate_sequence(
    pivots: Sequence[Pivot], params: ElliottParams | None = None
) -> list[WaveCount]:
    """Devuelve las hipótesis de conteo compatibles con la secuencia.

    Solo se devuelven conteos **válidos**, ordenados por score descendente. Una
    lista vacía significa que ninguna lectura sobrevive a las reglas duras, que
    es una respuesta legítima y frecuente: la mayoría de tramos de precio no son
    conteos de Elliott.

    Para inspeccionar por qué se descartó algo, usa `explain_sequence`.
    """
    return [count for count in explain_sequence(pivots, params) if count.valid]


def explain_sequence(
    pivots: Sequence[Pivot], params: ElliottParams | None = None
) -> list[WaveCount]:
    """Como `validate_sequence` pero incluye también los conteos descartados,
    con el detalle de qué regla los invalidó."""
    params = params or ElliottParams()
    pivots = tuple(pivots)

    legs = len(pivots) - 1
    if legs == 5:
        counts = _analyse_five_legs(pivots, params)
    elif legs == 3:
        counts = _analyse_three_legs(pivots, params)
    else:
        raise SequenceError(
            f"se admiten secuencias de 3 tramos (4 pivotes) o 5 tramos (6 pivotes), "
            f"se han recibido {legs} tramos ({len(pivots)} pivotes)"
        )

    return sorted(counts, key=lambda c: (c.valid, c.score), reverse=True)


def _analyse_five_legs(pivots: tuple[Pivot, ...], params: ElliottParams) -> list[WaveCount]:
    _check_shape(pivots, expected_legs=5)
    direction = _sequence_direction(pivots)
    waves = _build_waves(pivots, IMPULSE_LABELS)

    shape_rule = _rule_wave3_exceeds_wave1(waves, direction)
    base_rules = [shape_rule, _rule_wave2_retracement(waves, params.wave2_max_retrace)]
    if params.wave3_never_shortest:
        base_rules.append(_rule_wave3_not_shortest(waves))

    guides = (
        _guide_wave2_retracement(
            waves, *params.wave2_retrace_range, params.weight_wave2_retracement
        ),
        _guide_wave3_extension(
            waves,
            params.wave3_extension_target,
            params.ratio_tolerance,
            params.weight_wave3_extension,
        ),
        _guide_alternation(waves, params.weight_alternation),
    )

    overlap_rule = _rule_wave4_no_overlap(waves, direction)

    # Hipótesis de impulso: aplica la regla de solape.
    impulse_rules = list(base_rules)
    if params.wave4_no_overlap_wave1:
        impulse_rules.append(overlap_rule)

    impulse = WaveCount(
        hypothesis=IMPULSE,
        direction=direction,
        pivots=pivots,
        waves=waves,
        rules=tuple(impulse_rules),
        guides=guides,
        notes=(
            "Un impulso completo puede ser a su vez la onda 1, 3, 5, A o C de un grado "
            "superior. La secuencia por sí sola no determina su papel.",
            "Una onda 5 truncada (que no supera el final de la onda 3) es legítima y no "
            "se penaliza.",
        ),
    )
    counts = [impulse]

    # Hipótesis de diagonal: mismas cinco ondas, pero el solape de la onda 4 con
    # la 1 es su rasgo característico, no un defecto. Se trata como hipótesis
    # aparte en vez de como excepción dentro de la regla general.
    if params.allow_diagonals and not overlap_rule.passed:
        diagonal = WaveCount(
            hypothesis=DIAGONAL,
            direction=direction,
            pivots=pivots,
            waves=waves,
            rules=tuple(base_rules),
            guides=guides,
            notes=(
                "La onda 4 solapa el territorio de la onda 1, lo que descarta el impulso "
                "pero es precisamente lo que caracteriza a una diagonal.",
                "No se distingue aquí entre diagonal inicial y terminal: eso depende de "
                "dónde se sitúe la estructura en el grado superior, que esta secuencia "
                "no contiene.",
            ),
        )
        counts.append(diagonal)

    valid_names = [c.hypothesis for c in counts if c.valid]
    if len(valid_names) > 1:
        for count in counts:
            if count.valid:
                count.ambiguous_with = tuple(n for n in valid_names if n != count.hypothesis)

    return counts


def _analyse_three_legs(pivots: tuple[Pivot, ...], params: ElliottParams) -> list[WaveCount]:
    """Tres tramos son ambiguos por naturaleza.

    Pueden ser una corrección A-B-C completa o las ondas 1-2-3 de un impulso en
    curso. No hay forma de distinguirlo con la secuencia sola, así que se
    devuelven ambas lecturas marcadas como ambiguas entre sí.
    """
    _check_shape(pivots, expected_legs=3)
    direction = _sequence_direction(pivots)

    abc_waves = _build_waves(pivots, ABC_LABELS)
    impulse_waves = _build_waves(pivots, PARTIAL_LABELS)

    # En un zigzag A-B-C, la onda B no retrocede más del 100% de la A: si lo
    # hiciera, el punto de partida quedaría superado y no sería una corrección.
    ratio_b = abc_waves[1].length / abc_waves[0].length if abc_waves[0].length else float("inf")
    abc_rule = RuleResult(
        name="ondaB_no_retrocede_mas_del_100",
        passed=ratio_b <= 1.0,
        detail=f"la onda B retrocede {ratio_b:.3f} de la onda A",
    )

    ratio_c = abc_waves[2].length / abc_waves[0].length if abc_waves[0].length else 0.0
    abc_guides = (
        GuideScore(
            name="proporcion_C_sobre_A",
            score=max(
                proximity_score(ratio_c, 1.0, params.ratio_tolerance),
                proximity_score(ratio_c, 1.618, params.ratio_tolerance),
            ),
            weight=1.0,
            detail=f"C/A = {ratio_c:.3f}; los zigzags tienden a C≈A o C≈1.618·A",
        ),
    )

    corrective = WaveCount(
        hypothesis=CORRECTIVE_ABC,
        direction=direction,
        pivots=pivots,
        waves=abc_waves,
        rules=(abc_rule,),
        guides=abc_guides,
        notes=(
            "Tres tramos no permiten distinguir una corrección completa de un impulso "
            "en curso. Ambas lecturas se devuelven a propósito.",
        ),
    )

    partial_rules = (_rule_wave2_retracement(impulse_waves, params.wave2_max_retrace),)
    partial_guides = (
        _guide_wave2_retracement(
            impulse_waves, *params.wave2_retrace_range, params.weight_wave2_retracement
        ),
        _guide_wave3_extension(
            impulse_waves,
            params.wave3_extension_target,
            params.ratio_tolerance,
            params.weight_wave3_extension,
        ),
    )

    partial = WaveCount(
        hypothesis=IMPULSE_PARTIAL,
        direction=direction,
        pivots=pivots,
        waves=impulse_waves,
        rules=partial_rules,
        guides=partial_guides,
        notes=(
            "Impulso incompleto: faltarían las ondas 4 y 5. Las reglas de la onda 3 y "
            "del solape de la onda 4 todavía no son aplicables.",
        ),
    )

    counts = [corrective, partial]
    valid_names = [c.hypothesis for c in counts if c.valid]
    if len(valid_names) > 1:
        for count in counts:
            if count.valid:
                count.ambiguous_with = tuple(n for n in valid_names if n != count.hypothesis)

    return counts


def scan_recent(
    pivots: Sequence[Pivot], params: ElliottParams | None = None, *, max_windows: int = 4
) -> list[WaveCount]:
    """Busca conteos válidos en las ventanas de pivotes más recientes.

    Recorre las últimas ventanas de 6 y de 4 pivotes. Es el pegamento que
    usarán las fases 4 y 6; el análisis en sí lo hace `validate_sequence`.
    """
    pivots = tuple(pivots)
    found: list[WaveCount] = []

    for size in (6, 4):
        for offset in range(max_windows):
            end = len(pivots) - offset
            start = end - size
            if start < 0:
                break
            found.extend(validate_sequence(pivots[start:end], params))

    return sorted(found, key=lambda c: c.score, reverse=True)
