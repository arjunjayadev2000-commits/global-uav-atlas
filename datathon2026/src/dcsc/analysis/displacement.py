"""Traffic displacement: reading conflict off the *absence* of ships.

Conflict shows up in the maritime picture in two opposite ways.

*Identification* failure - ships still sail, but stop being identifiable. That is
the dark-spot signal (see :mod:`darkspots`).

*Avoidance* - ships stop sailing there at all. The Red Sea is the textbook case:
after the attack campaign on shipping, the traffic did not go dark, it went
around Africa. The correct instrument is therefore not the dark rate but the
traffic count, compared against a corridor that carries the diverted flow.

Because Sentinel-1 does not image every sea equally often, every comparison here
is normalised by the number of scenes that actually observed the corridor.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..features.maritime_features import SOLAS_LENGTH_M
from ..io_utils import get_logger, save_table

LOG = get_logger("dcsc.analysis.displacement")

#: The two ways a ship can get from the Indian Ocean to Europe.
SUEZ_ROUTE = ("bab_el_mandeb", "southern_red_sea", "northern_red_sea", "suez_canal")
CAPE_ROUTE = ("cape_of_good_hope",)

#: Categories that represent commercial cargo movement rather than local activity.
COMMERCIAL = ("cargo", "carrier", "bunker", "passenger")


def corridor_traffic(det: pd.DataFrame) -> pd.DataFrame:
    """Traffic intensity per corridor, normalised for satellite revisit."""
    solas = det[det["length_m"] >= SOLAS_LENGTH_M]
    out = (
        solas.groupby(["chokepoint_id", "chokepoint", "theatre"], observed=True)
        .agg(
            solas_detections=("detection_id", "size"),
            scenes=("scene_id", "nunique"),
            commercial=("matched_category", lambda s: int(s.isin(COMMERCIAL).sum())),
            mean_length_m=("length_m", "mean"),
            dark=("is_dark", "sum"),
        )
        .reset_index()
    )
    out["solas_per_scene"] = out["solas_detections"] / out["scenes"]
    out["commercial_per_scene"] = out["commercial"] / out["scenes"]
    out["dark_rate"] = out["dark"] / out["solas_detections"]
    return out.sort_values("solas_per_scene", ascending=False).reset_index(drop=True)


def route_comparison(det: pd.DataFrame) -> pd.DataFrame:
    """Suez routing versus Cape of Good Hope routing over the observed window."""
    solas = det[det["length_m"] >= SOLAS_LENGTH_M].copy()
    solas["route"] = np.select(
        [solas["chokepoint_id"].isin(SUEZ_ROUTE), solas["chokepoint_id"].isin(CAPE_ROUTE)],
        ["Suez / Red Sea route", "Cape of Good Hope route"],
        default="Other",
    )
    routes = solas[solas["route"] != "Other"]
    out = (
        routes.groupby("route", observed=True)
        .agg(
            solas_detections=("detection_id", "size"),
            commercial=("matched_category", lambda s: int(s.isin(COMMERCIAL).sum())),
            scenes=("scene_id", "nunique"),
            mean_length_m=("length_m", "mean"),
            dark_rate=("is_dark", "mean"),
        )
        .reset_index()
    )
    out["solas_per_scene"] = out["solas_detections"] / out["scenes"]
    out["commercial_per_scene"] = out["commercial"] / out["scenes"]
    LOG.info(
        "route comparison: %s",
        out.set_index("route")[["solas_detections", "commercial_per_scene"]].to_dict(),
    )
    return out


def chokepoint_traffic_deficit(traffic: pd.DataFrame, reference_ids: tuple[str, ...]) -> pd.DataFrame:
    """Express each critical corridor's throughput against a peer benchmark.

    The benchmark is the median SOLAS-class throughput per imaged scene across a
    set of *uncontested* reference corridors. A ratio well below 1 on a corridor
    that is normally among the world's busiest is the quantitative form of the
    sentence "the ships are not there any more".

    Two measurement traps are avoided here.

    *Do not measure throughput with the AIS category.* ``matched_category`` is
    only known for vessels the AIS picture identified, so in a corridor where
    most ships are dark the commercial count collapses by construction - the
    concealment would be misread as an evacuation. Throughput is therefore
    counted on radar length alone, which is measured for dark and matched hulls
    alike. ``commercial_per_scene`` is retained only as a secondary, and must
    never be compared between corridors with very different dark rates.

    *Scene counts are inferred from scenes that produced at least one detection
    in the box*, because scene footprints are not in the extract. A corridor that
    is genuinely empty therefore under-counts its own observation opportunities,
    which inflates its per-scene rate. That bias runs against the finding, so a
    measured deficit is a lower bound on the real one.
    """
    ref = traffic[traffic["chokepoint_id"].isin(reference_ids)]
    benchmark = float(ref["solas_per_scene"].median())
    out = traffic.copy()
    out["benchmark_solas_per_scene"] = benchmark
    out["throughput_ratio"] = out["solas_per_scene"] / benchmark
    out["deficit_pct"] = (1 - out["throughput_ratio"]) * 100
    LOG.info("uncontested benchmark = %.1f SOLAS detections per imaged scene", benchmark)
    return out.sort_values("throughput_ratio").reset_index(drop=True)


def run(det: pd.DataFrame, control_corridors: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    traffic = corridor_traffic(det)
    routes = route_comparison(det)
    deficit = chokepoint_traffic_deficit(traffic, control_corridors)
    save_table(traffic, "traffic_by_corridor")
    save_table(routes, "route_suez_vs_cape")
    save_table(deficit, "corridor_throughput_deficit")
    return {"traffic": traffic, "routes": routes, "deficit": deficit}
