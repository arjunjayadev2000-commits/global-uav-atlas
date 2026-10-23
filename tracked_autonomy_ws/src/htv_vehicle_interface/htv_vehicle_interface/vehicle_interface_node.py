"""ROS 2 host node for a LegacyTrackedVehicleInterface backend.

Consumes only ``/safe_cmd_vel`` (SafeMotionCommand). Independently of the
command content it also enforces:

* a fresh ``/safety/status`` heartbeat (stale => emergency stop),
* supervisor EMERGENCY_STOP / FAULT => latched emergency stop,
* supervisor CONTROLLED_STOP => controlled stop requiring re-enable,
* ``/safety/watchdog_estop`` => latched emergency stop.
"""

from __future__ import annotations

from htv_common.heartbeat import HeartbeatPublisher
from htv_common.node_main import run_node
from htv_common.ros_time import clock_ready, from_seconds, now_seconds, to_seconds
from htv_common.stall_guard import StallGuard
from htv_common.topics import (
    OPERATOR_STATE,
    SAFE_CMD_VEL,
    SAFETY_STATUS,
    SIM_TRACK_DEMAND,
    TRACK_FEEDBACK,
    VEHICLE_STATUS,
    WATCHDOG_ESTOP,
)
from htv_interfaces.msg import (
    OperatorState,
    SafeMotionCommand,
    SafetyStatus,
    SimTrackDemand,
    TrackState,
    VehicleStatus,
)
from htv_interfaces.srv import GetVehicleStatus, ResetEmergencyStop
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import Trigger

from .interface import (
    ActuationRequest,
    MotionCommand,
    StopMode,
    VehicleFeedback,
    VehicleInterfaceState,
)
from .registry import create_backend

LATCHING_SAFETY_STATES = (SafetyStatus.EMERGENCY_STOP, SafetyStatus.FAULT)
OPERATOR_ENABLED_STATES = (OperatorState.AUTONOMY_ARMED, OperatorState.AUTONOMOUS)


