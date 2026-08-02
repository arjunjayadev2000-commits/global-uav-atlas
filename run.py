#!/usr/bin/env python3
"""Command line entry point for the Global UAV Visual Atlas pipeline.

Examples
--------
    python run.py --all
    python run.py --discover
    python run.py --dedupe
    python run.py --images
    python run.py --verify
    python run.py --build
    python run.py --resume
    python run.py --limit 25
    python run.py --country "India"
    python run.py --manufacturer "DJI"
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from app.config import get_settings
from app.logging import configure_logging, run_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Build the Global UAV Visual Atlas 2026.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    stages = parser.add_argument_group("stages (default: --all)")
    stages.add_argument("--all", action="store_true", help="run the complete pipeline")
    stages.add_argument("--discover", action="store_true", help="seed import + discovery passes")
    stages.add_argument("--promote", action="store_true", help="promote raw discoveries to platforms")
    stages.add_argument("--dedupe", action="store_true", help="deduplicate canonical platforms")
    stages.add_argument("--classify", action="store_true", help="re-classify country of origin")
    stages.add_argument("--images", action="store_true", help="acquire and validate images")
    stages.add_argument("--verify", action="store_true", help="verify sources and image identity")
    stages.add_argument("--build", action="store_true", help="build the PDF and HTML atlas")
    stages.add_argument("--export", action="store_true", help="write CSV/XLSX/SQLite exports")
    stages.add_argument("--update", action="store_true", help="incremental refresh (weekly job)")
    stages.add_argument("--sideload-images", action="store_true",
                        help="ingest locally supplied images from data/imports/images/manifest.csv")

    control = parser.add_argument_group("control")
    control.add_argument("--resume", action="store_true", help="skip stages already completed")
    control.add_argument("--limit", type=int, default=None, help="cap records processed per stage")
    control.add_argument("--country", type=str, default=None, help="restrict to one country")
    control.add_argument("--manufacturer", type=str, default=None, help="restrict to one manufacturer")
    control.add_argument("--passes", type=int, default=None, help="number of discovery passes")
    control.add_argument("--skip-images", action="store_true", help="do not attempt image acquisition")
    control.add_argument("--dry-run", action="store_true", help="deduplication only: report, do not merge")

    info = parser.add_argument_group("inspection")
    info.add_argument("--status", action="store_true", help="print pipeline status and exit")
    info.add_argument("--stop-conditions", action="store_true", help="evaluate the stop conditions and exit")
    info.add_argument("--stats", action="store_true", help="print coverage statistics and exit")
    info.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    info.add_argument("--json", action="store_true", help="emit machine-readable JSON results")
    return parser


def _selected_stages(args: argparse.Namespace) -> tuple[str, ...]:
    from agents.orchestrator import STAGES

    mapping = [
        ("discover", ("migrate", "discover", "promote")),
        ("promote", ("migrate", "promote")),
        ("dedupe", ("migrate", "dedupe")),
        ("classify", ("migrate", "classify")),
        ("images", ("migrate", "images")),
        ("verify", ("migrate", "verify_sources", "verify_images")),
        ("build", ("migrate", "build")),
        ("export", ("migrate", "export")),
    ]
    chosen: list[str] = []
    for flag, stage_names in mapping:
        if getattr(args, flag, False):
            for stage in stage_names:
                if stage not in chosen:
                    chosen.append(stage)
    if not chosen or args.all:
        return STAGES
    return tuple(chosen)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logger = configure_logging(verbose=args.verbose)
    settings = get_settings()
    logger.info("run_id=%s database=%s", run_id(), settings.database_path)

    from app.db import migrate
    from agents import export_agent, image_discovery_agent, orchestrator, update_agent

    result: Any

    if args.status:
        migrate()
        result = orchestrator.status()
    elif args.stop_conditions:
        migrate()
        result = orchestrator.check_stop_conditions()
    elif args.stats:
        migrate()
        result = export_agent.coverage_statistics()
    elif args.sideload_images:
        migrate()
        result = image_discovery_agent.sideload()
    elif args.update:
        migrate()
        result = update_agent.run(
            passes=args.passes or 2, limit=args.limit, skip_images=args.skip_images
        )
    elif args.dedupe and args.dry_run and not args.all:
        from agents import deduplication_agent

        migrate()
        result = deduplication_agent.run(dry_run=True, limit=args.limit)
    else:
        result = orchestrator.run_pipeline(
            resume=args.resume,
            limit=args.limit,
            country=args.country,
            manufacturer=args.manufacturer,
            stages=_selected_stages(args),
            discovery_passes=args.passes,
            skip_images=args.skip_images,
        )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_summary(result)
    return 0


def _print_summary(result: Any) -> None:
    if not isinstance(result, dict):
        print(result)
        return
    print()
    for key, value in result.items():
        if key == "settings":
            continue
        if isinstance(value, dict):
            compact = ", ".join(
                f"{k}={v}" for k, v in list(value.items())[:8] if not isinstance(v, (dict, list))
            )
            print(f"  {key:<26} {compact}")
        elif isinstance(value, list):
            print(f"  {key:<26} {len(value)} item(s)")
        else:
            print(f"  {key:<26} {value}")
    print()


if __name__ == "__main__":
    sys.exit(main())
