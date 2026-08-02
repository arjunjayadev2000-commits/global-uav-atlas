"""Orchestrator: sequences the agents and enforces the stop conditions.

Each stage records completion in ``pipeline_state`` so ``--resume`` restarts at
the first stage that has not finished.  Stage failures are isolated: a stage that
raises is logged, recorded as an unresolved item, and the remaining stages still
run so partial outputs are always produced.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from typing import Any

from agents import (
    atlas_builder_agent,
    country_classifier_agent,
    deduplication_agent,
    discovery_agent,
    export_agent,
    image_discovery_agent,
    image_validation_agent,
    metadata_agent,
    source_verification_agent,
    vision_verification_agent,
)
from app.config import get_settings
from app.db import add_unresolved, connect, get_state, is_done, mark_done, migrate, query, set_state
from app.logging import AgentLogger, run_id, utc_now

LOG = AgentLogger("orchestrator")
AGENT = "orchestrator"

STAGES = (
    "migrate",
    "discover",
    "promote",
    "dedupe",
    "classify",
    "verify_sources",
    "images",
    "verify_images",
    "build",
    "export",
)


def _run_stage(
    name: str,
    func: Callable[[], Any],
    *,
    resume: bool,
    results: dict[str, Any],
) -> None:
    conn = connect()
    if resume and is_done(name, conn):
        LOG.info("stage %-14s already complete - skipping (resume)", name)
        results[name] = {"skipped": "already complete"}
        return

    started = time.monotonic()
    LOG.info("stage %-14s starting", name)
    LOG.event("stage_start", stage=name)
    try:
        outcome = func()
    except Exception as exc:
        elapsed = time.monotonic() - started
        LOG.error("stage %s failed after %.1fs: %s", name, elapsed, exc)
        LOG.event(
            "stage_failed",
            status="error",
            stage=name,
            error=str(exc)[:400],
            traceback=traceback.format_exc()[-1500:],
        )
        add_unresolved(
            item_type="pipeline_stage_failure",
            subject=f"stage {name} failed",
            detail=str(exc)[:800],
            severity="high",
            suggested_action=f"Re-run `python run.py --{name}` after addressing the error.",
            conn=conn,
        )
        results[name] = {"error": str(exc)[:400]}
        return

    elapsed = time.monotonic() - started
    mark_done(name, outcome if isinstance(outcome, dict) else str(outcome), conn)
    results[name] = outcome
    LOG.info("stage %-14s done in %.1fs", name, elapsed)
    LOG.event("stage_complete", stage=name, seconds=round(elapsed, 2))


def run_pipeline(
    *,
    resume: bool = False,
    limit: int | None = None,
    country: str | None = None,
    manufacturer: str | None = None,
    stages: tuple[str, ...] = STAGES,
    discovery_passes: int | None = None,
    skip_images: bool = False,
) -> dict[str, Any]:
    """Run the requested stages end to end."""
    settings = get_settings()
    results: dict[str, Any] = {
        "run_id": run_id(),
        "started_at": utc_now(),
        "settings": settings.as_dict(),
    }

    stage_map: dict[str, Callable[[], Any]] = {
        "migrate": lambda: {"applied": migrate()},
        "discover": lambda: discovery_agent.run(
            passes=discovery_passes,
            country=country,
            manufacturer_filter=manufacturer,
            limit=limit,
        ),
        "promote": lambda: metadata_agent.promote(),
        "dedupe": lambda: deduplication_agent.run(),
        "classify": lambda: {
            "evidence": country_classifier_agent.run(),
            "manufacturer_inference": country_classifier_agent.infer_from_manufacturer(),
        },
        "verify_sources": lambda: source_verification_agent.run(),
        "images": lambda: (
            {"skipped": "images disabled for this run"}
            if skip_images
            else image_discovery_agent.run(
                limit=limit, country=country, manufacturer=manufacturer
            )
        ),
        "verify_images": lambda: {
            "validation": image_validation_agent.revalidate_stored(),
            "vision": vision_verification_agent.run(limit=limit),
        },
        "build": lambda: atlas_builder_agent.run(),
        "export": lambda: export_agent.run(),
    }

    for stage in stages:
        if stage not in stage_map:
            LOG.warning("unknown stage %r - ignored", stage)
            continue
        _run_stage(stage, stage_map[stage], resume=resume, results=results)

    results["finished_at"] = utc_now()
    results["stop_conditions"] = check_stop_conditions()
    set_state("last_pipeline_run", {"at": results["finished_at"], "run_id": run_id()})
    LOG.event("pipeline_complete", stages=list(stages))
    return results


# ---------------------------------------------------------------------------
# Stop conditions
# ---------------------------------------------------------------------------


def check_stop_conditions() -> dict[str, Any]:
    """Evaluate the specification's stop conditions against the current state."""
    settings = get_settings()
    conn = connect()
    out = settings.paths.output

    def one(sql: str) -> int:
        rows = query(sql, conn=conn)
        return int(rows[0][0]) if rows else 0

    platforms = one("SELECT COUNT(*) FROM platforms WHERE is_merged_into IS NULL")
    images_selected = one("SELECT COUNT(*) FROM images WHERE selected_for_atlas=1")
    fully_documented = one(
        """
        SELECT COUNT(*) FROM images
        WHERE selected_for_atlas=1 AND license_verified=1
          AND source_page_url IS NOT NULL AND source_page_url <> ''
          AND attribution_text IS NOT NULL AND attribution_text <> ''
          AND identity_verdict <> 'unverified'
        """
    )
    open_duplicates = one(
        "SELECT COUNT(*) FROM unresolved_items WHERE status='open' AND item_type='possible_duplicate'"
    )
    unresolved_open = one("SELECT COUNT(*) FROM unresolved_items WHERE status='open'")

    passes = [
        dict(r)
        for r in query(
            "SELECT pass_number, SUM(new_candidates) AS new_candidates FROM discovery_runs "
            "WHERE pass_number > 0 GROUP BY pass_number ORDER BY pass_number",
            conn=conn,
        )
    ]
    trailing_empty = 0
    for row in reversed(passes):
        if (row["new_candidates"] or 0) == 0:
            trailing_empty += 1
        else:
            break

    required_outputs = {
        "Global_UAV_Visual_Atlas_2026.pdf": (out / "Global_UAV_Visual_Atlas_2026.pdf"),
        "Global_UAV_Visual_Atlas_2026.html": (out / "Global_UAV_Visual_Atlas_2026.html"),
        "uav_database.csv": (out / "uav_database.csv"),
        "uav_database.xlsx": (out / "uav_database.xlsx"),
        "uav_database.sqlite": (out / "uav_database.sqlite"),
        "photo_attribution.csv": (out / "photo_attribution.csv"),
        "unresolved_records.csv": (out / "unresolved_records.csv"),
        "coverage_statistics.json": (out / "coverage_statistics.json"),
        "coverage_report.md": (out / "coverage_report.md"),
        "audit.jsonl": (settings.paths.logs / "audit.jsonl"),
        "run.log": (settings.paths.logs / "run.log"),
    }
    missing_outputs = [name for name, path in required_outputs.items() if not path.is_file()]

    duplicate_rate = round(open_duplicates / platforms, 4) if platforms else 0.0

    conditions = {
        "pipeline_ran_end_to_end": is_done("export", conn) and is_done("build", conn),
        "database_and_outputs_generated": not missing_outputs,
        "discovery_converged": trailing_empty >= settings.discovery_stop_after_empty_passes,
        "unresolved_documented": (settings.paths.docs / "UNRESOLVED.md").is_file(),
        # Vacuously true with zero images, so it is paired with the condition
        # below rather than standing in for "the atlas has photographs".
        "every_atlas_image_fully_documented": images_selected == fully_documented,
        "atlas_contains_real_images": images_selected > 0,
        "duplicates_below_threshold": duplicate_rate <= 0.02,
        "pdf_present": (out / "Global_UAV_Visual_Atlas_2026.pdf").is_file(),
        "html_present": (out / "Global_UAV_Visual_Atlas_2026.html").is_file(),
        "coverage_statistics_generated": (out / "coverage_statistics.json").is_file(),
    }

    detail = {
        "platforms": platforms,
        "images_selected": images_selected,
        "images_fully_documented": fully_documented,
        "open_unresolved": unresolved_open,
        "open_duplicate_reviews": open_duplicates,
        "duplicate_review_rate": duplicate_rate,
        "trailing_empty_discovery_passes": trailing_empty,
        "missing_outputs": missing_outputs,
        "checked_at": utc_now(),
    }
    result = {"conditions": conditions, "detail": detail, "all_met": all(conditions.values())}
    set_state("stop_conditions", result, conn)
    LOG.event("stop_conditions_checked", all_met=result["all_met"], **detail)
    return result


def status() -> dict[str, Any]:
    conn = connect()
    return {
        "stages": {stage: is_done(stage, conn) for stage in STAGES},
        "last_pipeline_run": get_state("last_pipeline_run", None, conn),
        "discovery": discovery_agent.stats(),
        "images": image_discovery_agent.coverage(),
        "stop_conditions": get_state("stop_conditions", None, conn),
    }
