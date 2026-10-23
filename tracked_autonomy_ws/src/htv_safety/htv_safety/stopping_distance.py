"""Simulation-only stopping-distance estimator and speed cap.

    stopping_distance = reaction_distance + braking_distance + safety_margin

    reaction_distance = v * (command_latency + braking_latency + reaction_time)
    braking_distance  = v^2 / (2 * a_eff)
    a_eff             = min(max_deceleration, mu * g * cos(theta)) + g * sin(theta)
    safety_margin     = margin_fixed + margin_ratio * (reaction + braking)

``theta`` is the terrain pitch along the direction of travel (positive uphill).
Unknown terrain (low confidence) uses conservative traction and slope defaults,
and terrain confidence additionally scales the permitted speed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

GRAVITY = 9.80665


@dataclass
class StoppingDistanceConfig:
    max_deceleration: float = 1.5
    command_latency: float = 0.25
    braking_latency: float = 0.40
    reaction_time: float = 0.20          # supervisor detection + compute
    margin_fixed: float = 1.0            # [m]
    margin_ratio: float = 0.25
    # Conservative defaults for unknown terrain.
    unknown_traction: float = 0.35
    unknown_slope: float = math.radians(-8.0)   # assume a downhill
    min_terrain_confidence: float = 0.3
    unknown_terrain_speed: float = 0.3   # [m/s] cap when terrain unknown
    min_confidence_scale: float = 0.4
    min_effective_deceleration: float = 0.05


@dataclass
class StoppingEstimate:
    velocity: float
    reaction_distance: float
    braking_distance: float
    safety_margin: float
    stopping_distance: float
    effective_deceleration: float
    traction: float
    slope: float
    confidence: float


class StoppingDistanceEstimator:
    def __init__(self, config: StoppingDistanceConfig | None = None) -> None:
        self.config = config or StoppingDistanceConfig()

    def _terrain(self, traction: float | None, slope: float | None, confidence: float) -> tuple[float, float]:
        c = self.config
        known = confidence >= c.min_terrain_confidence
        mu = traction if (known and traction is not None) else c.unknown_traction
        theta = slope if (known and slope is not None) else c.unknown_slope
        # Even with known terrain, never assume better than the conservative default
        # when braking downhill on poorer data.
        return max(0.01, mu), theta

    def effective_deceleration(self, traction: float, slope: float) -> float:
        c = self.config
        a = min(c.max_deceleration, traction * GRAVITY * math.cos(slope)) + GRAVITY * math.sin(slope)
        return max(a, c.min_effective_deceleration)

    @property
    def dead_time(self) -> float:
        c = self.config
        return c.command_latency + c.braking_latency + c.reaction_time

    def estimate(
        self,
        velocity: float,
        traction: float | None = None,
        slope: float | None = None,
        confidence: float = 0.0,
    ) -> StoppingEstimate:
        c = self.config
        v = abs(velocity)
        mu, theta = self._terrain(traction, slope, confidence)
        # Slope along the direction of travel: reversing flips it.
        if velocity < 0.0:
            theta = -theta
        a = self.effective_deceleration(mu, theta)
        reaction = v * self.dead_time
        braking = v * v / (2.0 * a)
        margin = c.margin_fixed + c.margin_ratio * (reaction + braking)
        return StoppingEstimate(
            velocity=velocity,
            reaction_distance=reaction,
            braking_distance=braking,
            safety_margin=margin,
            stopping_distance=reaction + braking + margin,
            effective_deceleration=a,
            traction=mu,
            slope=theta,
            confidence=confidence,
        )

    def max_safe_velocity(
        self,
        available_distance: float,
        traction: float | None = None,
        slope: float | None = None,
        confidence: float = 0.0,
    ) -> float:
        """Largest speed whose stopping distance fits in ``available_distance``."""
        c = self.config
        mu, theta = self._terrain(traction, slope, confidence)
        a = self.effective_deceleration(mu, theta)
        # (1 + r) * (v*t + v^2 / 2a) + m <= D
        budget = (available_distance - c.margin_fixed) / (1.0 + c.margin_ratio)
        if budget <= 0.0:
            return 0.0
        t = self.dead_time
        v = a * (-t + math.sqrt(t * t + 2.0 * budget / a))
        if confidence < c.min_terrain_confidence:
            return min(v, c.unknown_terrain_speed)
        span = 1.0 - c.min_terrain_confidence
        frac = (confidence - c.min_terrain_confidence) / span if span > 0 else 1.0
        scale = c.min_confidence_scale + (1.0 - c.min_confidence_scale) * min(1.0, frac)
        return v * scale
