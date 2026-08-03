"""Detección de swings mediante ZigZag con umbral en ATR.

El ZigZag clásico usa un umbral porcentual fijo, lo que hace que el mismo
parámetro signifique cosas distintas en un mercado tranquilo y en uno agitado.
Aquí el umbral es un múltiplo del ATR, de modo que "swing relevante" quiere
decir lo mismo en régimenes de volatilidad distintos.

## Ausencia de lookahead bias

Es el requisito duro del módulo, y se sostiene sobre tres decisiones:

1. **El ATR es causal y estable ante prefijos** (ver `indicators.py`).

2. **Nunca se asume el orden intrabar.** Con solo OHLC no sabemos si dentro de
   una vela ocurrió antes el máximo o el mínimo. Por eso una reversión jamás se
   confirma en la misma vela que marca el extremo: hace falta una vela
   posterior que retroceda el umbral. Un ZigZag que confirma en la misma vela
   está asumiendo un orden que sus datos no contienen.

3. **Cada pivote lleva su `confirmed_index`.** Un pivote se detecta en la vela
   del extremo pero solo se puede *saber* más tarde: cuando el precio retrocede
   el umbral y, además, han cerrado `confirmation_bars` velas desde el extremo.
   `detect_swings` devuelve únicamente pivotes ya confirmados dentro de la serie
   recibida, así que ejecutarla sobre `frame[:t+1]` da exactamente el mismo
   resultado que ejecutarla sobre la serie completa y filtrar por
   `confirmed_index <= t`. Ese es el invariante que verifica
   `tests/test_swings.py::test_no_hay_lookahead_bias_invariancia_ante_prefijos`.

El pivote en formación —el extremo del tramo actual, todavía sin reversión— se
excluye deliberadamente. Es información que en tiempo real aún no existe.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from ehs.config import Config
from ehs.structure.indicators import first_valid_position, wilder_atr

LOGGER = logging.getLogger(__name__)

HIGH = "H"
LOW = "L"

ATR_REFERENCES = ("extreme", "current")


@dataclass(frozen=True)
class Pivot:
    """Un extremo de swing confirmado.

    `index` es la posición de la vela donde está el extremo; `confirmed_index`
    la primera vela en la que ese pivote pasó a ser conocido. La distancia
    entre ambas es el retardo estructural del sistema, y no se puede eliminar
    sin mirar al futuro.
    """

    index: int
    timestamp: pd.Timestamp
    price: float
    kind: str  # "H" o "L"
    atr_at_pivot: float
    magnitude_atr: float | None  # None en el primer pivote: no hay tramo previo
    confirmed_index: int
    confirmed_at: pd.Timestamp

    @property
    def confirmation_lag(self) -> int:
        """Velas transcurridas entre el extremo y su confirmación."""
        return self.confirmed_index - self.index

    def __str__(self) -> str:
        magnitude = "—" if self.magnitude_atr is None else f"{self.magnitude_atr:.2f} ATR"
        return (
            f"{self.kind} {self.timestamp:%Y-%m-%d %H:%M} @ {self.price:,.4f} "
            f"({magnitude}, confirmado +{self.confirmation_lag} velas)"
        )


def detect_swings(
    frame: pd.DataFrame,
    *,
    atr_period: int,
    atr_threshold: float,
    confirmation_bars: int = 0,
    atr_reference: str = "extreme",
) -> list[Pivot]:
    """Localiza los pivotes de swing confirmados de una serie OHLCV.

    `atr_threshold` es el múltiplo de ATR que el precio debe retroceder desde un
    extremo para dar ese extremo por bueno. Rango razonable: 1.0-5.0. Por debajo
    de 1.5 se detecta ruido de grado menor; por encima de 4.0 solo sobreviven
    los swings mayores y se pierden las ondas 4 y 5. Hay que recalibrarlo por
    timeframe.
    """
    if atr_threshold <= 0:
        raise ValueError(f"atr_threshold debe ser positivo, es {atr_threshold}")
    if confirmation_bars < 0:
        raise ValueError(f"confirmation_bars no puede ser negativo, es {confirmation_bars}")
    if atr_reference not in ATR_REFERENCES:
        raise ValueError(f"atr_reference debe ser uno de {ATR_REFERENCES}, es {atr_reference!r}")

    n = len(frame)
    if n == 0:
        return []

    atr = wilder_atr(frame, atr_period).to_numpy(dtype="float64")
    start = first_valid_position(pd.Series(atr))
    if start is None or start >= n - 1:
        # Sin ATR definido no hay umbral que aplicar.
        return []

    high = frame["high"].to_numpy(dtype="float64")
    low = frame["low"].to_numpy(dtype="float64")

    # `direction` describe el tramo en curso:
    #   +1 -> subiendo, el candidato a pivote es un máximo
    #   -1 -> bajando, el candidato es un mínimo
    #    0 -> indeterminado, se siguen ambos hasta que uno rompa el umbral
    direction = 0
    ext_high, ext_high_idx = high[start], start
    ext_low, ext_low_idx = low[start], start

    detected: list[tuple[int, str]] = []  # (índice del extremo, tipo)
    confirmations: list[int] = []  # vela en la que se observó la reversión

    for i in range(start + 1, n):
        tracking_high = direction >= 0
        tracking_low = direction <= 0

        new_high = tracking_high and high[i] > ext_high
        if new_high:
            ext_high, ext_high_idx = high[i], i
        new_low = tracking_low and low[i] < ext_low
        if new_low:
            ext_low, ext_low_idx = low[i], i

        # Una vela que marca un nuevo extremo no puede confirmar además la
        # reversión desde ese mismo extremo: haría falta saber el orden
        # intrabar. Se espera a la siguiente.
        down_move = (ext_high - low[i]) if (tracking_high and not new_high) else -np.inf
        up_move = (high[i] - ext_low) if (tracking_low and not new_low) else -np.inf

        threshold_high = atr_threshold * atr[ext_high_idx if atr_reference == "extreme" else i]
        threshold_low = atr_threshold * atr[ext_low_idx if atr_reference == "extreme" else i]

        # Un umbral nulo aceptaría cualquier movimiento, incluido ninguno. Pasa
        # cuando el ATR es cero: mercado parado o velas planas por una
        # interrupción del exchange. Sin esta guarda se generarían pivotes
        # fantasma justo donde no ha ocurrido nada.
        confirm_high = threshold_high > 0 and down_move >= threshold_high
        confirm_low = threshold_low > 0 and up_move >= threshold_low

        if confirm_high and confirm_low:
            # Solo ocurre con dirección indeterminada. Gana la excursión mayor
            # en unidades de ATR; el empate se resuelve a favor del máximo.
            confirm_low = (up_move / threshold_low) > (down_move / threshold_high)
            confirm_high = not confirm_low

        if confirm_high:
            detected.append((ext_high_idx, HIGH))
            confirmations.append(i)
            direction = -1
            # El nuevo candidato a mínimo es el punto más bajo desde el máximo,
            # no necesariamente el mínimo de la vela actual.
            offset = ext_high_idx + 1
            ext_low_idx = offset + int(np.argmin(low[offset : i + 1]))
            ext_low = low[ext_low_idx]

        elif confirm_low:
            detected.append((ext_low_idx, LOW))
            confirmations.append(i)
            direction = 1
            offset = ext_low_idx + 1
            ext_high_idx = offset + int(np.argmax(high[offset : i + 1]))
            ext_high = high[ext_high_idx]

    return _build_pivots(frame, atr, detected, confirmations, confirmation_bars)


def _build_pivots(
    frame: pd.DataFrame,
    atr: np.ndarray,
    detected: list[tuple[int, str]],
    confirmations: list[int],
    confirmation_bars: int,
) -> list[Pivot]:
    """Convierte los extremos detectados en pivotes, descartando los que aún
    no están confirmados dentro de la serie recibida."""
    n = len(frame)
    pivots: list[Pivot] = []
    previous_price: float | None = None

    for (index, kind), reversal_index in zip(detected, confirmations, strict=True):
        price = float(frame["high"].iloc[index] if kind == HIGH else frame["low"].iloc[index])
        magnitude = (
            None if previous_price is None else abs(price - previous_price) / float(atr[index])
        )
        previous_price = price

        confirmed_index = max(reversal_index, index + confirmation_bars)
        if confirmed_index >= n:
            # Detectado pero todavía no observable: se omite. Mantener el
            # `previous_price` actualizado es lo que hace que el resto de
            # magnitudes coincidan al recalcular sobre la serie completa.
            continue

        pivots.append(
            Pivot(
                index=index,
                timestamp=frame.index[index],
                price=price,
                kind=kind,
                atr_at_pivot=float(atr[index]),
                magnitude_atr=magnitude,
                confirmed_index=confirmed_index,
                confirmed_at=frame.index[confirmed_index],
            )
        )

    return pivots


def detect_swings_from_config(frame: pd.DataFrame, cfg: Config) -> list[Pivot]:
    """Igual que `detect_swings`, tomando los parámetros del `config.yaml`."""
    return detect_swings(
        frame,
        atr_period=int(cfg.get("swings.atr_period")),
        atr_threshold=float(cfg.get("swings.atr_threshold")),
        confirmation_bars=int(cfg.get("swings.confirmation_bars", 0)),
        atr_reference=str(cfg.get("swings.atr_reference", "extreme")),
    )


def pivots_visible_at(pivots: list[Pivot], position: int) -> list[Pivot]:
    """Pivotes ya conocidos en la vela `position`.

    Es el filtro que debe usar cualquier backtest sobre una serie completa para
    no leer el futuro.
    """
    return [pivot for pivot in pivots if pivot.confirmed_index <= position]


PIVOT_COLUMNS: tuple[str, ...] = tuple(Pivot.__dataclass_fields__)


def pivots_to_frame(pivots: list[Pivot]) -> pd.DataFrame:
    """Vuelca los pivotes a un DataFrame indexado por timestamp."""
    records = [asdict(pivot) for pivot in pivots]
    frame = pd.DataFrame(records, columns=list(PIVOT_COLUMNS))
    return frame.set_index("timestamp", drop=False)
