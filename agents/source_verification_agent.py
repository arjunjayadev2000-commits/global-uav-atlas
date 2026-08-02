"""Source verification: enforce the evidence policy on every canonical record.

Rules enforced (from the source-priority section of the specification):

* every canonical platform must have at least one supporting source;
* a record supported only by tier-4 material (forums, social media, unverified
  blogs) may never be treated as verified - tier 4 is leads only;
* high confidence requires two or more independent sources where practical;
* records failing these rules are demoted to ``Needs Verification`` and queued.

The agent is idempotent and recomputes status from the evidence currently in the
database, so re-running it after new discovery automatically upgrades records
that have since gained corroboration.
"""

from __future__ import annotations

from typing import Any

from app.db import add_unresolved, connect, query, resolve_unresolved, update_fields
from app.logging import AgentLogger
from app.models import (
    VERIFICATION_NEEDS,
    VERIFICATION_PROBABLE,
    VERIFICATION_VERIFIED,
)
from app.utils import UNKNOWN_COUNTRY, stable_id

LOG = AgentLogger("source_verification_agent")
AGENT = "source_verification_agent"


def evaluate_record(
    *, tiers: list[int], distinct_sources: int, country: str, has_manufacturer: bool
) -> tuple[str, float, str]:
    """Return ``(verification_status, confidence, rationale)`` for one record."""
    if not tiers:
        return VERIFICATION_NEEDS, 0.0, "no supporting source is linked to this record"

    best_tier = min(tiers)
    if best_tier >= 4:
        return (
            VERIFICATION_NEEDS,
            0.1,
            "only tier-4 material (forums/social/unverified) supports this record; "
            "tier 4 may be used for leads but never as sole verification",
        )

    known_country = bool(country) and country != UNKNOWN_COUNTRY

    score = {1: 0.45, 2: 0.35, 3: 0.22}.get(best_tier, 0.05)
    score += min(distinct_sources, 4) * 0.10
    if known_country:
        score += 0.15
    if has_manufacturer:
        score += 0.10
    score = round(min(1.0, score), 3)

    if best_tier <= 2 and distinct_sources >= 2 and known_country:
        return (
            VERIFICATION_VERIFIED,
            score,
            f"{distinct_sources} independent sources, best tier {best_tier}, origin established",
        )
    if (best_tier <= 2 and known_country) or distinct_sources >= 2:
        return (
            VERIFICATION_PROBABLE,
            score,
            f"{distinct_sources} source(s), best tier {best_tier}; corroboration still thin",
        )
    return (
        VERIFICATION_NEEDS,
        score,
        f"single tier-{best_tier} source"
        + ("" if known_country else " and unresolved country of origin"),
    )


def run(*, limit: int | None = None) -> dict[str, Any]:
    conn = connect()
    sql = """
        SELECT p.id, p.canonical_name, p.verification_status, p.confidence_score,
               p.manufacturer_id, COALESCE(c.name,'') AS country
        FROM platforms p
        LEFT JOIN countries c ON c.id = p.country_id
        WHERE p.is_merged_into IS NULL
        ORDER BY p.id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    stats = {
        "examined": 0,
        "verified": 0,
        "probable": 0,
        "needs_verification": 0,
        "no_source": 0,
        "changed": 0,
    }

    for platform in query(sql, conn=conn):
        stats["examined"] += 1
        rows = query(
            """
            SELECT s.credibility_tier AS tier, s.title,
                   COALESCE(s.is_aggregator, 0) AS is_aggregator
            FROM platform_sources ps JOIN sources s ON s.id = ps.source_id
            WHERE ps.platform_id = ?
            """,
            (platform["id"],),
            conn,
        )
        tiers = [int(r["tier"] or 3) for r in rows]
        # Aggregators republish other datasets: they prove the record exists but
        # they do not corroborate it, so they never count toward independence.
        distinct = len({r["title"] for r in rows if not r["is_aggregator"]})

        status, confidence, rationale = evaluate_record(
            tiers=tiers,
            distinct_sources=distinct,
            country=platform["country"],
            has_manufacturer=platform["manufacturer_id"] is not None,
        )

        if not tiers:
            stats["no_source"] += 1
            add_unresolved(
                item_type="missing_source",
                subject=platform["canonical_name"],
                detail="canonical record has no linked supporting source",
                severity="high",
                entity_type="platforms",
                entity_id=int(platform["id"]),
                suggested_action="Link a tier 1-3 source or remove the record from the atlas.",
                conn=conn,
            )

        key = {
            VERIFICATION_VERIFIED: "verified",
            VERIFICATION_PROBABLE: "probable",
            VERIFICATION_NEEDS: "needs_verification",
        }[status]
        stats[key] += 1

        changed = update_fields(
            "platforms",
            int(platform["id"]),
            {"verification_status": status, "confidence_score": confidence},
            reason=rationale,
            agent=AGENT,
            conn=conn,
        )
        if changed:
            stats["changed"] += 1
        if status != VERIFICATION_NEEDS:
            resolve_unresolved(
                stable_id("missing_source", platform["canonical_name"], "platforms", str(platform["id"])),
                conn,
            )

    LOG.info("source verification: %s", stats)
    LOG.event("source_verification_complete", **stats)
    return stats


def source_summary() -> list[dict[str, Any]]:
    conn = connect()
    return [
        dict(r)
        for r in query(
            """
            SELECT s.title, s.publisher, s.url, s.source_type, s.credibility_tier,
                   COUNT(ps.platform_id) AS platform_count
            FROM sources s
            LEFT JOIN platform_sources ps ON ps.source_id = s.id
            GROUP BY s.id
            ORDER BY s.credibility_tier, platform_count DESC
            """,
            conn=conn,
        )
    ]
