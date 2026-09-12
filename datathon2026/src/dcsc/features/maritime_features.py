"""Maritime-side feature engineering from the SAR detection extract.

The central methodological problem is that a raw dark rate is not comparable
between corridors. Small craft are dark because they are small - below the SOLAS
carriage threshold they are not required to transmit AIS at all - so a lane full
of fishing boats looks 'dark' for entirely innocent reasons, and the Bay of
Bengal would out-rank the Black Sea.

Two corrections are applied:

* a **SOLAS-class subset** (>= 100 m), where AIS carriage is mandatory and a dark
  detection is a genuine anomaly; and
* **direct standardisation** of the dark rate to the global length-class mix, the
  same device epidemiology uses for age-standardised rates, which answers: what
  would this corridor's dark rate be if it carried the world's average mix of
  ship sizes?
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import load_chokepoints
from ..io_utils import get_logger
from .geo import bbox_area_km2, wilson_interval

LOG = get_logger("dcsc.features.maritime")

SOLAS_LENGTH_M = 100.0
"""Working proxy for the SOLAS Chapter V AIS carriage threshold (300 GT on
international voyages). Length is what SAR measures; 100 m is comfortably above
the tonnage threshold for every normal hull form, so a dark detection at or above
it is an anomaly rather than an exemption."""


def standardised_dark_rate(
    df: pd.DataFrame,
    group_cols: list[str],
    dark_col: str = "is_dark",
    strata_col: str = "length_class",
    min_stratum_n: int = 15,
) -> pd.DataFrame:
    """Crude and length-standardised dark rates per group.

    The standard population is the length-class distribution of the whole
    detection set, so the standardised rate is directly comparable across
    corridors and is on the same scale as the global crude rate.

    Strata with fewer than ``min_stratum_n`` observations in a group are dropped
    rather than trusted: a single dark 300 m hull out of two would otherwise be
    imported into the group's rate with the full weight of the world's capesize
    traffic. The share of a group's detections that survives that filter is
    returned as ``standardised_coverage`` so a thin result can be discounted
    instead of silently believed.
    """
    standard = df[strata_col].value_counts(normalize=True, dropna=False)

    strata = (
        df.groupby([*group_cols, strata_col], dropna=False, observed=True)
        .agg(n=(dark_col, "size"), dark=(dark_col, "sum"))
        .reset_index()
    )
    strata["rate"] = strata["dark"] / strata["n"]
    strata["w"] = strata[strata_col].map(standard).astype(float)

    total_n = strata.groupby(group_cols, observed=True)["n"].transform("sum")

    # Strata the corridor never sees, or sees too rarely to estimate, contribute
    # nothing and their weight is redistributed over the strata that remain.
    present = strata[(strata["n"] >= min_stratum_n) & strata["rate"].notna()].copy()
    present["group_total_n"] = total_n[present.index]
    weight_sum = present.groupby(group_cols, observed=True)["w"].transform("sum")
    present["contrib"] = present["rate"] * present["w"] / weight_sum
    present["covered"] = present["n"] / present["group_total_n"]

    out = (
        present.groupby(group_cols, observed=True)
        .agg(
            standardised_dark_rate=("contrib", "sum"),
            strata_used=("contrib", "size"),
            standardised_coverage=("covered", "sum"),
        )
        .reset_index()
    )
    crude = (
        df.groupby(group_cols, observed=True)
        .agg(detections=(dark_col, "size"), dark=(dark_col, "sum"))
        .reset_index()
    )
    crude["crude_dark_rate"] = crude["dark"] / crude["detections"]
    return crude.merge(out, on=group_cols, how="left")


def corridor_profile(det: pd.DataFrame) -> pd.DataFrame:
    """One row per corridor: traffic, mix, density and every dark-rate variant."""
    areas = {cp.id: bbox_area_km2(cp) for cp in load_chokepoints()}
    names = {cp.id: cp.name for cp in load_chokepoints()}
    theatres = {cp.id: cp.theatre for cp in load_chokepoints()}
    critical = {cp.id: cp.critical for cp in load_chokepoints()}

    base = (
        det.groupby("chokepoint_id", observed=True)
        .agg(
            detections=("detection_id", "size"),
            scenes=("scene_id", "nunique"),
            mean_length_m=("length_m", "mean"),
            median_length_m=("length_m", "median"),
            large_vessels=("is_large", "sum"),
            fishing_like=("likely_fishing", "sum"),
            dark=("is_dark", "sum"),
            dark_strict=("is_dark_strict", "sum"),
            dark_no_candidate=("dark_class", lambda s: int((s == "dark_no_candidate").sum())),
            cargo=("matched_category", lambda s: int((s == "cargo").sum())),
        )
        .reset_index()
    )

    solas = det[det["length_m"] >= SOLAS_LENGTH_M]
    solas_stats = (
        solas.groupby("chokepoint_id", observed=True)
        .agg(solas_detections=("detection_id", "size"), solas_dark=("is_dark", "sum"))
        .reset_index()
    )

    std = standardised_dark_rate(det, ["chokepoint_id"])

    out = (
        base.merge(solas_stats, on="chokepoint_id", how="left")
        .merge(
            std[["chokepoint_id", "standardised_dark_rate", "standardised_coverage"]],
            on="chokepoint_id",
            how="left",
        )
        .fillna({"solas_detections": 0, "solas_dark": 0})
    )
    out["chokepoint"] = out["chokepoint_id"].map(names).fillna("Open ocean / other")
    out["theatre"] = out["chokepoint_id"].map(theatres).fillna("Other")
    out["critical"] = out["chokepoint_id"].map(critical).fillna(False)
    out["area_km2"] = out["chokepoint_id"].map(areas)

    out["dark_rate"] = out["dark"] / out["detections"]
    out["dark_rate_strict"] = out["dark_strict"] / out["detections"]
    out["solas_dark_rate"] = out["solas_dark"] / out["solas_detections"].replace(0, np.nan)
    out["fishing_share"] = out["fishing_like"] / out["detections"]
    out["large_share"] = out["large_vessels"] / out["detections"]
    out["cargo_share"] = out["cargo"] / out["detections"]
    out["density_per_100k_km2"] = out["detections"] / out["area_km2"] * 1e5
    # Sentinel-1 does not image every sea equally often, so raw counts partly
    # measure satellite tasking. Detections per imaged scene removes the revisit
    # component and is the fair traffic-intensity comparison between corridors.
    out["detections_per_scene"] = out["detections"] / out["scenes"]

    lo, hi = wilson_interval(out["solas_dark"].to_numpy(), out["solas_detections"].to_numpy())
    out["solas_dark_lo"] = lo
    out["solas_dark_hi"] = hi

    LOG.info("corridor profile rows=%d", len(out))
    return out.sort_values("detections", ascending=False).reset_index(drop=True)


def daily_corridor_series(det: pd.DataFrame) -> pd.DataFrame:
    """Daily detections and dark rate per corridor - the maritime time series."""
    out = (
        det.groupby(["date", "chokepoint_id", "chokepoint"], observed=True)
        .agg(
            detections=("detection_id", "size"),
            dark=("is_dark", "sum"),
            solas=("is_large", "sum"),
            solas_dark=("is_dark", lambda s: 0),
        )
        .reset_index()
        .drop(columns=["solas_dark"])
    )
    solas = (
        det[det["length_m"] >= SOLAS_LENGTH_M]
        .groupby(["date", "chokepoint_id"], observed=True)
        .agg(solas_detections=("detection_id", "size"), solas_dark=("is_dark", "sum"))
        .reset_index()
    )
    out = out.merge(solas, on=["date", "chokepoint_id"], how="left").fillna(
        {"solas_detections": 0, "solas_dark": 0}
    )
    out["dark_rate"] = out["dark"] / out["detections"]
    out["solas_dark_rate"] = out["solas_dark"] / out["solas_detections"].replace(0, np.nan)
    return out


def vessel_mix(det: pd.DataFrame) -> pd.DataFrame:
    """Corridor x category counts, used for the traffic-composition views."""
    return (
        det.groupby(["chokepoint_id", "chokepoint", "matched_category"], observed=True)
        .agg(detections=("detection_id", "size"), mean_length_m=("length_m", "mean"))
        .reset_index()
    )
