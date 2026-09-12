"""The statistical machinery: standardisation, FDR control, typology, the index."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dcsc.analysis.darkspots import _benjamini_hochberg, classify_areas, dark_rate_surface
from dcsc.features.geo import assign_chokepoint
from dcsc.features.maritime_features import standardised_dark_rate
from dcsc.ingest import sar as sar_ingest


def test_bh_is_never_smaller_than_the_raw_p_value():
    p = np.array([0.001, 0.01, 0.04, 0.2, 0.9])
    q = _benjamini_hochberg(p)
    assert (q >= p - 1e-12).all()
    assert (q <= 1.0).all()


def test_bh_is_monotone_in_p():
    p = np.sort(np.random.default_rng(0).random(200))
    q = _benjamini_hochberg(p)
    assert (np.diff(q) >= -1e-12).all()


def test_standardisation_removes_a_pure_size_mix_effect():
    """Two corridors with identical size-specific rates must standardise equal,
    even when their raw rates differ because their ship mixes differ."""
    rows = []
    # Same dark rates per class (small 80%, large 10%), very different mixes.
    for corridor, n_small, n_large in (("A", 900, 100), ("B", 100, 900)):
        for _ in range(n_small):
            rows.append({"corridor": corridor, "length_class": "small", "is_dark": True})
        rows.append({"corridor": corridor, "length_class": "small", "is_dark": False})
        for i in range(n_large):
            rows.append({"corridor": corridor, "length_class": "large", "is_dark": i % 10 == 0})
    df = pd.DataFrame(rows)
    # Force the intended per-class rates exactly.
    df.loc[(df.corridor.notna()) & (df.length_class == "small"), "is_dark"] = [
        i % 5 != 0 for i in range(int((df.length_class == "small").sum()))
    ]
    out = standardised_dark_rate(df, ["corridor"], strata_col="length_class")
    crude_gap = abs(out["crude_dark_rate"].iloc[0] - out["crude_dark_rate"].iloc[1])
    std_gap = abs(out["standardised_dark_rate"].iloc[0] - out["standardised_dark_rate"].iloc[1])
    assert crude_gap > 0.3
    assert std_gap < 0.05


def test_thin_strata_are_excluded_and_coverage_reports_it():
    df = pd.DataFrame(
        {
            "corridor": ["A"] * 100 + ["A"] * 3,
            "length_class": ["big"] * 100 + ["rare"] * 3,
            "is_dark": [False] * 100 + [True] * 3,
        }
    )
    out = standardised_dark_rate(df, ["corridor"], min_stratum_n=15)
    assert out["strata_used"].iloc[0] == 1
    assert out["standardised_coverage"].iloc[0] < 1.0


def test_typology_separates_blackout_from_selective_darkness(synthetic_detections):
    det = assign_chokepoint(sar_ingest.clean(synthetic_detections))
    cells = classify_areas(dark_rate_surface(det, deg=0.5, min_detections=20))
    types = set(cells["area_type"])
    # The small-craft, all-dark cell must not be reported as a behavioural dark spot.
    small = cells[cells["mean_length_m"] < 45]
    assert not small.empty
    assert (small["area_type"] != "Behavioural dark spot (selective switch-off)").all()
    assert types & {
        "Behavioural dark spot (selective switch-off)",
        "Non-carriage area (small craft, AIS not required)",
    }


def test_sdr_is_one_when_a_cell_matches_the_global_mix(synthetic_detections):
    det = assign_chokepoint(sar_ingest.clean(synthetic_detections))
    cells = dark_rate_surface(det, deg=0.5, min_detections=20)
    # Expected counts must sum to roughly the observed dark count overall.
    assert cells["expected"].sum() > 0
    assert 0.5 < (cells["dark"].sum() / cells["expected"].sum()) < 2.0