class VehicleInterfaceNode(Node):
    def __init__(self) -> None:
        super().__init__("vehicle_interface")
        p = self.declare_parameter
        backend = p("backend", "simulated").value
        allow_hw = p("allow_non_simulated_backends", False).value
        rate = p("update_rate", 50.0).value
        self._status_timeout = p("safety_status_timeout", 0.6).value
        self._follow_operator = p("follow_operator_enable", True).value
        config = {
            "track_separation": p("vehicle.track_separation", 2.80).value,
            "max_linear_velocity": p("vehicle.research_speed_limit", 1.0).value,
            "max_reverse_velocity": p("vehicle.research_reverse_speed_limit", 0.5).value,
            "max_yaw_rate": p("vehicle.research_yaw_rate_limit", 0.15).value,
            "limit_tolerance": p("limit_tolerance", 0.05).value,
            "command_timeout": p("command_timeout", 0.30).value,
            "feedback_timeout": p("feedback_timeout", 0.50).value,
            "standstill_threshold": p("vehicle.standstill_threshold", 0.02).value,
            "steering_compensation": p("steering_compensation", 1.0).value,
        }

        self._demand_pub = self.create_publisher(SimTrackDemand, SIM_TRACK_DEMAND, 10)
        self._backend = create_backend(backend, config, self._publish_sim_demand, allow_hw)
        self._backend.initialize(0.0)

        self._status_pub = self.create_publisher(VehicleStatus, VEHICLE_STATUS, 10)
        self.create_subscription(SafeMotionCommand, SAFE_CMD_VEL, self._on_command, 10)
        self.create_subscription(TrackState, TRACK_FEEDBACK, self._on_feedback, 10)
        self.create_subscription(SafetyStatus, SAFETY_STATUS, self._on_safety, 10)
        self.create_subscription(Bool, WATCHDOG_ESTOP, self._on_watchdog_estop, 10)
        self.create_subscription(OperatorState, OPERATOR_STATE, self._on_operator, 10)

        self.create_service(Trigger, "/vehicle/enable", self._srv(self._backend.enable))
        self.create_service(Trigger, "/vehicle/disable", self._srv(self._backend.disable))
        self.create_service(Trigger, "/vehicle/request_stop", self._srv(self._backend.request_stop))
        self.create_service(Trigger, "/vehicle/emergency_stop", self._srv(self._estop_service))
        self.create_service(ResetEmergencyStop, "/vehicle/reset_emergency_stop", self._on_reset)
        self.create_service(GetVehicleStatus, "/vehicle/get_status", self._on_get_status)

        self._last_safety: SafetyStatus | None = None
        self._last_safety_time: float | None = None
        self._operator_sequence: int | None = None
        self._operator_enabled = False
        self._stall_guard = StallGuard(self._status_timeout)

        self._heartbeat = HeartbeatPublisher(self)
        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(f"vehicle interface up, backend='{backend}' (disabled until operator enable)")

    # ---------------------------------------------------------------- inputs
    def _latch_estop(self, now: float, reason: str) -> None:
        if not self._backend.get_status(now).emergency_stop_latched:
            self.get_logger().error(f"EMERGENCY STOP latched: {reason}")
        self._backend.emergency_stop(now, reason)

    def _on_command(self, msg: SafeMotionCommand) -> None:
        cmd = MotionCommand(msg.linear_velocity, msg.yaw_rate, to_seconds(msg.timestamp), msg.enable_motion)
        if not self._backend.submit_command(cmd, now_seconds(self)):
            self.get_logger().warn(
                f"rejected command: {getattr(self._backend, 'last_rejection', '')}", throttle_duration_sec=1.0
            )

    def _on_feedback(self, msg: TrackState) -> None:
        # Feedback age is measured on reception: the plant's own clock is not trusted.
        self._backend.on_feedback(
            VehicleFeedback(
                stamp=now_seconds(self),
                left_track_velocity=msg.left_track_velocity,
                right_track_velocity=msg.right_track_velocity,
                brake_engaged=msg.brake_engaged,
                emergency_brake_engaged=msg.emergency_brake_engaged,
            )
        )

    def _on_safety(self, msg: SafetyStatus) -> None:
        now = now_seconds(self)
        previous = self._last_safety.state if self._last_safety else None
        self._last_safety = msg
        self._last_safety_time = now
        if msg.state in LATCHING_SAFETY_STATES:
            if previous != msg.state:
                self._latch_estop(now, f"safety supervisor {msg.state_name}")
        elif msg.state == SafetyStatus.CONTROLLED_STOP and previous != msg.state:
            self._backend.request_stop(now, "safety supervisor CONTROLLED_STOP")

    def _on_watchdog_estop(self, msg: Bool) -> None:
        if msg.data:
            self._latch_estop(now_seconds(self), "watchdog emergency stop")

    def _on_operator(self, msg: OperatorState) -> None:
        if not self._follow_operator:
            return
        now = now_seconds(self)
        enabled = msg.state in OPERATOR_ENABLED_STATES
        new_request = self._operator_sequence is not None and msg.enable_sequence != self._operator_sequence
        if enabled and msg.state == OperatorState.AUTONOMY_ARMED and (new_request or not self._operator_enabled):
            ok, text = self._backend.enable(now)
            if ok:
                self.get_logger().info(f"operator enable -> vehicle enable: {text}")
            else:
                self.get_logger().warn(f"operator enable -> vehicle enable refused: {text}")
        elif not enabled and self._operator_enabled:
            self._backend.request_stop(now, "operator disabled autonomy")
        self._operator_sequence = msg.enable_sequence
        self._operator_enabled = enabled

    # -------------------------------------------------------------- services
    def _srv(self, fn):
        def handler(_request, response):
            response.success, response.message = fn(now_seconds(self))
            return response

        return handler

    def _estop_service(self, now: float):
        self._latch_estop(now, "emergency stop service")
        return True, "emergency stop latched"

    def _on_reset(self, request, response):
        if request.confirmation != "RESET":
            response.success, response.message = False, "confirmation must be 'RESET'"
            return response
        if self._last_safety is not None and self._last_safety.state in LATCHING_SAFETY_STATES:
            response.success, response.message = False, "reset the safety supervisor first"
            return response
        response.success, response.message = self._backend.reset_emergency_stop(now_seconds(self))
        self.get_logger().warn(f"E-stop reset by '{request.operator_id}': {response.message}")
        return response

    def _on_get_status(self, _request, response):
        response.status = self._status_msg(now_seconds(self))
        return response

    # ------------------------------------------------------------------ loop
    def _tick(self) -> None:
        if not clock_ready(self):
            return
        now = now_seconds(self)
        if self._stall_guard.should_defer(now):
            # This node stalled: queued supervisor status and feedback are not yet
            # processed, so they cannot be judged this tick. Brake for one cycle
            # instead of acting on anything old; normal checks resume next tick.
            self.get_logger().warn("vehicle interface stalled; holding for one cycle")
            self._backend.hold(now)
            self._status_pub.publish(self._status_msg(now))
            return
        supervisor_ok = self._last_safety_time is not None and (
            0.0 <= now - self._last_safety_time <= self._status_timeout
        )
        if not supervisor_ok:
            state = self._backend.get_status(now).state
            if state in (VehicleInterfaceState.ENABLED, VehicleInterfaceState.STOPPING):
                # Motion is possible: losing the supervisor is severe.
                self._latch_estop(now, "safety supervisor status stale")
            else:
                # Disabled: brakes are held and no enable is possible without a live
                # supervisor (operator flow requires it), so hold rather than latch.
                self._backend.hold(now)
                self._status_pub.publish(self._status_msg(now))
                return
        self._backend.update(now)
        self._status_pub.publish(self._status_msg(now))

    def _publish_sim_demand(self, request: ActuationRequest, now: float) -> None:
        msg = SimTrackDemand()
        msg.stamp = from_seconds(now)
        msg.left_track_velocity = request.left_track_velocity
        msg.right_track_velocity = request.right_track_velocity
        msg.service_brake = request.stop_mode == StopMode.SERVICE
        msg.emergency_brake = request.stop_mode == StopMode.EMERGENCY
        self._demand_pub.publish(msg)

    def _status_msg(self, now: float) -> VehicleStatus:
        s = self._backend.get_status(now)
        msg = VehicleStatus()
        msg.header.stamp = from_seconds(now)
        msg.header.frame_id = "base_link"
        msg.state = int(s.state)
        msg.state_name = s.state.name
        msg.backend = s.backend
        msg.ready = s.ready
        msg.enabled = s.enabled
        msg.emergency_stop_latched = s.emergency_stop_latched
        msg.brake_engaged = s.brake_engaged
        msg.stopped = s.stopped
        msg.measured_linear_velocity = s.measured_linear_velocity
        msg.measured_yaw_rate = s.measured_yaw_rate
        msg.left_track_velocity = s.left_track_velocity
        msg.right_track_velocity = s.right_track_velocity
        msg.commanded_linear_velocity = s.commanded_linear_velocity
        msg.commanded_yaw_rate = s.commanded_yaw_rate
        msg.command_age = s.command_age
        msg.feedback_age = s.feedback_age
        msg.rejected_command_count = s.rejected_command_count
        msg.faults = s.faults
        return msg


def main(args=None) -> None:
    run_node(VehicleInterfaceNode, args)
