import pytest
from htv_vehicle_interface import (
    BackendNotAllowedError,
    InterfaceLimits,
    LegacyTrackedVehicleInterface,
    MotionCommand,
    SimulatedLegacyTrackedVehicleInterface,
    StopMode,
    VehicleFeedback,
    VehicleInterfaceState,
    create_backend,
)


class Recorder:
    def __init__(self):
        self.requests = []

    def __call__(self, request, now):
        self.requests.append(request)


def make(now=0.0, moving=False):
    sink = Recorder()
    vi = SimulatedLegacyTrackedVehicleInterface(InterfaceLimits(), sink)
    vi.initialize(now)
    speed = 0.5 if moving else 0.0
    vi.on_feedback(VehicleFeedback(now, speed, speed))
    return vi, sink


def feed(vi, now, speed=0.0):
    vi.on_feedback(VehicleFeedback(now, speed, speed))


def test_is_a_legacy_tracked_vehicle_interface():
    vi, _ = make()
    assert isinstance(vi, LegacyTrackedVehicleInterface)
    assert vi.backend_name == "simulated"


def test_starts_disabled_and_never_moves_without_enable():
    vi, _ = make()
    assert vi.state == VehicleInterfaceState.DISABLED
    assert vi.submit_command(MotionCommand(0.5, 0.0, 0.0, True), 0.0)
    req = vi.update(0.01)
    assert req.stop_mode == StopMode.SERVICE
    assert req.left_track_velocity == 0.0 and req.right_track_velocity == 0.0


def test_enabled_fresh_command_maps_to_track_speeds():
    vi, _ = make()
    assert vi.enable(0.0)[0]
    vi.submit_command(MotionCommand(0.5, 0.1, 0.0, True), 0.0)
    req = vi.update(0.05)
    assert req.stop_mode == StopMode.NONE
    half = 0.5 * vi.limits.track_separation * 0.1
    assert req.left_track_velocity == pytest.approx(0.5 - half)
    assert req.right_track_velocity == pytest.approx(0.5 + half)


def test_enable_motion_false_is_a_stop():
    vi, _ = make()
    vi.enable(0.0)
    vi.submit_command(MotionCommand(0.5, 0.0, 0.0, False), 0.0)
    assert vi.update(0.01).stop_mode == StopMode.SERVICE


def test_stale_command_stops():
    vi, _ = make()
    vi.enable(0.0)
    vi.submit_command(MotionCommand(0.5, 0.0, 0.0, True), 0.0)
    feed(vi, 1.0)
    assert vi.update(1.0).stop_mode == StopMode.SERVICE


@pytest.mark.parametrize(
    "cmd",
    [
        MotionCommand(float("nan"), 0.0, 0.0, True),
        MotionCommand(5.0, 0.0, 0.0, True),
        MotionCommand(0.5, 2.0, 0.0, True),
        MotionCommand(0.5, 0.0, 10.0, True),
    ],
)
def test_invalid_commands_are_rejected_and_clear_previous(cmd):
    vi, _ = make()
    vi.enable(0.0)
    assert vi.submit_command(MotionCommand(0.5, 0.0, 0.0, True), 0.0)
    assert not vi.submit_command(cmd, 0.0)
    assert vi.update(0.01).stop_mode == StopMode.SERVICE
    assert vi.get_status(0.01).rejected_command_count == 1


def test_emergency_stop_is_latched_until_reset_at_standstill():
    vi, _ = make(moving=True)
    vi.enable(0.0)
    vi.emergency_stop(0.1, "test")
    assert vi.update(0.1).stop_mode == StopMode.EMERGENCY
    assert not vi.enable(0.1)[0]
    feed(vi, 0.2, speed=0.5)
    assert not vi.reset_emergency_stop(0.2)[0]
    feed(vi, 0.3, speed=0.0)
    assert vi.reset_emergency_stop(0.3)[0]
    assert vi.state == VehicleInterfaceState.DISABLED
    # Reset never re-enables motion on its own.
    vi.submit_command(MotionCommand(0.5, 0.0, 0.3, True), 0.3)
    assert vi.update(0.31).stop_mode == StopMode.SERVICE


def test_request_stop_requires_re_enable():
    vi, _ = make(moving=True)
    vi.enable(0.0)
    vi.request_stop(0.1)
    assert vi.state == VehicleInterfaceState.STOPPING
    feed(vi, 0.2, speed=0.0)
    vi.update(0.2)
    assert vi.state == VehicleInterfaceState.DISABLED
    vi.submit_command(MotionCommand(0.5, 0.0, 0.2, True), 0.2)
    assert vi.update(0.21).stop_mode == StopMode.SERVICE


def test_feedback_timeout_while_enabled_is_a_latched_fault():
    vi, _ = make()
    vi.enable(0.0)
    vi.submit_command(MotionCommand(0.5, 0.0, 1.0, True), 1.0)
    req = vi.update(1.0)
    assert vi.state == VehicleInterfaceState.FAULT
    assert req.stop_mode == StopMode.EMERGENCY


def test_enable_refused_without_feedback():
    vi = SimulatedLegacyTrackedVehicleInterface(InterfaceLimits())
    vi.initialize(0.0)
    assert not vi.enable(0.0)[0]


def test_registry_is_simulation_only_by_default():
    backend = create_backend("simulated", {"track_separation": 3.0})
    assert isinstance(backend, SimulatedLegacyTrackedVehicleInterface)
    assert backend.limits.track_separation == 3.0
    with pytest.raises(BackendNotAllowedError):
        create_backend("some_hardware_adapter", {})
    with pytest.raises(KeyError):
        create_backend("some_hardware_adapter", {}, allow_non_simulated=True)


def test_hold_brakes_without_changing_state():
    vi, sink = make()
    vi.enable(0.0)
    vi.submit_command(MotionCommand(0.5, 0.0, 0.0, True), 0.0)
    assert vi.hold(0.01).stop_mode == StopMode.SERVICE
    assert vi.state == VehicleInterfaceState.ENABLED
    assert sink.requests[-1].left_track_velocity == 0.0
    vi.emergency_stop(0.02)
    assert vi.hold(0.03).stop_mode == StopMode.EMERGENCY
