"""Configurable parameters for the generic heavy tracked vehicle model.

Values describe a *generic* ~42 t class tracked vehicle and are deliberately
approximate. They are not derived from, and must not be treated as, data for any
specific operational vehicle.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields
from typing import Any

GRAVITY = 9.80665


@dataclass
class TrackedVehicleParams:
    # --- Mass / geometry -------------------------------------------------
    vehicle_mass: float = 42000.0          # [kg]
    track_separation: float = 2.80         # track centreline to centreline [m]
    track_contact_length: float = 4.60     # ground contact length per track [m]
    track_width: float = 0.58              # [m]
    vehicle_length: float = 7.50           # hull overall length [m]
    vehicle_width: float = 3.40            # overall width incl. tracks [m]

    # --- Limits ----------------------------------------------------------
    max_vehicle_speed: float = 15.0        # physical plant limit [m/s]
    research_speed_limit: float = 1.0      # conservative research limit [m/s]
    max_acceleration: float = 0.5          # [m/s^2]
    max_deceleration: float = 1.5          # service braking [m/s^2]
    emergency_deceleration: float = 2.5    # emergency braking [m/s^2]
    max_yaw_rate: float = 0.30             # [rad/s]
    max_yaw_acceleration: float = 0.25     # [rad/s^2]

    # --- Latency / lag ---------------------------------------------------
    command_latency: float = 0.25          # actuation dead time [s]
    braking_latency: float = 0.40          # brake build-up delay [s]
    track_time_constant: float = 0.80      # first-order track speed lag [s]
    yaw_time_constant: float = 1.20        # yaw-inertia lag [s]

    # --- Terrain interaction --------------------------------------------
    slip_coefficient: float = 0.08         # slip gain (dimensionless)
    terrain_friction: float = 0.70         # Coulomb traction coefficient mu
    lateral_resistance_coefficient: float = 0.50  # skid-steer turning resistance
    steering_inefficiency: float = 0.0     # ICR expansion chi; <=0 => derived
    lateral_slip_gain: float = 0.05        # lateral skid velocity gain [s]
    rolling_resistance: float = 0.04       # rolling resistance coefficient
    terrain_slope: float = 0.0             # pitch of terrain along heading [rad]

    # --- Misc -------------------------------------------------------------
    standstill_threshold: float = 0.02     # [m/s]
    excessive_slip_threshold: float = 0.35

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TrackedVehicleParams:
        """Build parameters from a (possibly partial) mapping, ignoring unknown keys."""
        data = data or {}
        known = {f.name for f in fields(cls)}
        params = cls(**{k: float(v) for k, v in data.items() if k in known})
        params.validate()
        return params

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @property
    def chi(self) -> float:
        """Steering inefficiency (ICR expansion factor, >= 1).

        Skid steering needs more track speed difference than an ideal differential
        drive to achieve a given yaw rate because the tracks scrub sideways. The
        derived value grows with the contact-length to track-separation ratio.
        """
        if self.steering_inefficiency > 0.0:
            return max(1.0, self.steering_inefficiency)
        return 1.0 + self.lateral_resistance_coefficient * (
            self.track_contact_length / self.track_separation
        )

    @property
    def yaw_inertia(self) -> float:
        """Approximate yaw inertia of a uniform box [kg m^2]."""
        return self.vehicle_mass * (self.vehicle_length**2 + self.vehicle_width**2) / 12.0

    def validate(self) -> None:
        positive = [
            "vehicle_mass", "track_separation", "track_contact_length", "max_vehicle_speed",
            "research_speed_limit", "max_acceleration", "max_deceleration",
            "emergency_deceleration", "max_yaw_rate", "max_yaw_acceleration",
            "track_time_constant", "yaw_time_constant", "terrain_friction",
        ]
        for name in positive:
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and > 0 (got {value})")
        non_negative = [
            "command_latency", "braking_latency", "slip_coefficient",
            "lateral_resistance_coefficient", "lateral_slip_gain", "rolling_resistance",
        ]
        for name in non_negative:
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and >= 0 (got {value})")
        if self.research_speed_limit > self.max_vehicle_speed:
            raise ValueError("research_speed_limit must not exceed max_vehicle_speed")
        if abs(self.terrain_slope) >= math.pi / 2:
            raise ValueError("terrain_slope must be within (-pi/2, pi/2)")
