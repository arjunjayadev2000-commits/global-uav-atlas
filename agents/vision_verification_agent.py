"""Optional vision verification of image identity.

When an Anthropic API key is present, each selected atlas image is shown to a
vision model together with the platform name, manufacturer, country and the file
metadata, and the model must answer with one of:

``match`` | ``probable match`` | ``uncertain`` | ``mismatch``

plus a short explanation.  The verdict, confidence and explanation are stored on
the image row and in ``verification_events``.

Without a key the pipeline continues on metadata-based verification only,
flagging low-confidence images for manual review.  Nothing here is allowed to
stop the run, and OCR-style text evidence is never treated as conclusive.
"""

from __future__ import annotations

import base64
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db import add_unresolved, connect, query, record_verification, update_fields
from app.logging import AgentLogger
from app.models import (
    IDENTITY_MATCH,
    IDENTITY_MISMATCH,
    IDENTITY_PROBABLE,
    IDENTITY_UNCERTAIN,
    IdentityVerdict,
)
from app.utils import clean_text

LOG = AgentLogger("vision_verification_agent")
AGENT = "vision_verification_agent"

VALID_VERDICTS = {IDENTITY_MATCH, IDENTITY_PROBABLE, IDENTITY_UNCERTAIN, IDENTITY_MISMATCH}

PROMPT = """You are verifying whether a photograph shows a specific unmanned aerial vehicle.

Platform name: {name}
Manufacturer: {manufacturer}
Country of origin: {country}
Category: {category}
File title: {title}
Source page: {source_page}

Judge ONLY from what is visible in the image plus the metadata above. Text
appearing in the image is weak evidence and must never be the sole basis for a
match. If the image shows a different aircraft type, a model/mock-up presented as
the real airframe, a logo, or is too ambiguous to tell, say so.

Reply with strict JSON and nothing else:
{{"verdict": "match" | "probable match" | "uncertain" | "mismatch",
  "confidence": <number between 0 and 1>,
  "explanation": "<one or two sentences>"}}"""


def available() -> bool:
    settings = get_settings()
    if not settings.vision_enabled or not settings.anthropic_api_key:
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        LOG.warning("anthropic SDK not installed; vision verification unavailable")
        return False
    return True


def _client() -> Any:
    import anthropic

    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key)


