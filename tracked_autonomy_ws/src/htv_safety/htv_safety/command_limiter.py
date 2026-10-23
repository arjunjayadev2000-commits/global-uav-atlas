"""Heavy-vehicle command limiter (ROS-agnostic).

Applies, in order: speed cap (research limit x safety speed scale, and the
stopping-distance cap), yaw-rate cap, minimum turning radius (no pivot turns
unless explicitly enabled), curvature-preserving scaling, then acceleration and
yaw-acceleration rate limits. Deceleration toward zero is always permitted at the
higher braking rate so the limiter never delays a stop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class LimiterConfig:
    research_speed_limit: float = 1.0
    research_reverse_speed_limit: float = 0.5
    research_yaw_rate_limit: float = 0.15
    max_acceleration: float = 0.3
    max_deceleration: float = 1.0
    max_yaw_acceleration: float = 0.15
    allow_pivot_turns: bool = False
    min_turning_radius: float = 4.0       # [m], used when pivots are disabled
    allow_reverse: bool = True


def _approach(current: float, target: float, up_rate: float, down_rate: float, dt: float) -> float:
    """Move ``current`` toward ``target``; moving toward zero uses ``down_rate``."""
    if target == current:
        return target
    toward_zero = abs(target) < abs(current) or current * target < 0.0
    step = (down_rate if toward_zero else up_rate) * dt
    if target > current:
        return min(target, current + step)
    return max(target, current - step)


class CommandLimiter:
    def __init__(self, config: LimiterConfig | None = None) -> None:
        self.config = config or LimiterConfig()
        self.last_linear = 0.0
        self.last_yaw = 0.0

    def reset(self) -> None:
        self.last_linear = 0.0
        self.last_yaw = 0.0

    def limit(
        self,
        linear: float,
        yaw: float,
        dt: float,
        speed_scale: float = 1.0,
        speed_cap: float | None = None,
    ) -> tuple[float, float]:
        c = self.config
        if not (math.isfinite(linear) and math.isfinite(yaw)):
            linear, yaw = 0.0, 0.0
        scale = max(0.0, min(1.0, speed_scale))
        fwd = c.research_speed_limit * scale
        rev = (c.research_reverse_speed_limit if c.allow_reverse else 0.0) * scale
        if speed_cap is not None:
            fwd = min(fwd, max(0.0, speed_cap))
            rev = min(rev, max(0.0, speed_cap))

        v = max(-rev, min(fwd, linear))
        # Preserve the requested path curvature when the speed is reduced.
        if linear != 0.0 and v != linear:
            yaw *= v / linear
        w_cap = c.research_yaw_rate_limit * scale
        w = max(-w_cap, min(w_cap, yaw))
        if not c.allow_pivot_turns:
            max_w = abs(v) / c.min_turning_radius
            if abs(w) > max_w:
                w = math.copysign(max_w, w)

        dt = max(dt, 0.0)
        v = _approach(self.last_linear, v, c.max_acceleration, c.max_deceleration, dt)
        w = _approach(self.last_yaw, w, c.max_yaw_acceleration, 2.0 * c.max_yaw_acceleration, dt)
        if not c.allow_pivot_turns:
            # Re-apply after rate limiting: a decelerating vehicle must tighten no turn.
            max_w = abs(v) / c.min_turning_radius
            w = max(-max_w, min(max_w, w))
        self.last_linear, self.last_yaw = v, w
        return v, w
