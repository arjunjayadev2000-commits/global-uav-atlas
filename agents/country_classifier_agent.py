"""Country-of-origin classification.

Policy implemented here (from the specification):

* origin means **design origin**, never merely an operator;
* joint programmes become ``Multinational`` with participants kept in metadata;
* licensed production keeps the original design country and records the
  production country separately;
* anything unclear becomes ``Unknown``, is queued for review, and is never
  guessed.

Evidence is ranked by source tier.  A regulator's registered address
(``origin_is_registration_only``) is explicitly *not* accepted as design origin
because an EU class-mark declaration says where the paperwork was filed, not
where the aircraft was designed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db import add_unresolved, connect, get_or_create_country, query, update_fields
from app.logging import AgentLogger
from app.utils import MULTINATIONAL, UNKNOWN_COUNTRY, clean_text, normalize_country

LOG = AgentLogger("country_classifier_agent")

AGENT = "country_classifier_agent"

#: Evidence weight per credibility tier (tier 1 strongest).
TIER_WEIGHT = {1: 1.0, 2: 0.8, 3: 0.55, 4: 0.2}


@dataclass(slots=True)
class OriginEvidence:
    country: str
    tier: int
    source: str
    registration_only: bool = False
    participants: list[str] | None = None
    is_aggregator: bool = False


@dataclass(slots=True)
class OriginDecision:
    country: str
    confidence: str
    participants: list[str]
    production_country: str
    rationale: str


def classify(evidence: list[OriginEvidence]) -> OriginDecision:
    """Weigh origin evidence and decide, refusing to guess."""
    usable = [e for e in evidence if e.country and e.country != UNKNOWN_COUNTRY]
    design_evidence = [e for e in usable if not e.registration_only]
    registration_evidence = [e for e in usable if e.registration_only]

    if not design_evidence:
        production = ""
        if registration_evidence:
            production = registration_evidence[0].country
        return OriginDecision(
            country=UNKNOWN_COUNTRY,
            confidence="None",
            participants=[],
            production_country=production,
            rationale=(
                "no design-origin evidence; only registration/market-placement data available"
                if registration_evidence
                else "no origin evidence in any source"
            ),
        )

    # Weigh each independent dataset once. Two rows from the same catalogue - or a
    # row plus the aggregator that republishes it - are one piece of evidence,
    # not two, and must not add up to a "High" confidence origin.
    scores: dict[str, float] = {}
    participants: list[str] = []
    counted: set[tuple[str, str]] = set()
    aggregator_only = all(e.is_aggregator for e in design_evidence)
    for item in design_evidence:
        if item.is_aggregator and not aggregator_only:
            continue
        key = (item.country, item.source or f"tier{item.tier}")
        if key in counted:
            continue
        counted.add(key)
        weight = TIER_WEIGHT.get(item.tier, 0.3)
        if item.is_aggregator:
            weight *= 0.5  # republished data, discounted
        scores[item.country] = scores.get(item.country, 0.0) + weight
        for participant in item.participants or []:
            if participant not in participants:
                participants.append(participant)

    if not scores:
        return OriginDecision(
            country=UNKNOWN_COUNTRY, confidence="None", participants=[],
            production_country="", rationale="no independent design-origin evidence",
        )

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, best_score = ordered[0]
    runner_up_score = ordered[1][1] if len(ordered) > 1 else 0.0

    # Genuine disagreement between comparable-strength sources -> do not guess.
    conflicting = len(ordered) > 1 and runner_up_score >= best_score * 0.9

    if best == MULTINATIONAL or (conflicting and _looks_like_joint(ordered)):
        joint = [c for c, _ in ordered if c not in (MULTINATIONAL, UNKNOWN_COUNTRY)]
        for candidate in joint:
            if candidate not in participants:
                participants.append(candidate)
        return OriginDecision(
            country=MULTINATIONAL,
            confidence="Medium",
            participants=participants,
            production_country="",
            rationale=f"joint programme evidence across {len(joint)} countries",
        )

    if conflicting:
        return OriginDecision(
            country=UNKNOWN_COUNTRY,
            confidence="None",
            participants=[c for c, _ in ordered],
            production_country="",
            rationale=(
                "sources of comparable credibility disagree: "
                + ", ".join(f"{c} ({s:.2f})" for c, s in ordered[:3])
            ),
        )

    if best_score >= 1.0:
        confidence = "High"
    elif best_score >= 0.55:
        confidence = "Medium"
    else:
        confidence = "Low"

    production = ""
    for item in registration_evidence:
        if item.country != best:
            production = item.country
            break

    return OriginDecision(
        country=best,
        confidence=confidence,
        participants=participants,
        production_country=production,
        rationale=f"strongest design-origin evidence: {best} (weight {best_score:.2f})",
    )


def _looks_like_joint(ordered: list[tuple[str, float]]) -> bool:
    """Two or more near-equal European/allied partners usually means joint."""
    return len([c for c, _ in ordered if c not in (UNKNOWN_COUNTRY, MULTINATIONAL)]) >= 2


def evidence_from_raw(rows: list[dict[str, Any]]) -> list[OriginEvidence]:
    """Build evidence objects from raw discovery payloads."""
    evidence: list[OriginEvidence] = []
    for row in rows:
        payload = row.get("payload") or {}
        country, participants = normalize_country(row.get("raw_country", ""))
        registration_only = bool(payload.get("origin_is_registration_only"))
        if registration_only and not country:
            country, _ = normalize_country(payload.get("registered_country", ""))
        if not country or country == UNKNOWN_COUNTRY:
            continue
        evidence.append(
            OriginEvidence(
                country=country,
                tier=int(payload.get("credibility_tier", row.get("credibility_tier", 3)) or 3),
                source=clean_text(row.get("source_dataset", "")),
                registration_only=registration_only,
                participants=participants,
                is_aggregator=bool(row.get("is_aggregator")),
            )
        )
    return evidence


def run(*, limit: int | None = None, only_unknown: bool = False) -> dict[str, Any]:
    """Re-classify origin for stored platforms using all linked raw evidence."""
    conn = connect()
    where = "WHERE p.is_merged_into IS NULL"
    if only_unknown:
        where += " AND (c.name IS NULL OR c.name = 'Unknown')"
    sql = f"""
        SELECT p.id, p.canonical_name, p.origin_confidence, c.name AS country
        FROM platforms p LEFT JOIN countries c ON c.id = p.country_id
        {where}
        ORDER BY p.id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    platforms = query(sql, conn=conn)
    stats = {"examined": 0, "changed": 0, "unknown": 0, "multinational": 0}

    for platform in platforms:
        stats["examined"] += 1
        raw_rows = [
            {
                "raw_country": r["raw_country"],
                "source_dataset": r["source_dataset"],
                "payload": _json_or_empty(r["payload_json"]),
                "credibility_tier": r["credibility_tier"],
                "is_aggregator": r["is_aggregator"],
            }
            for r in query(
                """
                SELECT rd.raw_country, rd.source_dataset, rd.payload_json,
                       COALESCE(s.credibility_tier, 3) AS credibility_tier,
                       COALESCE(s.is_aggregator, 0) AS is_aggregator
                FROM raw_discoveries rd
                LEFT JOIN sources s ON s.id = rd.source_id
                WHERE rd.promoted_platform_id = ?
                """,
                (platform["id"],),
                conn=conn,
            )
        ]
        if not raw_rows:
            continue

        decision = classify(evidence_from_raw(raw_rows))
        if decision.country == UNKNOWN_COUNTRY:
            stats["unknown"] += 1
            add_unresolved(
                item_type="country_of_origin",
                subject=platform["canonical_name"],
                detail=decision.rationale,
                severity="medium",
                entity_type="platforms",
                entity_id=int(platform["id"]),
                suggested_action="Consult a tier 1 manufacturer or defence-ministry page for design origin.",
                conn=conn,
            )
        if decision.country == MULTINATIONAL:
            stats["multinational"] += 1

        country_id = get_or_create_country(decision.country, conn=conn)
        changed = update_fields(
            "platforms",
            int(platform["id"]),
            {
                "country_id": country_id,
                "origin_confidence": decision.confidence,
                "participating_countries": ", ".join(decision.participants) or None,
                "production_country": decision.production_country or None,
            },
            reason=decision.rationale,
            agent=AGENT,
            conn=conn,
        )
        if changed:
            stats["changed"] += 1

    LOG.info("country classification: %s", stats)
    LOG.event("country_classification_complete", **stats)
    return stats