def _encode(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
    return media_type, base64.standard_b64encode(data).decode("ascii")


def parse_response(text: str) -> IdentityVerdict:
    """Parse the model reply defensively - a malformed reply means 'uncertain'."""
    raw = clean_text(text)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return IdentityVerdict(IDENTITY_UNCERTAIN, 0.0, f"unparseable reply: {raw[:120]}", "vision")
    try:
        payload = json.loads(match.group(0))
    except ValueError:
        return IdentityVerdict(IDENTITY_UNCERTAIN, 0.0, f"invalid JSON: {raw[:120]}", "vision")

    verdict = str(payload.get("verdict", "")).strip().lower()
    if verdict not in VALID_VERDICTS:
        verdict = IDENTITY_UNCERTAIN
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    explanation = clean_text(payload.get("explanation", ""))[:600]
    return IdentityVerdict(verdict, confidence, explanation, "vision")


def verify_image(row: sqlite3.Row, *, client: Any = None) -> IdentityVerdict:
    settings = get_settings()
    path = Path(row["atlas_path"] or row["local_path"] or "")
    if not path.is_file():
        return IdentityVerdict(IDENTITY_UNCERTAIN, 0.0, "image file not found on disk", "vision")

    media_type, encoded = _encode(path)
    prompt = PROMPT.format(
        name=row["canonical_name"],
        manufacturer=row["manufacturer"] or "unknown",
        country=row["country"] or "unknown",
        category=row["category"] or "unknown",
        title=row["source_page_url"] or "",
        source_page=row["source_page_url"] or "",
    )
    api = client or _client()
    message = api.messages.create(
        model=settings.vision_model,
        max_tokens=400,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": encoded},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    text = "".join(
        block.text for block in getattr(message, "content", []) if getattr(block, "type", "") == "text"
    )
    return parse_response(text)


def run(*, limit: int | None = None) -> dict[str, Any]:
    """Verify selected atlas images; degrade gracefully when unavailable."""
    conn = connect()
    settings = get_settings()
    stats: dict[str, Any] = {
        "available": available(),
        "checked": 0,
        "match": 0,
        "probable": 0,
        "uncertain": 0,
        "mismatch": 0,
        "errors": 0,
        "flagged_for_review": 0,
    }

    sql = """
        SELECT i.id, i.local_path, i.atlas_path, i.source_page_url, i.identity_confidence,
               i.identity_verdict, p.canonical_name, p.category,
               COALESCE(m.name,'') AS manufacturer, COALESCE(c.name,'') AS country
        FROM images i
        JOIN platforms p ON p.id = i.platform_id
        LEFT JOIN manufacturers m ON m.id = p.manufacturer_id
        LEFT JOIN countries c ON c.id = p.country_id
        WHERE i.selected_for_atlas = 1
        ORDER BY i.identity_confidence ASC, i.id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = query(sql, conn=conn)

    if not stats["available"]:
        LOG.info(
            "vision verification unavailable (no API key or SDK); "
            "continuing with metadata-based verification for %d images",
            len(rows),
        )
        for row in rows:
            if float(row["identity_confidence"] or 0) < 0.6:
                stats["flagged_for_review"] += 1
                add_unresolved(
                    item_type="image_identity_unverified",
                    subject=row["canonical_name"],
                    detail=(
                        f"metadata-only identity confidence "
                        f"{float(row['identity_confidence'] or 0):.2f}; no vision API available"
                    ),
                    severity="medium",
                    entity_type="images",
                    entity_id=int(row["id"]),
                    suggested_action="Set ANTHROPIC_API_KEY and re-run `python run.py --verify`, or review by eye.",
                    blocker="no vision API key configured",
                    conn=conn,
                )
        LOG.event("vision_verification_skipped", **stats)
        return stats

    api = _client()
    budget = settings.vision_max_calls or len(rows)
    for row in rows[:budget]:
        stats["checked"] += 1
        try:
            verdict = verify_image(row, client=api)
        except Exception as exc:
            stats["errors"] += 1
            LOG.warning("vision verification failed for %s: %s", row["canonical_name"], exc)
            continue

        key = {
            IDENTITY_MATCH: "match",
            IDENTITY_PROBABLE: "probable",
            IDENTITY_UNCERTAIN: "uncertain",
            IDENTITY_MISMATCH: "mismatch",
        }[verdict.verdict]
        stats[key] += 1

        update_fields(
            "images",
            int(row["id"]),
            {
                "identity_verdict": verdict.verdict,
                "identity_confidence": verdict.confidence,
                "identity_explanation": f"[vision] {verdict.explanation}",
                "selected_for_atlas": 0 if verdict.verdict == IDENTITY_MISMATCH else 1,
                "rejection_reason": "vision verification: mismatch"
                if verdict.verdict == IDENTITY_MISMATCH
                else None,
            },
            reason="vision verification",
            agent=AGENT,
            conn=conn,
        )
        record_verification(
            entity_type="images",
            entity_id=int(row["id"]),
            agent=AGENT,
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            explanation=verdict.explanation,
            evidence={"model": settings.vision_model},
            conn=conn,
        )
        if verdict.verdict in (IDENTITY_UNCERTAIN, IDENTITY_MISMATCH):
            stats["flagged_for_review"] += 1
            add_unresolved(
                item_type="image_identity_unverified",
                subject=row["canonical_name"],
                detail=f"vision verdict {verdict.verdict}: {verdict.explanation}",
                severity="high" if verdict.verdict == IDENTITY_MISMATCH else "medium",
                entity_type="images",
                entity_id=int(row["id"]),
                suggested_action="Replace the image or confirm the identification by hand.",
                conn=conn,
            )

    LOG.info("vision verification: %s", stats)
    LOG.event("vision_verification_complete", **stats)
    return stats
