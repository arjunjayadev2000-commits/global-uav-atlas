"""Simulation stack common to every phase: plant, vehicle interface and safety chain.

Command chain (no bypass exists):
  /cmd_vel_nav -> safety_supervisor -> /safety/gated_cmd -> command_limiter
  -> /control/limited_cmd -> motion_arbitration -> /safe_cmd_vel -> vehicle_interface
  -> /sim/track_demand -> tracked_vehicle_sim
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

RECORDED_TOPICS = [
    "/cmd_vel_nav", "/safety/gated_cmd", "/control/limited_cmd", "/safe_cmd_vel",
    "/safety/status", "/safety/stopping_distance", "/watchdog/status", "/geofence/status",
    "/autonomy/operator_state", "/vehicle/status", "/vehicle/track_feedback", "/sim/track_demand",
    "/ground_truth/odom", "/ground_truth/track_slip", "/localization/health", "/tf", "/tf_static",
]


def generate_launch_description():
    default_params = os.path.join(get_package_share_directory("htv_bringup"), "config", "simulation_safe.yaml")
    params = LaunchConfiguration("params_file")
    sim_time = LaunchConfiguration("use_sim_time")
    common = [params, {"use_sim_time": sim_time}]

    def node(package, executable, name, extra=None):
        return Node(
            package=package,
            executable=executable,
            name=name,
            output="screen",
            parameters=[*common, *(extra or [])],
        )

    return LaunchDescription([
        DeclareLaunchArgument("params_file", default_value=default_params),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        DeclareLaunchArgument("backend", default_value="headless", description="headless | gazebo"),
        DeclareLaunchArgument("use_phase_stubs", default_value="true"),
        DeclareLaunchArgument("record_bag", default_value="false"),
        DeclareLaunchArgument("bag_dir", default_value="bags/htv_run"),
        node("htv_sim", "tracked_vehicle_sim_node", "tracked_vehicle_sim",
             [{"backend": LaunchConfiguration("backend")}]),
        node("htv_vehicle_interface", "vehicle_interface_node", "vehicle_interface"),
        node("htv_safety", "safety_supervisor_node", "safety_supervisor"),
        node("htv_safety", "command_limiter_node", "command_limiter"),
        node("htv_safety", "motion_arbitration_node", "motion_arbitration"),
        node("htv_safety", "operator_mode_node", "operator_mode"),
        node("htv_safety", "watchdog_node", "watchdog"),
        node("htv_safety", "geofence_monitor_node", "geofence_monitor"),
        Node(
            package="htv_sim",
            executable="sim_health_stub_node",
            name="sim_health_stub",
            output="screen",
            parameters=common,
            condition=IfCondition(LaunchConfiguration("use_phase_stubs")),
        ),
        ExecuteProcess(
            cmd=["ros2", "bag", "record", "-o", LaunchConfiguration("bag_dir"), *RECORDED_TOPICS],
            output="screen",
            condition=IfCondition(LaunchConfiguration("record_bag")),
        ),
    ])
