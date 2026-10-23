"""Independent heartbeat watchdog.

Monitors /system/heartbeat for a configured set of nodes, each with a severity:

* critical -> /watchdog/status CRITICAL; if the node was alive and then went
  silent or unhealthy, also /safety/watchdog_estop (the vehicle interface latches
  an emergency stop directly, even if the supervisor itself is dead);
* major    -> supervisor performs a controlled stop;
* minor    -> reported only.

A node that never started is reported through ``worst_severity`` only; the
supervisor's INITIALIZING gate (and its timeout into FAULT) handles start-up.
"""

from __future__ import annotations

from htv_common.heartbeat import HEARTBEAT_QOS
from htv_common.node_main import run_node
from htv_common.ros_time import clock_ready, from_seconds, now_seconds
from htv_common.topics import HEARTBEAT, WATCHDOG_ESTOP, WATCHDOG_STATUS
from htv_interfaces.msg import Heartbeat, WatchdogStatus
from rclpy.node import Node
from std_msgs.msg import Bool

from .heartbeat_monitor import SEVERITY_NAMES, HeartbeatMonitor


class WatchdogNode(Node):
    def __init__(self) -> None:
        super().__init__("watchdog")
        p = self.declare_parameter
        names = list(p("monitored_nodes", ["safety_supervisor", "vehicle_interface"]).value)
        severities = list(p("monitored_severities", ["critical", "critical"]).value)
        if len(names) != len(severities):
            raise ValueError("monitored_nodes and monitored_severities must have equal length")
        unknown = [s for s in severities if s not in SEVERITY_NAMES]
        if unknown:
            raise ValueError(f"unknown severities {unknown}; use {sorted(SEVERITY_NAMES)}")
        self._monitor = HeartbeatMonitor(
            {n: SEVERITY_NAMES[s] for n, s in zip(names, severities, strict=True)},
            timeout=p("heartbeat_timeout", 0.6).value,
            startup_grace=p("startup_grace", 5.0).value,
        )
        self.create_subscription(Heartbeat, HEARTBEAT, self._on_heartbeat, HEARTBEAT_QOS)
        self._status_pub = self.create_publisher(WatchdogStatus, WATCHDOG_STATUS, 10)
        self._estop_pub = self.create_publisher(Bool, WATCHDOG_ESTOP, 10)
        self.create_timer(1.0 / p("rate", 10.0).value, self._tick)

    def _on_heartbeat(self, msg: Heartbeat) -> None:
        self._monitor.beat(msg.node_name, msg.healthy, now_seconds(self))

    def _tick(self) -> None:
        if not clock_ready(self):
            return
        now = now_seconds(self)
        report = self._monitor.evaluate(now)
        if report.deferred:
            self.get_logger().warn("watchdog stalled; deferring one evaluation", throttle_duration_sec=2.0)
        msg = WatchdogStatus()
        msg.header.stamp = from_seconds(now)
        msg.ok = not report.stale
        msg.worst_severity = int(report.worst)
        msg.stale_nodes = report.stale
        msg.monitored_nodes = list(self._monitor.severities)
        self._status_pub.publish(msg)
        self._estop_pub.publish(Bool(data=report.lost_critical))
        if report.stale:
            self.get_logger().warn(f"stale heartbeats: {report.stale}", throttle_duration_sec=2.0)


def main(args=None) -> None:
    run_node(WatchdogNode, args)
