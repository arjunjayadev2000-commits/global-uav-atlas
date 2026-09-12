"""Geospatial helpers: great-circle distance, grid binning and corridor tagging.

No GIS dependency is used on purpose. Everything the analysis needs - distance,
equal-angle cells, rectangle membership, area-corrected cell weights - is a few
lines of numpy, which keeps the project installable anywhere a Python
interpreter and pandas exist (a real constraint on service networks).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import SETTINGS, Chokepoint, load_chokepoints

EARTH_RADIUS_KM = 6371.0088


def haversine_km(
    lat1: np.ndarray | float,
    lon1: np.ndarray | float,
    lat2: np.ndarray | float,
    lon2: np.ndarray | float,
) -> np.ndarray:
    """Great-circle distance in km; broadcasts over numpy arrays."""
    lat1r, lon1r, lat2r, lon2r = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def assign_chokepoint(df: pd.DataFrame, lat_col: str = "lat", lon_col: str = "lon") -> pd.DataFrame:
    """Tag each row with the corridor box that contains it.

    Boxes overlap by design (the Gulf of Aden sits inside the wider Horn
    approaches), so they are applied in the priority order defined by
    :func:`config.load_chokepoints`: the first box to claim a point keeps it,
    and priority is ordered narrow-strait-first.
    """
    out = df.copy()
    out["chokepoint_id"] = pd.NA
    out["chokepoint"] = pd.NA
    out["theatre"] = pd.NA
    lat = out[lat_col].to_numpy()
    lon = out[lon_col].to_numpy()
    unassigned = np.ones(len(out), dtype=bool)

    for cp in load_chokepoints():
        if not unassigned.any():
            break
        inside = (
            unassigned
            & (lat >= cp.lat_min)
            & (lat <= cp.lat_max)
            & (lon >= cp.lon_min)
            & (lon <= cp.lon_max)
        )
        if inside.any():
            out.loc[inside, "chokepoint_id"] = cp.id
            out.loc[inside, "chokepoint"] = cp.name
            out.loc[inside, "theatre"] = cp.theatre
            unassigned &= ~inside

    out["chokepoint_id"] = out["chokepoint_id"].fillna("open_ocean")
    out["chokepoint"] = out["chokepoint"].fillna("Open ocean / other")
    out["theatre"] = out["theatre"].fillna("Other")
    return out


def distance_to_chokepoints(
    lat: np.ndarray, lon: np.ndarray, corridors: tuple[Chokepoint, ...] | None = None
) -> pd.DataFrame:
    """Distance in km from every point to the *edge* of every corridor box.

    Distance is measured to the nearest point of the rectangle rather than to its
    centroid: an air strike on the Yemeni coast is adjacent to the Bab-el-Mandeb
    lane even though the box centroid is 100 km offshore.
    """
    corridors = corridors or load_chokepoints()
    result = {}
    for cp in corridors:
        near_lat = np.clip(lat, cp.lat_min, cp.lat_max)
        near_lon = np.clip(lon, cp.lon_min, cp.lon_max)
        result[cp.id] = haversine_km(lat, lon, near_lat, near_lon)
    return pd.DataFrame(result)


def add_grid(
    df: pd.DataFrame,
    deg: float | None = None,
    lat_col: str = "lat",
    lon_col: str = "lon",
) -> pd.DataFrame:
    """Add equal-angle grid-cell keys and the cell's true surface area.

    Equal-angle cells shrink towards the poles, so any density expressed per cell
    must be divided by ``cell_area_km2`` before cells at different latitudes are
    compared.
    """
    deg = deg or SETTINGS.grid_deg
    out = df.copy()
    out["cell_lat"] = np.floor(out[lat_col] / deg) * deg
    out["cell_lon"] = np.floor(out[lon_col] / deg) * deg
    out["cell_id"] = (
        out["cell_lat"].round(3).astype(str) + "_" + out["cell_lon"].round(3).astype(str)
    )
    lat_rad = np.radians(out["cell_lat"].to_numpy())
    lat_top = np.radians(out["cell_lat"].to_numpy() + deg)
    out["cell_area_km2"] = (
        (np.radians(deg)) * (EARTH_RADIUS_KM**2) * np.abs(np.sin(lat_top) - np.sin(lat_rad))
    )
    return out


def wilson_interval(successes: np.ndarray, trials: np.ndarray, z: float = 1.96) -> tuple:
    """Wilson score interval for a binomial proportion.

    Used instead of the normal approximation because dark-rate cells routinely
    have small denominators, where the naive interval is badly wrong and would
    manufacture 'dark spots' out of three detections.
    """
    successes = np.asarray(successes, dtype=float)
    trials = np.asarray(trials, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        phat = np.where(trials > 0, successes / trials, np.nan)
        denom = 1.0 + z**2 / trials
        centre = (phat + z**2 / (2 * trials)) / denom
        margin = (
            z * np.sqrt(phat * (1 - phat) / trials + z**2 / (4 * trials**2)) / denom
        )
    return centre - margin, centre + margin


def bbox_area_km2(cp: Chokepoint) -> float:
    """Surface area of a corridor box in km^2 (for traffic density per corridor)."""
    lat1, lat2 = np.radians(cp.lat_min), np.radians(cp.lat_max)
    return float(
        np.radians(cp.lon_max - cp.lon_min) * EARTH_RADIUS_KM**2 * abs(np.sin(lat2) - np.sin(lat1))
    )
