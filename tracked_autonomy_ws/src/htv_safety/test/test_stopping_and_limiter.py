import math

import pytest
from htv_safety.command_limiter import CommandLimiter, LimiterConfig
from htv_safety.geometry import (
    distance_to_boundary,
    footprint_clearance,
    inflate_convex_polygon,
    parse_polygon,
    point_in_polygon,
    transform_polygon,
)
from htv_safety.stopping_distance import StoppingDistanceConfig, StoppingDistanceEstimator


def test_stopping_distance_components():
    cfg = StoppingDistanceConfig(max_deceleration=1.5, command_latency=0.25, braking_latency=0.4,
                                 reaction_time=0.2, margin_fixed=1.0, margin_ratio=0.0)
    est = StoppingDistanceEstimator(cfg).estimate(2.0, traction=0.8, slope=0.0, confidence=1.0)
    assert est.reaction_distance == pytest.approx(2.0 * 0.85)
    assert est.braking_distance == pytest.approx(4.0 / 3.0)
    assert est.stopping_distance == pytest.approx(1.7 + 4.0 / 3.0 + 1.0)


def test_poor_traction_and_downhill_increase_stopping_distance():
    est = StoppingDistanceEstimator()
    base = est.estimate(1.0, traction=0.8, slope=0.0, confidence=1.0).stopping_distance
    assert est.estimate(1.0, traction=0.1, slope=0.0, confidence=1.0).stopping_distance > base
    assert est.estimate(1.0, traction=0.8, slope=math.radians(-10), confidence=1.0).stopping_distance > base


def test_unknown_terrain_is_conservative():
    est = StoppingDistanceEstimator()
    known = est.estimate(1.0, traction=0.8, slope=0.0, confidence=1.0).stopping_distance
    unknown = est.estimate(1.0, traction=0.8, slope=0.0, confidence=0.0).stopping_distance
    assert unknown > known
    assert est.max_safe_velocity(50.0, confidence=0.0) <= est.config.unknown_terrain_speed


def test_max_safe_velocity_is_consistent_with_estimate():
    est = StoppingDistanceEstimator()
    v = est.max_safe_velocity(10.0, traction=0.7, slope=0.0, confidence=1.0)
    assert v > 0
    assert est.estimate(v, traction=0.7, slope=0.0, confidence=1.0).stopping_distance == pytest.approx(10.0)
    assert est.max_safe_velocity(0.5) == 0.0


def test_confidence_reduces_speed():
    est = StoppingDistanceEstimator()
    hi = est.max_safe_velocity(20.0, traction=0.7, slope=0.0, confidence=1.0)
    mid = est.max_safe_velocity(20.0, traction=0.7, slope=0.0, confidence=0.5)
    assert mid < hi


def test_limiter_caps_and_preserves_curvature():
    lim = CommandLimiter(LimiterConfig(research_speed_limit=1.0, max_acceleration=100.0,
                                       max_yaw_acceleration=100.0, min_turning_radius=1.0))
    v, w = lim.limit(2.0, 0.2, dt=1.0)
    assert v == pytest.approx(1.0)
    assert w == pytest.approx(0.1)


def test_limiter_prevents_pivot_turns_by_default():
    lim = CommandLimiter(LimiterConfig(max_yaw_acceleration=100.0))
    _, w = lim.limit(0.0, 0.15, dt=1.0)
    assert w == 0.0
    pivot = CommandLimiter(LimiterConfig(allow_pivot_turns=True, max_yaw_acceleration=100.0))
    assert pivot.limit(0.0, 0.15, dt=1.0)[1] == pytest.approx(0.15)


def test_limiter_rate_limits_acceleration_but_brakes_faster():
    lim = CommandLimiter(LimiterConfig(max_acceleration=0.3, max_deceleration=1.0))
    v, _ = lim.limit(1.0, 0.0, dt=1.0)
    assert v == pytest.approx(0.3)
    lim.last_linear = 1.0
    v, _ = lim.limit(0.0, 0.0, dt=0.5)
    assert v == pytest.approx(0.5)


def test_limiter_speed_scale_and_cap_and_nan():
    lim = CommandLimiter(LimiterConfig(max_acceleration=100.0))
    assert lim.limit(1.0, 0.0, 1.0, speed_scale=0.0)[0] == 0.0
    lim.reset()
    assert lim.limit(1.0, 0.0, 1.0, speed_cap=0.2)[0] == pytest.approx(0.2)
    assert lim.limit(float("nan"), 0.0, 1.0) == (0.0, 0.0)


def test_geometry_helpers():
    square = parse_polygon([0, 0, 10, 0, 10, 10, 0, 10])
    assert point_in_polygon((5, 5), square)
    assert not point_in_polygon((15, 5), square)
    assert distance_to_boundary((5, 5), square) == pytest.approx(5.0)
    assert distance_to_boundary((12, 5), square) == pytest.approx(-2.0)
    fp = parse_polygon([1, 1, -1, 1, -1, -1, 1, -1])
    big = inflate_convex_polygon(fp, 0.5)
    assert max(abs(x) for x, _ in big) == pytest.approx(1.5)
    assert footprint_clearance(transform_polygon(fp, 5, 5, 0.3), square) > 3.0
    with pytest.raises(ValueError):
        parse_polygon([0, 0, 1])
