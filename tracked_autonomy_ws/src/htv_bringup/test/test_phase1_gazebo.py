"""Phase 1 system test in Gazebo Harmonic (server only, no rendering sensors).

Spawns the heavy tracked vehicle model into the flat test track and checks that
the model, bridge, TF tree and safety chain come up, that the vehicle only moves
after operator enable, and that an emergency stop brings it to rest in Gazebo.
Skipped where Gazebo is not installed.
"""

import os
import shutil
import time
import unittest

import launch
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from ament_index_python.packages import get_package_share_directory
from htv_bringup.testing import Harness
from htv_interfaces.msg import SafetyStatus
from launch.launch_description_sources import PythonLaunchDescriptionSource
from std_msgs.msg import Bool
from tf2_ros import Buffer, TransformListener

pytestmark = pytest.mark.skipif(shutil.which("gz") is None, reason="Gazebo (gz) not installed")

REQUIRED_FRAMES = ["base_link", "imu_link", "gnss_link", "lidar_link", "front_camera_link", "rear_camera_link"]


@pytest.mark.launch_test
def generate_test_description():
    launch_file = os.path.join(get_package_share_directory("htv_bringup"), "launch", "phase1_gazebo.launch.py")
    return launch.LaunchDescription([
        launch.actions.IncludeLaunchDescription(
            PythonLaunchDescriptionSource(launch_file),
            launch_arguments={
                "headless": "true",
                "rendering_sensors": "false",
                # Headroom for loaded CI machines: sim time runs at half real time.
                "real_time_factor": "0.5",
                "world": "01_flat_test_track",
            }.items(),
        ),
        launch_testing.actions.ReadyToTest(),
    ])


class TestPhase1Gazebo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.h = Harness()
        cls.tf_buffer = Buffer()
        cls.tf_listener = TransformListener(cls.tf_buffer, cls.h.node)

    @classmethod
    def tearDownClass(cls):
        cls.h.shutdown()
        rclpy.shutdown()

    def test_01_comes_up_ready_with_ground_truth(self):
        h = self.h
        self.assertTrue(h.wait_for(lambda: h.odom is not None, 60.0), "no ground truth from Gazebo")
        self.assertTrue(h.wait_for(lambda: h.state() == SafetyStatus.READY, 60.0), str(h.safety))

    def test_02_tf_tree_contains_sensor_frames(self):
        missing = []
        for frame in REQUIRED_FRAMES:
            ok = self.h.wait_for(lambda f=frame: self.tf_buffer.can_transform("odom", f, rclpy.time.Time()), 15.0)
            if not ok:
                missing.append(frame)
        self.assertEqual(missing, [])

    def test_03_moves_only_after_enable_and_estop_stops(self):
        h = self.h
        x0 = h.x()
        h.drive(0.8)
        time.sleep(3.0)
        self.assertLess(abs(h.x() - x0), 0.05)
        self.assertTrue(h.wait_for(lambda: h.enable().success, 15.0))
        self.assertTrue(h.wait_for(lambda: h.state() == SafetyStatus.AUTONOMOUS, 15.0), str(h.safety))
        self.assertTrue(h.wait_for(lambda: h.x() - x0 > 0.5, 40.0), f"vehicle did not move in Gazebo: {h.x()}")
        h.estop_pub.publish(Bool(data=True))
        self.assertTrue(h.wait_for(lambda: h.state() == SafetyStatus.EMERGENCY_STOP, 5.0))
        self.assertTrue(h.wait_for(lambda: h.speed() < 0.02, 30.0), f"still moving: {h.speed()}")
        h.stop_publishing()
