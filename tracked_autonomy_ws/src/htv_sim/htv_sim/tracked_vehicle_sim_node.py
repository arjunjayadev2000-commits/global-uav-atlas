"""Simulated tracked-vehicle plant.

Consumes ``/sim/track_demand`` (from SimulatedLegacyTrackedVehicleInterface) and
runs :class:`htv_dynamics.TrackedVehicleModel`. Two backends:

* ``headless`` - the model integrates the pose itself (fast, CI-friendly);
* ``gazebo``   - the model's realised body velocity (with slip, lag, skid) is
  sent to Gazebo's VelocityControl system; Gazebo provides pose, collisions,
  terrain and sensors, and the terrain pitch reported by Gazebo feeds back into
  the model's slope term.

Publishes track feedback (encoder-like), ground-truth odometry and ground-truth
slip. Ground truth is for evaluation only and must never feed autonomy.
"""

from __future__ import annotations

import math

from geometry_msgs.msg import TransformStamped, Twist
from htv_common.node_main import run_node
from htv_common.ros_time import clock_ready, from_seconds, now_seconds
from htv_common.topics import GROUND_TRUTH_ODOM, GROUND_TRUTH_SLIP, SIM_TRACK_DEMAND, TRACK_FEEDBACK
from htv_dynamics import TrackDemand, TrackedVehicleModel, TrackedVehicleParams
from htv_interfaces.msg import SimTrackDemand, TrackSlipEstimate, TrackState
from nav_msgs.msg import Odometry
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from tf2_ros import TransformBroadcaster

PARAM_PREFIX = "vehicle."
RUNTIME_TERRAIN_PARAMS = {"vehicle.terrain_friction", "vehicle.terrain_slope"}


def yaw_to_quaternion(yaw: float) -> tuple[float, float, float, float]:
    return 0.0, 0.0, math.sin(0.5 * yaw), math.cos(0.5 * yaw)


def quaternion_pitch(q) -> float:
    s = 2.0 * (q.w * q.y - q.z * q.x)
    return math.asin(max(-1.0, min(1.0, s)))


