"""Command Limiter node: /safety/gated_cmd -> /control/limited_cmd.

Applies research speed/yaw limits, the supervisor speed scale, the dynamic
stopping-distance speed cap, pivot-turn prevention and acceleration limits.
"""

from __future__ import annotations

import math

from htv_common.heartbeat import HeartbeatPublisher
from htv_common.node_main import run_node
from htv_common.ros_time import from_seconds, now_seconds
from htv_common.topics import (
    GATED_CMD,
    LIMITED_CMD,
    SAFETY_STATUS,
    STOPPING_DISTANCE,
    VEHICLE_STATUS,
)
from htv_interfaces.msg import SafeMotionCommand, SafetyStatus, StoppingDistance, VehicleStatus
from rclpy.node import Node

from .command_limiter import CommandLimiter, LimiterConfig
from .inputs import Tracked
from .stopping_distance import StoppingDistanceConfig, StoppingDistanceEstimator


class CommandLimiterNode(Node):
    def __init__(self) -> None:
        super().__init__("command_limiter")
        p = self.declare_parameter
        self._limiter = CommandLimiter(
            LimiterConfig(
                research_speed_limit=p("vehicle.research_speed_limit", 1.0).value,
                research_reverse_speed_limit=p("vehicle.research_reverse_speed_limit", 0.5).value,
                research_yaw_rate_limit=p("vehicle.research_yaw_rate_limit", 0.15).value,
                max_acceleration=p("limiter.max_acceleration", 0.3).value,
                max_deceleration=p("limiter.max_deceleration", 1.0).value,
                max_yaw_acceleration=p("limiter.max_yaw_acceleration", 0.15).value,
                allow_pivot_turns=p("limiter.allow_pivot_turns", False).value,
                min_turning_radius=p("limiter.min_turning_radius", 4.0).value,
                allow_reverse=p("limiter.allow_reverse", True).value,
            )
        )
        self._estimator = StoppingDistanceEstimator(
            StoppingDistanceConfig(
                max_deceleration=p("vehicle.max_deceleration", 1.5).value,
                command_latency=p("vehicle.command_latency", 0.25).value,
                braking_latency=p("vehicle.braking_latency", 0.40).value,
                reaction_time=p("stopping.reaction_time", 0.20).value,
                margin_fixed=p("stopping.margin_fixed", 1.0).value,
                margin_ratio=p("stopping.margin_ratio", 0.25).value,
                unknown_traction=p("stopping.unknown_traction", 0.35).value,
                unknown_slope=math.radians(p("stopping.unknown_slope_deg", -8.0).value),
                min_terrain_confidence=p("stopping.min_terrain_confidence", 0.3).value,
                unknown_terrain_speed=p("stopping.unknown_terrain_speed", 0.3).value,
                min_confidence_scale=p("stopping.min_confidence_scale", 0.4).value,
            )
        )
        # Phase 1-9: no terrain perception yet, so terrain defaults to UNKNOWN
        # (confidence 0) which selects the conservative branch of the estimator.
        self._traction = p("terrain.default_traction", 0.6).value
        self._slope = math.radians(p("terrain.default_slope_deg", 0.0).value)
        self._confidence = p("terrain.default_confidence", 0.0).value
        self._available = p("stopping.available_distance", 12.0).value

        self._status = Tracked(p("safety_status_timeout", 0.3).value)
        self._vehicle = Tracked(p("vehicle_status_timeout", 0.3).value)
        self.create_subscription(SafetyStatus, SAFETY_STATUS, lambda m: self._status.set(m, now_seconds(self)), 10)
        self.create_subscription(VehicleStatus, VEHICLE_STATUS, lambda m: self._vehicle.set(m, now_seconds(self)), 10)
        self.create_subscription(SafeMotionCommand, GATED_CMD, self._on_gated, 10)
        self._pub = self.create_publisher(SafeMotionCommand, LIMITED_CMD, 10)
        self._sd_pub = self.create_publisher(StoppingDistance, STOPPING_DISTANCE, 10)
        self._last_time: float | None = None
        self._heartbeat = HeartbeatPublisher(self)

    def _on_gated(self, msg: SafeMotionCommand) -> None:
        now = now_seconds(self)
        dt = 0.05 if self._last_time is None else min(0.2, max(0.0, now - self._last_time))
        self._last_time = now
        status = self._status.get(now)
        vehicle = self._vehicle.get(now)
        velocity = vehicle.measured_linear_velocity if vehicle is not None else 0.0

        cap = self._estimator.max_safe_velocity(self._available, self._traction, self._slope, self._confidence)
        est = self._estimator.estimate(velocity, self._traction, self._slope, self._confidence)
        self._publish_stopping(now, est, cap)

        out = SafeMotionCommand()
        out.timestamp = msg.timestamp
        if msg.enable_motion and status is not None and status.motion_allowed:
            v, w = self._limiter.limit(msg.linear_velocity, msg.yaw_rate, dt, status.speed_scale, cap)
            out.linear_velocity, out.yaw_rate, out.enable_motion = v, w, True
        else:
            self._limiter.reset()
            out.enable_motion = False
        self._pub.publish(out)

    def _publish_stopping(self, now: float, est, cap: float) -> None:
        msg = StoppingDistance()
        msg.header.stamp = from_seconds(now)
        msg.header.frame_id = "base_link"
        msg.velocity = est.velocity
        msg.reaction_distance = est.reaction_distance
        msg.braking_distance = est.braking_distance
        msg.safety_margin = est.safety_margin
        msg.stopping_distance = est.stopping_distance
        msg.effective_deceleration = est.effective_deceleration
        msg.terrain_slope = est.slope
        msg.traction_estimate = est.traction
        msg.terrain_confidence = est.confidence
        msg.available_distance = self._available
        msg.max_safe_velocity = cap
        self._sd_pub.publish(msg)


def main(args=None) -> None:
    run_node(CommandLimiterNode, args)
