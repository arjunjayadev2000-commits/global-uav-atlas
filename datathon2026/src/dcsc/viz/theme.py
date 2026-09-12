"""One visual system for every figure in the submission.

Colour is assigned by the job it does, not by taste:

* **categorical** - identity (event types, vessel classes). A fixed slot order,
  never cycled; the order itself is what keeps adjacent series separable under
  colour-vision deficiency.
* **sequential** - magnitude (dark rate, detection density). One hue, light to
  dark. Never a rainbow.
* **diverging** - polarity (throughput above or below a benchmark). Two hues
  either side of a neutral grey midpoint.
* **status** - state (RED / AMBER / GREEN risk tiers). Reserved: these four
  colours never stand in for a series, and always ship with a text label so the
  meaning never rests on hue alone.

The palette was checked with the data-viz validator (lightness band, chroma
floor, CVD separation of adjacent pairs, normal-vision separation, contrast
against the chart surface) rather than eyeballed.
"""

from __future__ import annotations

import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --- surfaces and ink ------------------------------------------------------
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# --- categorical slots (fixed order) --------------------------------------
CATEGORICAL = [
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
]

# --- sequential ramp (blue, light -> dark) --------------------------------
SEQUENTIAL = [
    "#cde2fb",
    "#b7d3f6",
    "#9ec5f4",
    "#86b6ef",
    "#6da7ec",
    "#5598e7",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
    "#0d366b",
]

# --- diverging pair --------------------------------------------------------
DIVERGING_LOW = "#2a78d6"
DIVERGING_MID = "#f0efec"
DIVERGING_HIGH = "#d03b3b"

#: Series colour for "dark / unidentified" traffic. It is the categorical red
#: slot, deliberately NOT the status red: status colours stay reserved for the
#: risk tiers, so a series can never be mistaken for a severity rating.
SERIES_DARK = CATEGORICAL[7]
SERIES_MATCHED = CATEGORICAL[0]

# --- reserved status palette ----------------------------------------------
STATUS = {
    "GREEN": "#0ca30c",
    "AMBER": "#fab219",
    "SERIOUS": "#ec835a",
    "RED": "#d03b3b",
}

CMAP_SEQUENTIAL = matplotlib.colors.LinearSegmentedColormap.from_list("dcsc_seq", SEQUENTIAL)
CMAP_DIVERGING = matplotlib.colors.LinearSegmentedColormap.from_list(
    "dcsc_div", [DIVERGING_LOW, DIVERGING_MID, DIVERGING_HIGH]
)


def apply_theme() -> None:
    """Install the house style. Call once before drawing anything."""
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans", "Segoe UI", "Helvetica", "Arial"],
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.titleweight": "semibold",
            "axes.titlelocation": "left",
            "axes.titlepad": 10,
            "axes.labelsize": 9,
            "axes.labelcolor": INK_SECONDARY,
            "axes.edgecolor": AXIS,
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.color": GRID,
            "grid.linewidth": 0.7,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.frameon": False,
            "legend.fontsize": 8,
            "lines.linewidth": 2.0,
            "lines.markersize": 5,
            "figure.dpi": 110,
            "savefig.dpi": 160,
            "savefig.bbox": "tight",
            "text.color": INK,
        }
    )


def _wrap(ax, text: str, chars_per_inch: float) -> list[str]:
    """Wrap to the axes' own width so long captions never run past the plot."""
    width = max(int(ax.figure.get_size_inches()[0] * chars_per_inch), 40)
    return textwrap.wrap(text, width=width)


def annotate(ax, text: str, *, loc: str = "bottom") -> None:
    """Add a source or caveat note under an axes, in muted ink."""
    lines = _wrap(ax, text, 17.0)
    y = -0.16 - 0.02 * len(lines) if loc == "bottom" else 1.02
    ax.annotate(
        "\n".join(lines),
        xy=(0, y),
        xycoords="axes fraction",
        fontsize=7.2,
        color=INK_MUTED,
        va="top",
        ha="left",
        linespacing=1.4,
    )


def title(ax, headline: str, subline: str | None = None) -> None:
    """Headline plus an explanatory second line - the chart states its finding.

    The sub-line is wrapped to the axes width and the title is padded above it,
    so neither can collide with the other however long the sentence is.
    """
    if not subline:
        ax.set_title(headline, color=INK)
        return
    lines = _wrap(ax, subline, 14.5)
    ax.set_title(headline, color=INK, pad=8 + 11.0 * len(lines))
    ax.annotate(
        "\n".join(lines),
        xy=(0, 1.008),
        xycoords="axes fraction",
        fontsize=8.2,
        color=INK_SECONDARY,
        va="bottom",
        ha="left",
        linespacing=1.35,
    )
