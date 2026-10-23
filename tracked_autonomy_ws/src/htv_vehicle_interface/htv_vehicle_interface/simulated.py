"""The only backend shipped in this repository: a simulated vehicle interface.

It turns the generic :class:`ActuationRequest` into a ``SimTrackDemand`` for the
simulated tracked-vehicle plant. It contains no knowledge of any real vehicle's
controls, actuators or electrical system.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields
from typing import Any

from .interface import ActuationRequest, GuardedVehicleInterfaceBase, InterfaceLimits

ActuationSink = Callable[[ActuationRequest, float], None]


class SimulatedLegacyTrackedVehicleInterface(GuardedVehicleInterfaceBase):
    backend_name = "simulated"

    def __init__(self, limits: InterfaceLimits | None = None, actuation_sink: ActuationSink | None = None) -> None:
        super().__init__(limits)
        self._sink = actuation_sink

    @classmethod
    def from_config(cls, config: dict[str, Any], actuation_sink: ActuationSink | None = None):
        known = {f.name for f in fields(InterfaceLimits)}
        limits = InterfaceLimits(**{k: float(v) for k, v in config.items() if k in known})
        return cls(limits, actuation_sink)

    def _actuate(self, request: ActuationRequest, now: float) -> None:
        if self._sink is not None:
            self._sink(request, now)
