"""Heartbeat publisher used by every node monitored by the watchdog."""

from __future__ import annotations

from collections.abc import Callable

from htv_interfaces.msg import Heartbeat
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from .ros_time import from_seconds, now_seconds
from .topics import HEARTBEAT

HEARTBEAT_QOS = QoSProfile(depth=50, reliability=ReliabilityPolicy.RELIABLE)


class HeartbeatPublisher:
    def __init__(self, node: Node, period: float = 0.2, healthy: Callable[[], bool] | None = None) -> None:
        self._node = node
        self._healthy = healthy or (lambda: True)
        self._seq = 0
        self._pub = node.create_publisher(Heartbeat, HEARTBEAT, HEARTBEAT_QOS)
        self._timer = node.create_timer(period, self._tick)

    def _tick(self) -> None:
        self._seq += 1
        msg = Heartbeat()
        msg.stamp = from_seconds(now_seconds(self._node))
        msg.node_name = self._node.get_name()
        msg.sequence = self._seq
        msg.healthy = bool(self._healthy())
        self._pub.publish(msg)
