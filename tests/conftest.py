"""Shared fixtures.

Every test that touches the database gets its own temporary SQLite file so the
suite never mutates a real run, and the module-level connection cache in
:mod:`app.db` is reset between tests.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    """Point every writable path at a temp directory for the duration of a test."""
    from app import config, db

    paths = config.Paths(
        root=tmp_path,
        data=tmp_path / "data",
        seed=tmp_path / "data" / "seed",
        imports=tmp_path / "data" / "imports",
        cache=tmp_path / "data" / "cache",
        images=tmp_path / "images",
        output=tmp_path / "output",
        logs=tmp_path / "logs",
        docs=tmp_path / "docs",
    )
    paths.ensure()
    settings = config.Settings(paths=paths, database_path=tmp_path / "data" / "test.sqlite")
    monkeypatch.setattr(config, "SETTINGS", settings)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    for module_name in (
        "app.db",
        "app.logging",
        "crawlers.http",
        "agents.image_discovery_agent",
        "agents.image_validation_agent",
        "agents.image_license_agent",
        "agents.export_agent",
        "agents.atlas_builder_agent",
        "agents.discovery_agent",
        "agents.deduplication_agent",
        "crawlers.wikimedia",
    ):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "get_settings"):
            monkeypatch.setattr(module, "get_settings", lambda: settings, raising=False)

    db.close()
    yield settings
    db.close()


@pytest.fixture()
def database(_isolated_paths):
    from app import db

    conn = db.connect(fresh=True)
    db.migrate(conn)
    return conn


@pytest.fixture()
def seed_dir(_isolated_paths) -> Path:
    """A miniature seed package with the same column layout as the real one."""
    directory = _isolated_paths.paths.seed
    directory.mkdir(parents=True, exist_ok=True)

    (directory / "Global_UAV_Database_2026.csv").write_text(
        "record_id,platform_name,country_of_origin,manufacturer,domain,category,status,"
        "aliases,model_codes,source_count,source_datasets,source_urls,notes\n"
        "UAV-0001,MQ-9A Reaper,United States,General Atomics,Military,MALE fixed-wing,"
        "In service,Predator B,MQ-9,2,Curated UAV Seed 2026 | Bard Drone Databook 2019,"
        "internal,ISR / strike\n"
        "UAV-0002,Bayraktar TB2,Türkiye,Baykar,Military,MALE fixed-wing,In service,,TB2,"
        "1,Curated UAV Seed 2026,internal,Armed UAV\n"
        "UAV-0003,DJI Mavic 3,China,DJI,Civilian / Commercial,Consumer multirotor,"
        "In production,,,1,OpenDroneList,https://example.invalid,Consumer\n",
        encoding="utf-8",
    )
    (directory / "Global_UAV_Database_2026_Source_Records.csv").write_text(
        "source_record_id,platform_name,country_of_origin,manufacturer,domain,category,"
        "status,source_dataset,source_url,source_date,notes\n"
        "SRC-0001,MQ-9A Reaper,United States,General Atomics,Military,MALE fixed-wing,"
        "In service,Curated UAV Seed 2026,internal,2026-08-02,ISR\n"
        "SRC-0002,MQ-9A Reaper,United States,,Military,MALE fixed-wing,In service,"
        "Bard Drone Databook 2019,https://example.invalid/databook,2019-09-01,ISR\n"
        "SRC-0003,Mavic 3,China,DJI,Civilian / Commercial,Consumer multirotor,"
        "In production,OpenDroneList,https://example.invalid,2026-08-02,Consumer\n",
        encoding="utf-8",
    )
    return directory


@pytest.fixture()
def png_bytes():
    """Factory for real, decodable PNG bytes of a given size."""
    from PIL import Image

    def _make(width: int = 900, height: int = 600, colour: tuple[int, int, int] = (40, 90, 160)):
        buffer = io.BytesIO()
        image = Image.new("RGB", (width, height), colour)
        # A little structure so perceptual hashes of different colours differ.
        for x in range(0, width, 40):
            for y in range(0, height, 40):
                if (x // 40 + y // 40) % 2 == 0:
                    image.paste((255 - colour[0], 255 - colour[1], 255 - colour[2]), (x, y, x + 20, y + 20))
        image.save(buffer, "PNG")
        return buffer.getvalue()

    return _make


@pytest.fixture()
def no_network(monkeypatch):
    """Make any accidental real HTTP call fail loudly."""
    import requests

    def _boom(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(requests.Session, "get", _boom)
    monkeypatch.setattr(requests, "get", _boom)


os.environ.setdefault("UAV_LOG_LEVEL", "WARNING")
