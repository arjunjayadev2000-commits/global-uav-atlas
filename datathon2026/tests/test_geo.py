"""Geometry and corridor tagging."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dcsc.features.geo import add_grid, assign_chokepoint, haversine_km, wilson_interval


def test_haversine_known_distance():
    # London to Paris is about 344 km.
    d = haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
    assert 330 < float(d) < 360


def test_haversine_is_symmetric_and_zero_on_self():
    assert haversine_km(10.0, 20.0, 10.0, 20.0) == pytest.approx(0.0)
    assert haversine_km(10, 20, 30, 40) == pytest.approx(haversine_km(30, 40, 10, 20))


def test_narrow_strait_wins_over_surrounding_basin():
    """A point inside both Hormuz and the Persian Gulf box must resolve to Hormuz."""
    df = pd.DataFrame({"lat": [26.0], "lon": [56.0]})
    out = assign_chokepoint(df)
    assert out.loc[0, "chokepoint_id"] == "hormuz"


def test_points_outside_every_box_fall_through_to_open_ocean():
    df = pd.DataFrame({"lat": [-45.0], "lon": [-120.0]})
    assert assign_chokepoint(df).loc[0, "chokepoint_id"] == "open_ocean"


def test_grid_cell_area_shrinks_towards_the_poles():
    df = pd.DataFrame({"lat": [0.2, 60.2], "lon": [10.2, 10.2]})
    out = add_grid(df, deg=0.5)
    assert out["cell_area_km2"].iloc[0] > out["cell_area_km2"].iloc[1]


def test_wilson_interval_brackets_the_estimate_and_is_wider_when_n_is_small():
    lo_small, hi_small = wilson_interval(np.array([5]), np.array([10]))
    lo_big, hi_big = wilson_interval(np.array([500]), np.array([1000]))
    assert lo_small < 0.5 < hi_small
    assert (hi_small - lo_small) > (hi_big - lo_big)


def test_wilson_interval_stays_inside_zero_one():
    lo, hi = wilson_interval(np.array([0, 3]), np.array([3, 3]))
    assert lo.min() >= -1e-9
    assert hi.max() <= 1.0 + 1e-9
