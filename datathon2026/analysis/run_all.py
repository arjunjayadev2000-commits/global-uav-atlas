"""Run the full Datathon-2026 pipeline end to end (raw data -> figures, tables, metrics, Power BI tables)."""
import runpy
from pathlib import Path

from common import METRICS

HERE = Path(__file__).parent
METRICS.unlink(missing_ok=True)
for stage in ["01_preprocess", "02_conflict", "03_chokepoint_index", "04_sar", "05_model", "06_decision", "08_intel",
              "07_powerbi_export"]:
    runpy.run_path(str(HERE / f"{stage}.py"), run_name="__main__")
