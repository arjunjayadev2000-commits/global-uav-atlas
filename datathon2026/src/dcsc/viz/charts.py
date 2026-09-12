"""Every figure in the submission, one function per figure.

Chart form follows the job of the data: magnitude gets length (bars), change over
time gets position (lines), polarity gets a diverging scale about a meaningful
zero, identity gets a fixed categorical slot. Two measures on different scales are
never forced onto one pair of axes with two y-scales - they become two panels.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D

from ..config import FIGURES
from ..io_utils import get_logger
from .theme import (
    AXIS,
    CATEGORICAL,
    CMAP_DIVERGING,
    INK,
    INK_MUTED,
    INK_SECONDARY,
    STATUS,
    annotate,
    apply_theme,
    title,
)

LOG = get_logger("dcsc.viz.charts")


def _save(fig, name: str) -> str:
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    LOG.info("figure %s", path.name)
    return str(path)


# ---------------------------------------------------------------- conflict --


def fig_conflict_trend(weekly: pd.DataFrame, name: str = "fig01_conflict_trend") -> str:
    """Events and fatalities share an x-axis but never a y-axis: two panels."""
    fig, axes = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True, height_ratios=[1, 1])
    w = weekly.sort_values("week")
    roll = w.set_index("week")[["events", "fatalities"]].rolling(4).mean()

    axes[0].plot(w["week"], w["events"], color=CATEGORICAL[0], lw=0.8, alpha=0.35)
    axes[0].plot(roll.index, roll["events"], color=CATEGORICAL[0], lw=2.0)
    axes[0].set_ylabel("Events per week")
    title(
        axes[0],
        "Middle East conflict, weekly events and fatalities (2015-2026)",
        "Thin line: weekly value. Thick line: 4-week mean.",
    )

    axes[1].plot(w["week"], w["fatalities"], color=CATEGORICAL[1], lw=0.8, alpha=0.35)
    axes[1].plot(roll.index, roll["fatalities"], color=CATEGORICAL[1], lw=2.0)
    axes[1].set_ylabel("Fatalities per week")
    axes[1].set_xlabel("")

    for ax, label in zip(axes, ("Events", "Fatalities"), strict=True):
        ax.annotate(
            label,
            xy=(0.995, 0.92),
            xycoords="axes fraction",
            ha="right",
            fontsize=8.5,
            color=INK_SECONDARY,
        )
    annotate(axes[1], "Source: supplied ACLED-style Middle East weekly aggregate, 149,825 rows.")
    fig.tight_layout()
    return _save(fig, name)


def fig_event_mix(event_mix: pd.DataFrame, name: str = "fig02_event_mix") -> str:
    """Composition over time: stacked area, fixed slot order, 2px surface gaps."""
    pivot = (
        event_mix.pivot_table(index="year", columns="event_type", values="events", aggfunc="sum")
        .fillna(0)
        .loc[2015:2026]
    )
    order = pivot.sum().sort_values(ascending=False).index.tolist()
    pivot = pivot[order]

    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.stackplot(
        pivot.index,
        [pivot[c] for c in order],
        labels=order,
        colors=CATEGORICAL[: len(order)],
        edgecolor="#fcfcfb",
        linewidth=2.0,
    )
    ax.set_ylabel("Events per year")
    ax.set_xlim(pivot.index.min(), pivot.index.max())
    title(
        ax,
        "Explosions and remote violence dominate the mix, and grew fastest",
        "Event composition by year. 2026 is a part year (to 27 June).",
    )
    ax.legend(loc="upper left", ncols=3, fontsize=7.6)
    fig.tight_layout()
    return _save(fig, name)


def fig_country_heat(by_country_year: pd.DataFrame, name: str = "fig03_country_year_heat") -> str:
    """Magnitude across two categorical axes: one-hue sequential heatmap."""
    pivot = (
        by_country_year.pivot_table(index="country", columns="year", values="events", aggfunc="sum")
        .fillna(0)
        .loc[:, 2015:2026]
    )
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]

    fig, ax = plt.subplots(figsize=(9, 5.2))
    from .theme import CMAP_SEQUENTIAL

    im = ax.imshow(pivot.to_numpy(), aspect="auto", cmap=CMAP_SEQUENTIAL)
    ax.set_xticks(range(pivot.shape[1]), pivot.columns, rotation=0)
    ax.set_yticks(range(pivot.shape[0]), pivot.index)
    ax.grid(False)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.iloc[i, j]
            if v > pivot.to_numpy().max() * 0.35:
                ax.text(j, i, f"{int(v/1000)}k", ha="center", va="center", fontsize=6.5, color="#fcfcfb")
    cb = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("Events per year", color=INK_SECONDARY, fontsize=8)
    cb.outline.set_visible(False)
    title(ax, "Where the violence sits: events by country and year", "Darker means more events. Values in thousands shown on the heaviest cells.")
    fig.tight_layout()
    return _save(fig, name)


def fig_maritime_attacks(maritime: pd.DataFrame, name: str = "fig04_maritime_events") -> str:
    """ACLED events placed on the water itself - the attack-on-shipping series."""
    pivot = (
        maritime.pivot_table(index="week", columns="admin1", values="events", aggfunc="sum")
        .fillna(0)
        .sort_index()
    )
    pivot = pivot.rolling(4, min_periods=1).sum()

    fig, ax = plt.subplots(figsize=(9, 4.2))
    for i, col in enumerate(pivot.columns):
        ax.plot(pivot.index, pivot[col], color=CATEGORICAL[i], label=col, lw=2.0)
        last = pivot[col].iloc[-1]
        ax.annotate(
            col.replace(" Region", ""),
            xy=(pivot.index[-1], last),
            xytext=(6, 0),
            textcoords="offset points",
            fontsize=7.6,
            color=INK_SECONDARY,
            va="center",
        )
    ax.set_ylabel("Events at sea (4-week rolling sum)")
    ax.set_xlim(pd.Timestamp("2019-01-01"), pivot.index.max() + pd.Timedelta(weeks=40))
    title(
        ax,
        "Conflict moved onto the water from late 2023",
        "ACLED events whose location is a sea area rather than a land admin unit.",
    )
    ax.legend(loc="upper left", fontsize=7.6)
    annotate(ax, "The three sea areas carry a single centroid each, so these series carry no within-basin precision.")
    fig.tight_layout()
    return _save(fig, name)


# ---------------------------------------------------------------- maritime --


def fig_dark_by_length(by_length: pd.DataFrame, name: str = "fig05_dark_by_length") -> str:
    """Why a raw dark rate must never be compared between corridors."""
    df = by_length.copy()
    fig, ax = plt.subplots(figsize=(8.4, 4.0))
    bars = ax.bar(
        df["length_class"].astype(str),
        df["dark_rate"] * 100,
        color=CATEGORICAL[0],
        width=0.62,
    )
    for rect, v, n in zip(bars, df["dark_rate"] * 100, df["detections"], strict=True):
        ax.annotate(
            f"{v:.0f}%",
            xy=(rect.get_x() + rect.get_width() / 2, v),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            fontsize=8.2,
            color=INK,
        )
        ax.annotate(
            f"n={n:,}",
            xy=(rect.get_x() + rect.get_width() / 2, 1),
            ha="center",
            fontsize=7,
            color="#fcfcfb",
        )
    ax.axvspan(2.5, 5.5, color=STATUS["AMBER"], alpha=0.10, zorder=0)
    ax.annotate(
        "AIS carriage mandatory (SOLAS)",
        xy=(4.0, ax.get_ylim()[1] * 0.86),
        ha="center",
        fontsize=8,
        color=INK_SECONDARY,
    )
    ax.set_ylabel("Dark detections (%)")
    ax.set_xticks(range(len(df)), [c.split(" (")[0] for c in df["length_class"].astype(str)])
    title(
        ax,
        "Small craft are dark because they are small, not because they are hiding",
        "Any corridor comparison that ignores this measures fishing fleets, not concealment.",
    )
    fig.tight_layout()
    return _save(fig, name)


def fig_corridor_dark(profile: pd.DataFrame, name: str = "fig06_corridor_dark_rate") -> str:
    """Dot plot with Wilson intervals - the headline corridor ranking."""
    df = (
        profile[(profile["solas_detections"] >= 50) & (profile["chokepoint_id"] != "open_ocean")]
        .sort_values("solas_dark_rate")
        .copy()
    )
    baseline = float(
        profile.loc[profile["chokepoint_id"] == "open_ocean", "solas_dark_rate"].iloc[0]
    )

    fig, ax = plt.subplots(figsize=(8.6, 7.2))
    y = np.arange(len(df))
    ax.hlines(y, df["solas_dark_lo"] * 100, df["solas_dark_hi"] * 100, color=AXIS, lw=2.0)
    colors = [
        STATUS["RED"] if v > 0.4 else STATUS["AMBER"] if v > 0.2 else CATEGORICAL[0]
        for v in df["solas_dark_rate"]
    ]
    ax.scatter(df["solas_dark_rate"] * 100, y, s=54, color=colors, zorder=3, edgecolor="#fcfcfb", linewidth=1.2)
    ax.axvline(baseline * 100, color=INK_MUTED, lw=1.2, ls="--")
    ax.annotate(
        f"open-ocean baseline {baseline*100:.0f}%",
        xy=(baseline * 100, len(df) - 0.4),
        xytext=(6, 0),
        textcoords="offset points",
        fontsize=7.8,
        color=INK_MUTED,
    )
    for yi, (v, n) in enumerate(zip(df["solas_dark_rate"], df["solas_detections"], strict=True)):
        ax.annotate(
            f"{v*100:.0f}%  (n={int(n):,})",
            xy=(v * 100, yi),
            xytext=(10, 0),
            textcoords="offset points",
            va="center",
            fontsize=7.6,
            color=INK_SECONDARY,
        )
    ax.set_yticks(y, df["chokepoint"])
    ax.set_xlabel("SOLAS-class (>= 100 m) detections unmatched to AIS (%)")
    ax.set_xlim(0, 105)
    title(
        ax,
        "Where large ships stop being identifiable",
        "Bars are 95% Wilson intervals. Only vessels legally obliged to transmit AIS are counted.",
    )
    legend = [
        Line2D([], [], marker="o", ls="", color=STATUS["RED"], label="Severe (>40%)"),
        Line2D([], [], marker="o", ls="", color=STATUS["AMBER"], label="Elevated (20-40%)"),
        Line2D([], [], marker="o", ls="", color=CATEGORICAL[0], label="Normal (<20%)"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=7.8)
    fig.tight_layout()
    return _save(fig, name)


def fig_throughput_deficit(deficit: pd.DataFrame, name: str = "fig07_throughput_deficit") -> str:
    """Polarity about a meaningful zero: diverging scale, blue above, red below."""
    keep = (
        "bab_el_mandeb",
        "gulf_of_aden",
        "southern_red_sea",
        "northern_red_sea",
        "suez_canal",
        "hormuz",
        "persian_gulf",
        "black_sea",
        "eastern_med",
        "cape_of_good_hope",
        "malacca",
        "singapore_strait",
        "dover",
        "gibraltar",
        "panama",
    )
    df = deficit[deficit["chokepoint_id"].isin(keep)].copy()
    df["pct_vs_benchmark"] = (df["throughput_ratio"] - 1) * 100
    df = df.sort_values("pct_vs_benchmark")

    norm = plt.Normalize(-100, 100)
    colors = [CMAP_DIVERGING(norm(-v)) for v in df["pct_vs_benchmark"]]

    fig, ax = plt.subplots(figsize=(8.6, 5.6))
    y = np.arange(len(df))
    ax.barh(y, df["pct_vs_benchmark"], color=colors, height=0.62)
    ax.axvline(0, color=AXIS, lw=1.0)
    ax.set_yticks(y, df["chokepoint"])
    ax.set_xlabel("Large-vessel throughput per imaged scene, % vs uncontested-corridor benchmark")
    # Long bars carry their label inside the bar; short ones outside. Otherwise a
    # -81% label lands on top of the corridor name.
    span = max(abs(df["pct_vs_benchmark"].min()), abs(df["pct_vs_benchmark"].max()))
    for yi, v in zip(y, df["pct_vs_benchmark"], strict=True):
        inside = abs(v) > 0.45 * span
        if v >= 0:
            dx, ha, color = (-6, "right", "#fcfcfb") if inside else (6, "left", INK_SECONDARY)
        else:
            dx, ha, color = (6, "left", "#fcfcfb") if inside else (-6, "right", INK_SECONDARY)
        ax.annotate(
            f"{v:+.0f}%",
            xy=(v, yi),
            xytext=(dx, 0),
            textcoords="offset points",
            va="center",
            ha=ha,
            fontsize=7.8,
            color=color,
        )
    title(
        ax,
        "The Red Sea corridor's problem is absence, not concealment",
        "Benchmark = median SOLAS detections per scene across uncontested corridors (Dover, Gibraltar, Panama, Malacca, Singapore, Sunda, Lombok, Cape, Bay of Bengal).",
    )
    annotate(ax, "Scene counts are inferred from scenes yielding a detection, which under-counts observation of empty water: deficits shown are a lower bound.")
    fig.tight_layout()
    return _save(fig, name)


def fig_route_comparison(routes: pd.DataFrame, name: str = "fig08_route_suez_vs_cape") -> str:
    """Two routes, one measure: a plain comparison bar with the ratio called out."""
    df = routes.set_index("route")
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    order = ["Suez / Red Sea route", "Cape of Good Hope route"]
    vals = [df.loc[r, "solas_per_scene"] for r in order]
    bars = ax.barh(order, vals, color=[CATEGORICAL[1], CATEGORICAL[0]], height=0.5)
    for rect, v, n in zip(bars, vals, [df.loc[r, "solas_detections"] for r in order], strict=True):
        ax.annotate(
            f"{v:.1f} per scene   ({int(n):,} detections)",
            xy=(v, rect.get_y() + rect.get_height() / 2),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=8.4,
            color=INK_SECONDARY,
        )
    ax.set_xlim(0, max(vals) * 1.55)
    ax.set_xlabel("SOLAS-class detections per imaged Sentinel-1 scene")
    title(
        ax,
        "A detour around Africa now carries as much large-vessel traffic as the canal route",
        "Same 14 days, same sensor, same size threshold.",
    )
    fig.tight_layout()
    return _save(fig, name)


# ------------------------------------------------------------- inferential --


def fig_logit_forest(logit: pd.DataFrame, name: str = "fig09_logit_odds") -> str:
    """Effect sizes with intervals, on a log odds-ratio axis centred on 1."""
    labels = {
        "log_length": "Vessel length (per log-metre)",
        "fishing_score": "Fishing behaviour score",
        "conflict_log_300km": "Conflict events within 300 km (per log-unit)",
        "near_conflict_150km": "Within 150 km of recent conflict",
        "ascending_pass": "Ascending satellite pass",
    }
    df = logit[logit["term"] != "const"].copy()
    df["label"] = df["term"].map(labels).fillna(df["term"])
    df = df.sort_values("odds_ratio")

    fig, ax = plt.subplots(figsize=(8.4, 3.8))
    y = np.arange(len(df))
    ax.hlines(y, df["or_lo"], df["or_hi"], color=AXIS, lw=2.2)
    colors = [
        STATUS["RED"] if (lo > 1) else CATEGORICAL[0] if (hi < 1) else INK_MUTED
        for lo, hi in zip(df["or_lo"], df["or_hi"], strict=True)
    ]
    ax.scatter(df["odds_ratio"], y, s=56, color=colors, zorder=3, edgecolor="#fcfcfb", linewidth=1.2)
    ax.axvline(1.0, color=INK_MUTED, lw=1.0, ls="--")
    ax.set_xscale("log")
    ax.set_xticks([0.5, 0.75, 1, 1.5, 2, 3, 5], ["0.5", "0.75", "1", "1.5", "2", "3", "5"])
    ax.set_yticks(y, df["label"])
    ax.set_xlabel("Odds ratio for a SOLAS-class vessel being dark (log scale)")
    for yi, row in enumerate(df.itertuples()):
        ax.annotate(
            f"{row.odds_ratio:.2f}  [{row.or_lo:.2f}-{row.or_hi:.2f}]",
            xy=(row.or_hi, yi),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=7.6,
            color=INK_SECONDARY,
        )
    ax.set_xlim(0.3, 12)
    title(
        ax,
        "Conflict nearby raises the odds that a large ship goes dark",
        f"Logistic regression, n={logit.attrs.get('n', 0):,} SOLAS-class detections, standard errors clustered on 0.5-degree cells.",
    )
    fig.tight_layout()
    return _save(fig, name)


def fig_lead_lag(ll: pd.DataFrame, name: str = "fig10_lead_lag") -> str:
    fig, ax = plt.subplots(figsize=(8.2, 3.6))
    colors = [CATEGORICAL[0] if lag == 0 else "#9ec5f4" for lag in ll["lag_weeks"]]
    ax.bar(ll["lag_weeks"], ll["correlation"], color=colors, width=0.68)
    peak = ll.loc[ll["correlation"].idxmax()]
    ax.annotate(
        f"peak r = {peak['correlation']:.2f} at lag {int(peak['lag_weeks'])}",
        xy=(peak["lag_weeks"], peak["correlation"]),
        xytext=(0, 8),
        textcoords="offset points",
        ha="center",
        fontsize=8,
        color=INK,
    )
    ax.set_xlabel("Lag (weeks). Positive = violence ashore leads attacks at sea")
    ax.set_ylabel("Pearson correlation")
    ax.set_ylim(0, max(ll["correlation"]) * 1.25)
    title(
        ax,
        "Attacks at sea move with the land campaign, not after it",
        "Cross-correlation, weekly series, 2019-2026. A flat profile means no exploitable warning time.",
    )
    fig.tight_layout()
    return _save(fig, name)


def fig_forecast(forecasts: pd.DataFrame, pressure: pd.DataFrame, name: str = "fig11_forecast") -> str:
    """Small multiples: one panel per corridor, history plus interval-banded forecast."""
    corridors = forecasts["chokepoint_id"].unique()
    n = len(corridors)
    fig, axes = plt.subplots(int(np.ceil(n / 2)), 2, figsize=(9.4, 2.5 * np.ceil(n / 2)), sharex=True)
    axes = np.atleast_1d(axes).ravel()

    for ax, cid in zip(axes, corridors, strict=False):
        hist = pressure[pressure["chokepoint_id"] == cid].sort_values("week")
        hist = hist[hist["week"] >= "2023-01-01"]
        fc = forecasts[forecasts["chokepoint_id"] == cid]
        ax.plot(hist["week"], hist["events_within"], color=CATEGORICAL[0], lw=1.6, label="Observed")
        ax.fill_between(fc["week"], fc["lower"], fc["upper"], color=CATEGORICAL[1], alpha=0.18, lw=0)
        ax.plot(fc["week"], fc["forecast"], color=CATEGORICAL[1], lw=2.0, label="Forecast")
        ax.set_title(
            f"{hist['chokepoint'].iloc[0]}  ({fc['model'].iloc[0]})", fontsize=9.5, color=INK
        )
        ax.set_ylabel("Events/week")
    for ax in axes[len(corridors) :]:
        ax.set_visible(False)
    axes[0].legend(loc="upper left", fontsize=7.6)
    fig.suptitle(
        "Twelve-week outlook for conflict pressure on each corridor",
        x=0.01,
        ha="left",
        fontsize=11.5,
        weight="semibold",
        color=INK,
    )
    fig.text(
        0.01,
        0.015,
        "Band = 10th-90th percentile of the winning model's own backtest errors, widened with the square root of horizon. Model named per panel.",
        fontsize=7.2,
        color=INK_MUTED,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.96))
    return _save(fig, name)


def fig_model_performance(
    scores: pd.DataFrame, importance: pd.DataFrame, name: str = "fig12_darkspot_model"
) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.0), width_ratios=[1, 1.25])

    folds = scores[scores["fold"] != "overall (out-of-fold)"]
    overall = scores[scores["fold"] == "overall (out-of-fold)"].iloc[0]
    axes[0].bar(
        folds["fold"].astype(str), folds["roc_auc"], color=CATEGORICAL[0], width=0.6, label="ROC-AUC"
    )
    axes[0].axhline(0.5, color=INK_MUTED, ls="--", lw=1.0)
    axes[0].axhline(overall["roc_auc"], color=CATEGORICAL[1], lw=2.0)
    axes[0].annotate(
        f"out-of-fold {overall['roc_auc']:.3f}",
        xy=(0.02, overall["roc_auc"]),
        xytext=(0, 6),
        textcoords="offset points",
        fontsize=8,
        color=CATEGORICAL[1],
    )
    axes[0].annotate("chance", xy=(0.02, 0.5), xytext=(0, 5), textcoords="offset points", fontsize=7.6, color=INK_MUTED)
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("ROC-AUC")
    axes[0].set_xlabel("Spatial block fold")
    axes[0].set_title("Held-out skill by spatial fold", fontsize=9.5)

    labels = {
        "abs_lat": "Latitude (abs)",
        "conflict_nearest_km": "Distance to nearest conflict",
        "mean_length_m": "Mean vessel length",
        "fishing_share": "Fishing share",
        "dist_critical_km": "Distance to critical chokepoint",
        "conflict_events_300km": "Conflict events within 300 km",
        "density_per_1k_km2": "Traffic density",
        "solas_share": "Large-vessel share",
        "log_detections": "Detections (log)",
        "scenes": "Scenes observing cell",
    }
    imp = importance.sort_values("permutation_importance").tail(8)
    y = np.arange(len(imp))
    axes[1].barh(y, imp["permutation_importance"], xerr=imp["permutation_std"],
                 color=CATEGORICAL[0], height=0.6, error_kw={"ecolor": AXIS, "lw": 1.2})
    axes[1].set_yticks(y, [labels.get(f, f) for f in imp["feature"]])
    axes[1].set_xlabel("Drop in ROC-AUC when the feature is shuffled")
    axes[1].set_title("What predicts a dark spot", fontsize=9.5)

    fig.suptitle(
        "Dark-spot classifier: spatially blocked validation",
        x=0.01,
        ha="left",
        fontsize=11.5,
        weight="semibold",
        color=INK,
    )
    fig.text(
        0.01,
        0.02,
        "Folds are whole 5-degree blocks, so the model is always scored on water it has never seen. Random k-fold would inflate this score.",
        fontsize=7.2,
        color=INK_MUTED,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    return _save(fig, name)


# ------------------------------------------------------------------- risk --


def fig_msri(index: pd.DataFrame, name: str = "fig13_msri_ranking") -> str:
    """Stacked contribution bars: the index and what drives it, in one read."""
    from ..analysis.risk_index import COMPONENTS, load_weights

    weights = load_weights()["weights"]
    df = index.head(14).iloc[::-1].copy()
    contrib = df[COMPONENTS].mul(pd.Series(weights))

    fig, ax = plt.subplots(figsize=(9.0, 5.8))
    y = np.arange(len(df))
    left = np.zeros(len(df))
    pretty = {
        "conflict_intensity": "Conflict intensity",
        "escalation_trend": "Escalation trend",
        "identification_risk": "Identification risk (dark)",
        "throughput_disruption": "Throughput disruption",
        "strategic_criticality": "Strategic criticality",
    }
    for i, comp in enumerate(COMPONENTS):
        ax.barh(
            y,
            contrib[comp],
            left=left,
            color=CATEGORICAL[i],
            height=0.62,
            label=pretty[comp],
            edgecolor="#fcfcfb",
            linewidth=2.0,
        )
        left = left + contrib[comp].to_numpy()

    for yi, (score, tier) in enumerate(zip(df["msri"], df["tier"], strict=True)):
        ax.annotate(
            f"{score:.2f}  {tier}",
            xy=(score, yi),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=7.8,
            color=STATUS.get(tier, INK_SECONDARY),
            weight="semibold" if tier == "RED" else "normal",
        )
    ax.set_yticks(y, df["chokepoint"])
    ax.set_xlim(0, max(df["msri"]) * 1.28)
    ax.set_xlabel("Maritime Supply-Chain Risk Index (weighted component contributions)")
    title(
        ax,
        "Which lanes to worry about first, and why",
        "Segment length is each component's weighted contribution. Tier labels accompany the colour, never replace it.",
    )
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(0, -0.12),
        fontsize=7.8,
        ncols=3,
        columnspacing=1.4,
    )
    fig.tight_layout()
    return _save(fig, name)


def fig_india_exposure(index: pd.DataFrame, name: str = "fig14_india_exposure") -> str:
    df = index.sort_values("india_exposure", ascending=False).head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    y = np.arange(len(df))
    ax.barh(y, df["india_exposure"], color=CATEGORICAL[0], height=0.6)
    ax.scatter(df["msri"], y, s=40, color=CATEGORICAL[1], zorder=3, label="MSRI (risk alone)")
    ax.set_yticks(y, df["chokepoint"])
    ax.set_xlabel("Risk x Indian trade dependency")
    for yi, row in enumerate(df.itertuples()):
        ax.annotate(
            f"{row.india_exposure:.2f}",
            xy=(row.india_exposure, yi),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=7.6,
            color=INK_SECONDARY,
        )
    handles = [
        Line2D([], [], marker="s", ls="", color=CATEGORICAL[0], label="Exposure (risk x dependency)"),
        Line2D([], [], marker="o", ls="", color=CATEGORICAL[1], label="MSRI (risk alone)"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=7.8)
    # The headline names whatever the data actually ranks first and second, so the
    # chart can never assert an order it does not show.
    lead = df.iloc[::-1]["chokepoint"].tolist()[:2]
    title(
        ax,
        f"Indian exposure: {lead[0]} first, {lead[1]} second",
        "Dependency scores are a declared analyst judgement held in config/risk_weights.json, not a measurement.",
    )
    fig.tight_layout()
    return _save(fig, name)


def run_all(tables: dict) -> dict[str, str]:
    """Draw every chart from a dict of analysis frames."""
    apply_theme()
    figures = {
        "fig01": fig_conflict_trend(tables["conflict_weekly_totals"]),
        "fig02": fig_event_mix(tables["conflict_event_mix"]),
        "fig03": fig_country_heat(tables["conflict_by_country_year"]),
        "fig04": fig_maritime_attacks(tables["conflict_maritime_domain_events"]),
        "fig05": fig_dark_by_length(tables["sar_dark_by_length_class"]),
        "fig06": fig_corridor_dark(tables["corridor_profile"]),
        "fig07": fig_throughput_deficit(tables["deficit"]),
        "fig08": fig_route_comparison(tables["routes"]),
        "fig09": fig_logit_forest(tables["logit"]),
        "fig10": fig_lead_lag(tables["lead_lag"]),
        "fig12": fig_model_performance(tables["model_scores"], tables["model_importance"]),
        "fig13": fig_msri(tables["msri"]),
        "fig14": fig_india_exposure(tables["msri"]),
    }
    if "forecasts" in tables:
        figures["fig11"] = fig_forecast(tables["forecasts"], tables["pressure"])
    else:
        LOG.warning("no forecast frame supplied; fig11 skipped")
    return figures
