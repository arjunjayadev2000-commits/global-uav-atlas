"""Star-schema export for the Power BI deliverable.

The submission format asks for a ``.pbix``. A ``.pbix`` is a binary Power BI
artefact that only Power BI Desktop can author, so what this pipeline produces is
the thing a ``.pbix`` is built from and the instructions to build it in a few
minutes: a clean star schema, one CSV per table, plus ``measures.dax`` and
``docs/POWERBI_GUIDE.md``.

Modelling decisions worth stating, because they are what makes the file usable
rather than merely present:

* **One date dimension** drives both the weekly conflict facts and the daily
  detection facts, so a single slicer moves the whole report. Weekly facts join
  on the week-ending date.
* **The conflict fact does not carry a corridor key.** An admin unit can threaten
  more than one corridor, so the relationship is many-to-many and is expressed
  the correct way - through ``bridge_admin_corridor``, which carries the distance
  and the decay weight. Flattening it would double-count events.
* **Detections are exported at full grain** (one row per radar contact). At
  ~105k rows this imports in seconds and keeps every drill-through honest.
"""

from __future__ import annotations

import pandas as pd

from ..config import POWERBI
from ..io_utils import get_logger

LOG = get_logger("dcsc.powerbi")

MEASURES_DAX = '''// =====================================================================
// Datathon 2026 - Global Conflicts: Impact on Supply Chains
// DAX measures. Paste each block into Power BI Desktop as a new measure,
// or use Model view > "New measure" and copy one definition at a time.
// Table references assume the star schema exported to outputs/powerbi.
// =====================================================================

// ---------- Conflict ----------
Events = SUM ( fact_conflict_weekly[events] )

Fatalities = SUM ( fact_conflict_weekly[fatalities] )

Lethality =
DIVIDE ( [Fatalities], [Events] )

Events 4W =
CALCULATE (
    [Events],
    DATESINPERIOD ( dim_date[date], MAX ( dim_date[date] ), -28, DAY )
)

Events YoY % =
VAR Current = [Events]
VAR Prior =
    CALCULATE ( [Events], DATEADD ( dim_date[date], -1, YEAR ) )
RETURN
    DIVIDE ( Current - Prior, Prior )

Escalation Flag =
IF ( [Events 4W] > 2 * AVERAGEX ( VALUES ( dim_date[year] ), [Events 4W] ), "ESCALATING", "STEADY" )

// ---------- Maritime picture ----------
Detections = COUNTROWS ( fact_detections )

SOLAS Detections =
CALCULATE ( [Detections], fact_detections[is_solas] = TRUE () )

Dark Detections =
CALCULATE ( [Detections], fact_detections[is_dark] = TRUE () )

Dark Rate =
DIVIDE ( [Dark Detections], [Detections] )

SOLAS Dark Rate =
DIVIDE (
    CALCULATE ( [Detections], fact_detections[is_dark] = TRUE (), fact_detections[is_solas] = TRUE () ),
    [SOLAS Detections]
)

// The number that matters: large ships that should be transmitting and are not.
SOLAS Dark Rate vs Baseline =
VAR Baseline =
    CALCULATE (
        [SOLAS Dark Rate],
        REMOVEFILTERS ( dim_corridor ),
        dim_corridor[chokepoint_id] = "open_ocean"
    )
RETURN
    DIVIDE ( [SOLAS Dark Rate], Baseline )

Detections Per Scene =
DIVIDE ( [SOLAS Detections], DISTINCTCOUNT ( fact_detections[scene_id] ) )

// ---------- Dark spots ----------
Dark Spot Cells =
CALCULATE ( COUNTROWS ( fact_cells ), fact_cells[is_dark_spot] = TRUE () )

Mean SDR = AVERAGE ( fact_cells[sdr] )

Behavioural Dark Spots =
CALCULATE (
    COUNTROWS ( fact_cells ),
    fact_cells[area_type] = "Behavioural dark spot (selective switch-off)"
)

// ---------- Risk ----------
MSRI = AVERAGE ( fact_msri[msri] )

India Exposure = AVERAGE ( fact_msri[india_exposure] )

Red Tier Corridors =
CALCULATE ( DISTINCTCOUNT ( fact_msri[chokepoint_id] ), fact_msri[tier] = "RED" )

Risk Tier Colour =
SWITCH (
    SELECTEDVALUE ( fact_msri[tier] ),
    "RED", "#d03b3b",
    "AMBER", "#fab219",
    "#0ca30c"
)

// ---------- Conflict pressure on corridors (uses the bridge) ----------
Corridor Events =
CALCULATE (
    [Events],
    CROSSFILTER ( bridge_admin_corridor[admin_id], dim_admin_unit[admin_id], BOTH )
)

Corridor Events Weighted =
SUMX (
    bridge_admin_corridor,
    bridge_admin_corridor[decay_weight]
        * CALCULATE ( [Events], ALLEXCEPT ( dim_admin_unit, dim_admin_unit[admin_id] ) )
)
'''


