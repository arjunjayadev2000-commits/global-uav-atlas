"""Shared fixtures. Tests that need the real files are marked ``slow``."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="session")
def synthetic_detections() -> pd.DataFrame:
    """A small, fully controlled detection set with known properties.

    Cell A (Hormuz-like): large hulls, mostly dark, some matched -> behavioural.
    Cell B (coastal):     small craft, all dark                  -> non-carriage.
    Cell C (control):     large hulls, all matched               -> normal.
    """
    rng = np.random.default_rng(7)
    rows = []
    specs = [
        ("A", 25.6, 56.2, 200, 220.0, 0.85),
        ("B", 21.2, 91.2, 200, 20.0, 1.00),
        ("C", 51.0, 1.5, 200, 200.0, 0.02),
    ]
    for tag, lat, lon, n, length, dark_p in specs:
        for i in range(n):
            dark = rng.random() < dark_p
            rows.append(
                {
                    "detection_id": len(rows) + 1,
                    "scene_id": f"S_{tag}_{i % 5}",
                    "timestamp": pd.Timestamp("2026-03-01", tz="UTC") + pd.Timedelta(hours=i % 300),
                    "lat": lat + rng.normal(0, 0.05),
                    "lon": lon + rng.normal(0, 0.05),
                    "presence_score": 0.99,
                    "length_m": max(11.0, length + rng.normal(0, 8)),
                    "mmsi": np.nan if dark else 200000000 + i,
                    "matching_score": 0.0 if dark else 50.0,
                    "fishing_score": 0.9 if length < 30 else 0.02,
                    "matched_category": "unmatched" if dark else "cargo",
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def synthetic_conflict() -> pd.DataFrame:
    weeks = pd.date_range("2025-01-04", periods=60, freq="W-SAT")
    rows = []
    for i, w in enumerate(weeks):
        rows.append(
            {
                "WEEK": w,
                "REGION": "Middle East",
                "COUNTRY": "Testland",
                "ADMIN1": "Coastal",
                "EVENT_TYPE": "Explosions/Remote violence",
                "SUB_EVENT_TYPE": "Air/drone strike",
                "EVENTS": 10 + i % 7,
                "FATALITIES": i % 4,
                "POPULATION_EXPOSURE": 100000,
                "DISORDER_TYPE": "Political violence",
                "ID": 1,
                "CENTROID_LATITUDE": 26.0,
                "CENTROID_LONGITUDE": 56.5,
            }
        )
    return pd.DataFrame(rows)
