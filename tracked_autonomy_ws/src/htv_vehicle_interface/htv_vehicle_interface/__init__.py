"""Vehicle abstraction layer: SafeMotionCommand in, backend-specific actuation out."""

from .interface import (
    ActuationRequest,
    GuardedVehicleInterfaceBase,
    InterfaceLimits,
    LegacyTrackedVehicleInterface,
    MotionCommand,
    StopMode,
    VehicleFeedback,
    VehicleInterfaceState,
    VehicleInterfaceStatus,
)
from .registry import BackendNotAllowedError, available_backends, create_backend
from .simulated import SimulatedLegacyTrackedVehicleInterface

__all__ = [
    "ActuationRequest",
    "BackendNotAllowedError",
    "GuardedVehicleInterfaceBase",
    "InterfaceLimits",
    "LegacyTrackedVehicleInterface",
    "MotionCommand",
    "SimulatedLegacyTrackedVehicleInterface",
    "StopMode",
    "VehicleFeedback",
    "VehicleInterfaceState",
    "VehicleInterfaceStatus",
    "available_backends",
    "create_backend",
]
