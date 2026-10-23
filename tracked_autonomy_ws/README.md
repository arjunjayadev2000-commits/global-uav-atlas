# Heavy Tracked Vehicle (HTV) Research Autonomy — ROS 2 Jazzy workspace

Simulation-only autonomy stack for a **demilitarised, unarmed, generic WZT-3-class
heavy tracked recovery vehicle** used purely as a robotics research platform.

> **Scope.** This workspace contains no weapon, targeting, fire-control, smoke,
> mission-planning or command-and-control software; those systems are treated as
> physically removed. Recovery equipment (crane, winch, dozer) is out of scope.
> There is **no real-vehicle actuator implementation** of any kind: the only
> vehicle backend is `SimulatedLegacyTrackedVehicleInterface`. See
> [docs/HARDWARE_ADAPTER_CONTRACT.md](docs/HARDWARE_ADAPTER_CONTRACT.md).

```
LiDAR + Cameras + GNSS/RTK + IMU          (Gazebo sensors, Phase 3)
        ↓
ROS 2 Jazzy → time sync → localization → terrain/traversability → Nav2 / planner
        ↓ /cmd_vel_nav
Safety Supervisor ──► Command Limiter ──► Motion Arbitration
        (gates)        (limits + stopping     (sole publisher of /safe_cmd_vel)
                        distance cap)
        ↓ /safe_cmd_vel  (htv_interfaces/SafeMotionCommand)
═════════════ VEHICLE ABSTRACTION LAYER ═════════════
LegacyTrackedVehicleInterface → SimulatedLegacyTrackedVehicleInterface
        ↓ /sim/track_demand
Simulated heavy tracked vehicle plant (htv_dynamics: latency, lag, slip, skid)
        ✕  no real hardware implementation
```

## Packages

| Package | Contents |
|---|---|
| `htv_interfaces` | `SafeMotionCommand`, `SafetyStatus`, `LocalizationHealth`, `VehicleStatus`, `TraversabilityGrid`, … and services (`ResetEmergencyStop`, `InjectFailure`, `GetVehicleStatus`) |
| `htv_dynamics` | Pure-Python heavy tracked vehicle model: command/brake latency, track lag, traction & slope limits, slip, skid-steer inefficiency, yaw inertia |
| `htv_vehicle_interface` | `LegacyTrackedVehicleInterface` contract, `GuardedVehicleInterfaceBase` (validation, timeouts, latching), the simulated backend, backend registry, ROS host node |
| `htv_safety` | Safety supervisor state machine, command limiter, stopping-distance estimator, motion arbitration, operator mode, heartbeat watchdog, geofence monitor |
| `htv_sim` | Simulated plant node (headless or Gazebo-coupled), phase health stubs + failure injection |
| `htv_description` | Xacro model (polygon footprint, tracks, sensor suite), YAML-configurable sensor mounts |
| `htv_gazebo` | Five Gazebo Harmonic worlds, generator script, ros_gz bridge, spawn launch |
| `htv_bringup` | `config/simulation_safe.yaml`, launch files, ROS graph validator, system tests |
| `htv_common` | Shared helpers: topic names, heartbeats, time, stall guard |

## Build and test

Requires ROS 2 Jazzy (Ubuntu 24.04 apt packages, or RoboStack/conda) and, for the
Gazebo launch, Gazebo Harmonic with `ros_gz`.

```bash
cd tracked_autonomy_ws
rosdep install --from-paths src --ignore-src -y     # apt-based installs
colcon build
source install/setup.bash
colcon test && colcon test-result --verbose
```

> `colcon build --symlink-install` fails with recent setuptools (`--editable not
> recognized`); use a normal build.

## Run Phase 1

```bash
# Headless (no Gazebo): plant + vehicle interface + full safety chain + robot model
ros2 launch htv_bringup phase1_headless.launch.py

# Gazebo Harmonic. On machines without OpenGL (CI, containers) add
# rendering_sensors:=false (cameras/GPU LiDAR off; physics, IMU, GNSS still run).
ros2 launch htv_bringup phase1_gazebo.launch.py world:=02_obstacle_course
ros2 launch htv_bringup phase1_gazebo.launch.py headless:=true rendering_sensors:=false

# Validate the command chain in the live graph
ros2 run htv_bringup graph_check

# Autonomy never enables itself; an operator must:
ros2 service call /autonomy/enable std_srvs/srv/Trigger
ros2 topic pub -r 10 /cmd_vel_nav geometry_msgs/msg/Twist "{linear: {x: 0.8}}"
ros2 service call /autonomy/disable std_srvs/srv/Trigger

# Emergency stop (latched) and explicit operator reset
ros2 topic pub --once /safety/estop std_msgs/msg/Bool "{data: true}"
ros2 run htv_bringup reset_estop --operator <name>

# Simulation-only failure injection (phase stub subsystems)
ros2 service call /sim/inject_failure htv_interfaces/srv/InjectFailure "{failure: lidar_loss, active: true}"

# Record a bag of the safety-relevant topics
ros2 launch htv_bringup phase1_headless.launch.py record_bag:=true bag_dir:=bags/run1
```

Worlds: `01_flat_test_track`, `02_obstacle_course`, `03_rough_terrain`,
`04_slope_course`, `05_gnss_degraded_course` (regenerate with
`python3 src/htv_gazebo/scripts/generate_worlds.py`).

## Speed configuration

All limits live in [`src/htv_bringup/config/simulation_safe.yaml`](src/htv_bringup/config/simulation_safe.yaml);
no source change is needed to change them. Research defaults: 1.0 m/s forward,
0.3 m/s reverse, 0.10 rad/s yaw, no pivot turns (5 m minimum turning radius).
Before terrain perception exists (Phase 9) terrain is UNKNOWN, so the
stopping-distance supervisor caps speed at **0.3 m/s**. The supervisor refuses to
start (FAULT) if `research_speed_limit` exceeds `research_speed_hard_cap` (2.0 m/s).

## Documentation

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — nodes, topics, frames, parameters
* [docs/SAFETY.md](docs/SAFETY.md) — supervisor states, latching, watchdog, timeouts, failure matrix
* [docs/HARDWARE_ADAPTER_CONTRACT.md](docs/HARDWARE_ADAPTER_CONTRACT.md) — the abstraction boundary
* [docs/PHASES.md](docs/PHASES.md) — development phases and gate evidence