def _date_dimension(conflict: pd.DataFrame, det: pd.DataFrame) -> pd.DataFrame:
    start = min(conflict["week"].min(), pd.Timestamp(det["timestamp"].min()).tz_localize(None))
    end = max(conflict["week"].max(), pd.Timestamp(det["timestamp"].max()).tz_localize(None))
    idx = pd.date_range(start.normalize(), end.normalize(), freq="D")
    out = pd.DataFrame({"date": idx})
    out["year"] = out["date"].dt.year
    out["quarter"] = out["date"].dt.quarter
    out["month"] = out["date"].dt.month
    out["month_name"] = out["date"].dt.strftime("%b")
    out["month_start"] = out["date"].dt.to_period("M").dt.to_timestamp()
    out["iso_week"] = out["date"].dt.isocalendar().week.astype(int)
    out["week_ending"] = out["date"] + pd.to_timedelta((5 - out["date"].dt.weekday) % 7, unit="D")
    out["is_analysis_window"] = out["date"].between("2026-03-01", "2026-03-14")
    return out


def export_model(result) -> dict[str, str]:
    """Write every table of the star schema plus the DAX file."""
    POWERBI.mkdir(parents=True, exist_ok=True)
    f = result.frames
    conflict = f["conflict"]
    det = f["detections"]

    tables: dict[str, pd.DataFrame] = {}

    # ---- dimensions ----
    tables["dim_date"] = _date_dimension(conflict, det)
    tables["dim_corridor"] = f["corridor_profile"][
        [
            "chokepoint_id",
            "chokepoint",
            "theatre",
            "critical",
            "area_km2",
            "detections",
            "solas_detections",
            "solas_dark_rate",
            "standardised_dark_rate",
            "density_per_100k_km2",
        ]
    ].rename(columns={"detections": "corridor_detections"})
    tables["dim_admin_unit"] = f["conflict_units"]
    tables["dim_vessel_class"] = (
        det.groupby("length_class", observed=True)
        .agg(min_length_m=("length_m", "min"), max_length_m=("length_m", "max"))
        .reset_index()
        .assign(solas_class=lambda d: d["min_length_m"] >= 100)
    )
    tables["dim_event_type"] = (
        conflict.groupby(["event_type", "sub_event_type", "disorder_type"], observed=True)
        .size()
        .reset_index(name="row_count")
    )

    # ---- bridge ----
    bridge = cf_bridge(conflict)
    tables["bridge_admin_corridor"] = bridge

    # ---- facts ----
    tables["fact_conflict_weekly"] = conflict[
        [
            "week",
            "country",
            "admin1",
            "admin_id",
            "event_type",
            "sub_event_type",
            "disorder_type",
            "events",
            "fatalities",
            "population_exposure",
            "lat",
            "lon",
        ]
    ]
    tables["fact_detections"] = det.assign(
        is_solas=det["length_m"] >= 100.0,
        detection_date=det["timestamp"].dt.tz_localize(None).dt.normalize(),
    )[
        [
            "detection_id",
            "scene_id",
            "detection_date",
            "timestamp",
            "lat",
            "lon",
            "length_m",
            "length_class",
            "matched_category",
            "dark_class",
            "is_dark",
            "is_dark_strict",
            "is_solas",
            "likely_fishing",
            "fishing_score",
            "matching_score",
            "chokepoint_id",
            "chokepoint",
            "theatre",
            "pass_direction",
        ]
    ]
    tables["fact_cells"] = f["cells"][
        [
            "cell_id",
            "cell_lat",
            "cell_lon",
            "corridor",
            "detections",
            "dark",
            "expected",
            "sdr",
            "dark_rate",
            "solas_dark_rate",
            "q_value",
            "is_dark_spot",
            "area_type",
            "persistence",
            "days_observed",
        ]
    ]
    tables["fact_corridor_pressure"] = f["pressure"]
    tables["fact_msri"] = f["msri"]
    tables["fact_dark_clusters"] = f["clusters"]
    tables["fact_traffic_deficit"] = f["deficit"]
    if "forecasts" in f:
        tables["fact_forecast"] = f["forecasts"]
        tables["fact_forecast_scores"] = f["forecast_scores"]

    written = {}
    for name, frame in tables.items():
        path = POWERBI / f"{name}.csv"
        frame.to_csv(path, index=False)
        written[name] = str(path)
        LOG.info("powerbi %-28s %7d rows", name, len(frame))

    dax_path = POWERBI / "measures.dax"
    dax_path.write_text(MEASURES_DAX, encoding="utf-8")
    written["measures.dax"] = str(dax_path)

    relationships = pd.DataFrame(
        [
            ("dim_date", "date", "fact_detections", "detection_date", "one-to-many", "active"),
            ("dim_date", "week_ending", "fact_conflict_weekly", "week", "one-to-many", "inactive (use USERELATIONSHIP or set week as the key)"),
            ("dim_date", "week_ending", "fact_corridor_pressure", "week", "one-to-many", "active"),
            ("dim_corridor", "chokepoint_id", "fact_detections", "chokepoint_id", "one-to-many", "active"),
            ("dim_corridor", "chokepoint_id", "fact_corridor_pressure", "chokepoint_id", "one-to-many", "active"),
            ("dim_corridor", "chokepoint_id", "fact_msri", "chokepoint_id", "one-to-one", "active"),
            ("dim_corridor", "chokepoint_id", "bridge_admin_corridor", "chokepoint_id", "one-to-many", "active"),
            ("dim_admin_unit", "admin_id", "bridge_admin_corridor", "admin_id", "one-to-many", "active"),
            ("dim_admin_unit", "admin_id", "fact_conflict_weekly", "admin_id", "one-to-many", "active"),
            ("dim_vessel_class", "length_class", "fact_detections", "length_class", "one-to-many", "active"),
            ("dim_event_type", "sub_event_type", "fact_conflict_weekly", "sub_event_type", "one-to-many", "active (composite key recommended)"),
        ],
        columns=["from_table", "from_column", "to_table", "to_column", "cardinality", "notes"],
    )
    rel_path = POWERBI / "relationships.csv"
    relationships.to_csv(rel_path, index=False)
    written["relationships.csv"] = str(rel_path)
    LOG.info("power bi model exported: %d tables", len(tables))
    return written


def cf_bridge(conflict: pd.DataFrame) -> pd.DataFrame:
    """Admin-unit to corridor bridge with distance and decay weight."""
    import numpy as np

    from ..features.conflict_features import corridor_proximity

    prox = corridor_proximity(conflict)
    prox = prox[prox["distance_km"] <= 600.0].copy()
    prox["decay_weight"] = np.exp(-prox["distance_km"] / 150.0)
    return prox[["admin_id", "chokepoint_id", "chokepoint", "country", "admin1", "distance_km", "decay_weight"]]
