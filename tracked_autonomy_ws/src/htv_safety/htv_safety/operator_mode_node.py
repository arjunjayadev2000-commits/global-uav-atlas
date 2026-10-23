"""Operator-mode node: /autonomy/enable and /autonomy/disable services.

Autonomy never enables itself: the node starts in MANUAL and only the enable
service, called by a human operator, can arm it.
"""

from __future__ import annotations

from htv_common.heartbeat import HeartbeatPublisher
from htv_common.node_main import run_node
from htv_common.ros_time import from_seconds, now_seconds
from htv_common.topics import (
    AUTONOMY_DISABLE,
    AUTONOMY_ENABLE,
    OPERATOR_STATE,
    SAFETY_STATUS,
    VEHICLE_STATUS,
)
from htv_interfaces.msg import OperatorState, SafetyStatus, VehicleStatus
from rclpy.node import Node
from std_srvs.srv import Trigger

from .inputs import Tracked
from .operator_mode import OperatorModeStateMachine
from .state_machine import SafetyState


class OperatorModeNode(Node):
    def __init__(self) -> None:
        super().__init__("operator_mode")
        p = self.declare_parameter
        self._sm = OperatorModeStateMachine(arm_timeout=p("arm_timeout", 10.0).value)
        self._status = Tracked(p("safety_status_timeout", 0.5).value)
        self._vehicle = Tracked(p("vehicle_status_timeout", 0.5).value)
        self.create_subscription(SafetyStatus, SAFETY_STATUS, lambda m: self._status.set(m, now_seconds(self)), 10)
        self.create_subscription(VehicleStatus, VEHICLE_STATUS, lambda m: self._vehicle.set(m, now_seconds(self)), 10)
        self._pub = self.create_publisher(OperatorState, OPERATOR_STATE, 10)
        self.create_service(Trigger, AUTONOMY_ENABLE, self._on_enable)
        self.create_service(Trigger, AUTONOMY_DISABLE, self._on_disable)
        self._heartbeat = HeartbeatPublisher(self)
        self.create_timer(1.0 / p("rate", 10.0).value, self._tick)
        self.get_logger().info("operator mode MANUAL; autonomy requires an explicit /autonomy/enable")

    def _safety(self, now: float) -> SafetyState | None:
        msg = self._status.get(now)
        return SafetyState(msg.state) if msg is not None else None

    def _stopped(self, now: float) -> bool:
        msg = self._vehicle.get(now)
        return bool(msg is not None and msg.stopped)

    def _on_enable(self, _req, resp):
        now = now_seconds(self)
        resp.success, resp.message = self._sm.request_enable(now, self._safety(now), self._stopped(now))
        self.get_logger().info(f"/autonomy/enable: {resp.message}")
        self._publish(now)
        return resp

    def _on_disable(self, _req, resp):
        resp.success, resp.message = self._sm.request_disable()
        self.get_logger().info(f"/autonomy/disable: {resp.message}")
        self._publish(now_seconds(self))
        return resp

    def _tick(self) -> None:
        now = now_seconds(self)
        self._sm.update(now, self._safety(now), self._stopped(now))
        self._publish(now)

    def _publish(self, now: float) -> None:
        msg = OperatorState()
        msg.header.stamp = from_seconds(now)
        msg.state = int(self._sm.mode)
        msg.state_name = self._sm.mode.name
        msg.operator_enable = self._sm.operator_enable
        msg.enable_sequence = self._sm.enable_sequence
        self._pub.publish(msg)


def main(args=None) -> None:
    run_node(OperatorModeNode, args)
