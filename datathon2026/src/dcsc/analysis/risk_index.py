"""The Maritime Supply-Chain Risk Index (MSRI).

Individual findings - a dark rate here, a traffic deficit there, a conflict
forecast somewhere else - do not by themselves tell a staff officer which lane to
worry about first. The MSRI combines them into one ranked picture per corridor.

Five components, each scaled to 0-1 across corridors:

``conflict_intensity``    conflict pressure on the corridor over the last 12 weeks;
``escalation_trend``      last 12 weeks against the 12 before them - direction of travel;
``identification_risk``   SOLAS-class dark rate, i.e. loss of the recognised picture;
``throughput_disruption`` shortfall in large-vessel throughput against uncontested peers;
``strategic_criticality`` whether the corridor is a chokepoint with no practical bypass.

Scaling is min-max across the corridors in the run, so the index is explicitly
*relative*: it ranks lanes against each other in one period, and an MSRI of 0.8
means "among the worst lanes observed", never "80% likely to close". The weights
live in ``config/risk_weights.json`` and are a declared judgement, so an assessor
can dissent from them by editing one file and re-running.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..config import CONFIG_DIR
from ..io_utils import get_logger, save_table

LOG = get_logger("dcsc.analysis.risk")

COMPONENTS = [
    "conflict_intensity",
    "escalation_trend",
    "identification_risk",
    "throughput_disruption",
    "strategic_criticality",
]


def load_weights() -> dict:
    return json.loads((CONFIG_DIR / "risk_weights.json").read_text(encoding="utf-8"))


def _minmax(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if not np.isfinite(lo) or not np.isfinite(hi) or hi == lo:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def build(
    profile: pd.DataFrame,
    pressure: pd.DataFrame,
    deficit: pd.DataFrame,
    as_of: str = "2026-06-27",
) -> pd.DataFrame:
    """Assemble the index. ``as_of`` anchors the 12-week windows."""
    cfg = load_weights()
    weights = cfg["weights"]
    as_of_ts = pd.Timestamp(as_of)

    recent = pressure[
        (pressure["week"] > as_of_ts - pd.Timedelta(weeks=12)) & (pressure["week"] <= as_of_ts)
    ]
    prior = pressure[
        (pressure["week"] > as_of_ts - pd.Timedelta(weeks=24))
        & (pressure["week"] <= as_of_ts - pd.Timedelta(weeks=12))
    ]
    recent_agg = recent.groupby("chokepoint_id")["events_within"].sum().rename("events_12w")
    prior_agg = prior.groupby("chokepoint_id")["events_within"].sum().rename("events_prior_12w")

    df = (
        profile[
            [
                "chokepoint_id",
                "chokepoint",
                "theatre",
                "critical",
                "detections",
                "solas_detections",
                "solas_dark_rate",
                "standardised_dark_rate",
            ]
        ]
        .merge(
            deficit[["chokepoint_id", "solas_per_scene", "throughput_ratio", "deficit_pct"]],
            on="chokepoint_id",
            how="left",
        )
        .merge(recent_agg, on="chokepoint_id", how="left")
        .merge(prior_agg, on="chokepoint_id", how="left")
    )
    df = df[(df["chokepoint_id"] != "open_ocean") & (df["solas_detections"] >= 50)].copy()
    df[["events_12w", "events_prior_12w"]] = df[["events_12w", "events_prior_12w"]].fillna(0.0)

    # --- components --------------------------------------------------------
    df["conflict_intensity"] = _minmax(np.log1p(df["events_12w"]))
    growth = (df["events_12w"] + 1) / (df["events_prior_12w"] + 1)
    df["escalation_trend"] = _minmax(np.log(growth).clip(-2, 2))
    df["identification_risk"] = _minmax(df["solas_dark_rate"].fillna(0))
    df["throughput_disruption"] = _minmax((1 - df["throughput_ratio"]).clip(lower=0).fillna(0))
    df["strategic_criticality"] = df["critical"].astype(float)

    df["msri"] = sum(df[c] * weights[c] for c in COMPONENTS)
    tiers = cfg["tiers"]
    df["tier"] = np.select(
        [df["msri"] >= tiers["red_min"], df["msri"] >= tiers["amber_min"]],
        ["RED", "AMBER"],
        default="GREEN",
    )

    # --- India-specific view ----------------------------------------------
    dep = {k: v["score"] for k, v in cfg["india_dependency"].items()}
    why = {k: v["why"] for k, v in cfg["india_dependency"].items()}
    df["india_dependency"] = df["chokepoint_id"].map(dep).fillna(0.2)
    df["india_dependency_note"] = df["chokepoint_id"].map(why).fillna("")
    df["india_exposure"] = df["msri"] * df["india_dependency"]

    df = df.sort_values("msri", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))
    LOG.info(
        "MSRI built for %d corridors; RED=%d AMBER=%d",
        len(df),
        int((df["tier"] == "RED").sum()),
        int((df["tier"] == "AMBER").sum()),
    )
    return df


def watchlist(index: pd.DataFrame, top: int = 8) -> pd.DataFrame:
    """The ranked watchlist with the dominant driver named for each corridor."""
    out = index.head(top).copy()
    cfg = load_weights()["weights"]
    contributions = out[COMPONENTS].mul(pd.Series(cfg))
    out["dominant_driver"] = contributions.idxmax(axis=1).str.replace("_", " ")
    out["driver_share_pct"] = (contributions.max(axis=1) / out["msri"] * 100).round(1)
    return out[
        [
            "rank",
            "chokepoint",
            "theatre",
            "msri",
            "tier",
            "dominant_driver",
            "driver_share_pct",
            "solas_dark_rate",
            "deficit_pct",
            "events_12w",
            "india_dependency",
            "india_exposure",
        ]
    ]


def run(profile: pd.DataFrame, pressure: pd.DataFrame, deficit: pd.DataFrame) -> dict:
    index = build(profile, pressure, deficit)
    wl = watchlist(index)
    save_table(index, "risk_index_msri")
    save_table(wl, "risk_index_watchlist")
    save_table(
        index.sort_values("india_exposure", ascending=False)[
            ["chokepoint", "msri", "india_dependency", "india_exposure", "india_dependency_note"]
        ],
        "risk_index_india_exposure",
    )
    return {"index": index, "watchlist": wl}
