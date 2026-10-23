"""PHASE 1 (Gazebo): spawn the heavy tracked vehicle model into a test world.

    ros2 launch htv_bringup phase1_gazebo.launch.py world:=01_flat_test_track headless:=false
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    bringup = get_package_share_directory("htv_bringup")
    gazebo = get_package_share_directory("htv_gazebo")
    return LaunchDescription([
        DeclareLaunchArgument("world", default_value="01_flat_test_track"),
        DeclareLaunchArgument("headless", default_value="false"),
        DeclareLaunchArgument("rendering_sensors", default_value="true"),
        DeclareLaunchArgument("real_time_factor", default_value="1.0"),
        DeclareLaunchArgument("params_file", default_value=os.path.join(bringup, "config", "simulation_safe.yaml")),
        DeclareLaunchArgument("record_bag", default_value="false"),
        DeclareLaunchArgument("bag_dir", default_value="bags/phase1_gazebo"),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(gazebo, "launch", "gazebo_world.launch.py")),
            launch_arguments={
                "world": LaunchConfiguration("world"),
                "headless": LaunchConfiguration("headless"),
                "rendering_sensors": LaunchConfiguration("rendering_sensors"),
                "real_time_factor": LaunchConfiguration("real_time_factor"),
            }.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(bringup, "launch", "sim_stack.launch.py")),
            launch_arguments={
                "backend": "gazebo",
                "use_sim_time": "true",
                "params_file": LaunchConfiguration("params_file"),
                "record_bag": LaunchConfiguration("record_bag"),
                "bag_dir": LaunchConfiguration("bag_dir"),
            }.items(),
        ),
    ])
