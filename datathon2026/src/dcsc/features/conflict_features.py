"""Conflict-side feature engineering.

Turns the weekly ACLED aggregate into the three shapes the rest of the analysis
consumes:

1. calendar series (weekly / monthly, by country, theatre and event type);
2. an admin-unit x corridor proximity table, which is what lets a land-based
   strike be attributed to the sea lane it threatens;
3. a weekly *corridor pressure* series - conflict intensity experienced by each
   maritime corridor - which is the conflict-side variable in every coupling,
   forecasting and risk-index step.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import SETTINGS, load_chokepoints
from ..io_utils import get_logger
from .geo import distance_to_chokepoints

LOG = get_logger("dcsc.features.conflict")

#: ACLED admin units that are water bodies rather than land. Their events are
#: attacks on, or interceptions over, shipping itself.
MARITIME_ADMIN1 = (
    "North Indian Ocean",
    "Wider Black Sea Region",
    "Eastern Mediterranean Sea",
)

#: Sub-event types that directly signal interference with, or attack on, shipping.
SHIPPING_THREAT_SUB_EVENTS = (
    "Air/drone strike",
    "Shelling/artillery/missile attack",
    "Disrupted weapons use",
    "Attack",
    "Armed clash",
    "Remote explosive/landmine/IED",
)


def weekly_series(df: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    """Sum events, fatalities and exposure to a weekly grain."""
    keys = ["week", *(by or [])]
    out = (
        df.groupby(keys, dropna=False, observed=True)
        .agg(
            events=("events", "sum"),
            fatalities=("fatalities", "sum"),
            population_exposure=("population_exposure", "sum"),
            admin_units=("admin_id", "nunique"),
        )
        .reset_index()
    )
    out["lethality"] = out["fatalities"] / out["events"].replace(0, np.nan)
    return out


def admin_units(df: pd.DataFrame) -> pd.DataFrame:
    """One row per admin unit with its centroid and lifetime totals."""
    return (
        df.groupby(["admin_id", "country", "admin1"], observed=True)
        .agg(
            lat=("lat", "first"),
            lon=("lon", "first"),
            events=("events", "sum"),
            fatalities=("fatalities", "sum"),
            weeks_active=("week", "nunique"),
        )
        .reset_index()
        .assign(is_maritime=lambda d: d["admin1"].isin(MARITIME_ADMIN1))
    )


def corridor_proximity(df: pd.DataFrame) -> pd.DataFrame:
    """Distance from every admin unit to every corridor box, in long form.

    Only pairs within a generous cut-off are kept (10x the coupling buffer), which
    keeps the table small without pre-judging the radius used later.
    """
    units = admin_units(df)
    dist = distance_to_chokepoints(units["lat"].to_numpy(), units["lon"].to_numpy())
    long = (
        pd.concat([units[["admin_id", "country", "admin1"]], dist], axis=1)
        .melt(
            id_vars=["admin_id", "country", "admin1"],
            var_name="chokepoint_id",
            value_name="distance_km",
        )
        .query("distance_km <= @SETTINGS.coastal_buffer_km * 10")
        .reset_index(drop=True)
    )
    names = {cp.id: cp.name for cp in load_chokepoints()}
    long["chokepoint"] = long["chokepoint_id"].map(names)
    LOG.info("corridor proximity pairs=%d (from %d admin units)", len(long), len(units))
    return long


def corridor_pressure(
    df: pd.DataFrame,
    buffer_km: float | None = None,
    decay_km: float = 150.0,
) -> pd.DataFrame:
    """Weekly conflict pressure on each maritime corridor.

    Two weightings are produced side by side:

    ``events_within``   hard cut-off - events in admin units whose centroid is
                        within ``buffer_km`` of the corridor box.
    ``events_weighted`` exponential decay ``exp(-d / decay_km)`` applied to every
                        pair inside the cut-off, so a strike on the coast counts
                        for more than one 200 km inland.

    The decayed version is the one used for correlation work; the hard cut-off is
    kept because it is what a staff officer can reproduce on a paper map.
    """
    buffer_km = buffer_km or SETTINGS.coastal_buffer_km
    prox = corridor_proximity(df)
    near = prox[prox["distance_km"] <= buffer_km].copy()
    near["weight"] = np.exp(-near["distance_km"] / decay_km)

    weekly = (
        df.groupby(["week", "admin_id"], observed=True)
        .agg(
            events=("events", "sum"),
            fatalities=("fatalities", "sum"),
            shipping_threat=(
                "sub_event_type",
                lambda s: 0,
            ),
        )
        .reset_index()
        .drop(columns=["shipping_threat"])
    )
    threat = (
        df[df["sub_event_type"].isin(SHIPPING_THREAT_SUB_EVENTS)]
        .groupby(["week", "admin_id"], observed=True)["events"]
        .sum()
        .rename("threat_events")
        .reset_index()
    )
    weekly = weekly.merge(threat, on=["week", "admin_id"], how="left").fillna({"threat_events": 0})

    merged = weekly.merge(near[["admin_id", "chokepoint_id", "chokepoint", "weight"]], on="admin_id")
    merged["events_weighted"] = merged["events"] * merged["weight"]
    merged["threat_weighted"] = merged["threat_events"] * merged["weight"]

    out = (
        merged.groupby(["week", "chokepoint_id", "chokepoint"], observed=True)
        .agg(
            events_within=("events", "sum"),
            fatalities_within=("fatalities", "sum"),
            threat_events=("threat_events", "sum"),
            events_weighted=("events_weighted", "sum"),
            threat_weighted=("threat_weighted", "sum"),
            admin_units=("admin_id", "nunique"),
        )
        .reset_index()
        .sort_values(["chokepoint_id", "week"])
    )
    # 4-week trailing intensity: single weeks are noisy, and a lane's risk state is
    # better described by the month behind it than by one week's headline.
    out["events_4w"] = (
        out.groupby("chokepoint_id", observed=True)["events_within"]
        .transform(lambda s: s.rolling(4, min_periods=1).sum())
    )
    LOG.info("corridor pressure rows=%d corridors=%d", len(out), out["chokepoint_id"].nunique())
    return out


def maritime_events(df: pd.DataFrame) -> pd.DataFrame:
    """Events that ACLED places on the water itself, i.e. attacks on shipping."""
    out = df[df["admin1"].isin(MARITIME_ADMIN1)].copy()
    out["maritime_theatre"] = out["admin1"]
    return out


def escalation_index(weekly: pd.DataFrame, window: int = 8) -> pd.DataFrame:
    """Z-scored escalation of a weekly series against its own trailing window.

    A corridor is 'escalating' when the current week sits well above the mean of
    the preceding ``window`` weeks. Standardising per corridor keeps a quiet lane
    with a small absolute count comparable to a busy one.
    """
    out = weekly.sort_values("week").copy()
    grp = out.groupby("chokepoint_id", observed=True)["events_within"]
    roll_mean = grp.transform(lambda s: s.shift(1).rolling(window, min_periods=3).mean())
    roll_std = grp.transform(lambda s: s.shift(1).rolling(window, min_periods=3).std())
    out["escalation_z"] = (out["events_within"] - roll_mean) / roll_std.replace(0, np.nan)
    out["escalating"] = out["escalation_z"] > 2.0
    return out
