"""The vehicle abstraction layer contract.

Everything above this module (planning, safety, arbitration) speaks only in
``SafeMotionCommand`` terms: a body-frame linear velocity, a yaw rate, a time
stamp and a motion-permission flag. Everything below it is the responsibility of
a backend. This repository ships exactly one backend,
:class:`~htv_vehicle_interface.simulated.SimulatedLegacyTrackedVehicleInterface`.

There is deliberately **no** real hardware implementation here. An authorised
engineering team may implement a hardware adapter independently, in a separate
package, by subclassing :class:`GuardedVehicleInterfaceBase` (recommended, it
keeps the command validation and latching below) or :class:`LegacyTrackedVehicleInterface`
directly, and registering it under the ``htv_vehicle_interface.backends`` entry
point group. See ``docs/HARDWARE_ADAPTER_CONTRACT.md``.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum


class VehicleInterfaceState(IntEnum):
    # Values match htv_interfaces/msg/VehicleStatus constants.
    UNINITIALIZED = 0
    DISABLED = 1
    ENABLED = 2
    STOPPING = 3
    EMERGENCY_STOP = 4
    FAULT = 5


class StopMode(IntEnum):
    NONE = 0
    SERVICE = 1
    EMERGENCY = 2


@dataclass(frozen=True)
class MotionCommand:
    """ROS-agnostic mirror of ``htv_interfaces/msg/SafeMotionCommand``."""

    linear_velocity: float
    yaw_rate: float
    timestamp: float  # seconds, same clock as ``now`` arguments
    enable_motion: bool


@dataclass(frozen=True)
class VehicleFeedback:
    """Feedback a backend receives from its plant (simulated or otherwise)."""

    stamp: float
    left_track_velocity: float
    right_track_velocity: float
    brake_engaged: bool = False
    emergency_brake_engaged: bool = False


@dataclass(frozen=True)
class ActuationRequest:
    """Generic, platform-neutral actuation request produced every update cycle.

    Backends translate this into whatever their plant needs. The fields are
    kinematic only; no backend-specific detail is allowed to leak upward.
    """

    linear_velocity: float
    yaw_rate: float
    left_track_velocity: float
    right_track_velocity: float
    stop_mode: StopMode


@dataclass
class VehicleInterfaceStatus:
    state: VehicleInterfaceState = VehicleInterfaceState.UNINITIALIZED
    backend: str = ""
    ready: bool = False
    enabled: bool = False
    emergency_stop_latched: bool = False
    brake_engaged: bool = False
    stopped: bool = True
    measured_linear_velocity: float = 0.0
    measured_yaw_rate: float = 0.0
    left_track_velocity: float = 0.0
    right_track_velocity: float = 0.0
    commanded_linear_velocity: float = 0.0
    commanded_yaw_rate: float = 0.0
    command_age: float = -1.0
    feedback_age: float = -1.0
    rejected_command_count: int = 0
    faults: list[str] = field(default_factory=list)


class LegacyTrackedVehicleInterface(ABC):
    """Abstract contract every vehicle backend must satisfy.

    All methods take ``now`` explicitly (seconds) so implementations are
    deterministic and testable without a ROS clock. Methods return
    ``(success, message)``.
    """

    backend_name: str = "abstract"

    @abstractmethod
    def initialize(self, now: float) -> tuple[bool, str]: ...

    @abstractmethod
    def enable(self, now: float) -> tuple[bool, str]: ...

    @abstractmethod
    def disable(self, now: float) -> tuple[bool, str]: ...

    @abstractmethod
    def request_stop(self, now: float, reason: str = "") -> tuple[bool, str]: ...

    @abstractmethod
    def emergency_stop(self, now: float, reason: str = "") -> tuple[bool, str]: ...

    @abstractmethod
    def reset_emergency_stop(self, now: float) -> tuple[bool, str]: ...

    @abstractmethod
    def submit_command(self, command: MotionCommand, now: float) -> bool:
        """Offer a SafeMotionCommand. Returns False if it was rejected."""

    @abstractmethod
    def on_feedback(self, feedback: VehicleFeedback) -> None: ...

    @abstractmethod
    def update(self, now: float) -> ActuationRequest:
        """Periodic tick: apply timeouts and emit the actuation for this cycle."""

    @abstractmethod
    def hold(self, now: float) -> ActuationRequest:
        """Emit a stop actuation for this cycle without changing state.

        Used when the host could not evaluate its inputs this cycle (e.g. it stalled).
        Latched states must still emit their emergency actuation.
        """

    @abstractmethod
    def get_status(self, now: float) -> VehicleInterfaceStatus: ...


@dataclass
class InterfaceLimits:
    track_separation: float = 2.80
    max_linear_velocity: float = 1.0
    max_reverse_velocity: float = 0.5
    max_yaw_rate: float = 0.15
    # Commands beyond limits by more than this are rejected, not clamped: the
    # upstream limiter must never produce them, so they indicate a bypass or bug.
    limit_tolerance: float = 0.05
    command_timeout: float = 0.30
    future_tolerance: float = 0.10
    feedback_timeout: float = 0.50
    standstill_threshold: float = 0.02
    # Multiplier applied to the yaw component when mapping to track speeds.
    steering_compensation: float = 1.0


class GuardedVehicleInterfaceBase(LegacyTrackedVehicleInterface):
    """Common state machine, command validation, timeouts and E-stop latching.

    Subclasses implement :meth:`_actuate` only. The guard logic guarantees:

    * no motion unless ENABLED, the command is fresh, finite, within limits and
      ``enable_motion`` is set;
    * stale or missing commands produce a service stop;
    * missing feedback while enabled is a latched FAULT with emergency braking;
    * EMERGENCY_STOP is latched and only cleared by an explicit reset at standstill;
    * after ``request_stop``/``disable`` the interface must be explicitly re-enabled.
    """

    def __init__(self, limits: InterfaceLimits | None = None) -> None:
        self.limits = limits or InterfaceLimits()
        self._state = VehicleInterfaceState.UNINITIALIZED
        self._command: MotionCommand | None = None
        self._command_received_at: float | None = None
        self._feedback: VehicleFeedback | None = None
        self._rejected = 0
        self.last_rejection = ""
        self._faults: list[str] = []
        self._last_actuation = ActuationRequest(0.0, 0.0, 0.0, 0.0, StopMode.SERVICE)

    # -------------------------------------------------------- backend hook
    @abstractmethod
    def _actuate(self, request: ActuationRequest, now: float) -> None:
        """Deliver an actuation request to the plant."""

    # -------------------------------------------------------------- helpers
    @property
    def state(self) -> VehicleInterfaceState:
        return self._state

    def _feedback_fresh(self, now: float) -> bool:
        if self._feedback is None:
            return False
        age = now - self._feedback.stamp
        return 0.0 <= age <= self.limits.feedback_timeout

    def _measured(self) -> tuple[float, float]:
        if self._feedback is None:
            return 0.0, 0.0
        vl, vr = self._feedback.left_track_velocity, self._feedback.right_track_velocity
        return 0.5 * (vl + vr), (vr - vl) / self.limits.track_separation

    def _is_stopped(self) -> bool:
        if self._feedback is None:
            return False
        thr = self.limits.standstill_threshold
        return abs(self._feedback.left_track_velocity) < thr and abs(self._feedback.right_track_velocity) < thr

    def _latched(self) -> bool:
        return self._state in (VehicleInterfaceState.EMERGENCY_STOP, VehicleInterfaceState.FAULT)

    def _fault(self, reason: str) -> None:
        if reason not in self._faults:
            self._faults.append(reason)
        self._state = VehicleInterfaceState.FAULT

    # ------------------------------------------------------------------ API
    def initialize(self, now: float) -> tuple[bool, str]:
        if self._state != VehicleInterfaceState.UNINITIALIZED:
            return False, f"already initialised ({self._state.name})"
        self._state = VehicleInterfaceState.DISABLED
        return True, "initialised (disabled)"

    def enable(self, now: float) -> tuple[bool, str]:
        if self._latched():
            return False, f"cannot enable: {self._state.name} latched, explicit reset required"
        if self._state == VehicleInterfaceState.UNINITIALIZED:
            return False, "cannot enable: not initialised"
        if self._state == VehicleInterfaceState.STOPPING:
            return False, "cannot enable: stop in progress"
        if not self._feedback_fresh(now):
            return False, "cannot enable: no fresh vehicle feedback"
        if self._state == VehicleInterfaceState.ENABLED:
            return True, "already enabled"
        # Never accept a command that predates enabling.
        self._command = None
        self._state = VehicleInterfaceState.ENABLED
        return True, "enabled"

    def disable(self, now: float) -> tuple[bool, str]:
        return self.request_stop(now, "disable requested")

    def request_stop(self, now: float, reason: str = "") -> tuple[bool, str]:
        if self._latched():
            return True, f"{self._state.name} already latched"
        if self._state == VehicleInterfaceState.ENABLED:
            self._state = VehicleInterfaceState.STOPPING
        self._command = None
        return True, f"controlled stop: {reason}" if reason else "controlled stop"

    def emergency_stop(self, now: float, reason: str = "") -> tuple[bool, str]:
        if self._state != VehicleInterfaceState.FAULT:
            self._state = VehicleInterfaceState.EMERGENCY_STOP
        if reason and reason not in self._faults:
            self._faults.append(reason)
        self._command = None
        return True, "emergency stop latched"

    def reset_emergency_stop(self, now: float) -> tuple[bool, str]:
        if not self._latched():
            return True, "no emergency stop latched"
        if not self._feedback_fresh(now):
            return False, "reset refused: no fresh vehicle feedback"
        if not self._is_stopped():
            return False, "reset refused: vehicle not at standstill"
        self._state = VehicleInterfaceState.DISABLED
        self._faults.clear()
        return True, "reset to DISABLED; explicit enable required"

    def submit_command(self, command: MotionCommand, now: float) -> bool:
        lim = self.limits
        values = (command.linear_velocity, command.yaw_rate, command.timestamp)
        if not all(math.isfinite(v) for v in values):
            return self._reject("non-finite command")
        if command.timestamp - now > lim.future_tolerance:
            return self._reject("command timestamp in the future")
        if (
            command.linear_velocity > lim.max_linear_velocity + lim.limit_tolerance
            or command.linear_velocity < -(lim.max_reverse_velocity + lim.limit_tolerance)
            or abs(command.yaw_rate) > lim.max_yaw_rate + lim.limit_tolerance
        ):
            return self._reject("command exceeds interface limits")
        self._command = command
        self._command_received_at = now
        return True

    def _reject(self, reason: str) -> bool:
        self._rejected += 1
        self.last_rejection = reason
        # A rejected command must never leave an older command active.
        self._command = None
        return False

    def on_feedback(self, feedback: VehicleFeedback) -> None:
        self._feedback = feedback

    def update(self, now: float) -> ActuationRequest:
        lim = self.limits
        if self._state == VehicleInterfaceState.ENABLED and not self._feedback_fresh(now):
            self._fault("vehicle feedback timeout")

        if self._state == VehicleInterfaceState.STOPPING and self._is_stopped():
            self._state = VehicleInterfaceState.DISABLED

        if self._latched():
            request = ActuationRequest(0.0, 0.0, 0.0, 0.0, StopMode.EMERGENCY)
        elif self._state != VehicleInterfaceState.ENABLED:
            request = ActuationRequest(0.0, 0.0, 0.0, 0.0, StopMode.SERVICE)
        else:
            cmd = self._command
            fresh = cmd is not None and -lim.future_tolerance <= (now - cmd.timestamp) <= lim.command_timeout
            if not fresh or cmd is None or not cmd.enable_motion:
                request = ActuationRequest(0.0, 0.0, 0.0, 0.0, StopMode.SERVICE)
            else:
                v = max(-lim.max_reverse_velocity, min(lim.max_linear_velocity, cmd.linear_velocity))
                w = max(-lim.max_yaw_rate, min(lim.max_yaw_rate, cmd.yaw_rate))
                half = 0.5 * lim.track_separation * w * lim.steering_compensation
                request = ActuationRequest(v, w, v - half, v + half, StopMode.NONE)

        self._last_actuation = request
        self._actuate(request, now)
        return request

    def hold(self, now: float) -> ActuationRequest:
        mode = StopMode.EMERGENCY if self._latched() else StopMode.SERVICE
        request = ActuationRequest(0.0, 0.0, 0.0, 0.0, mode)
        self._last_actuation = request
        self._actuate(request, now)
        return request

    def get_status(self, now: float) -> VehicleInterfaceStatus:
        v, w = self._measured()
        cmd = self._command
        feedback_fresh = self._feedback_fresh(now)
        return VehicleInterfaceStatus(
            state=self._state,
            backend=self.backend_name,
            ready=feedback_fresh and not self._latched() and self._state != VehicleInterfaceState.UNINITIALIZED,
            enabled=self._state == VehicleInterfaceState.ENABLED,
            emergency_stop_latched=self._state == VehicleInterfaceState.EMERGENCY_STOP,
            brake_engaged=bool(self._feedback and self._feedback.brake_engaged),
            stopped=self._is_stopped(),
            measured_linear_velocity=v,
            measured_yaw_rate=w,
            left_track_velocity=self._feedback.left_track_velocity if self._feedback else 0.0,
            right_track_velocity=self._feedback.right_track_velocity if self._feedback else 0.0,
            commanded_linear_velocity=self._last_actuation.linear_velocity,
            commanded_yaw_rate=self._last_actuation.yaw_rate,
            command_age=(now - cmd.timestamp) if cmd else -1.0,
            feedback_age=(now - self._feedback.stamp) if self._feedback else -1.0,
            rejected_command_count=self._rejected,
            faults=list(self._faults),
        )
