"""The composite index: weights, scaling, tiers and the India overlay."""

from __future__ import annotations

import json

import pandas as pd

from dcsc.analysis.risk_index import COMPONENTS, build, load_weights, watchlist


def _frames():
    profile = pd.DataFrame(
        {
            "chokepoint_id": ["hormuz", "dover", "black_sea"],
            "chokepoint": ["Strait of Hormuz", "Dover Strait", "Black Sea"],
            "theatre": ["Persian Gulf", "North Europe", "Black Sea"],
            "critical": [True, False, True],
            "detections": [2000, 1600, 2600],
            "solas_detections": [1300, 800, 1400],
            "solas_dark_rate": [0.84, 0.04, 0.48],
            "standardised_dark_rate": [0.85, 0.05, 0.62],
        }
    )
    pressure = pd.DataFrame(
        {
            "week": pd.to_datetime(["2026-06-20"] * 3 + ["2026-01-10"] * 3),
            "chokepoint_id": ["hormuz", "dover", "black_sea"] * 2,
            "events_within": [300, 0, 700, 100, 0, 500],
        }
    )
    deficit = pd.DataFrame(
        {
            "chokepoint_id": ["hormuz", "dover", "black_sea"],
            "solas_per_scene": [118.0, 37.0, 23.0],
            "throughput_ratio": [3.5, 1.1, 0.7],
            "deficit_pct": [-250.0, -10.0, 30.0],
        }
    )
    return profile, pressure, deficit


def test_weights_sum_to_one():
    assert sum(load_weights()["weights"].values()) == 1.0


def test_every_component_is_weighted():
    assert set(load_weights()["weights"]) == set(COMPONENTS)


def test_index_is_bounded_and_ordered():
    index = build(*_frames())
    assert index["msri"].between(0, 1).all()
    assert index["rank"].is_monotonic_increasing
    assert index["msri"].is_monotonic_decreasing


def test_components_are_min_max_scaled_within_the_run():
    index = build(*_frames())
    for c in COMPONENTS:
        assert index[c].min() >= 0 - 1e-9
        assert index[c].max() <= 1 + 1e-9


def test_india_exposure_never_exceeds_the_risk_it_scales():
    index = build(*_frames())
    assert (index["india_exposure"] <= index["msri"] + 1e-9).all()


def test_watchlist_names_a_driver_that_is_a_real_component():
    index = build(*_frames())
    wl = watchlist(index, top=3)
    drivers = {d.replace(" ", "_") for d in wl["dominant_driver"]}
    assert drivers <= set(COMPONENTS)


def test_dependency_scores_are_declared_with_a_rationale():
    cfg = json.loads((__import__("dcsc.config", fromlist=["CONFIG_DIR"]).CONFIG_DIR / "risk_weights.json").read_text())
    for key, value in cfg["india_dependency"].items():
        assert 0.0 <= value["score"] <= 1.0, key
        assert value["why"].strip(), key
