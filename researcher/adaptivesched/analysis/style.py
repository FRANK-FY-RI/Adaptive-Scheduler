"""One fixed colour per strategy across every plot, and shared figure styling.

Colours are slots 1-3 of the dataviz skill's validated categorical palette (light mode),
which pass the all-pairs colour-vision checks needed for scatter plots. A fourth strategy
gets neutral grey, never a generated hue; add a slot here deliberately if one is registered.
"""
from __future__ import annotations

import re

import matplotlib

matplotlib.use("Agg")  # files only, never shown interactively
import matplotlib.pyplot as plt  # noqa: E402

STRATEGY_COLORS = {"fifo": "#2a78d6", "sjf": "#eb6834", "adaptive": "#1baf7a"}  # easy_backfill: OTHER (no 4th hue passes all-pairs)
OTHER = "#8a8985"
SURFACE, TEXT, TEXT_2, GRID, IDLE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#efeeea"
CONDITION_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2, "text.color": TEXT,
    "xtick.color": TEXT_2, "ytick.color": TEXT_2, "axes.grid": True, "grid.color": GRID,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 9, "axes.titlesize": 9, "legend.frameon": False,
    "svg.hashsalt": "adaptivesched",  # stable SVG ids across reruns
})


def color(strategy: str) -> str:
    return STRATEGY_COLORS.get(strategy, OTHER)


def split_seed(workload_id: str) -> tuple[str, int | None]:
    """'synth:heavy:n=300:seed=7' -> ('synth:heavy:n=300', 7); CSV ids -> (id, None)."""
    m = re.fullmatch(r"(.*):seed=(\d+)", workload_id)
    return (m[1], int(m[2])) if m else (workload_id, None)


def save(fig, path_stem) -> list:
    """Write <stem>.png and <stem>.svg; return both paths."""
    from pathlib import Path

    stem = Path(path_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    paths = [stem.with_suffix(".png"), stem.with_suffix(".svg")]
    fig.savefig(paths[0], dpi=150, bbox_inches="tight", metadata={"Software": None})
    fig.savefig(paths[1], bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)
    return paths
