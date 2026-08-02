"""Metadata agent: promote raw discoveries into canonical platform records.

Responsibilities
----------------
* group raw observations by normalised name and pick the best value per field,
  preferring higher-credibility sources;
* split genuinely combined designations (``Malloy T150/T400``) into distinct
  variants while keeping export/service names (``Heron TP / Eitan``) as aliases -
  the specification is explicit that variants must not be collapsed and that
  distinct names for one airframe must not be duplicated;
* attach aliases, model codes, families, sources and specifications;
* compute ``verification_status`` and ``confidence_score`` from the evidence
  actually present - never from assumption.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from agents import country_classifier_agent as cca
from app.db import (
    add_alias,
    connect,
    get_or_create_country,
    get_or_create_manufacturer,
    insert,
    insert_ignore,
    link_platform_source,
    query,
    query_one,
    update_fields,
)
from app.logging import AgentLogger, utc_now
from app.models import (
    DOMAIN_UNKNOWN,
    VERIFICATION_NEEDS,
    VERIFICATION_PROBABLE,
    VERIFICATION_VERIFIED,
    PlatformRecord,
    normalize_domain,
)
from app.utils import (
    UNKNOWN_COUNTRY,
    clean_text,
    coerce_year,
    extract_model_codes,
    name_similarity,
    normalize_name,
    ratio,
    stable_id,
)

LOG = AgentLogger("metadata_agent")
AGENT = "metadata_agent"

TIER_PRIORITY = {1: 3, 2: 2, 3: 1, 4: 0}

_DESIGNATION_SHAPE = re.compile(r"^[A-Za-z]{1,6}[- ]?\d{1,4}[A-Za-z]?$")
_SPLIT_RE = re.compile(r"\s*/\s*")


# ---------------------------------------------------------------------------
# Combined-name handling
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NameSplit:
    names: list[str]
    aliases: list[str]
    family: str
    reason: str


def split_combined_name(raw_name: str) -> NameSplit:
    """Decide whether ``A/B`` means two variants or two names for one aircraft.

    Two variants when the right-hand side is a single token that either closely
    resembles the left-hand side's final token (``SkyGuardian``/``SeaGuardian``)
    or has the same designation shape (``T150``/``T400``).  Everything else -
    multi-word export names, service names, descriptive suffixes - stays a single
    platform and the alternate becomes an alias.
    """
    name = clean_text(raw_name)
    if "/" not in name:
        return NameSplit([name], [], "", "no separator")

    parts = [p for p in _SPLIT_RE.split(name) if p]
    if len(parts) < 2:
        return NameSplit([name], [], "", "degenerate split")

    left = parts[0]
    left_tokens = left.split()
    if not left_tokens:
        return NameSplit([name], [], "", "empty left side")

    prefix = " ".join(left_tokens[:-1])
    left_tail = left_tokens[-1]

    variants: list[str] = [left]
    aliases: list[str] = []
    for candidate in parts[1:]:
        tokens = candidate.split()
        if len(tokens) != 1:
            aliases.append(candidate)
            continue
        token = tokens[0]
        similar = ratio(left_tail.lower(), token.lower()) >= 0.5
        same_shape = bool(
            _DESIGNATION_SHAPE.match(left_tail) and _DESIGNATION_SHAPE.match(token)
        )
        if similar or same_shape:
            variants.append(f"{prefix} {token}".strip())
        else:
            aliases.append(candidate)

    if len(variants) == 1:
        return NameSplit([left], aliases, "", "alternate names treated as aliases")

    family = prefix or left_tail
    return NameSplit(
        variants,
        aliases,
        family,
        f"combined designation split into {len(variants)} variants",
    )


# ---------------------------------------------------------------------------
# Evidence merging
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Evidence:
    raw_id: int
    raw_name: str
    source_id: int | None
    source_dataset: str
    source_url: str
    tier: int
    country: str
    manufacturer: str
    domain: str
    category: str
    status: str
    payload: dict[str, Any]
    is_aggregator: bool = False

    @property
    def priority(self) -> int:
        return TIER_PRIORITY.get(self.tier, 0)


def _load_payload(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _gather_evidence(conn: sqlite3.Connection, limit: int | None = None) -> dict[str, list[Evidence]]:
    sql = """
        SELECT rd.id, rd.raw_name, rd.normalized_name, rd.source_id, rd.source_dataset,
               rd.source_url, rd.raw_country, rd.raw_manufacturer, rd.domain, rd.category,
               rd.status, rd.payload_json, COALESCE(s.credibility_tier, 3) AS tier,
               COALESCE(s.is_aggregator, 0) AS is_aggregator
        FROM raw_discoveries rd
        LEFT JOIN sources s ON s.id = rd.source_id
        WHERE rd.processed = 0
        ORDER BY rd.id
    """
    rows = query(sql, conn=conn)
    groups: dict[str, list[Evidence]] = defaultdict(list)
    for row in rows:
        payload = _load_payload(row["payload_json"])
        tier = int(payload.get("credibility_tier", row["tier"]) or row["tier"])
        key = row["normalized_name"]
        if not key:
            continue
        groups[key].append(
            Evidence(
                raw_id=int(row["id"]),
                raw_name=clean_text(row["raw_name"]),
                source_id=row["source_id"],
                source_dataset=clean_text(row["source_dataset"]),
                source_url=clean_text(row["source_url"]),
                tier=tier,
                country=clean_text(row["raw_country"]),
                manufacturer=clean_text(row["raw_manufacturer"]),
                domain=clean_text(row["domain"]),
                category=clean_text(row["category"]),
                status=clean_text(row["status"]),
                payload=payload,
                is_aggregator=bool(row["is_aggregator"]),
            )
        )
        if limit is not None and len(groups) >= limit:
            break
    return groups


def _best(values: list[tuple[str, int]]) -> str:
    """Pick the value backed by the highest-priority source, then by frequency."""
    scored: dict[str, tuple[int, int]] = {}
    for value, priority in values:
        cleaned = clean_text(value)
        if not cleaned:
            continue
        best_priority, count = scored.get(cleaned, (-1, 0))
        scored[cleaned] = (max(best_priority, priority), count + 1)
    if not scored:
        return ""
    return sorted(scored.items(), key=lambda kv: (kv[1][0], kv[1][1]), reverse=True)[0][0]


def _independent_sources(evidence: list[Evidence]) -> set[str]:
    """Distinct *independent* datasets - aggregators republish, they do not corroborate."""
    return {e.source_dataset for e in evidence if e.source_dataset and not e.is_aggregator}


def assess_confidence(
    evidence: list[Evidence], country: str, has_manufacturer: bool
) -> tuple[str, float]:
    """Derive verification status and a 0-1 confidence score from the evidence."""
    datasets = _independent_sources(evidence)
    tiers = sorted({e.tier for e in evidence})
    best_tier = tiers[0] if tiers else 4
    lead_only = all(e.payload.get("lead_only") for e in evidence) if evidence else False

    score = 0.0
    score += {1: 0.45, 2: 0.35, 3: 0.22, 4: 0.05}.get(best_tier, 0.05)
    score += min(len(datasets), 4) * 0.10
    if country and country != UNKNOWN_COUNTRY:
        score += 0.15
    if has_manufacturer:
        score += 0.10
    if lead_only:
        score -= 0.20
    score = round(max(0.0, min(1.0, score)), 3)

    if lead_only:
        status = VERIFICATION_NEEDS
    elif best_tier <= 2 and len(datasets) >= 2 and country != UNKNOWN_COUNTRY:
        status = VERIFICATION_VERIFIED
    elif (best_tier <= 2 and country != UNKNOWN_COUNTRY) or len(datasets) >= 2:
        status = VERIFICATION_PROBABLE
    else:
        status = VERIFICATION_NEEDS
    return status, score


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


def _extract_specs(evidence: list[Evidence]) -> dict[str, Any]:
    """Pull the specification fields the seed carries, highest tier first."""
    spec_keys = (
        "mtow_kg",
        "endurance_min",
        "endurance_h",
        "range_km",
        "max_speed_kmh",
        "payload_kg",
        "wingspan_m",
        "length_m",
        "class_mark",
        "airframe_type",
        "model_codes",
        "aliases",
        "notes",
        "photo_search_url",
    )
    out: dict[str, Any] = {}
    for item in sorted(evidence, key=lambda e: e.priority, reverse=True):
        for key in spec_keys:
            value = clean_text(item.payload.get(key, ""))
            if value and key not in out:
                out[key] = value
    return out


def _family_id(conn: sqlite3.Connection, family: str, manufacturer_id: int | None, country_id: int | None) -> int | None:
    name = clean_text(family)
    if not name:
        return None
    normalized = normalize_name(name)
    if not normalized:
        return None
    row = query_one(
        "SELECT id FROM platform_families WHERE normalized_name=?", (normalized,), conn
    )
    if row:
        return int(row["id"])
    return insert(
        "platform_families",
        {
            "name": name,
            "normalized_name": normalized,
            "manufacturer_id": manufacturer_id,
            "country_id": country_id,
            "created_at": utc_now(),
        },
        conn,
    )


def promote(*, limit: int | None = None) -> dict[str, Any]:
    """Turn unprocessed raw discoveries into canonical platform rows."""
    conn = connect()
    groups = _gather_evidence(conn, limit=limit)
    stats = {
        "groups": len(groups),
        "created": 0,
        "updated": 0,
        "variants_created": 0,
        "aliases_added": 0,
        "raw_processed": 0,
    }

    for evidence in groups.values():
        try:
            created, updated, variants, aliases = _promote_group(conn, evidence)
        except Exception as exc:
            LOG.error("promotion failed for %r: %s", evidence[0].raw_name if evidence else "?", exc)
            LOG.event(
                "promotion_failed",
                status="error",
                name=evidence[0].raw_name if evidence else "",
                error=str(exc)[:300],
            )
            continue
        stats["created"] += created
        stats["updated"] += updated
        stats["variants_created"] += variants
        stats["aliases_added"] += aliases
        stats["raw_processed"] += len(evidence)

    LOG.info("promotion: %s", stats)
    LOG.event("promotion_complete", **stats)
    return stats


def _promote_group(
    conn: sqlite3.Connection, evidence: list[Evidence]
) -> tuple[int, int, int, int]:
    display_name = _best([(e.raw_name, e.priority) for e in evidence])
    if not display_name:
        return 0, 0, 0, 0

    split = split_combined_name(display_name)

    manufacturer_name = _best([(e.manufacturer, e.priority) for e in evidence])
    domain = normalize_domain(_best([(e.domain, e.priority) for e in evidence])) or DOMAIN_UNKNOWN
    category = _best([(e.category, e.priority) for e in evidence])
    status = _best([(e.status, e.priority) for e in evidence])
    specs = _extract_specs(evidence)

    decision = cca.classify(
        cca.evidence_from_raw(
            [
                {
                    "raw_country": e.country,
                    "source_dataset": e.source_dataset,
                    "payload": e.payload,
                    "credibility_tier": e.tier,
                    "is_aggregator": e.is_aggregator,
                }
                for e in evidence
            ]
        )
    )

    country_id = get_or_create_country(decision.country, conn=conn)
    manufacturer_id = get_or_create_manufacturer(
        manufacturer_name, country_id=country_id if decision.country != UNKNOWN_COUNTRY else None, conn=conn
    )
    family_id = _family_id(conn, split.family, manufacturer_id, country_id)

    verification, confidence = assess_confidence(
        evidence, decision.country, bool(manufacturer_id)
    )

    created = updated = variants_created = aliases_added = 0
    platform_ids: list[int] = []

    for index, name in enumerate(split.names):
        record = PlatformRecord(
            canonical_name=name,
            country=decision.country,
            manufacturer=manufacturer_name,
            domain=domain,
            category=category,
            airframe_type=specs.get("airframe_type", ""),
            status=status,
            family=split.family,
            aliases=list(split.aliases),
            description_short=clean_text(specs.get("notes", ""))[:240],
            verification_status=verification,
            confidence_score=confidence,
            origin_confidence=decision.confidence,
            participating_countries=decision.participants,
            production_country=decision.production_country,
        )
        platform_id, was_created = _upsert_platform(
            conn,
            record,
            manufacturer_id=manufacturer_id,
            country_id=country_id,
            family_id=family_id,
            specs=specs,
        )
        platform_ids.append(platform_id)
        created += int(was_created)
        updated += int(not was_created)

        if len(split.names) > 1:
            insert_ignore(
                "platform_variants",
                {
                    "platform_id": platform_id,
                    "parent_platform_id": platform_ids[0] if index else None,
                    "variant_name": name,
                    "normalized_variant": normalize_name(name),
                    "variant_role": "split from combined designation",
                    "notes": split.reason,
                    "created_at": utc_now(),
                },
                conn,
            )
            if index:
                variants_created += 1

        # Aliases: the original combined string, export names, seed aliases.
        alias_pool = list(split.aliases)
        if display_name != name:
            alias_pool.append(display_name)
        for raw_alias in str(specs.get("aliases", "")).split("|"):
            if clean_text(raw_alias):
                alias_pool.append(clean_text(raw_alias))
        for other in {e.raw_name for e in evidence}:
            if other and normalize_name(other) != normalize_name(name):
                alias_pool.append(other)
        for alias in alias_pool:
            add_alias(platform_id, alias, alias_type="alias", conn=conn)
            aliases_added += 1

        for code in extract_model_codes(name) + [
            c.strip() for c in str(specs.get("model_codes", "")).split("|") if c.strip()
        ]:
            add_alias(platform_id, code, alias_type="model_code", conn=conn)

        for item in evidence:
            if item.source_id:
                link_platform_source(
                    platform_id,
                    int(item.source_id),
                    excerpt=item.source_url[:400] or None,
                    conn=conn,
                )

    # Mark the raw rows as processed and record which platform they produced.
    for item in evidence:
        conn.execute(
            "UPDATE raw_discoveries SET processed=1, promoted_platform_id=? WHERE id=?",
            (platform_ids[0] if platform_ids else None, item.raw_id),
        )

    return created, updated, variants_created, aliases_added


def _upsert_platform(
    conn: sqlite3.Connection,
    record: PlatformRecord,
    *,
    manufacturer_id: int | None,
    country_id: int,
    family_id: int | None,
    specs: dict[str, Any],
) -> tuple[int, bool]:
    normalized = record.normalized_name
    existing = query_one(
        "SELECT id FROM platforms WHERE normalized_name=?", (normalized,), conn
    )
    now = utc_now()
    values: dict[str, Any] = {
        "canonical_name": record.canonical_name,
        "manufacturer_id": manufacturer_id,
        "country_id": country_id,
        "family_id": family_id,
        "domain": record.domain,
        "category": record.category or None,
        "airframe_type": record.airframe_type or None,
        "status": record.status or None,
        "first_seen_year": coerce_year(specs.get("first_seen_year")),
        "introduced_year": coerce_year(specs.get("introduced_year")),
        "retired_year": coerce_year(specs.get("retired_year")),
        "description_short": record.description_short or None,
        "verification_status": record.verification_status,
        "confidence_score": record.confidence_score,
        "origin_confidence": record.origin_confidence or None,
        "participating_countries": ", ".join(record.participating_countries) or None,
        "production_country": record.production_country or None,
    }

    if existing:
        platform_id = int(existing["id"])
        # Keep the strongest assessment if this pass is weaker than a prior one.
        current = query_one("SELECT confidence_score FROM platforms WHERE id=?", (platform_id,), conn)
        if current and float(current["confidence_score"] or 0) > record.confidence_score:
            values.pop("confidence_score")
            values.pop("verification_status")
        update_fields(
            "platforms",
            platform_id,
            values,
            reason="metadata refresh from raw discoveries",
            agent=AGENT,
            conn=conn,
        )
        return platform_id, False

    values.update(
        {
            "public_id": record.public_id,
            "normalized_name": normalized,
            "created_at": now,
            "updated_at": now,
        }
    )
    platform_id = insert("platforms", values, conn)
    return platform_id, True


def run(*, limit: int | None = None) -> dict[str, Any]:
    return promote(limit=limit)


def backfill_public_ids() -> int:
    """Guarantee every platform has a stable public identifier."""
    conn = connect()
    fixed = 0
    for row in query("SELECT id, canonical_name, public_id FROM platforms", conn=conn):
        if row["public_id"]:
            continue
        new_id = "UAV-" + stable_id(normalize_name(row["canonical_name"])).upper()[:12]
        update_fields(
            "platforms",
            int(row["id"]),
            {"public_id": new_id},
            reason="public id backfill",
            agent=AGENT,
            conn=conn,
        )
        fixed += 1
    return fixed


def similar_names(name: str, *, threshold: float = 0.85, limit: int = 10) -> list[dict[str, Any]]:
    """Utility used by the review tooling to eyeball near-miss names."""
    conn = connect()
    out: list[dict[str, Any]] = []
    for row in query("SELECT id, canonical_name FROM platforms WHERE is_merged_into IS NULL", conn=conn):
        score = name_similarity(name, row["canonical_name"])
        if score >= threshold:
            out.append({"id": int(row["id"]), "name": row["canonical_name"], "score": score})
    return sorted(out, key=lambda r: r["score"], reverse=True)[:limit]