class TrackedVehicleSimNode(Node):
    def __init__(self) -> None:
        super().__init__("tracked_vehicle_sim")
        p = self.declare_parameter
        defaults = TrackedVehicleParams().to_dict()
        values = {name: p(PARAM_PREFIX + name, value).value for name, value in defaults.items()}
        self._model = TrackedVehicleModel(TrackedVehicleParams.from_dict(values))
        self._backend = p("backend", "headless").value
        if self._backend not in ("headless", "gazebo"):
            raise ValueError("backend must be 'headless' or 'gazebo'")
        self._rate = p("physics_rate", 100.0).value
        self._demand_timeout = p("demand_timeout", 0.3).value
        self._odom_frame = p("odom_frame", "odom").value
        self._base_frame = p("base_frame", "base_footprint").value
        self._publish_tf = p("publish_ground_truth_tf", True).value
        self._excessive_slip = self._model.params.excessive_slip_threshold
        self._model.reset(p("initial_x", 0.0).value, p("initial_y", 0.0).value, p("initial_yaw", 0.0).value)

        self.create_subscription(SimTrackDemand, SIM_TRACK_DEMAND, self._on_demand, 10)
        self._feedback_pub = self.create_publisher(TrackState, TRACK_FEEDBACK, 10)
        self._slip_pub = self.create_publisher(TrackSlipEstimate, GROUND_TRUTH_SLIP, 10)
        self._tf = TransformBroadcaster(self) if self._publish_tf else None
        if self._backend == "headless":
            self._odom_pub = self.create_publisher(Odometry, GROUND_TRUTH_ODOM, 10)
        else:
            self._gz_cmd_pub = self.create_publisher(Twist, p("gazebo_cmd_topic", "/model/htv/cmd_vel").value, 10)
            self.create_subscription(Odometry, GROUND_TRUTH_ODOM, self._on_gazebo_odom, 10)

        self._last_demand_time: float | None = None
        self._last_step = now_seconds(self)
        self._publish_every = max(1, round(self._rate / p("feedback_rate", 50.0).value))
        self._ticks = 0
        self.add_on_set_parameters_callback(self._on_params)
        self.create_timer(1.0 / self._rate, self._step)
        self.get_logger().info(f"simulated tracked vehicle ({self._backend}), mass {self._model.params.vehicle_mass:.0f} kg")

    def _on_params(self, params) -> SetParametersResult:
        for param in params:
            if param.name == "vehicle.terrain_friction":
                self._model.set_terrain(friction=param.value)
            elif param.name == "vehicle.terrain_slope" and self._backend == "headless":
                self._model.set_terrain(slope=param.value)
            elif param.name.startswith(PARAM_PREFIX) and param.name not in RUNTIME_TERRAIN_PARAMS:
                return SetParametersResult(successful=False, reason="only terrain parameters change at runtime")
        return SetParametersResult(successful=True)

    def _on_demand(self, msg: SimTrackDemand) -> None:
        self._last_demand_time = now_seconds(self)
        self._model.set_demand(
            TrackDemand(
                left=msg.left_track_velocity,
                right=msg.right_track_velocity,
                service_brake=msg.service_brake,
                emergency_brake=msg.emergency_brake,
            )
        )

    def _on_gazebo_odom(self, msg: Odometry) -> None:
        # Uphill (nose up) is a negative ROS pitch; the model wants positive uphill.
        self._model.set_terrain(slope=-quaternion_pitch(msg.pose.pose.orientation))
        if self._tf is not None:
            self._broadcast(msg.header.stamp, msg.pose.pose.position.x, msg.pose.pose.position.y,
                            msg.pose.pose.position.z, msg.pose.pose.orientation)

    def _step(self) -> None:
        if not clock_ready(self):
            return
        now = now_seconds(self)
        dt = min(0.05, max(0.0, now - self._last_step))
        self._last_step = now
        if self._last_demand_time is not None and now - self._last_demand_time > self._demand_timeout:
            # Plant-side failsafe: lost actuation link => service brake.
            self._model.set_demand(TrackDemand(service_brake=True))
            self._last_demand_time = None
        state = self._model.step(dt)
        if self._backend == "gazebo":
            cmd = Twist()
            cmd.linear.x = state.linear_velocity
            cmd.linear.y = state.lateral_velocity
            cmd.angular.z = state.yaw_rate
            self._gz_cmd_pub.publish(cmd)
        self._ticks += 1
        if self._ticks % self._publish_every == 0:
            self._publish(now)

    def _publish(self, now: float) -> None:
        s = self._model.state
        stamp = from_seconds(now)
        fb = TrackState()
        fb.header.stamp = stamp
        fb.header.frame_id = "base_link"
        fb.left_track_velocity = s.left_track_velocity
        fb.right_track_velocity = s.right_track_velocity
        fb.left_track_distance = s.left_track_distance
        fb.right_track_distance = s.right_track_distance
        fb.brake_engaged = s.brake_engaged
        fb.emergency_brake_engaged = s.emergency_brake_engaged
        self._feedback_pub.publish(fb)

        slip = TrackSlipEstimate()
        slip.header = fb.header
        slip.left_slip = s.left_slip
        slip.right_slip = s.right_slip
        slip.yaw_rate_ratio = s.yaw_rate_ratio
        slip.lateral_velocity = s.lateral_velocity
        slip.excessive = max(s.left_slip, s.right_slip) >= self._excessive_slip
        self._slip_pub.publish(slip)

        if self._backend != "headless":
            return
        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self._odom_frame
        odom.child_frame_id = self._base_frame
        odom.pose.pose.position.x = s.x
        odom.pose.pose.position.y = s.y
        qx, qy, qz, qw = yaw_to_quaternion(s.yaw)
        odom.pose.pose.orientation.x, odom.pose.pose.orientation.y = qx, qy
        odom.pose.pose.orientation.z, odom.pose.pose.orientation.w = qz, qw
        odom.twist.twist.linear.x = s.linear_velocity
        odom.twist.twist.linear.y = s.lateral_velocity
        odom.twist.twist.angular.z = s.yaw_rate
        self._odom_pub.publish(odom)
        if self._tf is not None:
            self._broadcast(stamp, s.x, s.y, 0.0, odom.pose.pose.orientation)

    def _broadcast(self, stamp, x: float, y: float, z: float, orientation) -> None:
        t = TransformStamped()
        t.header.stamp = stamp
        t.header.frame_id = self._odom_frame
        t.child_frame_id = self._base_frame
        t.transform.translation.x = x
        t.transform.translation.y = y
        t.transform.translation.z = z
        t.transform.rotation = orientation
        self._tf.sendTransform(t)


def main(args=None) -> None:
    run_node(TrackedVehicleSimNode, args)
