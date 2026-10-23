"""Geofence monitor: checks the inflated vehicle footprint against a polygon fence."""

from __future__ import annotations

import math

from htv_common.heartbeat import HeartbeatPublisher
from htv_common.node_main import run_node
from htv_common.ros_time import from_seconds, now_seconds
from htv_common.topics import GEOFENCE_STATUS, GROUND_TRUTH_ODOM
from htv_interfaces.msg import GeofenceStatus
from nav_msgs.msg import Odometry
from rclpy.node import Node

from .geometry import footprint_clearance, inflate_convex_polygon, parse_polygon, transform_polygon
from .inputs import Tracked

DEFAULT_FENCE = [-50.0, -50.0, 150.0, -50.0, 150.0, 50.0, -50.0, 50.0]
DEFAULT_FOOTPRINT = [3.75, 1.70, -3.75, 1.70, -3.75, -1.70, 3.75, -1.70]


class GeofenceMonitorNode(Node):
    def __init__(self) -> None:
        super().__init__("geofence_monitor")
        p = self.declare_parameter
        self._fence = parse_polygon(p("geofence.polygon", DEFAULT_FENCE).value)
        self._name = p("geofence.name", "sim_test_area").value
        self._soft_margin = p("geofence.soft_margin", 5.0).value
        footprint = parse_polygon(p("footprint.nominal", DEFAULT_FOOTPRINT).value)
        self._footprint = inflate_convex_polygon(footprint, p("footprint.safety_inflation", 0.5).value)
        # Phase 1-5 use ground truth; from Phase 6 this is /odometry/filtered.
        topic = p("pose_topic", GROUND_TRUTH_ODOM).value
        self._pose = Tracked(p("pose_timeout", 0.5).value)
        self.create_subscription(Odometry, topic, lambda m: self._pose.set(m, now_seconds(self)), 10)
        self._pub = self.create_publisher(GeofenceStatus, GEOFENCE_STATUS, 10)
        self._heartbeat = HeartbeatPublisher(self)
        self.create_timer(1.0 / p("rate", 10.0).value, self._tick)

    def _tick(self) -> None:
        now = now_seconds(self)
        msg = GeofenceStatus()
        msg.header.stamp = from_seconds(now)
        msg.header.frame_id = "odom"
        msg.fence_name = self._name
        odom = self._pose.get(now)
        if odom is None:
            # Unknown position: not valid, but not proof of a breach either.
            msg.valid, msg.breached, msg.distance_to_boundary = False, False, float("nan")
        else:
            pose = odom.pose.pose
            q = pose.orientation
            yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
            world = transform_polygon(self._footprint, pose.position.x, pose.position.y, yaw)
            clearance = footprint_clearance(world, self._fence)
            msg.distance_to_boundary = clearance
            msg.breached = clearance < 0.0
            msg.valid = clearance >= self._soft_margin
        self._pub.publish(msg)


def main(args=None) -> None:
    run_node(GeofenceMonitorNode, args)
