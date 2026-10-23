"""Safety supervisor state machine (ROS-agnostic).

States::

    POWER_OFF -> INITIALIZING -> STANDBY <-> READY -> AUTONOMOUS <-> DEGRADED
                                   ^                      |             |
                                   +--- CONTROLLED_STOP <-+-------------+
    ANY --(severe)--> EMERGENCY_STOP (latched)      ANY --(internal)--> FAULT (latched)

Rules enforced here:

* AUTONOMOUS requires localization, perception, vehicle interface, safety system,
  operator enable and geofence all valid, **and** a fresh operator enable request
  (``enable_sequence`` newer than the one consumed by the previous autonomy run):
  autonomy can never re-arm itself after a stop.
* Loss of any safety-critical input in AUTONOMOUS/DEGRADED => CONTROLLED_STOP.
* Severe faults from any state => EMERGENCY_STOP, latched until an explicit
  operator reset at standstill with the cause cleared.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class SafetyState(IntEnum):
    # Values match htv_interfaces/msg/SafetyStatus constants.
    POWER_OFF = 0
    INITIALIZING = 1
    STANDBY = 2
    READY = 3
    AUTONOMOUS = 4
    DEGRADED = 5
    CONTROLLED_STOP = 6
    EMERGENCY_STOP = 7
    FAULT = 8


MOTION_STATES = frozenset({SafetyState.AUTONOMOUS, SafetyState.DEGRADED})
LATCHED_STATES = frozenset({SafetyState.EMERGENCY_STOP, SafetyState.FAULT})


class SlipLevel(IntEnum):
    NORMAL = 0
    HIGH = 1        # degrade: reduced speed
    EXCESSIVE = 2   # controlled stop


@dataclass
class SafetyInputs:
    """Snapshot of every supervisor input. Missing/stale inputs must be False."""

    localization_valid: bool = False
    perception_valid: bool = False
    lidar_valid: bool = False
    imu_valid: bool = False
    gnss_valid: bool = False
    compute_watchdog_ok: bool = False
    vehicle_interface_ready: bool = False
    vehicle_interface_enabled: bool = False
    vehicle_interface_alive: bool = False
    vehicle_stopped: bool = False
    brake_ok: bool = True
    geofence_valid: bool = False
    geofence_breached: bool = False
    estop_active: bool = False
    watchdog_critical: bool = False
    operator_enable: bool = False
    operator_enable_sequence: int = 0
    slip_level: SlipLevel = SlipLevel.NORMAL
    safety_self_test_ok: bool = True


@dataclass
class SupervisorConfig:
    min_initialization_time: float = 1.0
    initialization_timeout: float = 30.0
    degraded_speed_scale: float = 0.5
    gnss_required: bool = False  # GNSS loss is DEGRADED unless required


@dataclass
class SafetyOutput:
    state: SafetyState
    motion_allowed: bool
    speed_scale: float
    reasons: list[str] = field(default_factory=list)
    entry_conditions: dict[str, bool] = field(default_factory=dict)


class SafetySupervisorStateMachine:
    def __init__(self, config: SupervisorConfig | None = None) -> None:
        self.config = config or SupervisorConfig()
        self.state = SafetyState.POWER_OFF
        self.reasons: list[str] = []
        self.intervention_count = 0
        self.latched_reasons: list[str] = []
        self._init_started: float | None = None
        self._consumed_enable_sequence = 0
        self._last_inputs = SafetyInputs()

    # ---------------------------------------------------------------- events
    def power_on(self, now: float) -> None:
        if self.state == SafetyState.POWER_OFF:
            self.state = SafetyState.INITIALIZING
            self._init_started = now

    def internal_fault(self, reason: str) -> None:
        self._latch(SafetyState.FAULT, [reason])

    def request_reset(self, confirmed: bool) -> tuple[bool, str]:
        """Explicit operator reset of EMERGENCY_STOP / FAULT."""
        if self.state not in LATCHED_STATES:
            return False, f"nothing to reset (state {self.state.name})"
        if not confirmed:
            return False, "reset requires explicit operator confirmation"
        inputs = self._last_inputs
        severe = self._severe_reasons(inputs)
        if severe:
            return False, "reset refused, cause still present: " + ", ".join(severe)
        if not inputs.vehicle_stopped:
            return False, "reset refused: vehicle not at standstill"
        if not inputs.safety_self_test_ok:
            return False, "reset refused: safety self-test failing"
        self.state = SafetyState.STANDBY
        self.latched_reasons = []
        # Any enable request issued before the reset is void.
        self._consumed_enable_sequence = max(self._consumed_enable_sequence, inputs.operator_enable_sequence)
        return True, "reset to STANDBY; operator must re-enable autonomy"

    # ------------------------------------------------------------ evaluation
    def critical_reasons(self, i: SafetyInputs) -> list[str]:
        checks = {
            "localization invalid": i.localization_valid,
            "perception invalid": i.perception_valid,
            "lidar invalid": i.lidar_valid,
            "imu invalid": i.imu_valid,
            "compute watchdog": i.compute_watchdog_ok,
            "vehicle interface not ready": i.vehicle_interface_ready,
            "geofence invalid": i.geofence_valid,
        }
        if self.config.gnss_required:
            checks["gnss invalid"] = i.gnss_valid
        reasons = [name for name, ok in checks.items() if not ok]
        if i.slip_level >= SlipLevel.EXCESSIVE:
            reasons.append("excessive track slip")
        return reasons

    def degrade_reasons(self, i: SafetyInputs) -> list[str]:
        reasons = []
        if not i.gnss_valid and not self.config.gnss_required:
            reasons.append("gnss unavailable")
        if i.slip_level == SlipLevel.HIGH:
            reasons.append("high track slip")
        return reasons

    @staticmethod
    def _severe_reasons(i: SafetyInputs) -> list[str]:
        reasons = []
        if i.estop_active:
            reasons.append("emergency stop input")
        if i.watchdog_critical:
            reasons.append("critical heartbeat lost")
        if not i.vehicle_interface_alive:
            reasons.append("vehicle interface timeout")
        if not i.brake_ok:
            reasons.append("brake fault")
        if i.geofence_breached:
            reasons.append("geofence breached")
        return reasons

    def entry_conditions(self, i: SafetyInputs) -> dict[str, bool]:
        return {
            "localization_valid": i.localization_valid,
            "perception_valid": i.perception_valid and i.lidar_valid and i.imu_valid,
            "vehicle_interface_ready": i.vehicle_interface_ready and i.vehicle_interface_enabled,
            "safety_system_ready": self._safety_system_ready(i),
            "operator_enable": i.operator_enable,
            "geofence_valid": i.geofence_valid,
        }

    def _safety_system_ready(self, i: SafetyInputs) -> bool:
        return i.safety_self_test_ok and i.compute_watchdog_ok and not self._severe_reasons(i)

    def _latch(self, state: SafetyState, reasons: list[str]) -> None:
        if self.state not in LATCHED_STATES or state == SafetyState.FAULT:
            if self.state in MOTION_STATES:
                self.intervention_count += 1
            self.state = state
        for reason in reasons:
            if reason not in self.latched_reasons:
                self.latched_reasons.append(reason)

    def _stop(self, reasons: list[str]) -> None:
        self.intervention_count += 1
        self.state = SafetyState.CONTROLLED_STOP
        self.reasons = reasons

    def update(self, i: SafetyInputs, now: float) -> SafetyOutput:
        self._last_inputs = i
        state = self.state
        if state == SafetyState.POWER_OFF:
            self.reasons = ["power off"]
            return self._output(i)

        severe = self._severe_reasons(i)
        # During initialisation monitored nodes may legitimately not be up yet;
        # INITIALIZING itself never permits motion and times out into FAULT.
        if state == SafetyState.INITIALIZING:
            severe = [r for r in severe if r not in ("vehicle interface timeout", "critical heartbeat lost")]
        if not i.safety_self_test_ok:
            self._latch(SafetyState.FAULT, ["safety self-test failed"])
        elif severe:
            self._latch(SafetyState.EMERGENCY_STOP, severe)

        if self.state in LATCHED_STATES:
            self.reasons = list(self.latched_reasons)
            return self._output(i)

        critical = self.critical_reasons(i)
        conditions = self.entry_conditions(i)
        all_entry = all(conditions.values())
        fresh_enable = i.operator_enable and i.operator_enable_sequence > self._consumed_enable_sequence

        if state == SafetyState.INITIALIZING:
            assert self._init_started is not None
            elapsed = now - self._init_started
            pending = [
                name
                for name, ok in (
                    ("waiting for vehicle interface", i.vehicle_interface_alive),
                    ("waiting for watchdog", not i.watchdog_critical and i.compute_watchdog_ok),
                )
                if not ok
            ]
            if elapsed >= self.config.min_initialization_time and not pending:
                self.state = SafetyState.STANDBY
                self.reasons = []
            elif elapsed > self.config.initialization_timeout:
                self._latch(SafetyState.FAULT, ["initialization timeout: " + ", ".join(pending)])
                self.reasons = list(self.latched_reasons)
            else:
                self.reasons = ["initializing", *pending]
        elif state in (SafetyState.STANDBY, SafetyState.READY):
            ready = not critical and conditions["safety_system_ready"]
            self.state = SafetyState.READY if ready else SafetyState.STANDBY
            self.reasons = critical if critical else []
            if self.state == SafetyState.READY:
                if all_entry and fresh_enable:
                    self.state = SafetyState.AUTONOMOUS
                    self._consumed_enable_sequence = i.operator_enable_sequence
                    self.reasons = []
                elif not fresh_enable:
                    self.reasons = ["awaiting operator enable"]
                else:
                    self.reasons = [k for k, ok in conditions.items() if not ok]
        elif state in MOTION_STATES:
            if not i.operator_enable:
                self._stop(["operator disabled autonomy"])
            elif critical or not all_entry:
                self._stop(critical or [k for k, ok in conditions.items() if not ok])
            else:
                degrade = self.degrade_reasons(i)
                self.state = SafetyState.DEGRADED if degrade else SafetyState.AUTONOMOUS
                self.reasons = degrade
        elif state == SafetyState.CONTROLLED_STOP:
            if i.vehicle_stopped:
                self.state = SafetyState.STANDBY
                self.reasons = ["stopped; operator must re-enable"]
        return self._output(i)

    def _output(self, i: SafetyInputs) -> SafetyOutput:
        motion = self.state in MOTION_STATES
        if self.state == SafetyState.AUTONOMOUS:
            scale = 1.0
        elif self.state == SafetyState.DEGRADED:
            scale = self.config.degraded_speed_scale
        else:
            scale = 0.0
        return SafetyOutput(self.state, motion, scale, list(self.reasons), self.entry_conditions(i))
