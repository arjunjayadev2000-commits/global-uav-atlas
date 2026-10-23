# Architecture

## Command chain

There is exactly one path from any planner to the vehicle. `htv_bringup/graph_rules.py`
encodes it and `graph_check` / the system tests enforce it on the live graph.

| Topic | Type | Only publisher | Only subscriber |
|---|---|---|---|
| `/cmd_vel_nav` | `geometry_msgs/Twist` | Nav2 / planner (Phase 7) | `safety_supervisor` |
| `/safety/gated_cmd` | `SafeMotionCommand` | `safety_supervisor` | `command_limiter` |
| `/control/limited_cmd` | `SafeMotionCommand` | `command_limiter` | `motion_arbitration` |
| `/safe_cmd_vel` | `SafeMotionCommand` | `motion_arbitration` | `vehicle_interface` |
| `/sim/track_demand` | `SimTrackDemand` | `vehicle_interface` (simulated backend) | `tracked_vehicle_sim` |

Each stage re-checks independently (defence in depth):

1. **Safety supervisor** passes the planner command only in AUTONOMOUS/DEGRADED,
   stamped with its reception time so staleness propagates.
2. **Command limiter** applies research limits × supervisor speed scale, the
   stopping-distance speed cap, minimum turning radius (no pivots unless enabled),
   curvature-preserving scaling and acceleration limits.
3. **Motion arbitration** selects the highest-priority fresh source (one source in
   Phase 1) and outputs zero unless a fresh `SafetyStatus` allows motion.
4. **Vehicle interface** rejects non-finite, out-of-limit, future-stamped or stale
   commands, requires explicit enable, and latches E-stop on supervisor
   EMERGENCY_STOP/FAULT, watchdog E-stop, or loss of the supervisor while enabled.
5. **Simulated plant** service-brakes if track demands stop arriving.

## Nodes

| Node | Package | Role |
|---|---|---|
| `safety_supervisor` | htv_safety | State machine, input freshness, gating, `/safety/reset_emergency_stop` |
| `command_limiter` | htv_safety | Limits, stopping-distance cap, `/safety/stopping_distance` |
| `motion_arbitration` | htv_safety | Source selection; sole `/safe_cmd_vel` publisher |
| `operator_mode` | htv_safety | MANUAL / AUTONOMY_ARMED / AUTONOMOUS / STOPPED, `/autonomy/enable`, `/autonomy/disable` |
| `watchdog` | htv_safety | Heartbeats on `/system/heartbeat`, `/watchdog/status`, `/safety/watchdog_estop` |
| `geofence_monitor` | htv_safety | Inflated footprint vs fence polygon → `/geofence/status` |
| `vehicle_interface` | htv_vehicle_interface | Hosts a `LegacyTrackedVehicleInterface` backend (`simulated` only) |
| `tracked_vehicle_sim` | htv_sim | `htv_dynamics` plant; headless or Gazebo VelocityControl coupling |
| `sim_health_stub` | htv_sim | PHASE STUB health for not-yet-built subsystems; `/sim/inject_failure` |
| `robot_state_publisher` | — | TF from the Xacro model |

## Tracked vehicle dynamics (`htv_dynamics`)

Inputs are sprocket track-speed demands. Per step:

* demands pass through a `command_latency` delay line;
* each track follows a first-order lag (`track_time_constant`) limited by
  `min(max_acceleration, μ g cosθ) − g sinθ` when driving;
* deceleration starts only after `braking_latency`, then at
  `min(max_deceleration | emergency_deceleration, μ g cosθ) + g sinθ`;
* longitudinal slip grows with turning and falls with friction; outer track slips more;
* yaw rate = (v_r' − v_l') / (B · χ), χ = 1 + k·L/B (steering inefficiency),
  then yaw inertia (`yaw_time_constant`, `max_yaw_acceleration`, `max_yaw_rate`);
* lateral skid ∝ v · ω / μ.

Track feedback reports sprocket speed, not ground speed, so odometry from it
drifts under slip; ground truth (`/ground_truth/odom`, `/ground_truth/track_slip`)
is for evaluation only.

In Gazebo, the model's realised body twist drives the `VelocityControl` system and
Gazebo's terrain pitch feeds back into the slope term; Gazebo handles pose,
collisions and sensors.

## Frames

`odom → base_footprint → base_link → {left,right}_track_link, superstructure_link,
imu_link, gnss_link, lidar_link, [lidar_secondary_link], front_camera_link,
front_aux_camera_link, left_camera_link, right_camera_link, rear_camera_link`
(cameras also have `*_optical_frame`). Phases 1–5 publish `odom → base_footprint`
from ground truth; from Phase 6 the EKF owns it. Sensor mounts come from
`htv_description/config/sensor_mounts.yaml`, overridable with
`xacro htv.urdf.xacro sensor_config:=<file>`.

## Footprints

Polygons (flat `[x0, y0, …]` in `base_link`) in `simulation_safe.yaml`:
`footprint.nominal` (7.5 × 3.4 m), `footprint.low_speed_safety` (9.0 × 4.8 m),
`footprint.safety_inflation` (0.5 m) and `footprint.navigation_inflation_radius` (2.5 m).

## Time

All nodes use the ROS clock (`use_sim_time` with Gazebo). Every freshness check
treats a negative age (clock jumped backwards) as stale. Nodes wait for a valid
clock before starting their state machines. With sim time, Gazebo advances
regardless of ROS scheduling; on overloaded machines lower
`real_time_factor` (the Gazebo system test uses 0.5).
