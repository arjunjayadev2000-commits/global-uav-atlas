# Vehicle abstraction boundary

```
AUTONOMY SOFTWARE  (planning, safety, arbitration)
        |
        |  htv_interfaces/SafeMotionCommand on /safe_cmd_vel
        v
VEHICLE ABSTRACTION LAYER  (htv_vehicle_interface)
        |
        X  NO REAL HARDWARE IMPLEMENTATION IN THIS REPOSITORY
```

The autonomy stack knows only body-frame kinematics: linear velocity, yaw rate,
a time stamp and a motion-permission flag. It has no knowledge of how any
platform produces motion.

This repository deliberately contains **no** actuator wiring, hydraulic,
transmission, engine, electrical or vehicle-specific control code, and none may
be added to it. The only backend is `SimulatedLegacyTrackedVehicleInterface`.

## Contract (`htv_vehicle_interface/interface.py`)

`LegacyTrackedVehicleInterface` (abstract), with all methods taking the current
time explicitly:

| Method | Required behaviour |
|---|---|
| `initialize(now)` | Enter DISABLED. Never enable motion. |
| `enable(now)` | Refuse if latched, stopping, or without fresh feedback. Discard any command received before enabling. |
| `disable(now)` / `request_stop(now)` | Controlled stop; a new `enable` is required afterwards. |
| `emergency_stop(now, reason)` | Latch immediately; emit emergency stop actuation every cycle. |
| `reset_emergency_stop(now)` | Only at standstill with fresh feedback; return to DISABLED (never ENABLED). |
| `submit_command(cmd, now)` | Reject non-finite, future-stamped or out-of-limit commands; a rejection clears the active command. |
| `on_feedback(feedback)` | Accept plant feedback (track speeds, brake state). |
| `update(now)` | Periodic: enforce command/feedback timeouts and emit this cycle's actuation. |
| `hold(now)` | Emit a stop actuation for this cycle without a state change. |
| `get_status(now)` | Report state, readiness, latch, standstill, ages and faults. |

`GuardedVehicleInterfaceBase` implements all of the above; a backend subclass
supplies only `_actuate(ActuationRequest, now)`. `ActuationRequest` is
platform-neutral (body velocity, nominal track speeds, stop mode).

## Registering a backend

Backends are discovered through the `htv_vehicle_interface.backends` entry point
group and constructed with `cls.from_config(config: dict, actuation_sink=...)`.
The host node loads a non-simulated backend only when
`allow_non_simulated_backends: true` is set explicitly; the shipped configuration
sets it to `false`.

## For any future adapter (outside this repository)

An adapter for a physical platform is a separate engineering effort by an
authorised team, with its own hazard analysis, independent hardware emergency
stop, and the legal and organisational approvals required for the platform. This
contract defines a software interface only. Conforming to it does **not** make an
adapter safe, and the simulation-only safety logic in this repository has not
been assessed for use on any real vehicle.
