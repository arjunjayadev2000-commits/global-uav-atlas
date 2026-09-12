"""Contracts the downstream deliverables rely on.

These are the tests that break loudly if a refactor silently changes what the
report, the Power BI model or an assessor's CSV expects to find.
"""

from __future__ import annotations

import json

import pytest

from dcsc.config import CONFIG_DIR, CONFLICT_XLSX, SAR_CSV, load_chokepoints


def test_chokepoint_boxes_are_well_formed():
    for cp in load_chokepoints():
        assert cp.lat_min < cp.lat_max, cp.id
        assert cp.lon_min < cp.lon_max, cp.id
        assert -90 <= cp.lat_min <= 90 and -90 <= cp.lat_max <= 90, cp.id
        assert -180 <= cp.lon_min <= 180 and -180 <= cp.lon_max <= 180, cp.id


def test_chokepoint_ids_are_unique():
    ids = [cp.id for cp in load_chokepoints()]
    assert len(ids) == len(set(ids))


def test_chokepoints_are_ordered_narrow_first():
    """Priority ordering is what makes corridor assignment deterministic."""
    priorities = [cp.priority for cp in load_chokepoints()]
    assert priorities == sorted(priorities)


def test_every_india_dependency_key_is_a_real_corridor():
    cfg = json.loads((CONFIG_DIR / "risk_weights.json").read_text())
    known = {cp.id for cp in load_chokepoints()}
    assert set(cfg["india_dependency"]) <= known


def test_supplied_data_files_are_present():
    assert CONFLICT_XLSX.exists(), "the supplied conflict workbook must be committed"
    assert SAR_CSV.exists(), "the supplied detection CSV must be committed"


@pytest.mark.slow
def test_full_pipeline_produces_the_documented_artefacts(tmp_path):
    from dcsc.pipeline import run

    result = run(with_forecast=False, with_figures=False)
    for key in ("corridor_profile", "cells", "msri", "logit", "deficit", "clusters"):
        assert key in result.frames, key
    assert result.manifest["headline"]["dark_spot_cells"] > 0
    assert (result.frames["msri"]["tier"] == "RED").any()


@pytest.mark.slow
def test_headline_numbers_match_the_frames():
    """The report interpolates its numbers; this checks the source of truth."""
    from dcsc.analysis.eda import headline_numbers
    from dcsc.features.geo import assign_chokepoint
    from dcsc.ingest import conflict as ci
    from dcsc.ingest import sar as si

    det = assign_chokepoint(si.build())
    con = ci.build()
    table = headline_numbers(con, det).set_index("metric")["value"]
    solas = det[det["length_m"] >= 100]
    assert float(table["SOLAS-class dark rate"]) == pytest.approx(solas["is_dark"].mean(), abs=1e-4)
    assert int(table["SAR detections analysed"]) == len(det)
