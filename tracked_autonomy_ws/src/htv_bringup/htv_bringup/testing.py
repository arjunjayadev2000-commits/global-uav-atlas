"""Test harness shared by the system-level launch tests."""

from __future__ import annotations

import math
import threading
import time

import rclpy
from geometry_msgs.msg import Twist
from htv_interfaces.msg import SafetyStatus, VehicleStatus
from nav_msgs.msg import Odometry
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


class Harness:
    def __init__(self):
        self.node = rclpy.create_node("htv_test_harness")
        self.safety: SafetyStatus | None = None
        self.vehicle: VehicleStatus | None = None
        self.odom: Odometry | None = None
        self.max_speed = 0.0
        self.node.create_subscription(SafetyStatus, "/safety/status", self._on_safety, 10)
        self.node.create_subscription(VehicleStatus, "/vehicle/status", self._on_vehicle, 10)
        self.node.create_subscription(Odometry, "/ground_truth/odom", self._on_odom, 10)
        self.cmd_pub = self.node.create_publisher(Twist, "/cmd_vel_nav", 10)
        self.estop_pub = self.node.create_publisher(Bool, "/safety/estop", 10)
        self.command: Twist | None = None
        self.node.create_timer(0.1, self._publish_cmd)
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        self._thread = threading.Thread(target=self.executor.spin, daemon=True)
        self._thread.start()

    def _on_safety(self, msg):
        self.safety = msg

    def _on_vehicle(self, msg):
        self.vehicle = msg

    def _on_odom(self, msg):
        self.odom = msg
        self.max_speed = max(self.max_speed, abs(msg.twist.twist.linear.x))

    def _publish_cmd(self):
        if self.command is not None:
            self.cmd_pub.publish(self.command)

    def drive(self, v, w=0.0):
        cmd = Twist()
        cmd.linear.x, cmd.angular.z = v, w
        self.command = cmd

    def stop_publishing(self):
        self.command = None

    def wait_for(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return predicate()

    def state(self):
        return self.safety.state if self.safety else None

    def speed(self):
        return abs(self.odom.twist.twist.linear.x) if self.odom else math.inf

    def x(self):
        return self.odom.pose.pose.position.x if self.odom else 0.0

    def call(self, srv_type, name, request, timeout=5.0):
        client = self.node.create_client(srv_type, name)
        assert client.wait_for_service(timeout_sec=timeout), f"{name} unavailable"
        future = client.call_async(request)
        assert self.wait_for(future.done, timeout), f"{name} timed out"
        return future.result()

    def enable(self):
        return self.call(Trigger, "/autonomy/enable", Trigger.Request())

    def shutdown(self):
        self.executor.shutdown()
        self._thread.join(timeout=5.0)
        self.node.destroy_node()
