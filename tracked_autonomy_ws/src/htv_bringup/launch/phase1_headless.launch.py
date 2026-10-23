"""PHASE 1 (headless): vehicle model + track dynamics + safety chain, no Gazebo.

    ros2 launch htv_bringup phase1_headless.launch.py
    ros2 service call /autonomy/enable std_srvs/srv/Trigger
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    bringup = get_package_share_directory("htv_bringup")
    description = get_package_share_directory("htv_description")
    return LaunchDescription([
        DeclareLaunchArgument("params_file", default_value=os.path.join(bringup, "config", "simulation_safe.yaml")),
        DeclareLaunchArgument("record_bag", default_value="false"),
        DeclareLaunchArgument("bag_dir", default_value="bags/phase1_headless"),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(description, "launch", "description.launch.py")),
            launch_arguments={"use_gazebo": "false", "use_sim_time": "false"}.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(bringup, "launch", "sim_stack.launch.py")),
            launch_arguments={
                "backend": "headless",
                "use_sim_time": "false",
                "params_file": LaunchConfiguration("params_file"),
                "record_bag": LaunchConfiguration("record_bag"),
                "bag_dir": LaunchConfiguration("bag_dir"),
            }.items(),
        ),
    ])
