"""robot_state_publisher for the HTV description (sensor mounts configurable via xacro args)."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    share = FindPackageShare("htv_description")
    args = [
        DeclareLaunchArgument("use_gazebo", default_value="false"),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        DeclareLaunchArgument("enable_secondary_lidar", default_value="false"),
        DeclareLaunchArgument(
            "sensor_config", default_value=PathJoinSubstitution([share, "config", "sensor_mounts.yaml"])
        ),
    ]
    robot_description = ParameterValue(
        Command([
            "xacro ", PathJoinSubstitution([share, "urdf", "htv.urdf.xacro"]),
            " use_gazebo:=", LaunchConfiguration("use_gazebo"),
            " enable_secondary_lidar:=", LaunchConfiguration("enable_secondary_lidar"),
            " sensor_config:=", LaunchConfiguration("sensor_config"),
        ]),
        value_type=str,
    )
    rsp = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[{
            "robot_description": robot_description,
            "use_sim_time": LaunchConfiguration("use_sim_time"),
        }],
    )
    return LaunchDescription([*args, rsp])
