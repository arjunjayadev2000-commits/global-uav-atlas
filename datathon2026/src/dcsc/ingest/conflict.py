"""Ingest of the supplied ACLED-style Middle East weekly conflict aggregate.

Raw shape (149,825 rows x 13 cols): one row per
``WEEK x COUNTRY x ADMIN1 x EVENT_TYPE x SUB_EVENT_TYPE``, with event counts,
fatalities, the population living in the affected admin unit, and the admin-unit
centroid.

Cleaning decisions are deliberately conservative and all of them are logged:
nothing is dropped silently.
"""

from __future__ import annotations

import pandas as pd

from ..config import CONFLICT_PARQUET, CONFLICT_XLSX, DATA_INTERIM
from ..io_utils import get_logger

LOG = get_logger("dcsc.ingest.conflict")

RENAMES = {
    "WEEK": "week",
    "REGION": "region",
    "COUNTRY": "country",
    "ADMIN1": "admin1",
    "EVENT_TYPE": "event_type",
    "SUB_EVENT_TYPE": "sub_event_type",
    "EVENTS": "events",
    "FATALITIES": "fatalities",
    "POPULATION_EXPOSURE": "population_exposure",
    "DISORDER_TYPE": "disorder_type",
    "ID": "admin_id",
    "CENTROID_LATITUDE": "lat",
    "CENTROID_LONGITUDE": "lon",
}


def load_raw(path=CONFLICT_XLSX) -> pd.DataFrame:
    """Read the workbook exactly as supplied."""
    LOG.info("reading %s", path.name)
    df = pd.read_excel(path, sheet_name=0, engine="openpyxl")
    LOG.info("raw conflict rows=%d cols=%d", len(df), df.shape[1])
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise names and types, drop impossible rows, derive calendar keys."""
    out = df.rename(columns=RENAMES).copy()

    out["week"] = pd.to_datetime(out["week"], errors="coerce")
    before = len(out)
    out = out.dropna(subset=["week"])
    if len(out) != before:
        LOG.warning("dropped %d rows with an unparseable WEEK", before - len(out))

    for col in ("events", "fatalities", "population_exposure"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype("int64")

    for col in ("region", "country", "admin1", "event_type", "sub_event_type", "disorder_type"):
        out[col] = out[col].astype("string").str.strip()

    # A row with zero events carries no information for any count-based measure but
    # can still carry fatalities in some ACLED exports; keep it and flag it instead.
    out["zero_event_row"] = out["events"] <= 0

    bad_coords = (~out["lat"].between(-90, 90)) | (~out["lon"].between(-180, 180))
    if bad_coords.any():
        LOG.warning("dropping %d rows with out-of-range centroids", int(bad_coords.sum()))
        out = out[~bad_coords]

    # Calendar helpers used by every downstream aggregation.
    out["year"] = out["week"].dt.year.astype("int16")
    out["month"] = out["week"].dt.to_period("M").dt.to_timestamp()
    out["iso_week"] = out["week"].dt.isocalendar().week.astype("int16")

    # Severity: fatalities per event, guarded against divide-by-zero.
    out["fatalities_per_event"] = (
        out["fatalities"] / out["events"].where(out["events"] > 0)
    ).fillna(0.0)

    out = out.sort_values(["week", "country", "admin1"]).reset_index(drop=True)
    LOG.info(
        "clean conflict rows=%d  weeks %s..%s  countries=%d",
        len(out),
        out["week"].min().date(),
        out["week"].max().date(),
        out["country"].nunique(),
    )
    return out


def build(force: bool = False) -> pd.DataFrame:
    """Return the cleaned frame, caching it to parquet for fast re-runs."""
    DATA_INTERIM.mkdir(parents=True, exist_ok=True)
    if CONFLICT_PARQUET.exists() and not force:
        LOG.info("using cached %s", CONFLICT_PARQUET.name)
        return pd.read_parquet(CONFLICT_PARQUET)
    out = clean(load_raw())
    out.to_parquet(CONFLICT_PARQUET, index=False)
    return out