def infer_from_manufacturer(*, min_supporting_platforms: int = 1) -> dict[str, Any]:
    """Second pass: resolve ``Unknown`` origins from the manufacturer's own record.

    This is an *inference from evidence already in the database*, not a guess: it
    only fires when the same manufacturer already has other platforms whose
    design origin was established from sourced country data.  The result is
    labelled ``Low (inferred from manufacturer)`` and every affected record stays
    in the unresolved queue so the inference is visible and reversible.

    A community catalogue that lists ``DJI Matrice 400`` with no country, when
    twenty sourced DJI records already resolve to China, is stronger evidence
    than leaving the row blank - but it is weaker than a manufacturer or
    ministry page, and the confidence label says so.
    """
    conn = connect()
    manufacturer_country = {
        int(r["manufacturer_id"]): (r["country"], int(r["n"]))
        for r in query(
            """
            SELECT p.manufacturer_id, c.name AS country, COUNT(*) AS n
            FROM platforms p
            JOIN countries c ON c.id = p.country_id
            WHERE p.is_merged_into IS NULL
              AND p.manufacturer_id IS NOT NULL
              AND c.name NOT IN ('Unknown', 'Multinational')
              AND p.origin_confidence IN ('High', 'Medium')
            GROUP BY p.manufacturer_id, c.name
            ORDER BY n DESC
            """,
            conn=conn,
        )
    }

    targets = query(
        """
        SELECT p.id, p.canonical_name, p.manufacturer_id, m.name AS manufacturer
        FROM platforms p
        JOIN countries c ON c.id = p.country_id
        LEFT JOIN manufacturers m ON m.id = p.manufacturer_id
        WHERE p.is_merged_into IS NULL AND c.name = 'Unknown'
          AND p.manufacturer_id IS NOT NULL
        """,
        conn=conn,
    )

    stats = {"candidates": len(targets), "inferred": 0, "still_unknown": 0}
    for row in targets:
        entry = manufacturer_country.get(int(row["manufacturer_id"]))
        if not entry or entry[1] < min_supporting_platforms:
            stats["still_unknown"] += 1
            continue
        country, supporting = entry
        country_id = get_or_create_country(country, conn=conn)
        rationale = (
            f"inferred from manufacturer {row['manufacturer']}: {supporting} sourced "
            f"platform(s) by the same organisation resolve to {country}"
        )
        update_fields(
            "platforms",
            int(row["id"]),
            {
                "country_id": country_id,
                "origin_confidence": "Low (inferred from manufacturer)",
            },
            reason=rationale,
            agent=AGENT,
            conn=conn,
        )
        add_unresolved(
            item_type="country_inferred",
            subject=row["canonical_name"],
            detail=rationale,
            severity="low",
            entity_type="platforms",
            entity_id=int(row["id"]),
            suggested_action=(
                "Confirm design origin against a manufacturer or regulator page; the value "
                "currently shown is inferred from the organisation's other platforms."
            ),
            conn=conn,
        )
        stats["inferred"] += 1

    LOG.info("manufacturer-based origin inference: %s", stats)
    LOG.event("origin_inference_complete", **stats)
    return stats


def _json_or_empty(raw: Any) -> dict[str, Any]:
    import json

    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}
