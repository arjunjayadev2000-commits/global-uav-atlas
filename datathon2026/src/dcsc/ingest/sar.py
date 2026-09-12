"""Ingest of the supplied Sentinel-1 SAR vessel-detection extract.

Raw shape (107,257 rows x 10 cols). Each row is one radar-detected vessel inside
a Sentinel-1 IW scene, with the correlation result against the AIS picture for
the same instant.

The single most important derived field is the *dark* status. A SAR detection is
dark when the radar sees a ship that the AIS picture does not account for.

The supplied data carries two partially independent signals about that, and they
do not agree, so the pipeline keeps them apart:

* ``matched_category`` is the provider's own adjudication. ``"unmatched"`` means
  the match was rejected; every other value (``cargo``, ``fishing``, ``bunker``
  ...) means the detection was attributed to an AIS track.
* ``mmsi`` / ``matching_score`` describe the *candidate* association. 13,057
  detections carry a candidate MMSI and still end up labelled ``unmatched``:
  a candidate was considered and rejected. Conversely a third of the accepted
  matches sit below a correlation score of 1.0.

The headline definition therefore follows the provider label - ``is_dark`` is
``matched_category == "unmatched"`` - and splits it by whether a candidate MMSI
existed at all:

* ``dark_no_candidate``       - radar contact with no AIS candidate whatsoever;
* ``dark_rejected_candidate`` - a candidate existed but correlated too poorly.

``is_dark_strict`` additionally counts accepted matches whose score is below
``SETTINGS.match_score_floor``, and exists purely so that every dark-rate result
can be re-run against a harsher definition (see ``analysis.darkspots``).

Radar does not care whether a transponder is switched off, jammed, spoofed or
merely out of receiver range, which is exactly why SAR-vs-AIS disagreement is
the right instrument for finding AIS dead zones.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import DATA_INTERIM, SAR_CSV, SAR_PARQUET, SETTINGS
from ..io_utils import get_logger

LOG = get_logger("dcsc.ingest.sar")

#: Vessel length classes used throughout the analysis (metres).
LENGTH_BINS = [0, 25, 50, 100, 160, 250, 1000]
LENGTH_LABELS = [
    "<25 m (small craft)",
    "25-50 m (coastal)",
    "50-100 m (feeder)",
    "100-160 m (handy)",
    "160-250 m (panamax)",
    ">250 m (capesize/VLCC)",
]


def load_raw(path=SAR_CSV) -> pd.DataFrame:
    """Read the detection CSV as supplied."""
    LOG.info("reading %s", path.name)
    df = pd.read_csv(path)
    LOG.info("raw detections=%d cols=%d", len(df), df.shape[1])
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Apply quality gates, parse time, and derive the dark-status fields."""
    out = df.copy()

    # The supplied file carries a literal " UTC" suffix; a frame that already holds
    # timestamps (a test fixture, or a re-clean) must pass through untouched.
    if not pd.api.types.is_datetime64_any_dtype(out["timestamp"]):
        out["timestamp"] = out["timestamp"].astype("string").str.replace(" UTC", "", regex=False)
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce", utc=True)
    before = len(out)
    out = out.dropna(subset=["timestamp", "lat", "lon"])
    if len(out) != before:
        LOG.warning("dropped %d rows with unusable time or position", before - len(out))

    # --- quality gates -----------------------------------------------------
    low_conf = out["presence_score"] < SETTINGS.presence_score_floor
    tiny = out["length_m"] < SETTINGS.min_length_m
    LOG.info(
        "quality gates: %d below presence floor %.2f, %d below %.0f m",
        int(low_conf.sum()),
        SETTINGS.presence_score_floor,
        int(tiny.sum()),
        SETTINGS.min_length_m,
    )
    out = out[~(low_conf | tiny)].copy()

    # --- AIS association ---------------------------------------------------
    out["has_mmsi"] = out["mmsi"].notna()
    out["is_dark"] = out["matched_category"].eq("unmatched")
    out["weak_match"] = (~out["is_dark"]) & (out["matching_score"] < SETTINGS.match_score_floor)
    out["is_dark_strict"] = out["is_dark"] | out["weak_match"]
    out["dark_class"] = np.select(
        [
            out["is_dark"] & ~out["has_mmsi"],
            out["is_dark"] & out["has_mmsi"],
            out["weak_match"],
        ],
        ["dark_no_candidate", "dark_rejected_candidate", "matched_weak"],
        default="matched_strong",
    )

    # MMSI maritime identification digits (country of registry) where present.
    out["mid"] = (
        out["mmsi"].astype("Float64").astype("string").str.slice(0, 3).where(out["has_mmsi"])
    )

    # --- descriptive derivations ------------------------------------------
    out["length_class"] = pd.cut(
        out["length_m"], bins=LENGTH_BINS, labels=LENGTH_LABELS, right=False
    )
    out["likely_fishing"] = out["fishing_score"] >= 0.5
    out["date"] = out["timestamp"].dt.date
    out["hour_utc"] = out["timestamp"].dt.hour.astype("int16")
    out["is_large"] = out["length_m"] >= 100.0

    # Sentinel-1 passes are sun-synchronous: roughly 06:00/18:00 local. Splitting
    # ascending from descending passes guards against reading an orbit artefact
    # as a behavioural signal.
    out["pass_direction"] = np.where(out["hour_utc"].between(2, 13), "descending", "ascending")

    out = out.sort_values("timestamp").reset_index(drop=True)
    out["detection_id"] = np.arange(1, len(out) + 1)

    LOG.info(
        "clean detections=%d  %s..%s  dark=%.1f%% (no candidate %.1f%%, rejected candidate %.1f%%); "
        "strict dark=%.1f%%",
        len(out),
        out["timestamp"].min().date(),
        out["timestamp"].max().date(),
        100 * out["is_dark"].mean(),
        100 * (out["dark_class"] == "dark_no_candidate").mean(),
        100 * (out["dark_class"] == "dark_rejected_candidate").mean(),
        100 * out["is_dark_strict"].mean(),
    )
    return out


def build(force: bool = False) -> pd.DataFrame:
    """Return the cleaned detection frame, cached to parquet."""
    DATA_INTERIM.mkdir(parents=True, exist_ok=True)
    if SAR_PARQUET.exists() and not force:
        LOG.info("using cached %s", SAR_PARQUET.name)
        return pd.read_parquet(SAR_PARQUET)
    out = clean(load_raw())
    out.to_parquet(SAR_PARQUET, index=False)
    return out
