"""Start Gazebo Harmonic with an HTV test world and spawn the vehicle model.

    ros2 launch htv_gazebo gazebo_world.launch.py world:=02_obstacle_course headless:=true
"""

import os
import re
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    OpaqueFunction,
    RegisterEventHandler,
    SetEnvironmentVariable,
)
from launch.event_handlers import OnShutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

WORLDS = (
    "01_flat_test_track",
    "02_obstacle_course",
    "03_rough_terrain",
    "04_slope_course",
    "05_gnss_degraded_course",
)


def _gazebo(context):
    share = get_package_share_directory("htv_gazebo")
    world = LaunchConfiguration("world").perform(context)
    if world not in WORLDS and not world.endswith(".sdf"):
        raise RuntimeError(f"unknown world '{world}', choose one of {WORLDS}")
    path = world if world.endswith(".sdf") else os.path.join(share, "worlds", world + ".sdf")
    headless = LaunchConfiguration("headless").perform(context).lower() == "true"
    rendering = LaunchConfiguration("rendering_sensors").perform(context).lower() == "true"
    rtf = float(LaunchConfiguration("real_time_factor").perform(context))
    if not rendering or rtf != 1.0:
        with open(path, encoding="utf-8") as handle:
            sdf = handle.read()
        if not rendering:
            # Without a GPU/OpenGL the ogre2 Sensors system cannot start. Strip it so
            # physics, IMU, NavSat and odometry still run (cameras/LiDAR stay silent).
            sdf = re.sub(r"<plugin filename=\"gz-sim-sensors-system\".*?</plugin>", "", sdf, flags=re.S)
        # Sim time advances regardless of ROS node scheduling; on an overloaded
        # machine (e.g. CI) a lower real-time factor gives the stack headroom.
        sdf = re.sub(r"<real_time_factor>[^<]*</real_time_factor>", f"<real_time_factor>{rtf}</real_time_factor>", sdf)
        fd, path = tempfile.mkstemp(prefix=f"{os.path.basename(world)}_", suffix=".sdf")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(sdf)
    gz_args = f"-r {'-s --headless-rendering ' if headless else ''}{path}"
    ros_gz_sim = get_package_share_directory("ros_gz_sim")
    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(ros_gz_sim, "launch", "gz_sim.launch.py")),
            launch_arguments={"gz_args": gz_args, "on_exit_shutdown": "true"}.items(),
        ),
        # The gz ruby wrapper does not forward SIGINT to the server it spawns, which
        # leaves an orphan publishing /clock. Stop the server for this world file.
        RegisterEventHandler(
            OnShutdown(on_shutdown=[ExecuteProcess(cmd=["pkill", "-INT", "-f", f"gz sim .*{re.escape(path)}"])])
        ),
    ]


def generate_launch_description():
    share = get_package_share_directory("htv_gazebo")
    description_share = get_package_share_directory("htv_description")
    return LaunchDescription([
        DeclareLaunchArgument("world", default_value="01_flat_test_track"),
        DeclareLaunchArgument("headless", default_value="false"),
        DeclareLaunchArgument(
            "rendering_sensors", default_value="true",
            description="false = no cameras/GPU LiDAR (for machines without OpenGL, e.g. CI)",
        ),
        DeclareLaunchArgument("real_time_factor", default_value="1.0"),
        DeclareLaunchArgument("spawn_x", default_value="0.0"),
        DeclareLaunchArgument("spawn_y", default_value="0.0"),
        DeclareLaunchArgument("spawn_yaw", default_value="0.0"),
        DeclareLaunchArgument("enable_secondary_lidar", default_value="false"),
        SetEnvironmentVariable(
            "GZ_SIM_RESOURCE_PATH",
            os.pathsep.join(filter(None, [os.path.dirname(description_share), os.environ.get("GZ_SIM_RESOURCE_PATH", "")])),
        ),
        OpaqueFunction(function=_gazebo),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(description_share, "launch", "description.launch.py")),
            launch_arguments={
                "use_gazebo": "true",
                "use_sim_time": "true",
                "enable_secondary_lidar": LaunchConfiguration("enable_secondary_lidar"),
            }.items(),
        ),
        Node(
            package="ros_gz_sim",
            executable="create",
            arguments=[
                "-name", "htv", "-topic", "robot_description",
                "-x", LaunchConfiguration("spawn_x"), "-y", LaunchConfiguration("spawn_y"), "-z", "0.05",
                "-Y", LaunchConfiguration("spawn_yaw"),
            ],
            output="screen",
        ),
        Node(
            package="ros_gz_bridge",
            executable="parameter_bridge",
            name="gz_bridge",
            parameters=[{"config_file": os.path.join(share, "config", "gz_bridge.yaml"), "use_sim_time": True}],
            output="screen",
        ),
    ])
