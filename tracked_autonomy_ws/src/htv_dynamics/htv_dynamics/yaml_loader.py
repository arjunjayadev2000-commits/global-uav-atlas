"""Load vehicle parameters from a ROS 2 parameter YAML file.

Parameters live under ``/**: ros__parameters: vehicle:`` so every node in the
stack reads the same values; this helper lets non-ROS tools read them too.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .params import TrackedVehicleParams


def extract_vehicle_section(document: dict[str, Any]) -> dict[str, Any]:
    for section in document.values():
        if not isinstance(section, dict):
            continue
        ros_params = section.get("ros__parameters", {})
        if isinstance(ros_params, dict) and isinstance(ros_params.get("vehicle"), dict):
            return ros_params["vehicle"]
    return {}


def load_vehicle_params(*paths: str | Path) -> TrackedVehicleParams:
    """Merge the ``vehicle`` sections of the given YAML files, later files win."""
    merged: dict[str, Any] = {}
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            merged.update(extract_vehicle_section(yaml.safe_load(handle) or {}))
    return TrackedVehicleParams.from_dict(merged)
