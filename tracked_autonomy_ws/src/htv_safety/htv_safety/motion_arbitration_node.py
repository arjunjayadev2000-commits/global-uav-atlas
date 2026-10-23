"""Motion Arbitration node: the ONLY publisher of /safe_cmd_vel.

Selects among command sources by priority. In this phase there is a single
source (the limited autonomy command). Independently of upstream gating it
re-checks the safety status, so a fault anywhere upstream still yields a stop.
"""

from __future__ import annotations

from htv_common.heartbeat import HeartbeatPublisher
from htv_common.node_main import run_node
from htv_common.ros_time import from_seconds, now_seconds, to_seconds
from htv_common.topics import LIMITED_CMD, SAFE_CMD_VEL, SAFETY_STATUS
from htv_interfaces.msg import SafeMotionCommand, SafetyStatus
from rclpy.node import Node

from .inputs import Tracked


class MotionArbitrationNode(Node):
    def __init__(self) -> None:
        super().__init__("motion_arbitration")
        p = self.declare_parameter
        rate = p("rate", 20.0).value
        self._cmd_timeout = p("command_timeout", 0.3).value
        # Sources in descending priority. Additional sources (e.g. a supervised
        # teleoperation source) must also be produced downstream of the supervisor.
        topics = p("source_topics", [LIMITED_CMD]).value
        self._sources: list[tuple[str, Tracked]] = []
        for topic in topics:
            tracked = Tracked(self._cmd_timeout)
            self.create_subscription(
                SafeMotionCommand, topic, lambda m, t=tracked: t.set(m, now_seconds(self)), 10
            )
            self._sources.append((topic, tracked))
        self._status = Tracked(p("safety_status_timeout", 0.3).value)
        self.create_subscription(SafetyStatus, SAFETY_STATUS, lambda m: self._status.set(m, now_seconds(self)), 10)
        self._pub = self.create_publisher(SafeMotionCommand, SAFE_CMD_VEL, 10)
        self._heartbeat = HeartbeatPublisher(self)
        self.create_timer(1.0 / rate, self._tick)

    def _select(self, now: float) -> SafeMotionCommand | None:
        for _topic, tracked in self._sources:
            msg = tracked.get(now)
            if msg is not None and msg.enable_motion and now - to_seconds(msg.timestamp) <= self._cmd_timeout:
                return msg
        return None

    def _tick(self) -> None:
        now = now_seconds(self)
        status = self._status.get(now)
        out = SafeMotionCommand()
        chosen = self._select(now) if (status is not None and status.motion_allowed) else None
        if chosen is not None:
            out.linear_velocity = chosen.linear_velocity
            out.yaw_rate = chosen.yaw_rate
            out.timestamp = chosen.timestamp
            out.enable_motion = True
        else:
            out.timestamp = from_seconds(now)
            out.enable_motion = False
        self._pub.publish(out)


def main(args=None) -> None:
    run_node(MotionArbitrationNode, args)
