"""Run the full Datathon-2026 pipeline end to end (raw data -> figures, tables, metrics, Power BI tables)."""

# =====================================================================================================
# ANNOTATED SOURCE - run_all.py (one command rebuilds everything)
# -----------------------------------------------------------------------------------------------------
# Usage:   cd analysis && python run_all.py
# Runs every stage in order, from raw data to figures, tables, metrics and Power BI tables. The metrics file
# is deleted first so that no stale number can survive. Two runs in a row give identical metrics
# (checked before submission), i.e. the pipeline is deterministic and reproducible.
# Stage 07 (Power BI export) runs last because it copies tables made by the other stages.
# =====================================================================================================

import runpy
from pathlib import Path

from common import METRICS

HERE = Path(__file__).parent
# Start from an empty metrics file so every number is freshly computed.
METRICS.unlink(missing_ok=True)
for stage in ["01_preprocess", "02_conflict", "03_chokepoint_index", "04_sar", "05_model", "06_decision", "08_intel", "09_opendata", "10_infographic_assets", "11_darkwater", "12_portwatch",
              "07_powerbi_export"]:
    # Run each stage script exactly as if it were started on its own.
    runpy.run_path(str(HERE / f"{stage}.py"), run_name="__main__")
