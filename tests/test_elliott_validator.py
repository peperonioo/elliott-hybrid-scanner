"""Tests del validador de Elliott.

Se construyen secuencias de pivotes a mano, con precios elegidos para que cada
regla se rompa de una sola forma. Así un fallo señala una regla concreta y no
un enredo de varias.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ehs.config import Config, project_root
from ehs.elliott.validator import (
    BEARISH,
    BULLISH,
    CORRECTIVE_ABC,
    DIAGONAL_CONTRACTING,
    DIAGONAL_EXPANDING,
    IMPULSE,
    IMPULSE_PARTIAL,
    ElliottParams,
    SequenceError,
    explain_sequence,
    proximity_score,
    range_score,
    scan_recent,
    validate_sequence,
)
from ehs.structure.swings import HIGH, LOW, Pivot

PARAMS = ElliottParams()


def pivot(index: int, price: float, kind: str) -> Pivot:
    """Pivote sintético; solo importan índice, precio y tipo."""
    stamp = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(index * 4, unit="h")
    return Pivot(
        index=index,
        timestamp=stamp,
        price=price,
        kind=kind,
        atr_at_pivot=1.0,
        magnitude_atr=None,
        confirmed_index=index + 3,
        confirmed_at=stamp + pd.Timedelta(12, unit="h"),
    )


def sequence(prices: list[float], *, bullish: bool = True, spacing: int = 10) -> list[Pivot]:
    """Convierte una lista de precios en pivotes alternos correctamente tipados."""
    first = LOW if bullish else HIGH
    second = HIGH if bullish else LOW
    return [
        pivot(i * spacing, price, first if i % 2 == 0 else second) for i, price in enumerate(prices)
    ]


# Impulso alcista de libro: onda 2 retrocede 0.6, onda 3 mide 1.618 de la 1,
# onda 4 no solapa. Sirve de base a la que aplicar un único defecto cada vez.
TEXTBOOK = [100.0, 200.0, 140.0, 301.8, 240.0, 320.0]

# Diagonal contractiva: la onda 4 (190) entra en el territorio de la onda 1
# (100-200) y las longitudes contraen — 1=100, 3=80, 5=60, con 4=40 < 2=50.
CONTRACTING_DIAGONAL = [100.0, 200.0, 150.0, 230.0, 190.0, 250.0]

# Diagonal expansiva: 1=50, 3=100, 5=160, con 4=80 > 2=30 y la onda 4 (140)
# dentro del territorio de la onda 1 (100-150).
EXPANDING_DIAGONAL = [100.0, 150.0, 120.0, 220.0, 140.0, 300.0]


# --------------------------------------------------------------------------
# Reglas duras
# --------------------------------------------------------------------------


def test_un_impulso_de_libro_es_valido():
    counts = validate_sequence(sequence(TEXTBOOK), PARAMS)

    assert len(counts) == 1
    count = counts[0]
    assert count.hypothesis == IMPULSE
    assert count.direction == BULLISH
    assert count.valid
    assert count.score > 0.6
    assert [w.label for w in count.waves] == ["1", "2", "3", "4", "5"]


def test_regla_1_la_onda_2_no_puede_retroceder_mas_del_100():
    # La onda 2 cae por debajo del origen de la onda 1.
    roto = [100.0, 200.0, 95.0, 300.0, 250.0, 330.0]
    counts = explain_sequence(sequence(roto), PARAMS)
    impulso = next(c for c in counts if c.hypothesis == IMPULSE)

    assert not impulso.valid
    assert "onda2_no_retrocede_mas_del_100" in {r.name for r in impulso.violations}
    assert validate_sequence(sequence(roto), PARAMS) == []


def test_el_limite_exacto_del_100_por_ciento_no_invalida():
    """La onda 2 que toca justo el origen está en el límite, no fuera."""
    limite = [100.0, 200.0, 100.0, 300.0, 250.0, 330.0]
    impulso = next(c for c in explain_sequence(sequence(limite), PARAMS) if c.hypothesis == IMPULSE)
    regla = next(r for r in impulso.rules if r.name == "onda2_no_retrocede_mas_del_100")
    assert regla.passed


def test_regla_2_la_onda_3_nunca_es_la_mas_corta():
    # Longitudes: 1=100, 3=40, 5=100. La onda 3 es la más corta de las tres.
    roto = [100.0, 200.0, 150.0, 190.0, 185.0, 285.0]
    impulso = next(c for c in explain_sequence(sequence(roto), PARAMS) if c.hypothesis == IMPULSE)

    assert not impulso.valid
    assert "onda3_nunca_la_mas_corta" in {r.name for r in impulso.violations}


def test_la_onda_3_puede_ser_mas_corta_que_una_sola_de_las_otras():
    """La regla prohíbe ser la más corta, no ser corta."""
    # Longitudes: 1=100, 3=80, 5=40. La onda 3 no es la más corta.
    ok = [100.0, 200.0, 150.0, 230.0, 210.0, 250.0]
    impulso = next(c for c in explain_sequence(sequence(ok), PARAMS) if c.hypothesis == IMPULSE)
    regla = next(r for r in impulso.rules if r.name == "onda3_nunca_la_mas_corta")
    assert regla.passed


def test_regla_3_la_onda_4_no_solapa_el_territorio_de_la_onda_1():
    # La onda 4 termina en 190, por debajo del máximo de la onda 1 (200).
    solapado = [100.0, 200.0, 150.0, 300.0, 190.0, 320.0]
    impulso = next(
        c for c in explain_sequence(sequence(solapado), PARAMS) if c.hypothesis == IMPULSE
    )

    assert not impulso.valid
    assert "onda4_no_solapa_onda1" in {r.name for r in impulso.violations}


def test_una_cuna_contractiva_con_solape_es_una_diagonal():
    """El solape descarta el impulso, pero con forma de cuña es una diagonal."""
    counts = validate_sequence(sequence(CONTRACTING_DIAGONAL), PARAMS)

    assert [c.hypothesis for c in counts] == [DIAGONAL_CONTRACTING]
    assert counts[0].valid
    assert any("cuña" in nota.lower() for nota in counts[0].notes)


def test_un_solape_sin_forma_de_cuna_no_es_nada():
    """La exigencia de cuña es lo que impide que cualquier lateral de cinco
    piernas pase por diagonal.

    Longitudes 1=100, 3=150, 5=130: ni contrae (3>1) ni expande (5<3).
    """
    solapado_sin_cuna = [100.0, 200.0, 150.0, 300.0, 190.0, 320.0]
    permisivo = ElliottParams(allow_expanding_diagonals=True)
    assert validate_sequence(sequence(solapado_sin_cuna), permisivo) == []


def test_las_diagonales_se_pueden_desactivar():
    sin_diagonales = ElliottParams(allow_diagonals=False)
    assert validate_sequence(sequence(CONTRACTING_DIAGONAL), sin_diagonales) == []


def test_la_diagonal_expansiva_esta_desactivada_por_defecto():
    """Es una variante rara; se admite solo si se pide explícitamente."""
    assert validate_sequence(sequence(EXPANDING_DIAGONAL), PARAMS) == []


def test_la_diagonal_expansiva_se_puede_activar():
    permisivo = ElliottParams(allow_expanding_diagonals=True)
    counts = validate_sequence(sequence(EXPANDING_DIAGONAL), permisivo)

    assert [c.hypothesis for c in counts] == [DIAGONAL_EXPANDING]


def test_una_cuna_satisface_sola_la_regla_de_la_onda_3():
    """Si las longitudes son monótonas la onda 3 queda en medio y nunca es la
    más corta: la regla 2 y la forma de cuña son consistentes entre sí."""
    count = validate_sequence(sequence(CONTRACTING_DIAGONAL), PARAMS)[0]
    regla = next(r for r in count.rules if r.name == "onda3_nunca_la_mas_corta")
    assert regla.passed


def test_una_diagonal_sigue_sujeta_a_las_demas_reglas():
    """El solape se perdona; la onda 2 y la onda 3 no."""
    # Cuña contractiva, pero la onda 2 retrocede más del 100%.
    doble_fallo = [100.0, 200.0, 90.0, 230.0, 190.0, 250.0]
    assert validate_sequence(sequence(doble_fallo), PARAMS) == []


def test_condicion_de_forma_la_onda_3_debe_superar_el_final_de_la_onda_1():
    # La onda 3 termina en 180, por debajo del final de la onda 1 (200).
    roto = [100.0, 200.0, 150.0, 180.0, 160.0, 400.0]
    impulso = next(c for c in explain_sequence(sequence(roto), PARAMS) if c.hypothesis == IMPULSE)

    assert not impulso.valid
    assert "onda3_supera_el_final_de_la_onda1" in {r.name for r in impulso.violations}


def test_una_onda_5_truncada_sigue_siendo_valida():
    """Una quinta que no supera el final de la tercera es legítima."""
    truncada = [100.0, 200.0, 140.0, 301.8, 240.0, 290.0]
    counts = validate_sequence(sequence(truncada), PARAMS)

    assert counts and counts[0].hypothesis == IMPULSE
    assert any("truncada" in nota for nota in counts[0].notes)


# --------------------------------------------------------------------------
# Simetría bajista
# --------------------------------------------------------------------------


def test_un_impulso_bajista_se_valida_igual():
    espejo = [400.0, 300.0, 360.0, 198.2, 260.0, 180.0]
    counts = validate_sequence(sequence(espejo, bullish=False), PARAMS)

    assert len(counts) == 1
    assert counts[0].direction == BEARISH
    assert counts[0].hypothesis == IMPULSE


def test_la_cuna_bajista_tambien_da_diagonal():
    espejo = [300.0, 200.0, 250.0, 170.0, 210.0, 150.0]
    counts = validate_sequence(sequence(espejo, bullish=False), PARAMS)

    assert [c.hypothesis for c in counts] == [DIAGONAL_CONTRACTING]
    assert counts[0].direction == BEARISH


# --------------------------------------------------------------------------
# Ambigüedad de grado
# --------------------------------------------------------------------------


def test_tres_tramos_devuelven_las_dos_hipotesis_marcadas_como_ambiguas():
    """Es el requisito clave: no resolver lo que es genuinamente ambiguo."""
    tres = sequence([100.0, 200.0, 150.0, 250.0])
    counts = validate_sequence(tres, PARAMS)

    hipotesis = {c.hypothesis for c in counts}
    assert hipotesis == {CORRECTIVE_ABC, IMPULSE_PARTIAL}
    for count in counts:
        assert count.is_ambiguous
        assert count.ambiguous_with
    assert {c.ambiguous_with[0] for c in counts} == hipotesis


def test_un_impulso_completo_advierte_de_su_papel_en_el_grado_superior():
    count = validate_sequence(sequence(TEXTBOOK), PARAMS)[0]
    assert any("grado" in nota for nota in count.notes)


def test_impulso_y_diagonal_no_pueden_ser_validos_a_la_vez():
    """El solape es excluyente: o no lo hay (impulso) o lo hay (diagonal)."""
    for prices in (TEXTBOOK, CONTRACTING_DIAGONAL):
        counts = validate_sequence(sequence(prices), PARAMS)
        assert len(counts) == 1
        assert not counts[0].is_ambiguous


def test_un_segundo_tramo_que_supera_el_origen_descarta_las_dos_lecturas():
    """Si el retroceso se come el tramo inicial entero, no queda nada en pie.

    Deja de ser una corrección A-B-C (la B superaría el origen de la A) y deja
    de ser un impulso naciente (la onda 2 rompería la regla del 100%). Es el
    caso en que la ambigüedad se resuelve sola: por eliminación de ambas.
    """
    roto = sequence([100.0, 200.0, 90.0, 250.0])
    counts = explain_sequence(roto, PARAMS)

    abc = next(c for c in counts if c.hypothesis == CORRECTIVE_ABC)
    parcial = next(c for c in counts if c.hypothesis == IMPULSE_PARTIAL)
    assert not abc.valid
    assert not parcial.valid
    assert validate_sequence(roto, PARAMS) == []


# --------------------------------------------------------------------------
# Guías blandas y score
# --------------------------------------------------------------------------


def test_el_conteo_de_libro_puntua_mas_que_uno_desproporcionado():
    libro = validate_sequence(sequence(TEXTBOOK), PARAMS)[0]
    # Onda 2 muy superficial y onda 3 lejos de 1.618.
    pobre = validate_sequence(sequence([100.0, 200.0, 195.0, 240.0, 230.0, 260.0]), PARAMS)[0]

    assert libro.score > pobre.score


def test_la_onda_3_en_1618_maximiza_su_guia():
    count = validate_sequence(sequence(TEXTBOOK), PARAMS)[0]
    guia = next(g for g in count.guides if g.name == "extension_onda3")
    assert guia.score == pytest.approx(1.0)


def test_el_retroceso_de_la_onda_2_dentro_del_rango_puntua_1():
    count = validate_sequence(sequence(TEXTBOOK), PARAMS)[0]
    guia = next(g for g in count.guides if g.name == "retroceso_onda2")
    assert guia.score == pytest.approx(1.0)


def test_la_alternancia_se_declara_como_aproximacion():
    count = validate_sequence(sequence(TEXTBOOK), PARAMS)[0]
    guia = next(g for g in count.guides if g.name == "alternancia_2_4")
    assert "aproximación" in guia.detail
    assert 0.0 <= guia.score <= 1.0


def test_las_guias_nunca_invalidan_un_conteo():
    """Un impulso que incumple todas las guías sigue siendo válido.

    Onda 2 muy superficial, onda 3 lejos de 1.618 y sin alternancia: ninguna
    guía puntúa, pero las tres reglas duras se respetan.
    """
    feo = [100.0, 200.0, 195.0, 260.0, 255.0, 300.0]
    counts = validate_sequence(sequence(feo), PARAMS)

    assert counts and counts[0].valid
    assert counts[0].score < 0.5


def test_un_conteo_invalido_puntua_cero():
    roto = sequence([100.0, 200.0, 95.0, 300.0, 250.0, 330.0])
    impulso = next(c for c in explain_sequence(roto, PARAMS) if c.hypothesis == IMPULSE)
    assert impulso.score == 0.0


def test_los_pesos_de_las_guias_afectan_al_score():
    prices = sequence([100.0, 200.0, 130.0, 400.0, 300.0, 380.0])
    solo_extension = ElliottParams(
        weight_wave2_retracement=0.0, weight_wave3_extension=1.0, weight_alternation=0.0
    )
    solo_retroceso = ElliottParams(
        weight_wave2_retracement=1.0, weight_wave3_extension=0.0, weight_alternation=0.0
    )
    assert validate_sequence(prices, solo_extension)[0].score != pytest.approx(
        validate_sequence(prices, solo_retroceso)[0].score
    )


@pytest.mark.parametrize(
    ("value", "target", "esperado"),
    [(1.618, 1.618, 1.0), (1.7, 1.618, None), (5.0, 1.618, 0.0), (0.0, 1.618, 0.0)],
)
def test_proximity_score(value, target, esperado):
    score = proximity_score(value, target, 0.05)
    assert 0.0 <= score <= 1.0
    if esperado is not None:
        assert score == pytest.approx(esperado)


def test_range_score():
    assert range_score(0.6, 0.5, 0.786) == 1.0
    assert range_score(0.5, 0.5, 0.786) == 1.0
    assert range_score(0.2, 0.5, 0.786) == 0.0
    assert 0.0 < range_score(0.4, 0.5, 0.786) < 1.0


# --------------------------------------------------------------------------
# Validación de la entrada
# --------------------------------------------------------------------------


@pytest.mark.parametrize("n_pivotes", [0, 1, 2, 3, 5, 7, 8])
def test_longitudes_de_secuencia_no_admitidas(n_pivotes):
    pivotes = sequence([100.0 + i * 10 for i in range(n_pivotes)])
    with pytest.raises(SequenceError, match="tramos"):
        explain_sequence(pivotes, PARAMS)


def test_los_pivotes_deben_alternar():
    todos_maximos = [pivot(i * 10, 100.0 + i, HIGH) for i in range(6)]
    with pytest.raises(SequenceError, match="alternar"):
        explain_sequence(todos_maximos, PARAMS)


def test_los_pivotes_deben_estar_ordenados_en_el_tiempo():
    pivotes = sequence(TEXTBOOK)
    desordenados = [pivotes[0], pivotes[2], pivotes[1], *pivotes[3:]]
    with pytest.raises(SequenceError, match=r"alternar|ordenados"):
        explain_sequence(desordenados, PARAMS)


# --------------------------------------------------------------------------
# Nivel de invalidación y utilidades
# --------------------------------------------------------------------------


def test_el_nivel_de_invalidacion_de_un_impulso_es_el_origen_de_la_onda_1():
    count = validate_sequence(sequence(TEXTBOOK), PARAMS)[0]
    assert count.invalidation_level() == 100.0
    assert count.start.price == 100.0
    assert count.end.price == 320.0


def test_el_abc_no_declara_nivel_de_invalidacion():
    abc = next(
        c
        for c in validate_sequence(sequence([100.0, 200.0, 150.0, 250.0]), PARAMS)
        if c.hypothesis == CORRECTIVE_ABC
    )
    assert abc.invalidation_level() is None


def test_el_resumen_menciona_estado_y_ambiguedad():
    count = validate_sequence(sequence(TEXTBOOK), PARAMS)[0]
    assert "válido" in count.summary()

    ambiguo = validate_sequence(sequence([100.0, 200.0, 150.0, 250.0]), PARAMS)[0]
    assert "ambiguo con" in ambiguo.summary()


def test_scan_recent_encuentra_el_conteo_en_una_lista_larga():
    ruido = [100.0, 130.0, 110.0]
    pivotes = sequence([*ruido, *TEXTBOOK])
    # `sequence` alterna desde el primer precio; recortamos para que el impulso
    # arranque en un mínimo.
    counts = scan_recent(pivotes, PARAMS)

    assert counts
    assert all(c.valid for c in counts)
    assert counts == sorted(counts, key=lambda c: c.score, reverse=True)


def test_scan_recent_con_pocos_pivotes_no_falla():
    assert scan_recent(sequence([100.0, 200.0]), PARAMS) == []
    assert scan_recent([], PARAMS) == []


# --------------------------------------------------------------------------
# Carga desde configuración
# --------------------------------------------------------------------------


def test_los_parametros_se_leen_del_yaml():
    cfg = Config.load(project_root() / "config.yaml")
    params = ElliottParams.from_config(cfg)

    assert params.wave2_max_retrace == 1.0
    assert params.wave3_extension_target == 1.618
    assert params.wave2_retrace_range == (0.5, 0.786)
    assert params.allow_diagonals is True
    assert params.allow_expanding_diagonals is False
    assert params.weight_wave3_extension > 0
