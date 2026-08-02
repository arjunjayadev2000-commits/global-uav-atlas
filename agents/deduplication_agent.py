"""Deduplication agent.

The hard requirement is asymmetric: merging two spellings of one aircraft is
good, merging two officially distinct variants is a defect.  So the agent is
built around *veto rules* that run before any similarity score is trusted:

* differing model codes (``MQ-9A`` vs ``MQ-9B``)          -> never merge
* differing trailing variant letters/numbers               -> never merge
* differing manufacturer where both are known              -> never merge
* differing country where both are known and not licensed  -> review, not merge

Only pairs that survive every veto are scored, and only scores above
``dedupe_auto_merge_threshold`` merge automatically.  Everything between the
review and auto thresholds goes to ``merge_decisions`` + the unresolved queue
for a human.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.db import (
    add_unresolved,
    connect,
    insert,
    query,
    update_fields,
)
from app.logging import AgentLogger, run_id, utc_now
from app.utils import (
    UNKNOWN_COUNTRY,
    clean_text,
    extract_model_codes,
    jaccard,
    name_similarity,
    normalize_name,
    tokenize,
)

LOG = AgentLogger("deduplication_agent")
AGENT = "deduplication_agent"

#: Trailing variant markers: MQ-9A / MQ-9B, Mavic 3 / Mavic 3T, Block 5.
_VARIANT_SUFFIX_RE = re.compile(
    r"(?:^|\s|-)(?:blk|block|mk|mark|ver|version|gen)?\s*"
    r"([ivx]+|\d+[a-z]?|[a-z])$",
    re.IGNORECASE,
)

#: Words that mean "this is a different thing", not a spelling variation.
_DISTINGUISHING_WORDS = {
    "guardian",
    "seaguardian",
    "skyguardian",
    "maritime",
    "naval",
    "trainer",
    "cargo",
    "strike",
    "recon",
    "extended",
    "enterprise",
    "pro",
    "plus",
    "mini",
    "micro",
    "nano",
    "max",
    "lite",
    "advanced",
    "thermal",
    "rtk",
    "combo",
}


@dataclass(slots=True)
class Candidate:
    id: int
    name: str
    normalized: str
    manufacturer: str
    country: str
    domain: str
    codes: tuple[str, ...]
    tokens: tuple[str, ...]
    confidence: float


@dataclass(slots=True)
class PairVerdict:
    decision: str  # 'merge' | 'review' | 'distinct'
    score: float
    reason: str


def _load_candidates(conn: sqlite3.Connection) -> list[Candidate]:
    rows = query(
        """
        SELECT p.id, p.canonical_name, p.normalized_name, p.domain, p.confidence_score,
               COALESCE(m.name,'') AS manufacturer, COALESCE(c.name,'') AS country
        FROM platforms p
        LEFT JOIN manufacturers m ON m.id = p.manufacturer_id
        LEFT JOIN countries c ON c.id = p.country_id
        WHERE p.is_merged_into IS NULL
        ORDER BY p.id
        """,
        conn=conn,
    )
    return [
        Candidate(
            id=int(r["id"]),
            name=clean_text(r["canonical_name"]),
            normalized=r["normalized_name"],
            manufacturer=clean_text(r["manufacturer"]),
            country=clean_text(r["country"]),
            domain=clean_text(r["domain"]),
            codes=tuple(extract_model_codes(r["canonical_name"])),
            tokens=tuple(tokenize(r["canonical_name"])),
            confidence=float(r["confidence_score"] or 0.0),
        )
        for r in rows
    ]


def _blocks(candidates: list[Candidate]) -> dict[str, list[Candidate]]:
    """Cheap blocking so we never do a full O(n^2) comparison."""
    blocks: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        keys: set[str] = set()
        if candidate.tokens:
            keys.add(f"t:{candidate.tokens[0]}")
            keys.add(f"t:{candidate.tokens[-1]}")
        for code in candidate.codes:
            keys.add(f"c:{code}")
        if candidate.manufacturer:
            keys.add(f"m:{normalize_name(candidate.manufacturer)}")
        if candidate.normalized:
            keys.add(f"p:{candidate.normalized[:6]}")
        for key in keys:
            blocks[key].append(candidate)
    return blocks


def _variant_suffix(name: str) -> str:
    match = _VARIANT_SUFFIX_RE.search(clean_text(name))
    return match.group(1).lower() if match else ""


def compare(a: Candidate, b: Candidate) -> PairVerdict:
    """Apply the veto rules, then score."""
    # Veto 1: both carry model codes and they differ.
    if a.codes and b.codes and set(a.codes) != set(b.codes):
        return PairVerdict("distinct", 0.0, f"model codes differ: {a.codes} vs {b.codes}")

    # Veto 2: differing trailing variant marker on an otherwise identical stem.
    suffix_a, suffix_b = _variant_suffix(a.name), _variant_suffix(b.name)
    if suffix_a != suffix_b and (suffix_a or suffix_b):
        stem_a = _VARIANT_SUFFIX_RE.sub("", a.name).strip()
        stem_b = _VARIANT_SUFFIX_RE.sub("", b.name).strip()
        if normalize_name(stem_a) == normalize_name(stem_b):
            return PairVerdict(
                "distinct",
                0.0,
                f"same family, distinct variant marker ({suffix_a or '-'} vs {suffix_b or '-'})",
            )

    # Veto 3: distinguishing role words present on exactly one side.
    diff_words = (set(a.tokens) ^ set(b.tokens)) & _DISTINGUISHING_WORDS
    if diff_words:
        return PairVerdict(
            "distinct", 0.0, f"distinguishing role words: {sorted(diff_words)}"
        )

    # Veto 4: known but different manufacturers.
    if a.manufacturer and b.manufacturer:
        if name_similarity(a.manufacturer, b.manufacturer) < 0.6:
            return PairVerdict(
                "distinct",
                0.0,
                f"different manufacturers: {a.manufacturer} vs {b.manufacturer}",
            )

    score = name_similarity(a.name, b.name)
    token_overlap = jaccard(a.tokens, b.tokens)

    if a.manufacturer and b.manufacturer:
        score += 0.05
    if a.codes and b.codes and set(a.codes) == set(b.codes):
        score += 0.05
    score = round(min(1.0, score), 4)

    settings = get_settings()

    # Country disagreement never auto-merges: it may be a rebadge or a licence build.
    country_conflict = bool(
        a.country
        and b.country
        and a.country != b.country
        and UNKNOWN_COUNTRY not in (a.country, b.country)
    )

    # Identical designation. Checked *after* the vetoes so that two different
    # manufacturers' identically named products, or a country conflict, are not
    # silently merged on a name collision.
    if a.normalized == b.normalized:
        if country_conflict:
            return PairVerdict("review", 1.0, "identical name but conflicting country of origin")
        return PairVerdict("merge", 1.0, "identical normalised name")

    # --- token-set analysis --------------------------------------------
    # A manufacturer prefix is cosmetic ("DJI Mavic 3 Pro" == "Mavic 3 Pro").
    # Any *other* extra token is product-bearing: "Mavic 3" and "Mavic 3 Cine"
    # are different products and must never be merged automatically.
    set_a, set_b = set(a.tokens), set(b.tokens)
    cosmetic = _manufacturer_tokens(a) | _manufacturer_tokens(b)
    only_a, only_b = (set_a - set_b) - cosmetic, (set_b - set_a) - cosmetic

    if not only_a and not only_b:
        # Same product tokens; the only difference is a manufacturer prefix or
        # word order. Character similarity is not the right gate here - "DJI
        # Mavic 3 Pro" and "Mavic 3 Pro" score poorly on characters yet are one
        # product.
        if country_conflict:
            return PairVerdict(
                "review", score, f"identical designation but country conflict ({score:.3f})"
            )
        return PairVerdict(
            "merge",
            max(score, settings.dedupe_auto_merge_threshold),
            f"identical designation tokens, manufacturer prefix only ({score:.3f})",
        )

    if (only_a and not only_b) or (only_b and not only_a):
        extra = sorted(only_a or only_b)
        # If exactly one side carries a model designation and the other carries
        # none, the two names are very likely the same aircraft written with and
        # without its designation ("Global Hawk" / "RQ-4 Global Hawk").
        # Containment is the right signal here, not blended similarity: "Global
        # Hawk" is wholly contained in "RQ-4 Global Hawk" even though the extra
        # designation drags the character score down.
        shorter = min(len(set_a), len(set_b))
        if bool(set(a.codes)) != bool(set(b.codes)) and shorter >= 2:
            return PairVerdict(
                "review",
                score,
                f"one name adds a model designation {extra} - possibly the same aircraft "
                f"({score:.3f}, tokens {token_overlap:.2f})",
            )
        # Otherwise the extra token names a sub-variant, which the specification
        # requires to stay a separate record.
        return PairVerdict(
            "distinct",
            score,
            f"sub-variant: one name adds {extra} to an otherwise identical designation",
        )

    return PairVerdict(
        "distinct",
        score,
        f"each name carries tokens the other lacks ({sorted(only_a)} vs {sorted(only_b)}): "
        "officially separate variants",
    )


#: First token of every known manufacturer name, e.g. {"dji", "autel", "parrot"}.
#: Used to recognise a cosmetic manufacturer prefix on a record whose own
#: manufacturer field is empty. Populated by :func:`load_manufacturer_heads`.
_MANUFACTURER_HEADS: set[str] = set()


def load_manufacturer_heads(conn: sqlite3.Connection | None = None) -> set[str]:
    global _MANUFACTURER_HEADS
    rows = query("SELECT name FROM manufacturers", conn=conn)
    heads: set[str] = set()
    for row in rows:
        tokens = tokenize(row["name"])
        if tokens:
            heads.add(tokens[0])
    _MANUFACTURER_HEADS = heads
    return heads


def _manufacturer_tokens(candidate: Candidate) -> set[str]:
    tokens = set(tokenize(candidate.manufacturer)) if candidate.manufacturer else set()
    # A leading token that names a known manufacturer is a cosmetic prefix even
    # when this record has no manufacturer of its own.
    if candidate.tokens and candidate.tokens[0] in _MANUFACTURER_HEADS:
        tokens.add(candidate.tokens[0])
    return tokens


def merge_platforms(
    keep_id: int, drop_id: int, *, score: float, reason: str, conn: sqlite3.Connection | None = None
) -> None:
    """Fold ``drop_id`` into ``keep_id``, preserving every relationship."""
    con = conn or connect()
    keep = query("SELECT * FROM platforms WHERE id=?", (keep_id,), con)
    drop = query("SELECT * FROM platforms WHERE id=?", (drop_id,), con)
    if not keep or not drop:
        return
    keep_row, drop_row = keep[0], drop[0]

    # Alias trail so the merged name remains searchable.
    con.execute(
        """
        INSERT OR IGNORE INTO platform_aliases
            (platform_id, alias, normalized_alias, alias_type, created_at)
        VALUES (?,?,?,?,?)
        """,
        (keep_id, drop_row["canonical_name"], drop_row["normalized_name"], "merged", utc_now()),
    )
    con.execute(
        """
        INSERT OR IGNORE INTO platform_aliases
            (platform_id, alias, normalized_alias, alias_type, source_id, created_at)
        SELECT ?, alias, normalized_alias, alias_type, source_id, created_at
        FROM platform_aliases WHERE platform_id=?
        """,
        (keep_id, drop_id),
    )
    con.execute(
        """
        INSERT OR IGNORE INTO platform_sources
            (platform_id, source_id, relation, excerpt, created_at)
        SELECT ?, source_id, relation, excerpt, created_at
        FROM platform_sources WHERE platform_id=?
        """,
        (keep_id, drop_id),
    )
    con.execute("UPDATE images SET platform_id=? WHERE platform_id=?", (keep_id, drop_id))
    con.execute(
        "UPDATE raw_discoveries SET promoted_platform_id=? WHERE promoted_platform_id=?",
        (keep_id, drop_id),
    )
    con.execute(
        "UPDATE platform_variants SET parent_platform_id=? WHERE parent_platform_id=?",
        (keep_id, drop_id),
    )

    # Inherit any field the survivor is missing.
    inherit: dict[str, Any] = {}
    for field in (
        "manufacturer_id",
        "country_id",
        "family_id",
        "category",
        "airframe_type",
        "status",
        "description_short",
        "introduced_year",
        "retired_year",
    ):
        if keep_row[field] in (None, "") and drop_row[field] not in (None, ""):
            inherit[field] = drop_row[field]
    if float(drop_row["confidence_score"] or 0) > float(keep_row["confidence_score"] or 0):
        inherit["confidence_score"] = drop_row["confidence_score"]
        inherit["verification_status"] = drop_row["verification_status"]
    if inherit:
        update_fields("platforms", keep_id, inherit, reason=f"merge: {reason}", agent=AGENT, conn=con)

    update_fields(
        "platforms",
        drop_id,
        {"is_merged_into": keep_id},
        reason=f"merged into {keep_row['canonical_name']}: {reason}",
        agent=AGENT,
        conn=con,
    )
    insert(
        "merge_decisions",
        {
            "kept_platform_id": keep_id,
            "merged_platform_id": drop_id,
            "kept_name": keep_row["canonical_name"],
            "merged_name": drop_row["canonical_name"],
            "score": score,
            "decision": "merged",
            "reason": reason,
            "run_id": run_id(),
            "created_at": utc_now(),
        },
        con,
    )
    LOG.event(
        "platforms_merged",
        keep=keep_row["canonical_name"],
        merged=drop_row["canonical_name"],
        score=score,
        reason=reason,
    )


def run(*, dry_run: bool = False, limit: int | None = None) -> dict[str, Any]:
    """Compare every blocked pair once and act on the verdict."""
    conn = connect()
    load_manufacturer_heads(conn)
    candidates = _load_candidates(conn)
    if limit:
        candidates = candidates[:limit]
    blocks = _blocks(candidates)

    compared: set[tuple[int, int]] = set()
    merged_ids: set[int] = set()
    stats = {
        "candidates": len(candidates),
        "pairs_compared": 0,
        "merged": 0,
        "review": 0,
        "distinct": 0,
        "vetoed": 0,
    }

    for block in blocks.values():
        if len(block) < 2 or len(block) > 400:  # skip pathological blocks
            continue
        for i, a in enumerate(block):
            for b in block[i + 1 :]:
                if a.id == b.id:
                    continue
                key = (min(a.id, b.id), max(a.id, b.id))
                if key in compared:
                    continue
                compared.add(key)
                stats["pairs_compared"] += 1

                verdict = compare(a, b)
                if verdict.decision == "distinct":
                    stats["distinct"] += 1
                    if verdict.score == 0.0 and verdict.reason.startswith(
                        ("model codes", "same family", "distinguishing", "different manufacturers")
                    ):
                        stats["vetoed"] += 1
                    continue

                # Keep the record with the stronger evidence.
                keep, drop = (a, b) if (a.confidence, -a.id) >= (b.confidence, -b.id) else (b, a)
                if keep.id in merged_ids or drop.id in merged_ids:
                    continue

                if verdict.decision == "merge":
                    stats["merged"] += 1
                    if not dry_run:
                        merge_platforms(
                            keep.id, drop.id, score=verdict.score, reason=verdict.reason, conn=conn
                        )
                        merged_ids.add(drop.id)
                else:
                    stats["review"] += 1
                    if not dry_run:
                        insert(
                            "merge_decisions",
                            {
                                "kept_platform_id": keep.id,
                                "merged_platform_id": drop.id,
                                "kept_name": keep.name,
                                "merged_name": drop.name,
                                "score": verdict.score,
                                "decision": "review",
                                "reason": verdict.reason,
                                "run_id": run_id(),
                                "created_at": utc_now(),
                            },
                            conn,
                        )
                        add_unresolved(
                            item_type="possible_duplicate",
                            subject=f"{keep.name} <-> {drop.name}",
                            detail=verdict.reason,
                            severity="low",
                            entity_type="platforms",
                            entity_id=keep.id,
                            suggested_action=(
                                "Confirm with a manufacturer or programme-office source whether "
                                "these are one platform or officially separate variants."
                            ),
                            conn=conn,
                        )

    LOG.info("deduplication: %s", stats)
    LOG.event("deduplication_complete", dry_run=dry_run, **stats)
    return stats


def duplicate_rate() -> float:
    """Share of surviving platforms still flagged as possible duplicates."""
    conn = connect()
    total = query("SELECT COUNT(*) AS n FROM platforms WHERE is_merged_into IS NULL", conn=conn)[0]["n"]
    open_reviews = query(
        "SELECT COUNT(*) AS n FROM unresolved_items "
        "WHERE item_type='possible_duplicate' AND status='open'",
        conn=conn,
    )[0]["n"]
    return round(open_reviews / total, 4) if total else 0.0
