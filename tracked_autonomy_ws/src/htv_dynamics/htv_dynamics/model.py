"""Approximate planar dynamics of a heavy skid-steer tracked vehicle.

The model is intentionally simple but captures the behaviours that matter for
autonomy safety on a heavy platform and that an ideal differential-drive model
hides:

* actuation dead time (``command_latency``) through a delay line,
* first-order track-speed lag (longitudinal inertia / acceleration delay),
* brake build-up delay (``braking_latency``) before deceleration starts,
* acceleration and braking limited by traction ``mu*g*cos(slope)`` and gravity,
* longitudinal track slip that grows with demanded traction and turning,
* skid-steer steering inefficiency (ICR expansion factor ``chi``),
* yaw inertia (first-order, rate and acceleration limited),
* lateral skid while turning.

Inputs are *track speed demands*; producing those from a body-frame command is
the job of a vehicle interface, not of this plant.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from .params import GRAVITY, TrackedVehicleParams


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sign(value: float) -> float:
    if value > 0.0:
        return 1.0
    if value < 0.0:
        return -1.0
    return 0.0


@dataclass
class TrackDemand:
    left: float = 0.0
    right: float = 0.0
    emergency_brake: bool = False
    service_brake: bool = False


@dataclass
class TrackedVehicleState:
    time: float = 0.0
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    # Body-frame ground velocities (true motion).
    linear_velocity: float = 0.0
    lateral_velocity: float = 0.0
    yaw_rate: float = 0.0
    # Sprocket surface speeds (what encoders measure).
    left_track_velocity: float = 0.0
    right_track_velocity: float = 0.0
    left_track_distance: float = 0.0
    right_track_distance: float = 0.0
    # Slip diagnostics.
    left_slip: float = 0.0
    right_slip: float = 0.0
    yaw_rate_ratio: float = 1.0
    brake_engaged: bool = False
    emergency_brake_engaged: bool = False
    distance_travelled: float = 0.0


@dataclass
class _TrackActuator:
    velocity: float = 0.0
    brake_request_time: float | None = None
    distance: float = 0.0


@dataclass
class TrackedVehicleModel:
    params: TrackedVehicleParams = field(default_factory=TrackedVehicleParams)
    state: TrackedVehicleState = field(default_factory=TrackedVehicleState)

    def __post_init__(self) -> None:
        self.params.validate()
        self._pending: deque[tuple[float, TrackDemand]] = deque()
        self._active = TrackDemand()
        self._left = _TrackActuator()
        self._right = _TrackActuator()

    # ------------------------------------------------------------------ API
    def reset(self, x: float = 0.0, y: float = 0.0, yaw: float = 0.0) -> None:
        self.state = TrackedVehicleState(x=x, y=y, yaw=yaw)
        self._pending.clear()
        self._active = TrackDemand()
        self._left = _TrackActuator()
        self._right = _TrackActuator()

    def set_demand(self, demand: TrackDemand) -> None:
        """Queue a track demand; it takes effect after ``command_latency``.

        Emergency brake requests also pass through the dead time: no actuator is
        instantaneous, and the stopping-distance supervisor accounts for it.
        """
        apply_at = self.state.time + self.params.command_latency
        self._pending.append((apply_at, demand))

    def set_terrain(self, friction: float | None = None, slope: float | None = None) -> None:
        if friction is not None:
            self.params.terrain_friction = max(0.01, float(friction))
        if slope is not None:
            self.params.terrain_slope = _clamp(float(slope), -1.2, 1.2)

    @property
    def stopped(self) -> bool:
        thr = self.params.standstill_threshold
        s = self.state
        return (
            abs(s.linear_velocity) < thr
            and abs(s.left_track_velocity) < thr
            and abs(s.right_track_velocity) < thr
            and abs(s.yaw_rate) < thr
        )

    def step(self, dt: float) -> TrackedVehicleState:
        if dt <= 0.0:
            return self.state
        p = self.params
        s = self.state
        s.time += dt

        while self._pending and self._pending[0][0] <= s.time + 1e-9:
            self._active = self._pending.popleft()[1]
        demand = self._active

        emergency = demand.emergency_brake
        braking_cmd = emergency or demand.service_brake
        target_left = 0.0 if braking_cmd else _clamp(demand.left, -p.max_vehicle_speed, p.max_vehicle_speed)
        target_right = 0.0 if braking_cmd else _clamp(demand.right, -p.max_vehicle_speed, p.max_vehicle_speed)

        cos_t = math.cos(p.terrain_slope)
        sin_t = math.sin(p.terrain_slope)
        traction_accel = p.terrain_friction * GRAVITY * cos_t

        left_brake = self._update_track(self._left, target_left, dt, emergency, traction_accel, sin_t)
        right_brake = self._update_track(self._right, target_right, dt, emergency, traction_accel, sin_t)

        vl = self._left.velocity
        vr = self._right.velocity

        # Longitudinal slip: grows with how much of the available traction the
        # turn consumes, inversely with friction. Heavy vehicles on loose ground
        # slip substantially when turning.
        diff = vr - vl
        mean_abs = 0.5 * (abs(vl) + abs(vr))
        turn_ratio = abs(diff) / (abs(vl) + abs(vr) + 0.1)
        base_slip = p.slip_coefficient / max(p.terrain_friction, 0.05)
        turn_slip = _clamp(base_slip * (0.25 + turn_ratio), 0.0, 0.9)
        # Outer track (faster) slips more than inner track while turning.
        outer_bias = 0.5 * turn_ratio
        if abs(vr) >= abs(vl):
            sr, sl = turn_slip * (1.0 + outer_bias), turn_slip * (1.0 - outer_bias)
        else:
            sl, sr = turn_slip * (1.0 + outer_bias), turn_slip * (1.0 - outer_bias)
        sl = _clamp(sl if mean_abs > p.standstill_threshold else 0.0, 0.0, 0.95)
        sr = _clamp(sr if mean_abs > p.standstill_threshold else 0.0, 0.0, 0.95)

        vl_ground = vl * (1.0 - sl)
        vr_ground = vr * (1.0 - sr)
        v_body = 0.5 * (vl_ground + vr_ground)

        # Skid-steer kinematics with ICR expansion (steering inefficiency).
        yaw_kinematic = (vr_ground - vl_ground) / (p.track_separation * p.chi)
        yaw_kinematic = _clamp(yaw_kinematic, -p.max_yaw_rate, p.max_yaw_rate)

        # Yaw inertia: first-order lag with yaw-acceleration limit.
        yaw_acc = (yaw_kinematic - s.yaw_rate) / p.yaw_time_constant
        yaw_acc = _clamp(yaw_acc, -p.max_yaw_acceleration, p.max_yaw_acceleration)
        new_yaw_rate = s.yaw_rate + yaw_acc * dt
        if braking_cmd and self._both_stopped():
            new_yaw_rate = 0.0

        ideal_yaw = diff / p.track_separation
        s.yaw_rate_ratio = (new_yaw_rate / ideal_yaw) if abs(ideal_yaw) > 1e-3 else 1.0

        v_lat = -p.lateral_slip_gain * v_body * new_yaw_rate / max(p.terrain_friction, 0.05)

        # Integrate pose (midpoint heading).
        yaw_mid = s.yaw + 0.5 * new_yaw_rate * dt
        s.x += (v_body * math.cos(yaw_mid) - v_lat * math.sin(yaw_mid)) * dt
        s.y += (v_body * math.sin(yaw_mid) + v_lat * math.cos(yaw_mid)) * dt
        s.yaw = math.atan2(math.sin(s.yaw + new_yaw_rate * dt), math.cos(s.yaw + new_yaw_rate * dt))

        s.linear_velocity = v_body
        s.lateral_velocity = v_lat
        s.yaw_rate = new_yaw_rate
        s.left_track_velocity = vl
        s.right_track_velocity = vr
        self._left.distance += vl * dt
        self._right.distance += vr * dt
        s.left_track_distance = self._left.distance
        s.right_track_distance = self._right.distance
        s.left_slip = sl
        s.right_slip = sr
        s.brake_engaged = left_brake or right_brake
        s.emergency_brake_engaged = emergency and s.brake_engaged
        s.distance_travelled += math.hypot(v_body, v_lat) * dt
        return s

    # ------------------------------------------------------------- internals
    def _both_stopped(self) -> bool:
        thr = self.params.standstill_threshold
        return abs(self._left.velocity) < thr and abs(self._right.velocity) < thr

    def _update_track(
        self,
        track: _TrackActuator,
        target: float,
        dt: float,
        emergency: bool,
        traction_accel: float,
        sin_slope: float,
    ) -> bool:
        """Advance one track's sprocket speed. Returns True if the brake is applied."""
        p = self.params
        v = track.velocity
        direction = _sign(v) if v != 0.0 else _sign(target)
        decelerating = abs(target) < abs(v) - 1e-6 or (v * target < 0.0)

        # Gravity along the direction of motion: positive slope (uphill when
        # moving forward) opposes forward motion and assists braking.
        gravity_along = GRAVITY * sin_slope * direction

        if decelerating:
            if track.brake_request_time is None:
                track.brake_request_time = self.state.time
            brake_active = (self.state.time - track.brake_request_time) >= p.braking_latency - 1e-9
            if brake_active:
                limit = p.emergency_deceleration if emergency else p.max_deceleration
                decel = min(limit, traction_accel) + gravity_along
            else:
                # Brakes not yet built up: vehicle coasts against rolling resistance.
                decel = p.rolling_resistance * GRAVITY + gravity_along
            decel = max(decel, 0.0)
            step = decel * dt
            if v > target:
                v = max(target, v - step)
            else:
                v = min(target, v + step)
            track.velocity = v
            return brake_active

        track.brake_request_time = None
        # Driving: first-order lag toward target, limited by drive capability.
        desired_rate = (target - v) / p.track_time_constant
        accel_cap = min(p.max_acceleration, traction_accel) - gravity_along
        accel_cap = max(accel_cap, 0.0)
        rate = _clamp(desired_rate, -accel_cap, accel_cap)
        track.velocity = v + rate * dt
        return False
