"""Descriptive layer: the tables that answer "what is in this data" before any model.

These are deliberately plain. They exist so that every headline number in the
report and every visual in the Power BI model is traceable to a named CSV, and so
that a reader can check the arithmetic without running the pipeline.
"""

from __future__ import annotations

import pandas as pd

from ..features.conflict_features import MARITIME_ADMIN1, weekly_series
from ..features.maritime_features import SOLAS_LENGTH_M, standardised_dark_rate
from ..io_utils import get_logger, save_table

LOG = get_logger("dcsc.analysis.eda")


def conflict_tables(conflict: pd.DataFrame) -> dict[str, pd.DataFrame]:
    weekly = weekly_series(conflict)
    by_country_year = (
        conflict.groupby(["country", "year"], observed=True)
        .agg(events=("events", "sum"), fatalities=("fatalities", "sum"))
        .reset_index()
    )
    event_mix = (
        conflict.groupby(["year", "event_type"], observed=True)
        .agg(events=("events", "sum"), fatalities=("fatalities", "sum"))
        .reset_index()
    )
    sub_mix = (
        conflict.groupby(["year", "sub_event_type"], observed=True)["events"].sum().reset_index()
    )
    top_admin = (
        conflict.groupby(["country", "admin1"], observed=True)
        .agg(
            events=("events", "sum"),
            fatalities=("fatalities", "sum"),
            population_exposure=("population_exposure", "max"),
            lat=("lat", "first"),
            lon=("lon", "first"),
        )
        .reset_index()
        .sort_values("events", ascending=False)
    )
    maritime = (
        conflict[conflict["admin1"].isin(MARITIME_ADMIN1)]
        .groupby(["week", "admin1"], observed=True)
        .agg(events=("events", "sum"), fatalities=("fatalities", "sum"))
        .reset_index()
    )
    drone = (
        conflict[conflict["sub_event_type"] == "Air/drone strike"]
        .groupby(["year", "country"], observed=True)["events"]
        .sum()
        .reset_index()
        .sort_values(["year", "events"], ascending=[True, False])
    )

    out = {
        "conflict_weekly_totals": weekly,
        "conflict_by_country_year": by_country_year,
        "conflict_event_mix": event_mix,
        "conflict_sub_event_mix": sub_mix,
        "conflict_top_admin_units": top_admin,
        "conflict_maritime_domain_events": maritime,
        "conflict_drone_strikes": drone,
    }
    for name, frame in out.items():
        save_table(frame, name)
    return out


def maritime_tables(det: pd.DataFrame) -> dict[str, pd.DataFrame]:
    by_length = (
        det.groupby("length_class", observed=True)
        .agg(
            detections=("detection_id", "size"),
            dark=("is_dark", "sum"),
            mean_length_m=("length_m", "mean"),
        )
        .reset_index()
    )
    by_length["dark_rate"] = by_length["dark"] / by_length["detections"]

    by_category = (
        det.groupby("matched_category", observed=True)
        .agg(
            detections=("detection_id", "size"),
            mean_length_m=("length_m", "mean"),
            fishing_score=("fishing_score", "mean"),
        )
        .reset_index()
        .sort_values("detections", ascending=False)
    )

    daily = (
        det.groupby("date", observed=True)
        .agg(
            detections=("detection_id", "size"),
            dark=("is_dark", "sum"),
            scenes=("scene_id", "nunique"),
        )
        .reset_index()
    )
    daily["dark_rate"] = daily["dark"] / daily["detections"]

    std_theatre = standardised_dark_rate(det, ["theatre"])

    solas = det[det["length_m"] >= SOLAS_LENGTH_M]
    flag_mid = (
        solas[solas["mid"].notna()]
        .groupby("mid", observed=True)
        .agg(detections=("detection_id", "size"))
        .reset_index()
        .sort_values("detections", ascending=False)
        .head(30)
    )

    out = {
        "sar_dark_by_length_class": by_length,
        "sar_by_category": by_category,
        "sar_daily_totals": daily,
        "sar_dark_by_theatre": std_theatre,
        "sar_top_flag_mid": flag_mid,
    }
    for name, frame in out.items():
        save_table(frame, name)
    return out


def headline_numbers(conflict: pd.DataFrame, det: pd.DataFrame) -> pd.DataFrame:
    """The handful of figures the report leads with, in one auditable table."""
    solas = det[det["length_m"] >= SOLAS_LENGTH_M]
    rows = [
        ("Conflict records analysed", len(conflict), "weekly admin-unit x event-type rows"),
        ("Conflict weeks covered", conflict["week"].nunique(), f"{conflict['week'].min():%Y-%m-%d} to {conflict['week'].max():%Y-%m-%d}"),
        ("Conflict events", int(conflict["events"].sum()), "sum of EVENTS"),
        ("Fatalities", int(conflict["fatalities"].sum()), "sum of FATALITIES"),
        ("Countries / water bodies", conflict["country"].nunique(), "ACLED country field"),
        ("Maritime-domain events", int(conflict[conflict["admin1"].isin(MARITIME_ADMIN1)]["events"].sum()), "events ACLED places at sea"),
        ("SAR detections analysed", len(det), "after quality gates"),
        ("Sentinel-1 scenes", det["scene_id"].nunique(), "distinct radar scenes"),
        ("Detection window", 14, "2026-03-01 to 2026-03-14"),
        ("Overall dark rate", round(float(det["is_dark"].mean()), 4), "share unattributed to AIS"),
        ("SOLAS-class detections", len(solas), ">= 100 m, AIS carriage mandatory"),
        ("SOLAS-class dark rate", round(float(solas["is_dark"].mean()), 4), "the headline anomaly measure"),
        ("Distinct MMSIs matched", int(det["mmsi"].nunique()), "identified vessels"),
    ]
    out = pd.DataFrame(rows, columns=["metric", "value", "definition"])
    save_table(out, "headline_numbers")
    return out


def run(conflict: pd.DataFrame, det: pd.DataFrame) -> dict[str, pd.DataFrame]:
    tables = {}
    tables.update(conflict_tables(conflict))
    tables.update(maritime_tables(det))
    tables["headline_numbers"] = headline_numbers(conflict, det)
    LOG.info("descriptive tables written: %d", len(tables))
    return tables
