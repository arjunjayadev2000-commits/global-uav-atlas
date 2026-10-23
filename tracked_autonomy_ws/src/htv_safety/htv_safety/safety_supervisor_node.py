"""Safety Supervisor node: the only consumer of /cmd_vel_nav.

Every input is freshness-checked; a stale or missing input counts as invalid.
The node gates the planner command (``/safety/gated_cmd``) and publishes
``/safety/status`` at a fixed rate, which downstream nodes also treat as the
supervisor heartbeat.
"""

from __future__ import annotations

from geometry_msgs.msg import Twist
from htv_common.heartbeat import HeartbeatPublisher
from htv_common.node_main import run_node
from htv_common.ros_time import clock_ready, from_seconds, now_seconds
from htv_common.stall_guard import StallGuard
from htv_common.topics import (
    CMD_VEL_NAV,
    ESTOP_INPUT,
    GATED_CMD,
    GEOFENCE_STATUS,
    GNSS_HEALTH,
    IMU_HEALTH,
    LIDAR_HEALTH,
    LOCALIZATION_HEALTH,
    OPERATOR_STATE,
    PERCEPTION_HEALTH,
    SAFETY_STATUS,
    VEHICLE_STATUS,
    WATCHDOG_STATUS,
)
from htv_interfaces.msg import (
    GeofenceStatus,
    LocalizationHealth,
    OperatorState,
    SafeMotionCommand,
    SafetyStatus,
    SubsystemHealth,
    TrackSlipEstimate,
    VehicleStatus,
    WatchdogStatus,
)
from htv_interfaces.srv import ResetEmergencyStop
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import Trigger

from .inputs import Tracked
from .state_machine import (
    SafetyInputs,
    SafetyState,
    SafetySupervisorStateMachine,
    SlipLevel,
    SupervisorConfig,
)

OPERATOR_ENABLED = (OperatorState.AUTONOMY_ARMED, OperatorState.AUTONOMOUS)


