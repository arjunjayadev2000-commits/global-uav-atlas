"""Backend discovery via the ``htv_vehicle_interface.backends`` entry point group.

Only the ``simulated`` backend is registered by this repository. A separately
developed adapter package registers itself under the same group; it is loaded
only when the operator explicitly sets ``allow_non_simulated_backends: true``.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

from .interface import LegacyTrackedVehicleInterface
from .simulated import ActuationSink, SimulatedLegacyTrackedVehicleInterface

ENTRY_POINT_GROUP = "htv_vehicle_interface.backends"
SIMULATED_BACKENDS = frozenset({"simulated"})


class BackendNotAllowedError(RuntimeError):
    pass


def available_backends() -> dict[str, Any]:
    found = {ep.name: ep for ep in entry_points(group=ENTRY_POINT_GROUP)}
    found.setdefault("simulated", SimulatedLegacyTrackedVehicleInterface)
    return found


def create_backend(
    name: str,
    config: dict[str, Any],
    actuation_sink: ActuationSink | None = None,
    allow_non_simulated: bool = False,
) -> LegacyTrackedVehicleInterface:
    if name not in SIMULATED_BACKENDS and not allow_non_simulated:
        raise BackendNotAllowedError(
            f"backend '{name}' is not a simulation backend; this build is simulation-only"
        )
    backends = available_backends()
    if name not in backends:
        raise KeyError(f"unknown vehicle backend '{name}'; available: {sorted(backends)}")
    target = backends[name]
    cls = target.load() if hasattr(target, "load") else target
    backend = cls.from_config(config, actuation_sink=actuation_sink)
    if not isinstance(backend, LegacyTrackedVehicleInterface):
        raise TypeError(f"backend '{name}' does not implement LegacyTrackedVehicleInterface")
    return backend
