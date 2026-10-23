from dataclasses import replace

import pytest
from htv_safety.state_machine import (
    SafetyInputs,
    SafetyState,
    SafetySupervisorStateMachine,
    SlipLevel,
    SupervisorConfig,
)

HEALTHY = SafetyInputs(
    localization_valid=True,
    perception_valid=True,
    lidar_valid=True,
    imu_valid=True,
    gnss_valid=True,
    compute_watchdog_ok=True,
    vehicle_interface_ready=True,
    vehicle_interface_enabled=True,
    vehicle_interface_alive=True,
    vehicle_stopped=True,
    geofence_valid=True,
)


def ready_machine():
    sm = SafetySupervisorStateMachine(SupervisorConfig(min_initialization_time=0.0))
    sm.power_on(0.0)
    sm.update(HEALTHY, 0.1)  # INITIALIZING -> STANDBY
    sm.update(HEALTHY, 0.2)  # STANDBY -> READY
    assert sm.state == SafetyState.READY
    return sm


def autonomous_machine():
    sm = ready_machine()
    sm.update(replace(HEALTHY, operator_enable=True, operator_enable_sequence=1), 0.3)
    assert sm.state == SafetyState.AUTONOMOUS
    return sm


ENABLED = replace(HEALTHY, operator_enable=True, operator_enable_sequence=1)


def test_starts_power_off_and_never_allows_motion_before_autonomous():
    sm = SafetySupervisorStateMachine()
    assert sm.state == SafetyState.POWER_OFF
    assert not sm.update(ENABLED, 0.0).motion_allowed
    sm.power_on(0.0)
    out = sm.update(ENABLED, 0.1)
    assert sm.state == SafetyState.INITIALIZING
    assert not out.motion_allowed


def test_initialization_waits_for_vehicle_interface_then_times_out_to_fault():
    sm = SafetySupervisorStateMachine(SupervisorConfig(min_initialization_time=0.0, initialization_timeout=5.0))
    sm.power_on(0.0)
    dead = replace(HEALTHY, vehicle_interface_alive=False)
    sm.update(dead, 1.0)
    assert sm.state == SafetyState.INITIALIZING
    sm.update(dead, 6.0)
    assert sm.state == SafetyState.FAULT


def test_ready_does_not_enter_autonomous_without_operator_enable():
    sm = ready_machine()
    for t in range(10):
        out = sm.update(HEALTHY, 1.0 + t)
        assert sm.state == SafetyState.READY
        assert not out.motion_allowed


@pytest.mark.parametrize(
    "field",
    ["localization_valid", "perception_valid", "vehicle_interface_ready", "vehicle_interface_enabled", "geofence_valid"],
)
def test_each_entry_condition_is_required(field):
    sm = ready_machine()
    sm.update(replace(ENABLED, **{field: False}), 0.3)
    assert sm.state != SafetyState.AUTONOMOUS


def test_enter_autonomous_when_all_conditions_hold():
    sm = autonomous_machine()
    out = sm.update(ENABLED, 0.4)
    assert out.motion_allowed and out.speed_scale == 1.0


@pytest.mark.parametrize(
    "field", ["localization_valid", "perception_valid", "lidar_valid", "imu_valid", "vehicle_interface_ready"]
)
def test_critical_loss_causes_controlled_stop(field):
    sm = autonomous_machine()
    out = sm.update(replace(ENABLED, **{field: False}, vehicle_stopped=False), 0.4)
    assert sm.state == SafetyState.CONTROLLED_STOP
    assert not out.motion_allowed


def test_gnss_loss_degrades_and_recovers():
    sm = autonomous_machine()
    out = sm.update(replace(ENABLED, gnss_valid=False), 0.4)
    assert sm.state == SafetyState.DEGRADED
    assert out.motion_allowed and out.speed_scale < 1.0
    sm.update(ENABLED, 0.5)
    assert sm.state == SafetyState.AUTONOMOUS


def test_excessive_slip_stops_high_slip_degrades():
    sm = autonomous_machine()
    sm.update(replace(ENABLED, slip_level=SlipLevel.HIGH), 0.4)
    assert sm.state == SafetyState.DEGRADED
    sm.update(replace(ENABLED, slip_level=SlipLevel.EXCESSIVE, vehicle_stopped=False), 0.5)
    assert sm.state == SafetyState.CONTROLLED_STOP


def test_controlled_stop_never_resumes_without_new_enable_request():
    sm = autonomous_machine()
    sm.update(replace(ENABLED, localization_valid=False, vehicle_stopped=False), 0.4)
    assert sm.state == SafetyState.CONTROLLED_STOP
    sm.update(replace(ENABLED, vehicle_stopped=False), 0.5)
    assert sm.state == SafetyState.CONTROLLED_STOP
    sm.update(ENABLED, 0.6)  # stopped -> STANDBY
    for t in range(5):
        sm.update(ENABLED, 0.7 + t)  # same (consumed) enable sequence
        assert sm.state in (SafetyState.STANDBY, SafetyState.READY)
    sm.update(replace(ENABLED, operator_enable_sequence=2), 10.0)
    assert sm.state == SafetyState.AUTONOMOUS


def test_operator_disable_is_a_controlled_stop():
    sm = autonomous_machine()
    sm.update(replace(HEALTHY, vehicle_stopped=False), 0.4)
    assert sm.state == SafetyState.CONTROLLED_STOP


@pytest.mark.parametrize(
    "change",
    [
        {"estop_active": True},
        {"watchdog_critical": True},
        {"vehicle_interface_alive": False},
        {"brake_ok": False},
        {"geofence_breached": True},
    ],
)
def test_severe_faults_latch_emergency_stop_from_any_state(change):
    for factory in (ready_machine, autonomous_machine):
        sm = factory()
        sm.update(replace(ENABLED, **change), 1.0)
        assert sm.state == SafetyState.EMERGENCY_STOP
        # Latched even once the cause clears.
        sm.update(ENABLED, 2.0)
        assert sm.state == SafetyState.EMERGENCY_STOP


def test_emergency_stop_reset_requires_confirmation_cleared_cause_and_standstill():
    sm = autonomous_machine()
    sm.update(replace(ENABLED, estop_active=True, vehicle_stopped=False), 1.0)
    assert not sm.request_reset(confirmed=True)[0]  # cause present
    sm.update(replace(ENABLED, vehicle_stopped=False), 2.0)
    assert not sm.request_reset(confirmed=True)[0]  # moving
    sm.update(ENABLED, 3.0)
    assert not sm.request_reset(confirmed=False)[0]
    assert sm.request_reset(confirmed=True)[0]
    assert sm.state == SafetyState.STANDBY
    # Old enable request does not re-arm after reset.
    sm.update(ENABLED, 4.0)
    sm.update(ENABLED, 5.0)
    assert sm.state == SafetyState.READY


def test_self_test_failure_is_fault():
    sm = autonomous_machine()
    sm.update(replace(ENABLED, safety_self_test_ok=False), 1.0)
    assert sm.state == SafetyState.FAULT
    assert not sm.update(ENABLED, 2.0).motion_allowed


def test_intervention_count_increments():
    sm = autonomous_machine()
    sm.update(replace(ENABLED, localization_valid=False, vehicle_stopped=False), 0.4)
    assert sm.intervention_count == 1
