"""Maps drawn without a GIS stack.

There is no basemap library and no network here, and that turns out not to
matter: 104,840 radar detections trace the world's coastlines and shipping lanes
by themselves. Every map therefore plots the full detection set as a pale
context layer and draws the analysis on top of it. The reader gets real
geographic orientation, and nothing is imported that a staff network would block.

Projection is plain equirectangular with the aspect set to 1/cos(mean latitude)
on regional panels, so shapes are not grossly distorted at Gulf and Black Sea
latitudes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from ..config import FIGURES, load_chokepoints
from ..io_utils import get_logger
from .theme import (
    CATEGORICAL,
    CMAP_SEQUENTIAL,
    INK,
    INK_MUTED,
    INK_SECONDARY,
    SERIES_DARK,
    SERIES_MATCHED,
    STATUS,
    apply_theme,
    title,
)

LOG = get_logger("dcsc.viz.maps")

CONTEXT_COLOR = "#d8d7d0"


def _save(fig, name: str) -> str:
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    LOG.info("figure %s", path.name)
    return str(path)


def _context(ax, det: pd.DataFrame, extent=None, size: float = 0.35) -> None:
    """Pale detection cloud used as the basemap."""
    sub = det
    if extent:
        lon0, lon1, lat0, lat1 = extent
        sub = det[det["lon"].between(lon0, lon1) & det["lat"].between(lat0, lat1)]
    ax.scatter(sub["lon"], sub["lat"], s=size, color=CONTEXT_COLOR, linewidths=0, zorder=1)


def _frame(ax, extent, aspect_correct: bool = True) -> None:
    lon0, lon1, lat0, lat1 = extent
    ax.set_xlim(lon0, lon1)
    ax.set_ylim(lat0, lat1)
    if aspect_correct:
        mid = np.radians((lat0 + lat1) / 2)
        ax.set_aspect(1 / max(np.cos(mid), 0.2))
    ax.set_xlabel("Longitude", fontsize=8)
    ax.set_ylabel("Latitude", fontsize=8)
    ax.grid(True, color="#eceae3", lw=0.6)


def map_global_sdr(det: pd.DataFrame, cells: pd.DataFrame, name: str = "fig15_map_global_sdr") -> str:
    """World view: which cells are darker than their own traffic mix explains."""
    fig, ax = plt.subplots(figsize=(11.5, 5.6))
    _context(ax, det, size=0.25)

    flagged = cells[cells["is_dark_spot"]].sort_values("sdr")
    sc = ax.scatter(
        flagged["cell_lon"] + 0.25,
        flagged["cell_lat"] + 0.25,
        c=flagged["sdr"].clip(1, 5),
        s=np.clip(flagged["detections"] / 3.0, 12, 260),
        cmap=CMAP_SEQUENTIAL,
        linewidths=0.5,
        edgecolors="#fcfcfb",
        zorder=3,
    )
    cb = fig.colorbar(sc, ax=ax, shrink=0.72, pad=0.015)
    cb.set_label("Standardised dark ratio (observed / expected)", fontsize=8, color=INK_SECONDARY)
    cb.outline.set_visible(False)

    for label, lon, lat, dx, dy in [
        ("Strait of Hormuz", 56.0, 26.0, 6, 8),
        ("Black Sea", 37.0, 44.5, -4, 8),
        ("Persian Gulf", 52.0, 26.5, -16, -12),
        ("Bay of Bengal", 89.0, 20.5, 4, 8),
        ("Gulf of Tonkin", 107.0, 19.0, 6, -10),
    ]:
        ax.annotate(
            label,
            xy=(lon, lat),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=8,
            color=INK,
            arrowprops={"arrowstyle": "-", "color": INK_MUTED, "lw": 0.8},
        )

    _frame(ax, (-180, 180, -60, 75), aspect_correct=False)
    ax.set_aspect(1.0)
    title(
        ax,
        "Global AIS dark spots, 1-14 March 2026",
        "Grey cloud: all 104,840 radar detections (the basemap is the data). Circles: cells significantly darker than their traffic mix predicts (BH-FDR q<0.05, SDR>=1.5); size = detections.",
    )
    fig.tight_layout()
    return _save(fig, name)


def map_typology(det: pd.DataFrame, cells: pd.DataFrame, name: str = "fig16_map_typology") -> str:
    """Dead zones and behavioural dark spots are different problems: show both."""
    # Validated as an all-pairs set (scatter uses every pair, not only adjacent
    # ones): worst CVD separation 13.0, worst normal-vision separation 16.3.
    types = {
        "Behavioural dark spot (selective switch-off)": CATEGORICAL[7],
        "AIS dead zone (reception / feed gap)": CATEGORICAL[6],
        "Non-carriage area (small craft, AIS not required)": CATEGORICAL[0],
        "Blackout, cause unresolved": CATEGORICAL[3],
    }
    fig, ax = plt.subplots(figsize=(11.5, 5.6))
    _context(ax, det, size=0.22)
    for label, color in types.items():
        sub = cells[cells["area_type"] == label]
        ax.scatter(
            sub["cell_lon"] + 0.25,
            sub["cell_lat"] + 0.25,
            s=np.clip(sub["detections"] / 4.0, 10, 180),
            color=color,
            alpha=0.85,
            linewidths=0.4,
            edgecolors="#fcfcfb",
            label=f"{label}  (n={len(sub)})",
            zorder=3,
        )
    ax.set_aspect(1.0)
    _frame(ax, (-180, 180, -60, 75), aspect_correct=False)
    ax.legend(loc="lower left", fontsize=7.4, ncols=2)
    title(
        ax,
        "Not all darkness is deliberate: a typology of AIS absence",
        "A cell where every ship is dark is a reception failure; a cell where large ships are dark while others match is a decision.",
    )
    fig.tight_layout()
    return _save(fig, name)


def map_hormuz(det: pd.DataFrame, name: str = "fig17_map_hormuz") -> str:
    """Two panels, same water: who is matched, and who is not."""
    extent = (53.0, 60.0, 23.5, 28.0)
    sub = det[det["lon"].between(extent[0], extent[1]) & det["lat"].between(extent[2], extent[3])]
    solas = sub[sub["length_m"] >= 100.0]

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6), sharex=True, sharey=True)
    for ax, (label, frame, color) in zip(
        axes,
        [
            ("Matched to AIS", solas[~solas["is_dark"]], SERIES_MATCHED),
            ("Dark (no usable AIS attribution)", solas[solas["is_dark"]], SERIES_DARK),
        ],
        strict=True,
    ):
        _context(ax, det, extent=extent, size=1.2)
        ax.scatter(
            frame["lon"],
            frame["lat"],
            s=np.clip(frame["length_m"] / 6.0, 6, 60),
            color=color,
            alpha=0.75,
            linewidths=0.3,
            edgecolors="#fcfcfb",
            zorder=3,
        )
        ax.set_title(f"{label}  -  {len(frame):,} vessels", fontsize=9.5, color=INK)
        _frame(ax, extent)

    fig.suptitle(
        "Strait of Hormuz: 84% of large vessels carry no usable AIS identity",
        x=0.01,
        ha="left",
        fontsize=11.5,
        weight="semibold",
        color=INK,
    )
    fig.text(
        0.01,
        0.015,
        "SOLAS-class detections (>= 100 m), 1-14 March 2026. Marker size scales with radar-measured length. Grey cloud: all detections in frame.",
        fontsize=7.2,
        color=INK_MUTED,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 0.94))
    return _save(fig, name)


def map_black_sea(det: pd.DataFrame, name: str = "fig18_map_black_sea") -> str:
    extent = (27.0, 42.0, 40.5, 47.5)
    sub = det[det["lon"].between(extent[0], extent[1]) & det["lat"].between(extent[2], extent[3])]
    solas = sub[sub["length_m"] >= 100.0]

    fig, ax = plt.subplots(figsize=(9.0, 5.0))
    _context(ax, det, extent=extent, size=1.4)
    ax.scatter(
        solas.loc[~solas["is_dark"], "lon"],
        solas.loc[~solas["is_dark"], "lat"],
        s=16,
        color=SERIES_MATCHED,
        alpha=0.7,
        label=f"Matched ({int((~solas['is_dark']).sum()):,})",
        zorder=3,
    )
    ax.scatter(
        solas.loc[solas["is_dark"], "lon"],
        solas.loc[solas["is_dark"], "lat"],
        s=22,
        color=SERIES_DARK,
        alpha=0.8,
        label=f"Dark ({int(solas['is_dark'].sum()):,})",
        zorder=4,
    )
    for label, lon, lat in [("Kerch Strait", 36.6, 45.3), ("Novorossiysk", 37.8, 44.7), ("Bosphorus", 29.1, 41.2)]:
        ax.annotate(label, xy=(lon, lat), xytext=(6, 6), textcoords="offset points", fontsize=8, color=INK)
    _frame(ax, extent)
    ax.legend(loc="lower left", fontsize=8)
    title(
        ax,
        "Black Sea: darkness concentrates on the eastern approaches",
        "SOLAS-class detections, 1-14 March 2026. The Bosphorus, under Turkish VTS, stays almost fully identified.",
    )
    fig.tight_layout()
    return _save(fig, name)


def map_red_sea(det: pd.DataFrame, name: str = "fig19_map_red_sea") -> str:
    """The emptiness itself is the finding, so the corridor boxes are drawn in."""
    extent = (30.0, 60.0, 5.0, 33.0)
    sub = det[det["lon"].between(extent[0], extent[1]) & det["lat"].between(extent[2], extent[3])]
    solas = sub[sub["length_m"] >= 100.0]

    fig, ax = plt.subplots(figsize=(8.8, 6.4))
    _context(ax, det, extent=extent, size=1.6)
    ax.scatter(
        solas["lon"],
        solas["lat"],
        s=18,
        color=CATEGORICAL[0],
        alpha=0.75,
        zorder=3,
        label=f"SOLAS-class vessels ({len(solas):,})",
    )
    for cp in load_chokepoints():
        if cp.id not in ("bab_el_mandeb", "southern_red_sea", "northern_red_sea", "suez_canal", "gulf_of_aden", "hormuz"):
            continue
        ax.add_patch(
            Rectangle(
                (cp.lon_min, cp.lat_min),
                cp.lon_max - cp.lon_min,
                cp.lat_max - cp.lat_min,
                fill=False,
                edgecolor=INK_MUTED,
                lw=1.0,
                ls="--",
                zorder=2,
            )
        )
        ax.annotate(
            cp.name,
            xy=(cp.lon_min, cp.lat_max),
            xytext=(2, 3),
            textcoords="offset points",
            fontsize=7.4,
            color=INK_SECONDARY,
            bbox={"facecolor": "#fcfcfb", "edgecolor": "none", "alpha": 0.75, "pad": 1.5},
        )
    _frame(ax, extent)
    ax.legend(loc="upper right", fontsize=8)
    title(
        ax,
        "The Red Sea in March 2026: a thin stream where a trunk route should be",
        "56 SOLAS-class vessels at Bab-el-Mandeb across 14 days - 6.2 per imaged scene against a 33.2 benchmark across uncontested corridors. Dashed boxes are the corridor definitions used throughout.",
    )
    fig.tight_layout()
    return _save(fig, name)


def map_conflict_hotspots(conflict_units: pd.DataFrame, det: pd.DataFrame, name: str = "fig20_map_conflict") -> str:
    """Conflict intensity ashore against the sea lanes it overlooks."""
    fig, ax = plt.subplots(figsize=(9.6, 5.6))
    extent = (24.0, 66.0, 8.0, 45.0)
    _context(ax, det, extent=extent, size=1.0)

    df = conflict_units[conflict_units["events"] > 0].copy()
    df = df[df["lon"].between(extent[0], extent[1]) & df["lat"].between(extent[2], extent[3])]
    sc = ax.scatter(
        df["lon"],
        df["lat"],
        s=np.clip(df["events"] / 12.0, 8, 420),
        c=np.log10(df["fatalities"] + 1),
        cmap=CMAP_SEQUENTIAL,
        alpha=0.85,
        linewidths=0.4,
        edgecolors="#fcfcfb",
        zorder=3,
    )
    cb = fig.colorbar(sc, ax=ax, shrink=0.75, pad=0.015)
    cb.set_label("Fatalities (log10)", fontsize=8, color=INK_SECONDARY)
    cb.outline.set_visible(False)

    for cp in load_chokepoints():
        if cp.id not in ("bab_el_mandeb", "hormuz", "suez_canal"):
            continue
        ax.add_patch(
            Rectangle(
                (cp.lon_min, cp.lat_min),
                cp.lon_max - cp.lon_min,
                cp.lat_max - cp.lat_min,
                fill=False,
                edgecolor=STATUS["RED"],
                lw=1.4,
                zorder=4,
            )
        )
    _frame(ax, extent)
    handles = [
        Line2D([], [], marker="o", ls="", color=CATEGORICAL[0], label="Admin unit, size = lifetime events"),
        Line2D([], [], marker="s", ls="", markerfacecolor="none", markeredgecolor=STATUS["RED"], label="Critical chokepoint"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=7.8)
    title(
        ax,
        "Conflict sits on top of the sea lanes it disrupts",
        "Bubble = ACLED admin unit, sized by total events 2015-2026, coloured by fatalities. Grey cloud: radar detections.",
    )
    fig.tight_layout()
    return _save(fig, name)


def run_all(det: pd.DataFrame, cells: pd.DataFrame, conflict_units: pd.DataFrame) -> dict[str, str]:
    apply_theme()
    return {
        "fig15": map_global_sdr(det, cells),
        "fig16": map_typology(det, cells),
        "fig17": map_hormuz(det),
        "fig18": map_black_sea(det),
        "fig19": map_red_sea(det),
        "fig20": map_conflict_hotspots(conflict_units, det),
    }
