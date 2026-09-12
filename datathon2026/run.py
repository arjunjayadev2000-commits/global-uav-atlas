#!/usr/bin/env python3
"""Command-line entry point for the Datathon 2026 supply-chain analysis.

Examples
--------
    python run.py --all                 # full pipeline, figures and report
    python run.py --stage analysis      # analysis only, no figures or report
    python run.py --all --force-ingest  # rebuild the cleaned parquet caches
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from dcsc.io_utils import get_logger
from dcsc.pipeline import run as run_pipeline

LOG = get_logger("dcsc.run")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="run everything: analysis, figures, Power BI export, report")
    parser.add_argument(
        "--stage",
        choices=["analysis", "figures", "powerbi", "report"],
        help="run a single stage (analysis implies ingest)",
    )
    parser.add_argument("--force-ingest", action="store_true", help="ignore the cached parquet files")
    parser.add_argument("--no-forecast", action="store_true", help="skip the forecast backtest (saves ~1 minute)")
    args = parser.parse_args(argv)

    if not args.all and not args.stage:
        parser.print_help()
        return 1

    want_figures = args.all or args.stage in {"figures", None}
    result = run_pipeline(
        force_ingest=args.force_ingest,
        with_forecast=not args.no_forecast,
        with_figures=want_figures,
    )

    if args.all or args.stage == "powerbi":
        from dcsc.powerbi.export import export_model

        export_model(result)

    if args.all or args.stage == "report":
        from dcsc.report.build_report import build

        path = build(result)
        LOG.info("report written to %s", path)

    LOG.info("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
