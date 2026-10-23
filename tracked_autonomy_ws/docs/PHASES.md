# Development phases

Gate for every phase: `colcon build` passes, `colcon test` passes, launch files
run, and the ROS topic graph validates (`ros2 run htv_bringup graph_check`).

| # | Phase | Status |
|---|---|---|
| 1 | Generic heavy tracked vehicle Gazebo model | **Gate passed** (see below) |
| 2 | Track dynamics and skid/slip simulation | Core model built and unit-tested (`htv_dynamics`); Gazebo-terrain validation pending |
| 3 | LiDAR + cameras + GNSS + IMU | Sensors in Xacro and bridged; IMU/GNSS verified headless; cameras/LiDAR need an OpenGL-capable host |
| 4 | TF and sensor validation | TF tree verified by tests; per-sensor data validation pending |
| 5 | Track odometry | Track feedback + ground truth available; odometry node pending |
| 6 | EKF localization | Not started (`LocalizationHealth` defined; stub in place) |
| 7 | Nav2 basic navigation | Not started (`/cmd_vel_nav` entry point and footprints defined) |
| 8 | Safety Supervisor | Built ahead of schedule because the Phase-1 command chain needs it; tested |
| 9 | Terrain/traversability mapping | Not started (`TraversabilityGrid` defined) |
| 10 | Stopping-distance supervisor | Estimator and speed cap built and tested |
| 11 | Failure injection | Partial: `/sim/inject_failure` for GNSS, IMU, LiDAR, localization divergence, excessive slip |
| 12 | Automated validation | Partial: system tests and bag recording; metrics pending |

## Phase 1 gate evidence

Environment: Ubuntu 24.04, ROS 2 Jazzy (RoboStack), Gazebo Harmonic (gz-sim 8),
container without GPU/OpenGL.

* `colcon build`: 9 packages, no errors.
* `colcon test`: 127 tests, 0 failures, 0 skipped. Four consecutive full runs
  were green with packages tested in parallel.
* Worlds: all five pass `gz sdf -k`, and the tests check they match the generator output.
* `phase1_headless.launch.py`: full stack up; graph rules pass; drive, stop,
  failure-injection and E-stop scenarios pass.
* `phase1_gazebo.launch.py headless:=true rendering_sensors:=false`: model spawns;
  `/ground_truth/odom` ~44 Hz, `/imu/data` ~65 Hz, `/gnss/fix` ~10 Hz,
  `/vehicle/track_feedback` ~45 Hz; supervisor reaches READY; vehicle moves only
  after operator enable; E-stop brings it to rest in Gazebo.
* Not verified here: camera and GPU-LiDAR output (ogre2 needs OpenGL).

Phase 2 and later phases still need their own gates.
