import math

import pytest
from htv_dynamics import TrackDemand, TrackedVehicleModel, TrackedVehicleParams

DT = 0.01


def run(model: TrackedVehicleModel, seconds: float) -> None:
    for _ in range(round(seconds / DT)):
        model.step(DT)


def drive_straight(model: TrackedVehicleModel, speed: float, seconds: float) -> None:
    model.set_demand(TrackDemand(left=speed, right=speed))
    run(model, seconds)


def test_params_validation_rejects_bad_values():
    with pytest.raises(ValueError):
        TrackedVehicleParams.from_dict({"vehicle_mass": -1.0})
    with pytest.raises(ValueError):
        TrackedVehicleParams.from_dict({"research_speed_limit": 30.0, "max_vehicle_speed": 15.0})


def test_from_dict_ignores_unknown_keys():
    params = TrackedVehicleParams.from_dict({"vehicle_mass": 40000, "not_a_param": 1})
    assert params.vehicle_mass == 40000.0


def test_command_latency_delays_motion():
    model = TrackedVehicleModel(TrackedVehicleParams(command_latency=0.5))
    model.set_demand(TrackDemand(left=1.0, right=1.0))
    run(model, 0.45)
    assert model.state.linear_velocity == pytest.approx(0.0)
    run(model, 0.5)
    assert model.state.linear_velocity > 0.0


def test_acceleration_is_limited():
    params = TrackedVehicleParams(max_acceleration=0.5, command_latency=0.0)
    model = TrackedVehicleModel(params)
    model.set_demand(TrackDemand(left=5.0, right=5.0))
    run(model, 1.0)
    assert model.state.left_track_velocity <= 0.5 * 1.0 + 1e-6


def test_braking_latency_and_long_stopping_distance():
    params = TrackedVehicleParams(command_latency=0.25, braking_latency=0.4, max_deceleration=1.5)
    model = TrackedVehicleModel(params)
    drive_straight(model, 2.0, 20.0)
    v0 = model.state.left_track_velocity
    assert v0 == pytest.approx(2.0, abs=0.05)
    x0 = model.state.x
    model.set_demand(TrackDemand(service_brake=True))
    run(model, 10.0)
    assert model.stopped
    stopping = model.state.x - x0
    # Ideal braking distance alone is v^2 / 2a; latency adds reaction distance.
    ideal = v0**2 / (2 * 1.5)
    assert stopping > ideal + v0 * 0.25


def test_emergency_brake_stops_faster_than_service_brake():
    def stop_distance(emergency: bool) -> float:
        model = TrackedVehicleModel(TrackedVehicleParams())
        drive_straight(model, 2.0, 20.0)
        x0 = model.state.x
        model.set_demand(TrackDemand(emergency_brake=emergency, service_brake=not emergency))
        run(model, 10.0)
        assert model.stopped
        return model.state.x - x0

    assert stop_distance(True) < stop_distance(False)


def test_skid_steer_yaw_is_less_than_ideal_differential_drive():
    params = TrackedVehicleParams(command_latency=0.0)
    model = TrackedVehicleModel(params)
    model.set_demand(TrackDemand(left=0.6, right=1.0))
    run(model, 30.0)
    ideal = (1.0 - 0.6) / params.track_separation
    assert 0.0 < model.state.yaw_rate < ideal
    assert model.state.yaw_rate_ratio < 1.0


def test_yaw_rate_is_capped():
    params = TrackedVehicleParams(command_latency=0.0, max_yaw_rate=0.2)
    model = TrackedVehicleModel(params)
    model.set_demand(TrackDemand(left=-2.0, right=2.0))
    run(model, 30.0)
    assert abs(model.state.yaw_rate) <= 0.2 + 1e-6


def test_low_friction_increases_slip():
    def slip(mu: float) -> float:
        model = TrackedVehicleModel(TrackedVehicleParams(terrain_friction=mu, command_latency=0.0))
        model.set_demand(TrackDemand(left=0.5, right=1.0))
        run(model, 10.0)
        return max(model.state.left_slip, model.state.right_slip)

    assert slip(0.3) > slip(0.8)


def test_track_distance_exceeds_ground_distance_when_slipping():
    model = TrackedVehicleModel(TrackedVehicleParams(terrain_friction=0.4))
    drive_straight(model, 1.0, 20.0)
    track = 0.5 * (model.state.left_track_distance + model.state.right_track_distance)
    assert track > model.state.distance_travelled


def test_uphill_reduces_acceleration_and_downhill_lengthens_braking():
    def accel_speed(slope: float) -> float:
        model = TrackedVehicleModel(TrackedVehicleParams(terrain_slope=slope, command_latency=0.0))
        model.set_demand(TrackDemand(left=3.0, right=3.0))
        run(model, 2.0)
        return model.state.left_track_velocity

    assert accel_speed(math.radians(2.0)) < accel_speed(0.0)

    def brake_distance(slope: float) -> float:
        model = TrackedVehicleModel(TrackedVehicleParams(terrain_slope=slope))
        drive_straight(model, 1.0, 20.0)
        x0 = model.state.x
        model.set_demand(TrackDemand(service_brake=True))
        run(model, 15.0)
        return model.state.x - x0

    assert brake_distance(math.radians(-5.0)) > brake_distance(math.radians(5.0))


def test_zero_demand_reaches_standstill():
    model = TrackedVehicleModel(TrackedVehicleParams())
    model.set_demand(TrackDemand(left=1.0, right=0.8))
    run(model, 10.0)
    model.set_demand(TrackDemand())
    run(model, 15.0)
    assert model.stopped
