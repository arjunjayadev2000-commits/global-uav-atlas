"""Approximate heavy tracked vehicle dynamics (simulation only)."""

from .model import TrackDemand, TrackedVehicleModel, TrackedVehicleState
from .params import GRAVITY, TrackedVehicleParams
from .yaml_loader import load_vehicle_params

__all__ = [
    "GRAVITY",
    "TrackDemand",
    "TrackedVehicleModel",
    "TrackedVehicleParams",
    "TrackedVehicleState",
    "load_vehicle_params",
]
