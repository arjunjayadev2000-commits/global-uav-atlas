"""Static checks on simulation_safe.yaml: conservative, typed, consistent."""

from pathlib import Path

import pytest
import yaml
from htv_dynamics import TrackedVehicleParams, load_vehicle_params

CONFIG = Path(__file__).resolve().parents[1] / "config" / "simulation_safe.yaml"


@pytest.fixture(scope="module")
def doc():
    return yaml.safe_load(CONFIG.read_text())


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    else:
        yield path, node


def test_vehicle_params_load_and_validate():
    params = load_vehicle_params(CONFIG)
    assert isinstance(params, TrackedVehicleParams)
    assert params.vehicle_mass == pytest.approx(42000.0)


def test_research_limits_are_conservative(doc):
    vehicle = doc["/**"]["ros__parameters"]["vehicle"]
    hard_cap = doc["safety_supervisor"]["ros__parameters"]["research_speed_hard_cap"]
    assert vehicle["research_speed_limit"] <= 1.0
    assert vehicle["research_speed_limit"] <= hard_cap < vehicle["max_vehicle_speed"]
    assert vehicle["research_reverse_speed_limit"] <= vehicle["research_speed_limit"]
    assert vehicle["research_yaw_rate_limit"] <= vehicle["max_yaw_rate"]
    limiter = doc["command_limiter"]["ros__parameters"]
    assert limiter["limiter"]["allow_pivot_turns"] is False
    assert limiter["terrain"]["default_confidence"] == 0.0  # unknown terrain => conservative


def test_numeric_vehicle_params_are_floats(doc):
    """ROS parameters are typed: an int here would clash with the float declaration."""
    vehicle = doc["/**"]["ros__parameters"]["vehicle"]
    ints = [k for k, v in vehicle.items() if isinstance(v, int) and not isinstance(v, bool)]
    assert ints == []


def test_simulation_only_backend(doc):
    vi = doc["vehicle_interface"]["ros__parameters"]
    assert vi["backend"] == "simulated"
    assert vi["allow_non_simulated_backends"] is False


def test_watchdog_lists_are_aligned(doc):
    wd = doc["watchdog"]["ros__parameters"]
    assert len(wd["monitored_nodes"]) == len(wd["monitored_severities"])
    assert "safety_supervisor" in wd["monitored_nodes"]


def test_footprints_are_polygons(doc):
    fp = doc["/**"]["ros__parameters"]["footprint"]
    for key in ("nominal", "low_speed_safety"):
        assert len(fp[key]) >= 6 and len(fp[key]) % 2 == 0
    assert max(abs(v) for v in fp["low_speed_safety"]) > max(abs(v) for v in fp["nominal"])
