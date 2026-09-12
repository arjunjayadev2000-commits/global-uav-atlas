"""Cleaning rules and the dark-status definition."""

from __future__ import annotations

from dcsc.ingest import conflict as conflict_ingest
from dcsc.ingest import sar as sar_ingest


def test_dark_follows_the_provider_label_not_the_mmsi(synthetic_detections):
    """A row with a candidate MMSI but an 'unmatched' label is still dark."""
    df = synthetic_detections.copy()
    df.loc[0, "matched_category"] = "unmatched"
    df.loc[0, "mmsi"] = 123456789
    df.loc[0, "matching_score"] = 0.4
    out = sar_ingest.clean(df)
    row = out[out["mmsi"] == 123456789].iloc[0]
    assert bool(row["is_dark"]) is True
    assert row["dark_class"] == "dark_rejected_candidate"


def test_quality_gates_drop_low_confidence_and_tiny_contacts(synthetic_detections):
    df = synthetic_detections.copy()
    df.loc[1, "presence_score"] = 0.4
    df.loc[2, "length_m"] = 3.0
    out = sar_ingest.clean(df)
    assert len(out) == len(df) - 2


def test_strict_dark_is_a_superset_of_dark(synthetic_detections):
    out = sar_ingest.clean(synthetic_detections)
    assert (out["is_dark_strict"] | ~out["is_dark"]).all()


def test_dark_class_is_exhaustive(synthetic_detections):
    out = sar_ingest.clean(synthetic_detections)
    allowed = {"dark_no_candidate", "dark_rejected_candidate", "matched_weak", "matched_strong"}
    assert set(out["dark_class"]).issubset(allowed)


def test_conflict_clean_derives_calendar_keys_and_keeps_every_row(synthetic_conflict):
    out = conflict_ingest.clean(synthetic_conflict)
    assert len(out) == len(synthetic_conflict)
    assert {"year", "month", "iso_week", "fatalities_per_event"} <= set(out.columns)
    assert out["week"].dtype.kind == "M"


def test_conflict_clean_drops_impossible_coordinates(synthetic_conflict):
    df = synthetic_conflict.copy()
    df.loc[0, "CENTROID_LATITUDE"] = 991.0
    out = conflict_ingest.clean(df)
    assert len(out) == len(df) - 1
