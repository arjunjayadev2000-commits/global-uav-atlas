"""Worlds are well-formed, up to date with the generator and contain the required features."""

import importlib.util
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
WORLDS = ["01_flat_test_track", "02_obstacle_course", "03_rough_terrain", "04_slope_course",
          "05_gnss_degraded_course"]


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_worlds", PKG / "scripts" / "generate_worlds.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", WORLDS)
def test_world_parses_and_has_required_systems(name):
    root = ET.parse(PKG / "worlds" / f"{name}.sdf").getroot()
    assert root.tag == "sdf"
    plugins = {p.get("name") for p in root.iter("plugin")}
    for system in ("Physics", "Sensors", "Imu", "NavSat"):
        assert f"gz::sim::systems::{system}" in plugins
    assert root.find(".//spherical_coordinates") is not None
    assert len(root.findall(".//model")) > 5


@pytest.mark.parametrize("name", WORLDS)
def test_world_matches_generator(name, tmp_path):
    gen = load_generator()
    assert gen.WORLDS[name]() == (PKG / "worlds" / f"{name}.sdf").read_text()


def test_required_features_exist():
    names = {
        w: {m.get("name") for m in ET.parse(PKG / "worlds" / f"{w}.sdf").getroot().iter("model")} for w in WORLDS
    }
    assert any(n.startswith("corridor") for n in names["02_obstacle_course"])
    assert any("ditch" in n for n in names["02_obstacle_course"])
    assert any(n.startswith("rock") for n in names["03_rough_terrain"])
    assert {"up_5", "up_10", "up_15", "up_20"} <= names["04_slope_course"]
    assert "overpass_deck" in names["05_gnss_degraded_course"]


def test_no_battlefield_content():
    banned = ("bunker", "trench_line", "target", "enemy", "weapon", "mine")
    for w in WORLDS:
        text = (PKG / "worlds" / f"{w}.sdf").read_text().lower()
        assert not [b for b in banned if b in text], w


@pytest.mark.skipif(shutil.which("gz") is None, reason="gazebo not installed")
@pytest.mark.parametrize("name", WORLDS)
def test_gz_sdf_check(name):
    result = subprocess.run(["gz", "sdf", "-k", str(PKG / "worlds" / f"{name}.sdf")],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0 and "Valid" in result.stdout, result.stdout + result.stderr
