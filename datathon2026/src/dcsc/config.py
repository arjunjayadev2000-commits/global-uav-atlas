"""Paths, tunables and the reference geography used across the pipeline.

Everything that a reviewer might want to change - a detection confidence floor,
the grid resolution of the dark-spot search, the radius that ties a conflict
event to a sea lane - is declared here rather than buried in analysis code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_INTERIM = PROJECT_ROOT / "data" / "interim"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"

OUTPUTS = PROJECT_ROOT / "outputs"
FIGURES = OUTPUTS / "figures"
TABLES = OUTPUTS / "tables"
POWERBI = OUTPUTS / "powerbi"
REPORT = OUTPUTS / "report"

CONFIG_DIR = PROJECT_ROOT / "config"

CONFLICT_XLSX = DATA_RAW / "acled_middle_east_weekly_2026-06-27.xlsx"
SAR_CSV = DATA_RAW / "sar_vessel_detections_2026-03.csv"

# Interim (cleaned) artefacts, written by the ingest stage.
CONFLICT_PARQUET = DATA_INTERIM / "conflict_weekly.parquet"
SAR_PARQUET = DATA_INTERIM / "sar_detections.parquet"


def ensure_dirs() -> None:
    """Create every output directory the pipeline writes into."""
    for path in (DATA_INTERIM, DATA_PROCESSED, FIGURES, TABLES, POWERBI, REPORT):
        path.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Analysis tunables
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    """Analysis parameters. Frozen so a run cannot mutate them halfway through."""

    # --- SAR detection quality ---
    presence_score_floor: float = 0.90
    """Detections below this model confidence are dropped as probable clutter."""

    min_length_m: float = 10.0
    """Objects shorter than this are below the reliable Sentinel-1 IW detection size."""

    # --- AIS matching ---
    match_score_floor: float = 1.0
    """A detection carrying an MMSI but a correlation score below this is treated as a
    weak association rather than a confirmed AIS match (a 'possible dark' vessel)."""

    # --- Dark-spot search ---
    grid_deg: float = 0.5
    """Edge length of the equal-angle cells used for the dark-rate surface."""

    min_cell_detections: int = 25
    """A cell needs this many detections before its dark rate is tested."""

    dbscan_eps_km: float = 60.0
    """Neighbourhood radius for clustering dark detections into named dark spots."""

    dbscan_min_samples: int = 40
    """Minimum dark detections that make a cluster, not noise."""

    # --- Conflict / maritime coupling ---
    coastal_buffer_km: float = 250.0
    """A conflict event within this distance of a corridor box counts as pressure on it."""

    maritime_event_types: tuple[str, ...] = (
        "Explosions/Remote violence",
        "Battles",
    )
    """Event types that plausibly produce electromagnetic and navigational disruption."""

    maritime_sub_events: tuple[str, ...] = (
        "Air/drone strike",
        "Shelling/artillery/missile attack",
        "Remote explosive/landmine/IED",
        "Armed clash",
        "Attack",
    )

    # --- Forecasting ---
    forecast_horizon_weeks: int = 12
    backtest_weeks: int = 26
    random_state: int = 20260930

    # --- Reporting ---
    report_title: str = "Global Conflicts - Impact on Supply Chains"
    report_subtitle: str = "AIS dark spots, chokepoint exposure and the maritime cost of conflict"
    figure_dpi: int = 160


SETTINGS = Settings()


# --------------------------------------------------------------------------
# Reference geography
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Chokepoint:
    """A rectangular sea-lane box used to bucket points into corridors."""

    id: str
    name: str
    theatre: str
    priority: int
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    critical: bool = False
    note: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def centroid(self) -> tuple[float, float]:
        return ((self.lat_min + self.lat_max) / 2.0, (self.lon_min + self.lon_max) / 2.0)

    def contains(self, lat: float, lon: float) -> bool:
        return self.lat_min <= lat <= self.lat_max and self.lon_min <= lon <= self.lon_max


@lru_cache(maxsize=1)
def load_chokepoints() -> tuple[Chokepoint, ...]:
    """Load the corridor boxes, ordered so narrow straits are matched before basins."""
    payload = json.loads((CONFIG_DIR / "chokepoints.json").read_text(encoding="utf-8"))
    points = [
        Chokepoint(
            id=row["id"],
            name=row["name"],
            theatre=row["theatre"],
            priority=int(row["priority"]),
            lat_min=float(row["lat_min"]),
            lat_max=float(row["lat_max"]),
            lon_min=float(row["lon_min"]),
            lon_max=float(row["lon_max"]),
            critical=bool(row.get("critical", False)),
            note=str(row.get("note", "")),
        )
        for row in payload["chokepoints"]
    ]
    # Smaller priority number first; ties broken by box area so the tighter box wins.
    points.sort(key=lambda c: (c.priority, (c.lat_max - c.lat_min) * (c.lon_max - c.lon_min)))
    return tuple(points)


#: Corridors that sit inside, or immediately downstream of, the Middle East conflict
#: theatre covered by the ACLED extract. Used for the coupling analysis.
CONFLICT_EXPOSED_CORRIDORS: tuple[str, ...] = (
    "bab_el_mandeb",
    "southern_red_sea",
    "northern_red_sea",
    "suez_canal",
    "gulf_of_aden",
    "hormuz",
    "persian_gulf",
    "gulf_of_oman",
    "eastern_med",
    "black_sea",
)

#: Corridors used as the peacetime control group when testing dark-rate elevation.
CONTROL_CORRIDORS: tuple[str, ...] = (
    "dover",
    "gibraltar",
    "panama",
    "singapore_strait",
    "malacca",
    "sunda",
    "lombok",
    "cape_of_good_hope",
    "bay_of_bengal",
)
