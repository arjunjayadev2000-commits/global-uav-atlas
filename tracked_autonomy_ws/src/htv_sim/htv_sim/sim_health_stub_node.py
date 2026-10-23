"""PHASE STUB - simulation only.

Publishes health for subsystems that do not exist yet in the current
development phase (localization before Phase 6, perception before Phase 9, and
sensor drivers before Phase 3), so the safety chain can be exercised end to end.
Each stub is removed when its real producer lands; the ``stubbed`` parameter
lists which ones are active.

Localization health is derived from ground-truth availability, not hard-coded:
if the simulator stops, localization becomes invalid.

``/sim/inject_failure`` toggles stubbed health to exercise the supervisor.
"""

from __future__ import annotations

from htv_common.node_main import run_node
from htv_common.ros_time import from_seconds, now_seconds
from htv_common.topics import (
    GNSS_HEALTH,
    GROUND_TRUTH_ODOM,
    IMU_HEALTH,
    LIDAR_HEALTH,
    LOCALIZATION_HEALTH,
    PERCEPTION_HEALTH,
)
from htv_interfaces.msg import LocalizationHealth, SubsystemHealth, TrackSlipEstimate
from htv_interfaces.srv import InjectFailure
from nav_msgs.msg import Odometry
from rclpy.node import Node

HEALTH_TOPICS = {
    "lidar": LIDAR_HEALTH,
    "imu": IMU_HEALTH,
    "gnss": GNSS_HEALTH,
    "perception": PERCEPTION_HEALTH,
}
FAILURES = {
    "gnss_loss": "gnss",
    "imu_loss": "imu",
    "lidar_loss": "lidar",
    "localization_divergence": "localization",
    "excessive_slip": "slip",
}


class SimHealthStubNode(Node):
    def __init__(self) -> None:
        super().__init__("sim_health_stub")
        p = self.declare_parameter
        self._stubbed = set(p("stubbed", ["lidar", "imu", "gnss", "perception", "localization"]).value)
        self._gt_timeout = p("ground_truth_timeout", 0.5).value
        self._failed: set[str] = set()
        self._last_gt: float | None = None
        self.create_subscription(Odometry, GROUND_TRUTH_ODOM, self._on_gt, 10)
        self._pubs = {
            name: self.create_publisher(SubsystemHealth, topic, 10)
            for name, topic in HEALTH_TOPICS.items()
            if name in self._stubbed
        }
        self._loc_pub = (
            self.create_publisher(LocalizationHealth, LOCALIZATION_HEALTH, 10) if "localization" in self._stubbed else None
        )
        self._slip_pub = self.create_publisher(TrackSlipEstimate, "/vehicle/slip_estimate", 10)
        self.create_service(InjectFailure, "/sim/inject_failure", self._on_inject)
        self.create_timer(1.0 / p("rate", 10.0).value, self._tick)
        self.get_logger().warn(f"PHASE STUB active for: {sorted(self._stubbed)} (simulation only)")

    def _on_gt(self, _msg: Odometry) -> None:
        self._last_gt = now_seconds(self)

    def _on_inject(self, req, resp):
        if req.failure == "clear_all":
            self._failed.clear()
            resp.success, resp.message = True, "all injected failures cleared"
            return resp
        target = FAILURES.get(req.failure)
        if target is None:
            resp.success = False
            resp.message = f"'{req.failure}' is not injectable by the phase stub; supported: {sorted(FAILURES)}"
            return resp
        if req.active:
            self._failed.add(target)
        else:
            self._failed.discard(target)
        resp.success, resp.message = True, f"{req.failure} {'active' if req.active else 'cleared'}"
        self.get_logger().warn(f"failure injection: {resp.message}")
        return resp

    def _tick(self) -> None:
        now = now_seconds(self)
        stamp = from_seconds(now)
        for name, pub in self._pubs.items():
            msg = SubsystemHealth()
            msg.header.stamp = stamp
            msg.name = name
            msg.valid = name not in self._failed
            msg.level = SubsystemHealth.LEVEL_OK if msg.valid else SubsystemHealth.LEVEL_ERROR
            msg.detail = "phase stub" if msg.valid else "injected failure"
            pub.publish(msg)
        if self._loc_pub is not None:
            gt_ok = self._last_gt is not None and now - self._last_gt <= self._gt_timeout
            loc = LocalizationHealth()
            loc.header.stamp = stamp
            loc.gnss_available = "gnss" not in self._failed
            loc.imu_available = "imu" not in self._failed
            loc.odometry_available = gt_ok
            diverged = "localization" in self._failed
            loc.valid = gt_ok and loc.imu_available and not diverged
            loc.position_uncertainty = 0.05 if loc.gnss_available else 0.8
            loc.heading_uncertainty = 0.01 if loc.imu_available else 0.5
            if diverged:
                loc.position_uncertainty = 25.0
            self._loc_pub.publish(loc)
        if "slip" in self._failed:
            slip = TrackSlipEstimate()
            slip.header.stamp = stamp
            slip.left_slip = slip.right_slip = 0.9
            slip.excessive = True
            self._slip_pub.publish(slip)


def main(args=None) -> None:
    run_node(SimHealthStubNode, args)
