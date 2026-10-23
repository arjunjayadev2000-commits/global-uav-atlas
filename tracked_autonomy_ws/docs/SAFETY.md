# Safety design (simulation)

The safety subsystem (`htv_safety`) is independent of planning: it consumes the
planner's output but never depends on the planner behaving well. Its core logic
is ROS-agnostic and unit-tested (`state_machine.py`, `operator_mode.py`,
`stopping_distance.py`, `command_limiter.py`, `heartbeat_monitor.py`).

## Supervisor states

| State | Motion | Entered when |
|---|---|---|
| POWER_OFF | no | process start, before the first valid clock |
| INITIALIZING | no | power on; waits for vehicle interface + watchdog; FAULT after `initialization_timeout` |
| STANDBY | no | initialised, or a controlled stop / reset completed |
| READY | no | all critical inputs valid; awaiting a **fresh** operator enable |
| AUTONOMOUS | yes | READY ∧ localization ∧ perception ∧ vehicle interface ready+enabled ∧ safety system ∧ operator enable ∧ geofence |
| DEGRADED | yes, `degraded_speed_scale` | non-critical loss (GNSS while localization still valid, high slip) |
| CONTROLLED_STOP | no | critical loss or operator disable while moving → STANDBY at standstill |
| EMERGENCY_STOP | no, **latched** | E-stop input, critical heartbeat lost, vehicle interface timeout, brake fault, geofence breach |
| FAULT | no, **latched** | safety self-test failure (e.g. research speed above hard cap), internal exception, init timeout |

* Each autonomy run consumes the operator's `enable_sequence`; after any stop a
  *new* `/autonomy/enable` is required. Autonomy can never re-arm itself.
* EMERGENCY_STOP/FAULT clear only via `/safety/reset_emergency_stop` with
  `confirmation: "RESET"`, a non-empty `operator_id`, the cause cleared and the
  vehicle at standstill. Reset returns to STANDBY, never to AUTONOMOUS. The
  vehicle interface has its own latch, reset separately via
  `/vehicle/reset_emergency_stop` (`ros2 run htv_bringup reset_estop` does both).
* Any missing or stale input counts as invalid.

## Critical vs non-critical inputs

| Input | Loss → |
|---|---|
| localization, perception, LiDAR, IMU, vehicle interface ready, geofence valid, compute watchdog | CONTROLLED_STOP |
| GNSS (unless `gnss_required`) | DEGRADED |
| track slip ≥ `slip_high_threshold` / ≥ `slip_excessive_threshold` | DEGRADED / CONTROLLED_STOP |
| E-stop input, critical heartbeat lost, vehicle status stale, brake fault, geofence breached | EMERGENCY_STOP |

## Watchdog

Monitored nodes publish `Heartbeat` on `/system/heartbeat` (5 Hz). Severities:
`critical` (supervisor, vehicle interface, limiter, arbitration), `major`
(operator mode, geofence; Nav2/localization/perception join in later phases),
`minor`. The supervisor stops on major and E-stops on critical. The watchdog also
publishes `/safety/watchdog_estop` directly to the vehicle interface when a
critical node that was alive goes silent or unhealthy, so the vehicle stops even
if the supervisor itself has died. Nodes that never started are reported but
handled by the supervisor's INITIALIZING gate; the direct E-stop is armed after
`startup_grace`, since nothing can be enabled before READY.

## Timeouts (`simulation_safe.yaml`)

| Check | Timeout | Effect |
|---|---|---|
| planner command at supervisor | 0.5 s | zero command (not a state change) |
| command age at arbitration / vehicle interface | 0.3 s | zero command / service brake |
| vehicle status at supervisor | 0.5 s | EMERGENCY_STOP |
| supervisor status at vehicle interface | 0.6 s | latched E-stop if enabled, brake hold if disabled |
| track feedback at vehicle interface | 0.5 s | latched FAULT if enabled |
| heartbeats at watchdog | 0.6 s | per severity |
| track demand at plant | 0.3 s | service brake |

**Self-stall handling.** If an evaluating node (supervisor, watchdog, vehicle
interface) is itself descheduled for longer than its timeout, messages that
arrived meanwhile are still queued, so every input looks stale on the first tick
afterwards. That tick is deferred once (the supervisor holds its state and
commands zero; the vehicle interface brakes), and never twice in a row, so a node
that stays starved still fails safe (`htv_common/stall_guard.py`).

## Stopping-distance supervisor

```
stopping_distance = v·(command_latency + braking_latency + reaction_time)
                  + v² / (2·a_eff)
                  + margin_fixed + margin_ratio·(reaction + braking)
a_eff = min(max_deceleration, μ·g·cosθ) + g·sinθ        (θ > 0 uphill)
```

The limiter caps speed at the largest `v` whose stopping distance fits
`stopping.available_distance`, scaled by terrain confidence. Below
`min_terrain_confidence` the terrain is UNKNOWN: traction 0.35, an assumed −8°
downhill, and a hard cap of `unknown_terrain_speed` (0.3 m/s). Output is on
`/safety/stopping_distance`.

## Verified behaviour (system tests)

`htv_bringup/test/test_phase1_integration.py` (headless) and
`test_phase1_gazebo.py` (Gazebo) check that:

* the live graph has the single command chain and no bypass publishers or subscribers;
* nothing moves without operator enable, even with planner commands flowing;
* enabled autonomy moves within the 0.3 m/s cap;
* a stale planner command → zero motion;
* injected LiDAR loss → CONTROLLED_STOP → zero motion, and no self-resume after the cause clears;
* the E-stop latches, survives the cause clearing, refuses enable and a wrong
  confirmation, and an explicit reset does not re-enable motion.

Killing the supervisor while driving was checked by hand: the vehicle interface
latched its E-stop after 0.6 s and motion reached zero after 0.9 s. Automated
fault-injection coverage for node death is part of Phase 11.
