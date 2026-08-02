"""Update agent: incremental refresh of an existing atlas.

Used by the weekly CI workflow.  Rather than rebuilding from scratch it:

* re-runs discovery so new source entries are captured;
* promotes only unprocessed raw discoveries;
* re-verifies sources and origins so records that gained corroboration are
  upgraded automatically;
* re-checks stored images (files can vanish or be replaced upstream);
* re-acquires images only for platforms that still lack one;
* reports what changed since the previous run using ``update_history``.
"""

from __future__ import annotations

from typing import Any

from app.db import connect, get_state, query, set_state
from app.logging import AgentLogger, run_id, utc_now
from agents import (
    country_classifier_agent,
    deduplication_agent,
    discovery_agent,
    image_discovery_agent,
    image_validation_agent,
    metadata_agent,
    source_verification_agent,
)

LOG = AgentLogger("update_agent")
AGENT = "update_agent"


def snapshot() -> dict[str, Any]:
    conn = connect()

    def one(sql: str) -> int:
        return int(query(sql, conn=conn)[0][0])

    return {
        "platforms": one("SELECT COUNT(*) FROM platforms WHERE is_merged_into IS NULL"),
        "raw": one("SELECT COUNT(*) FROM raw_discoveries"),
        "images": one("SELECT COUNT(*) FROM images WHERE selected_for_atlas=1"),
        "unresolved": one("SELECT COUNT(*) FROM unresolved_items WHERE status='open'"),
        "at": utc_now(),
    }


def changes_since(timestamp: str) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in query(
            """
            SELECT entity_type, entity_id, field, old_value, new_value, reason, agent, created_at
            FROM update_history WHERE created_at >= ? ORDER BY created_at DESC LIMIT 500
            """,
            (timestamp,),
        )
    ]


def run(*, passes: int = 2, limit: int | None = None, skip_images: bool = False) -> dict[str, Any]:
    conn = connect()
    before = snapshot()
    started = before["at"]

    result: dict[str, Any] = {"run_id": run_id(), "before": before}
    result["discovery"] = discovery_agent.run(passes=passes, limit=limit, import_seed_first=False)
    result["promotion"] = metadata_agent.promote()
    result["deduplication"] = deduplication_agent.run()
    result["origins"] = country_classifier_agent.run()
    result["sources"] = source_verification_agent.run()
    result["image_revalidation"] = image_validation_agent.revalidate_stored()
    if not skip_images:
        result["images"] = image_discovery_agent.run(limit=limit)

    after = snapshot()
    result["after"] = after
    result["delta"] = {
        key: after[key] - before[key] for key in ("platforms", "raw", "images", "unresolved")
    }
    result["field_changes"] = len(changes_since(started))

    previous = get_state("last_update", None, conn)
    result["previous_update"] = previous
    set_state("last_update", after, conn)

    LOG.info("update complete: %s", result["delta"])
    LOG.event("update_complete", **result["delta"], field_changes=result["field_changes"])
    return result
