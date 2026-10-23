"""Operator-mode state machine: MANUAL, AUTONOMY_ARMED, AUTONOMOUS, STOPPED.

The system always starts in MANUAL. Only an explicit ``request_enable`` (the
``/autonomy/enable`` service) can arm autonomy, and every stop drops back to a
state from which another explicit enable is required.
"""

from __future__ import annotations

from enum import IntEnum

from .state_machine import MOTION_STATES, SafetyState


class OperatorMode(IntEnum):
    # Values match htv_interfaces/msg/OperatorState constants.
    MANUAL = 0
    AUTONOMY_ARMED = 1
    AUTONOMOUS = 2
    STOPPED = 3


class OperatorModeStateMachine:
    def __init__(self, arm_timeout: float = 10.0) -> None:
        self.mode = OperatorMode.MANUAL
        self.enable_sequence = 0
        self.arm_timeout = arm_timeout
        self._armed_at: float | None = None

    @property
    def operator_enable(self) -> bool:
        return self.mode in (OperatorMode.AUTONOMY_ARMED, OperatorMode.AUTONOMOUS)

    def request_enable(self, now: float, safety_state: SafetyState | None, vehicle_stopped: bool) -> tuple[bool, str]:
        if self.mode in (OperatorMode.AUTONOMY_ARMED, OperatorMode.AUTONOMOUS):
            return False, f"already {self.mode.name}"
        if self.mode == OperatorMode.STOPPED and not vehicle_stopped:
            return False, "vehicle still stopping"
        if safety_state is None:
            return False, "safety supervisor status unavailable"
        if safety_state != SafetyState.READY and safety_state != SafetyState.STANDBY:
            return False, f"safety supervisor in {safety_state.name}; must be STANDBY or READY"
        self.enable_sequence += 1
        self.mode = OperatorMode.AUTONOMY_ARMED
        self._armed_at = now
        return True, f"autonomy armed (request #{self.enable_sequence})"

    def request_disable(self) -> tuple[bool, str]:
        if self.mode == OperatorMode.MANUAL:
            return True, "already MANUAL"
        self.mode = OperatorMode.STOPPED
        self._armed_at = None
        return True, "autonomy disabled; stopping"

    def update(self, now: float, safety_state: SafetyState | None, vehicle_stopped: bool) -> OperatorMode:
        if self.mode == OperatorMode.AUTONOMY_ARMED:
            if safety_state in MOTION_STATES:
                self.mode = OperatorMode.AUTONOMOUS
            elif safety_state is None or safety_state in (
                SafetyState.CONTROLLED_STOP, SafetyState.EMERGENCY_STOP, SafetyState.FAULT
            ):
                self.mode = OperatorMode.STOPPED
            elif self._armed_at is not None and now - self._armed_at > self.arm_timeout:
                # Supervisor never accepted the request: do not leave autonomy armed.
                self.mode = OperatorMode.STOPPED
        elif self.mode == OperatorMode.AUTONOMOUS:
            if safety_state not in MOTION_STATES:
                self.mode = OperatorMode.STOPPED
        elif self.mode == OperatorMode.STOPPED and vehicle_stopped and safety_state not in MOTION_STATES:
            self.mode = OperatorMode.MANUAL
        return self.mode
