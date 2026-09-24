"""Run the full Theme 6.1 pipeline end to end (raw data -> figures, tables, metrics, Power BI tables)."""

# =====================================================================================================
# ANNOTATED SOURCE - run_all.py:  cd analysis && python run_all.py
# Deletes the metrics file first so no stale number survives, then runs every stage in order.
# =====================================================================================================
import runpy
from pathlib import Path

from common import METRICS

HERE = Path(__file__).parent
METRICS.unlink(missing_ok=True)
for stage in ["01_preprocess", "02_growth", "03_actors", "04_congestion", "05_contest", "06_spaceweather", "07_eo_value",
              "08_forecast", "09_india_iw", "10_powerbi_export"]:
    runpy.run_path(str(HERE / f"{stage}.py"), run_name="__main__")
