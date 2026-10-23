"""Phase 1 system test: headless plant + vehicle interface + full safety chain.

Verifies, against the real launch file:
  * the ROS graph has a single non-bypassable command chain,
  * no motion without explicit operator enable (autonomy never self-enables),
  * enabled autonomy moves the vehicle within the conservative speed cap,
  * a stale planner command brings the vehicle to zero motion,
  * an injected safety-critical failure causes CONTROLLED_STOP and zero motion,
  * the emergency stop latches, survives the cause clearing, and only an explicit
    operator reset clears it, without re-enabling autonomy.
"""

import os
import time
import unittest

import launch
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from ament_index_python.packages import get_package_share_directory
from htv_bringup.graph_check import snapshot
from htv_bringup.graph_rules import violations
from htv_bringup.testing import Harness
from htv_interfaces.msg import SafetyStatus
from htv_interfaces.srv import InjectFailure, ResetEmergencyStop
from launch.launch_description_sources import PythonLaunchDescriptionSource
from std_msgs.msg import Bool

SPEED_CAP = 0.3  # stopping.unknown_terrain_speed in simulation_safe.yaml


@pytest.mark.launch_test
def generate_test_description():
    launch_file = os.path.join(get_package_share_directory("htv_bringup"), "launch", "phase1_headless.launch.py")
    return launch.LaunchDescription([
        launch.actions.IncludeLaunchDescription(PythonLaunchDescriptionSource(launch_file)),
        launch_testing.actions.ReadyToTest(),
    ])


class TestPhase1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.h = Harness()

    @classmethod
    def tearDownClass(cls):
        cls.h.shutdown()
        rclpy.shutdown()

    def wait_ready(self):
        h = self.h
        self.assertTrue(h.wait_for(lambda: h.state() == SafetyStatus.READY, 30.0), f"not READY: {h.safety}")

    def wait_stopped(self, timeout=20.0):
        h = self.h
        self.assertTrue(h.wait_for(lambda: h.speed() < 0.02, timeout), f"still moving: {h.speed()}")

    def test_01_graph_is_a_single_command_chain(self):
        h = self.h
        self.wait_ready()
        problems = []
        for _ in range(20):
            problems = violations(*snapshot(h.node))
            if not problems:
                break
            time.sleep(0.5)
        self.assertEqual(problems, [])

    def test_02_no_motion_without_operator_enable(self):
        h = self.h
        self.wait_ready()
        x0 = h.x()
        h.drive(0.8)
        time.sleep(4.0)
        self.assertLess(abs(h.x() - x0), 0.01)
        self.assertEqual(h.state(), SafetyStatus.READY)
        self.assertFalse(h.vehicle.enabled)

    def test_03_enabled_autonomy_moves_within_speed_cap(self):
        h = self.h
        h.drive(0.8)
        resp = h.enable()
        self.assertTrue(resp.success, resp.message)
        self.assertTrue(h.wait_for(lambda: h.state() == SafetyStatus.AUTONOMOUS, 10.0), str(h.safety))
        x0 = h.x()
        self.assertTrue(h.wait_for(lambda: h.x() - x0 > 0.5, 20.0), "vehicle did not move")
        time.sleep(3.0)
        self.assertLessEqual(h.max_speed, SPEED_CAP + 0.02)

    def test_04_stale_command_stops_vehicle(self):
        h = self.h
        h.stop_publishing()
        self.wait_stopped()
        # The supervisor stays AUTONOMOUS (idle), the vehicle holds zero motion.
        self.assertIn(h.state(), (SafetyStatus.AUTONOMOUS, SafetyStatus.DEGRADED))

    def test_05_lidar_loss_controlled_stop(self):
        h = self.h
        h.drive(0.8)
        self.assertTrue(h.wait_for(lambda: h.speed() > 0.1, 15.0))
        resp = h.call(InjectFailure, "/sim/inject_failure", InjectFailure.Request(failure="lidar_loss", active=True))
        self.assertTrue(resp.success)
        self.assertTrue(h.wait_for(lambda: h.state() == SafetyStatus.CONTROLLED_STOP, 5.0), str(h.safety))
        self.wait_stopped()
        h.call(InjectFailure, "/sim/inject_failure", InjectFailure.Request(failure="clear_all", active=False))
        # Never resumes by itself even with the cause cleared and commands flowing.
        time.sleep(3.0)
        self.assertLess(h.speed(), 0.02)
        self.assertNotIn(h.state(), (SafetyStatus.AUTONOMOUS, SafetyStatus.DEGRADED))

    def test_06_emergency_stop_latches_until_explicit_reset(self):
        h = self.h
        self.wait_ready()
        self.assertTrue(h.wait_for(lambda: h.enable().success, 15.0))
        self.assertTrue(h.wait_for(lambda: h.state() == SafetyStatus.AUTONOMOUS, 10.0))
        self.assertTrue(h.wait_for(lambda: h.speed() > 0.1, 15.0))
        h.estop_pub.publish(Bool(data=True))
        self.assertTrue(h.wait_for(lambda: h.state() == SafetyStatus.EMERGENCY_STOP, 3.0), str(h.safety))
        self.wait_stopped()
        self.assertTrue(h.wait_for(lambda: h.vehicle.emergency_stop_latched, 3.0))
        time.sleep(2.0)
        self.assertEqual(h.state(), SafetyStatus.EMERGENCY_STOP)
        self.assertFalse(h.enable().success)

        bad = h.call(ResetEmergencyStop, "/safety/reset_emergency_stop",
                     ResetEmergencyStop.Request(operator_id="test", confirmation="yes"))
        self.assertFalse(bad.success)
        ok = h.call(ResetEmergencyStop, "/safety/reset_emergency_stop",
                    ResetEmergencyStop.Request(operator_id="test", confirmation="RESET"))
        self.assertTrue(ok.success, ok.message)
        self.assertTrue(h.wait_for(lambda: h.state() != SafetyStatus.EMERGENCY_STOP, 2.0))
        time.sleep(0.5)  # let the vehicle interface observe the supervisor reset
        ok = h.call(ResetEmergencyStop, "/vehicle/reset_emergency_stop",
                    ResetEmergencyStop.Request(operator_id="test", confirmation="RESET"))
        self.assertTrue(ok.success, ok.message)
        self.wait_ready()
        # Reset does not re-enable autonomy: commands still flowing, vehicle stays still.
        time.sleep(3.0)
        self.assertLess(h.speed(), 0.02)
        h.stop_publishing()


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):
    def test_processes_exited_cleanly(self, proc_info):
        launch_testing.asserts.assertExitCodes(proc_info, allowable_exit_codes=[0, -2, -15, 2, 130])
