"""End-to-end orchestration: raw files in, figures, tables and report out.

Run with ``python run.py --all``. Each stage is independently callable so a
single step can be re-run during analysis without repeating the expensive ones
(the SAR ingest and the forecast backtest dominate the runtime).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .analysis import coupling, darkspots, displacement, eda, forecast, predict, risk_index
from .config import CONTROL_CORRIDORS, OUTPUTS, SETTINGS, ensure_dirs
from .features import conflict_features as cf
from .features import maritime_features as mf
from .features.geo import assign_chokepoint
from .ingest import conflict as conflict_ingest
from .ingest import sar as sar_ingest
from .io_utils import describe_frame, get_logger, utc_stamp, write_json

LOG = get_logger("dcsc.pipeline")

#: Corridors carried through the forecasting stage. Deliberately short: the
#: backtest fits four models per corridor over 26 expanding windows.
FORECAST_CORRIDORS = ("bab_el_mandeb", "hormuz", "black_sea", "suez_canal")


@dataclass
class PipelineResult:
    """Everything the report and the Power BI export need, in one object."""

    frames: dict[str, Any] = field(default_factory=dict)
    figures: dict[str, str] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.frames[key]


def run(
    force_ingest: bool = False,
    with_forecast: bool = True,
    with_figures: bool = True,
) -> PipelineResult:
    ensure_dirs()
    started = time.time()
    result = PipelineResult()
    f = result.frames

    # -- 1. ingest ---------------------------------------------------------
    LOG.info("stage 1/7  ingest")
    conflict = conflict_ingest.build(force=force_ingest)
    det = assign_chokepoint(sar_ingest.build(force=force_ingest))
    f["conflict"] = conflict
    f["detections"] = det

    # -- 2. descriptive ----------------------------------------------------
    LOG.info("stage 2/7  descriptive tables")
    f.update(eda.run(conflict, det))

    # -- 3. features -------------------------------------------------------
    LOG.info("stage 3/7  features")
    f["corridor_profile"] = mf.corridor_profile(det)
    f["daily_corridor"] = mf.daily_corridor_series(det)
    f["vessel_mix"] = mf.vessel_mix(det)
    f["pressure"] = cf.escalation_index(cf.corridor_pressure(conflict))
    f["conflict_units"] = cf.admin_units(conflict)

    # -- 4. dark spots -----------------------------------------------------
    LOG.info("stage 4/7  dark-spot detection")
    dark = darkspots.run(det)
    f["cells"] = dark["surface"]
    f["clusters"] = dark["clusters"]
    f["dark_sensitivity"] = dark["sensitivity"]

    # -- 5. displacement and coupling --------------------------------------
    LOG.info("stage 5/7  displacement and conflict coupling")
    disp = displacement.run(det, CONTROL_CORRIDORS)
    f["traffic"] = disp["traffic"]
    f["routes"] = disp["routes"]
    f["deficit"] = disp["deficit"]

    coup = coupling.run(det, conflict, f["corridor_profile"], f["pressure"])
    f["exposed"] = coup["exposed"]
    f["logit"] = coup["logit"]
    f["cross_section"] = coup["cross"]
    f["cross_stats"] = coup["cross_stats"]
    f["lead_lag"] = coup["lead_lag"]

    # -- 6. prediction and risk -------------------------------------------
    LOG.info("stage 6/7  predictive models and risk index")
    pred = predict.run(f["cells"], f["exposed"])
    f["model_scores"] = pred["scores"]
    f["model_importance"] = pred["importance"]
    f["model_predictions"] = pred["predictions"]

    if with_forecast:
        fc = forecast.run(f["pressure"], FORECAST_CORRIDORS)
        f["forecast_scores"] = fc["scores"]
        f["forecasts"] = fc["forecasts"]
    else:
        # Skipping the backtest is a convenience for iterating on figures, not a
        # way to lose the forecast: reuse the last run's tables if they exist.
        from .io_utils import load_table

        try:
            f["forecast_scores"] = load_table("forecast_backtest_scores")
            f["forecasts"] = load_table("forecast_corridor_12w")
            f["forecasts"]["week"] = pd.to_datetime(f["forecasts"]["week"])
            LOG.info("forecast stage skipped; reusing cached forecast tables")
        except FileNotFoundError:
            LOG.warning("forecast stage skipped and no cached tables found")

    risk = risk_index.run(f["corridor_profile"], f["pressure"], f["deficit"])
    f["msri"] = risk["index"]
    f["watchlist"] = risk["watchlist"]

    # -- 7. figures --------------------------------------------------------
    if with_figures:
        LOG.info("stage 7/7  figures")
        from .viz import charts, maps

        result.figures.update(charts.run_all(f))
        result.figures.update(maps.run_all(det, f["cells"], f["conflict_units"]))

    elapsed = time.time() - started
    result.manifest = {
        "generated_at": utc_stamp(),
        "runtime_seconds": round(elapsed, 1),
        "settings": SETTINGS.__dict__,
        "inputs": [
            describe_frame(conflict, "conflict_weekly"),
            describe_frame(det, "sar_detections"),
        ],
        "figures": sorted(result.figures.values()),
        "headline": {
            "solas_dark_rate_global": float(det.loc[det["length_m"] >= 100, "is_dark"].mean()),
            "dark_spot_cells": int(f["cells"]["is_dark_spot"].sum()),
            "dark_clusters": len(f["clusters"]),
            "red_tier_corridors": int((f["msri"]["tier"] == "RED").sum()),
        },
    }
    write_json(result.manifest, OUTPUTS / "run_manifest.json")
    LOG.info("pipeline complete in %.1fs", elapsed)
    return result
