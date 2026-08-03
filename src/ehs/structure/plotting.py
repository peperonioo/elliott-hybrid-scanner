"""Gráficos de validación visual de los swings detectados.

No forman parte del pipeline de señales: existen para poder calibrar
`swings.atr_threshold` a ojo sobre el precio, que es la única manera honesta de
ajustar ese parámetro.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sin ventana: se escribe a fichero

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from ehs.structure.indicators import wilder_atr
from ehs.structure.swings import HIGH, Pivot, detect_swings

LOGGER = logging.getLogger(__name__)

COLOR_PRICE = "#8a8f98"
COLOR_ZIGZAG = "#1f6feb"
COLOR_HIGH = "#d1242f"
COLOR_LOW = "#1a7f37"
COLOR_LAG = "#b08800"


def _draw_price(ax, frame: pd.DataFrame) -> None:
    """Barras high-low: dejan ver los extremos reales sobre los que se apoyan
    los pivotes, cosa que una línea de cierres oculta."""
    ax.vlines(
        frame.index,
        frame["low"],
        frame["high"],
        color=COLOR_PRICE,
        linewidth=0.7,
        alpha=0.65,
        zorder=1,
    )


def _draw_pivots(ax, pivots: list[Pivot], *, show_lag: bool, annotate: bool) -> None:
    if not pivots:
        return

    ax.plot(
        [p.timestamp for p in pivots],
        [p.price for p in pivots],
        color=COLOR_ZIGZAG,
        linewidth=1.5,
        zorder=3,
        label="ZigZag",
    )

    for pivot in pivots:
        is_high = pivot.kind == HIGH
        ax.scatter(
            pivot.timestamp,
            pivot.price,
            marker="v" if is_high else "^",
            s=55,
            color=COLOR_HIGH if is_high else COLOR_LOW,
            zorder=4,
        )

        if show_lag:
            # Tramo desde el extremo hasta el momento en que pasó a ser
            # conocido: hace visible el retardo estructural del sistema.
            ax.plot(
                [pivot.timestamp, pivot.confirmed_at],
                [pivot.price, pivot.price],
                color=COLOR_LAG,
                linewidth=0.9,
                linestyle=":",
                zorder=2,
            )
            ax.scatter(pivot.confirmed_at, pivot.price, marker="|", s=45, color=COLOR_LAG, zorder=3)

        if annotate and pivot.magnitude_atr is not None:
            ax.annotate(
                f"{pivot.magnitude_atr:.1f}",
                (pivot.timestamp, pivot.price),
                textcoords="offset points",
                xytext=(0, 11 if is_high else -16),
                ha="center",
                fontsize=7,
                color=COLOR_HIGH if is_high else COLOR_LOW,
            )


def plot_swings(
    frame: pd.DataFrame,
    pivots: list[Pivot],
    *,
    title: str,
    output: Path,
    atr_period: int = 14,
    atr_threshold: float = 2.5,
    figsize: tuple[float, float] = (17, 9),
    dpi: int = 130,
    show_lag: bool = True,
    annotate: bool = True,
) -> Path:
    """Dibuja precio, pivotes y el umbral en unidades de precio."""
    fig, (ax_price, ax_atr) = plt.subplots(
        2, 1, figsize=figsize, dpi=dpi, sharex=True, height_ratios=[3, 1]
    )

    _draw_price(ax_price, frame)
    _draw_pivots(ax_price, pivots, show_lag=show_lag, annotate=annotate)

    ax_price.set_title(title, fontsize=12, loc="left")
    ax_price.set_ylabel("precio")
    ax_price.grid(alpha=0.18)
    ax_price.legend(loc="upper left", fontsize=8, framealpha=0.9)

    # El umbral traducido a unidades de precio: cuánto tiene que retroceder el
    # precio, en cada momento, para dar por bueno un extremo.
    atr = wilder_atr(frame, atr_period)
    ax_atr.plot(frame.index, atr * atr_threshold, color=COLOR_ZIGZAG, linewidth=1.0)
    ax_atr.fill_between(frame.index, 0, atr * atr_threshold, color=COLOR_ZIGZAG, alpha=0.12)
    ax_atr.set_ylabel(f"umbral\n({atr_threshold}×ATR{atr_period})")
    ax_atr.grid(alpha=0.18)
    ax_atr.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))

    fig.autofmt_xdate()
    fig.tight_layout()

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    LOGGER.info("Gráfico escrito en %s", output)
    return output


def plot_threshold_comparison(
    frame: pd.DataFrame,
    thresholds: list[float],
    *,
    title: str,
    output: Path,
    atr_period: int = 14,
    confirmation_bars: int = 0,
    atr_reference: str = "extreme",
    figsize: tuple[float, float] = (17, 9),
    dpi: int = 130,
) -> Path:
    """Mismo tramo de precio con varios umbrales, para calibrar comparando."""
    fig, axes = plt.subplots(len(thresholds), 1, figsize=figsize, dpi=dpi, sharex=True)
    axes = [axes] if len(thresholds) == 1 else list(axes)

    for ax, threshold in zip(axes, thresholds, strict=True):
        pivots = detect_swings(
            frame,
            atr_period=atr_period,
            atr_threshold=threshold,
            confirmation_bars=confirmation_bars,
            atr_reference=atr_reference,
        )
        _draw_price(ax, frame)
        _draw_pivots(ax, pivots, show_lag=False, annotate=False)
        ax.set_ylabel(f"{threshold}×ATR")
        ax.grid(alpha=0.18)
        ax.legend([], [], title=f"{len(pivots)} pivotes", loc="upper left", fontsize=8)

    axes[0].set_title(title, fontsize=12, loc="left")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))

    fig.autofmt_xdate()
    fig.tight_layout()

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    LOGGER.info("Gráfico comparativo escrito en %s", output)
    return output
