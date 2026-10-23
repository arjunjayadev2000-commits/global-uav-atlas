"""Expand the xacro and validate frames, sensor mounts and overrides."""

import math
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
XACRO = PKG / "urdf" / "htv.urdf.xacro"
REQUIRED_FRAMES = {
    "base_link", "base_footprint", "imu_link", "gnss_link", "lidar_link",
    "front_camera_link", "rear_camera_link",
}

pytestmark = pytest.mark.skipif(shutil.which("xacro") is None, reason="xacro not installed")


def expand(*args: str) -> ET.Element:
    out = subprocess.run(["xacro", str(XACRO), *args], check=True, capture_output=True, text=True).stdout
    return ET.fromstring(out)


def links(root):
    return {e.get("name") for e in root.findall("link")}


def joint_origin(root, child):
    for joint in root.findall("joint"):
        if joint.find("child").get("link") == child:
            return [float(v) for v in joint.find("origin").get("xyz").split()]
    raise KeyError(child)


def test_required_frames_present():
    assert links(expand()) >= REQUIRED_FRAMES


def test_tree_is_connected_from_base_footprint():
    root = expand("enable_secondary_lidar:=true")
    parent = {j.find("child").get("link"): j.find("parent").get("link") for j in root.findall("joint")}
    for link in links(root) - {"base_footprint"}:
        seen, node = set(), link
        while node != "base_footprint":
            assert node not in seen, f"cycle at {node}"
            seen.add(node)
            node = parent[node]


def test_secondary_lidar_optional():
    assert "lidar_secondary_link" not in links(expand())
    assert "lidar_secondary_link" in links(expand("enable_secondary_lidar:=true"))


def test_sensor_config_override(tmp_path):
    text = (PKG / "config" / "sensor_mounts.yaml").read_text()
    custom = tmp_path / "mounts.yaml"
    custom.write_text(text.replace("xyz: [0.80, 0.0, 2.45]", "xyz: [1.25, 0.0, 3.10]"))
    xyz = joint_origin(expand(f"sensor_config:={custom}"), "lidar_link")
    assert xyz == pytest.approx([1.25, 0.0, 3.10])


def test_gazebo_sensors_only_with_gazebo():
    assert expand().find(".//sensor") is None
    root = expand("use_gazebo:=true")
    types = {s.get("type") for s in root.iter("sensor")}
    assert {"gpu_lidar", "camera", "imu", "navsat"} <= types
    plugins = {p.get("name") for p in root.iter("plugin")}
    assert "gz::sim::systems::VelocityControl" in plugins


def test_mass_and_base_height():
    root = expand()
    base = next(e for e in root.findall("link") if e.get("name") == "base_link")
    assert float(base.find("inertial/mass").get("value")) == pytest.approx(42000.0)
    assert joint_origin(root, "base_link")[2] == pytest.approx(0.5)


def test_no_weapon_or_mission_frames():
    banned = ("weapon", "turret", "gun", "target", "launcher", "fire")
    names = links(expand("enable_secondary_lidar:=true"))
    assert not [n for n in names if any(b in n for b in banned)]


def test_camera_optical_frames():
    root = expand()
    for cam in ("front_camera", "rear_camera"):
        assert f"{cam}_optical_frame" in links(root)
    assert math.isfinite(joint_origin(root, "rear_camera_link")[0])