class SafetySupervisorNode(Node):
    def __init__(self) -> None:
        super().__init__("safety_supervisor")
        p = self.declare_parameter
        rate = p("rate", 20.0).value
        cmd_timeout = p("command_timeout", 0.5).value
        health_timeout = p("health_timeout", 1.0).value
        vehicle_timeout = p("vehicle_status_timeout", 0.5).value
        self._slip_required = p("slip_monitoring_required", False).value
        self._slip_high = p("slip_high_threshold", 0.25).value
        self._slip_excessive = p("slip_excessive_threshold", 0.45).value
        self._config = SupervisorConfig(
            min_initialization_time=p("min_initialization_time", 2.0).value,
            initialization_timeout=p("initialization_timeout", 30.0).value,
            degraded_speed_scale=p("degraded_speed_scale", 0.5).value,
            gnss_required=p("gnss_required", False).value,
        )
        self._self_test_ok, self._self_test_detail = self._self_test()

        self._sm = SafetySupervisorStateMachine(self._config)
        t = Tracked
        self._cmd = t(cmd_timeout)
        self._loc = t(health_timeout)
        self._perception = t(health_timeout)
        self._lidar = t(health_timeout)
        self._imu = t(health_timeout)
        self._gnss = t(health_timeout)
        self._watchdog = t(health_timeout)
        self._vehicle = t(vehicle_timeout)
        self._geofence = t(health_timeout)
        self._operator = t(health_timeout)
        self._slip = t(health_timeout)
        self._estop_latched_input = False

        sub = self.create_subscription
        sub(Twist, CMD_VEL_NAV, lambda m: self._cmd.set(m, now_seconds(self)), 10)
        sub(LocalizationHealth, LOCALIZATION_HEALTH, lambda m: self._loc.set(m, now_seconds(self)), 10)
        sub(SubsystemHealth, PERCEPTION_HEALTH, lambda m: self._perception.set(m, now_seconds(self)), 10)
        sub(SubsystemHealth, LIDAR_HEALTH, lambda m: self._lidar.set(m, now_seconds(self)), 10)
        sub(SubsystemHealth, IMU_HEALTH, lambda m: self._imu.set(m, now_seconds(self)), 10)
        sub(SubsystemHealth, GNSS_HEALTH, lambda m: self._gnss.set(m, now_seconds(self)), 10)
        sub(WatchdogStatus, WATCHDOG_STATUS, lambda m: self._watchdog.set(m, now_seconds(self)), 10)
        sub(VehicleStatus, VEHICLE_STATUS, lambda m: self._vehicle.set(m, now_seconds(self)), 10)
        sub(GeofenceStatus, GEOFENCE_STATUS, lambda m: self._geofence.set(m, now_seconds(self)), 10)
        sub(OperatorState, OPERATOR_STATE, lambda m: self._operator.set(m, now_seconds(self)), 10)
        sub(TrackSlipEstimate, "/vehicle/slip_estimate", lambda m: self._slip.set(m, now_seconds(self)), 10)
        sub(Bool, ESTOP_INPUT, self._on_estop, 10)

        self._status_pub = self.create_publisher(SafetyStatus, SAFETY_STATUS, 10)
        self._gated_pub = self.create_publisher(SafeMotionCommand, GATED_CMD, 10)
        self.create_service(ResetEmergencyStop, "/safety/reset_emergency_stop", self._on_reset)
        self.create_service(Trigger, "/safety/trigger_emergency_stop", self._on_trigger_estop)

        self._last_state: SafetyState | None = None
        self._last_status: SafetyStatus | None = None
        self._stall_guard = StallGuard(min(cmd_timeout, health_timeout, vehicle_timeout))
        self._heartbeat = HeartbeatPublisher(self, healthy=lambda: self._sm.state != SafetyState.FAULT)
        self.create_timer(1.0 / rate, self._tick)

    def _self_test(self) -> tuple[bool, str]:
        p = self.declare_parameter
        research = p("vehicle.research_speed_limit", 1.0).value
        physical = p("vehicle.max_vehicle_speed", 15.0).value
        hard_cap = p("research_speed_hard_cap", 2.0).value
        if research <= 0.0 or research > physical:
            return False, "research_speed_limit out of range"
        if research > hard_cap:
            return False, f"research_speed_limit {research} exceeds hard cap {hard_cap}"
        return True, "ok"

    def _on_estop(self, msg: Bool) -> None:
        if msg.data:
            self._estop_latched_input = True

    def _on_trigger_estop(self, _req, resp):
        self._estop_latched_input = True
        resp.success, resp.message = True, "emergency stop triggered"
        return resp

    def _on_reset(self, req, resp):
        confirmed = req.confirmation == "RESET" and bool(req.operator_id)
        # The E-stop input latch is cleared only by this explicit reset.
        previous_input = self._estop_latched_input
        self._estop_latched_input = False
        self._evaluate(now_seconds(self))
        resp.success, resp.message = self._sm.request_reset(confirmed)
        if not resp.success:
            self._estop_latched_input = previous_input
        self.get_logger().warn(f"reset request by '{req.operator_id}': {resp.message}")
        return resp

    # ------------------------------------------------------------------ core
    def _gather(self, now: float) -> SafetyInputs:
        def health(tracked: Tracked) -> bool:
            msg = tracked.get(now)
            return bool(msg is not None and msg.valid)

        loc = self._loc.get(now)
        vehicle = self._vehicle.get(now)
        geofence = self._geofence.get(now)
        operator = self._operator.get(now)
        watchdog = self._watchdog.get(now)
        slip_level = SlipLevel.NORMAL
        slip = self._slip.get(now)
        if slip is not None:
            worst = max(slip.left_slip, slip.right_slip)
            if slip.excessive or worst >= self._slip_excessive:
                slip_level = SlipLevel.EXCESSIVE
            elif worst >= self._slip_high:
                slip_level = SlipLevel.HIGH
        elif self._slip_required:
            slip_level = SlipLevel.EXCESSIVE

        return SafetyInputs(
            localization_valid=bool(loc is not None and loc.valid),
            perception_valid=health(self._perception),
            lidar_valid=health(self._lidar),
            imu_valid=health(self._imu),
            gnss_valid=health(self._gnss),
            compute_watchdog_ok=bool(watchdog is not None and watchdog.worst_severity < WatchdogStatus.SEVERITY_MAJOR),
            watchdog_critical=watchdog is None or watchdog.worst_severity >= WatchdogStatus.SEVERITY_CRITICAL,
            vehicle_interface_ready=bool(vehicle is not None and vehicle.ready),
            vehicle_interface_enabled=bool(vehicle is not None and vehicle.enabled),
            vehicle_interface_alive=vehicle is not None,
            vehicle_stopped=bool(vehicle is not None and vehicle.stopped),
            brake_ok=vehicle is None or not any("brake" in f for f in vehicle.faults),
            geofence_valid=bool(geofence is not None and geofence.valid),
            geofence_breached=bool(geofence is not None and geofence.breached),
            estop_active=self._estop_latched_input,
            operator_enable=bool(operator is not None and operator.state in OPERATOR_ENABLED),
            operator_enable_sequence=int(operator.enable_sequence) if operator is not None else 0,
            slip_level=slip_level,
            safety_self_test_ok=self._self_test_ok,
        )

    def _evaluate(self, now: float):
        try:
            return self._sm.update(self._gather(now), now)
        except Exception as exc:  # any internal error must fail safe
            self._sm.internal_fault(f"supervisor exception: {exc}")
            return self._sm.update(SafetyInputs(safety_self_test_ok=self._self_test_ok), now)

    def _tick(self) -> None:
        if not clock_ready(self):
            return
        now = now_seconds(self)
        if self._sm.state == SafetyState.POWER_OFF:
            self._sm.power_on(now)
        if self._stall_guard.should_defer(now) and self._last_status is not None:
            # This node itself stalled: inputs queued during the stall are not yet
            # processed. Hold the last state for one tick and command zero motion.
            self.get_logger().warn("supervisor stalled; deferring one evaluation")
            self._last_status.header.stamp = from_seconds(now)
            self._status_pub.publish(self._last_status)
            hold = SafeMotionCommand()
            hold.timestamp = from_seconds(now)
            hold.enable_motion = False
            self._gated_pub.publish(hold)
            return
        out = self._evaluate(now)
        if out.state != self._last_state:
            text = f"safety state -> {out.state.name} {out.reasons}"
            if out.state >= SafetyState.CONTROLLED_STOP:
                self.get_logger().warn(text)
            else:
                self.get_logger().info(text)
            self._last_state = out.state

        status = SafetyStatus()
        status.header.stamp = from_seconds(now)
        status.state = int(out.state)
        status.state_name = out.state.name
        status.motion_allowed = out.motion_allowed
        status.speed_scale = out.speed_scale
        status.emergency_stop_latched = out.state == SafetyState.EMERGENCY_STOP
        for key, value in out.entry_conditions.items():
            setattr(status, key, bool(value))
        reasons = list(out.reasons)
        if not self._self_test_ok:
            reasons.append(self._self_test_detail)
        status.reasons = reasons
        status.intervention_count = self._sm.intervention_count
        self._status_pub.publish(status)
        self._last_status = status

        gated = SafeMotionCommand()
        cmd = self._cmd.get(now)
        if out.motion_allowed and cmd is not None:
            gated.linear_velocity = float(cmd.linear.x)
            gated.yaw_rate = float(cmd.angular.z)
            # Carry the planner's reception time so staleness propagates downstream.
            gated.timestamp = from_seconds(self._cmd.received_at or now)
            gated.enable_motion = True
        else:
            gated.timestamp = from_seconds(now)
            gated.enable_motion = False
        self._gated_pub.publish(gated)


def main(args=None) -> None:
    run_node(SafetySupervisorNode, args)
