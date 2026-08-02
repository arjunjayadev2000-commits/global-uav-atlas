"""Image discovery: find, licence-screen, download and validate one photo per platform.

Flow per platform (all steps resumable, all failures isolated):

1. skip if an atlas image is already selected;
2. ask Wikimedia Commons for candidates (scored, pre-filtered);
3. licence-screen each candidate (:mod:`agents.image_license_agent`);
4. download the best surviving candidate to
   ``images/<country>/<platform-slug>/``;
5. validate bytes, reject exact and perceptual duplicates
   (:mod:`agents.image_validation_agent`);
6. build derivatives and record full provenance in ``images`` + ``image_sources``;
7. if nothing survives, write an unresolved item carrying the Commons media
   search URL so the gap is actionable rather than silent.

A ``sideload`` path exists for environments where outbound access to image hosts
is blocked by policy: drop files plus a manifest into ``data/imports/images``
and the same licence/validation/provenance rules are applied locally.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from agents import image_license_agent, image_validation_agent
from app.config import get_settings
from app.db import (
    add_unresolved,
    connect,
    get_or_create_source,
    insert,
    insert_ignore,
    note_url,
    query,
    query_one,
    record_verification,
)
from app.logging import AgentLogger, utc_now
from app.models import (
    IDENTITY_MATCH,
    IDENTITY_PROBABLE,
    IDENTITY_UNCERTAIN,
    ImageCandidate,
)
from app.utils import clean_text, name_similarity, safe_join, slugify, tokenize
from crawlers import wikimedia
from crawlers.http import FetchError, get_client

LOG = AgentLogger("image_discovery_agent")
AGENT = "image_discovery_agent"


# ---------------------------------------------------------------------------
# Metadata-based identity scoring (always runs; vision agent refines it later)
# ---------------------------------------------------------------------------


def metadata_identity(
    platform_name: str,
    manufacturer: str,
    country: str,
    candidate: ImageCandidate,
) -> tuple[str, float, str]:
    """Score how strongly the file's own metadata supports the platform identity.

    OCR-style evidence is deliberately excluded: per the specification, text on
    or about an image is never conclusive on its own.
    """
    haystack = " ".join(
        [candidate.title, candidate.description, " ".join(candidate.categories)]
    ).lower()
    tokens = set(tokenize(platform_name))
    hits = {t for t in tokens if t in haystack}
    coverage = len(hits) / len(tokens) if tokens else 0.0
    title_score = name_similarity(platform_name, candidate.title)

    score = round(0.6 * max(coverage, title_score) + 0.4 * coverage, 3)
    reasons = [f"name-token coverage {coverage:.0%}", f"title similarity {title_score:.2f}"]

    if manufacturer and manufacturer.lower() in haystack:
        score = min(1.0, score + 0.08)
        reasons.append("manufacturer named in file metadata")
    if country and country.lower() in haystack:
        score = min(1.0, score + 0.04)
        reasons.append("country named in file metadata")

    if score >= 0.82:
        verdict = IDENTITY_MATCH
    elif score >= 0.6:
        verdict = IDENTITY_PROBABLE
    else:
        verdict = IDENTITY_UNCERTAIN
    return verdict, round(score, 3), "; ".join(reasons)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def image_directory(country: str, platform_name: str) -> Path:
    """``images/<country>/<platform>/`` - traversal-safe by construction."""
    settings = get_settings()
    return safe_join(settings.paths.images, country or "unknown", platform_name)


def _store_image_row(
    conn: sqlite3.Connection,
    *,
    platform_id: int,
    candidate: ImageCandidate,
    license_row: dict[str, Any],
    verdict: Any,
    paths: dict[str, str],
    identity: tuple[str, float, str],
    local_path: Path,
) -> int:
    identity_verdict, identity_confidence, identity_reason = identity
    image_id = insert(
        "images",
        {
            "platform_id": platform_id,
            "local_path": str(local_path),
            "thumbnail_path": paths.get("thumbnail_path"),
            "atlas_path": paths.get("atlas_path"),
            "webp_path": paths.get("webp_path"),
            "source_url": candidate.source_url,
            "source_page_url": candidate.source_page_url,
            "photographer": candidate.photographer or None,
            "width": verdict.width,
            "height": verdict.height,
            "mime_type": verdict.mime_type,
            "file_size": local_path.stat().st_size if local_path.is_file() else None,
            "sha256": verdict.sha256,
            "perceptual_hash": verdict.perceptual_hash,
            "identity_confidence": identity_confidence,
            "identity_verdict": identity_verdict,
            "identity_explanation": identity_reason,
            "validation_status": "ok",
            "selected_for_atlas": 0,
            "retrieved_at": utc_now(),
            "created_at": utc_now(),
            **license_row,
        },
        conn,
    )
    source_id = get_or_create_source(
        title=f"{candidate.provider}: {candidate.title}" if candidate.title else candidate.provider,
        url=candidate.source_page_url or candidate.source_url,
        publisher=candidate.provider,
        source_type="image repository",
        credibility_tier=3,
        notes=f"licence: {license_row.get('license_name') or 'unknown'}",
        conn=conn,
    )
    insert_ignore(
        "image_sources",
        {
            "image_id": image_id,
            "source_id": source_id,
            "relation": "hosts",
            "created_at": utc_now(),
        },
        conn,
    )
    record_verification(
        entity_type="images",
        entity_id=image_id,
        agent=AGENT,
        verdict=identity_verdict,
        confidence=identity_confidence,
        explanation=identity_reason,
        evidence={"title": candidate.title, "source_page": candidate.source_page_url},
        conn=conn,
    )
    return image_id


def _select_for_atlas(conn: sqlite3.Connection, platform_id: int, image_id: int) -> None:
    conn.execute("UPDATE images SET selected_for_atlas=0 WHERE platform_id=?", (platform_id,))
    conn.execute("UPDATE images SET selected_for_atlas=1 WHERE id=?", (image_id,))


# ---------------------------------------------------------------------------
# Main pass
# ---------------------------------------------------------------------------


def platforms_needing_images(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
    country: str | None = None,
    manufacturer: str | None = None,
) -> list[sqlite3.Row]:
    sql = """
        SELECT p.id, p.canonical_name, COALESCE(c.name,'Unknown') AS country,
               COALESCE(m.name,'') AS manufacturer, p.domain
        FROM platforms p
        LEFT JOIN countries c ON c.id = p.country_id
        LEFT JOIN manufacturers m ON m.id = p.manufacturer_id
        WHERE p.is_merged_into IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM images i
              WHERE i.platform_id = p.id AND i.selected_for_atlas = 1
          )
    """
    params: list[Any] = []
    if country:
        sql += " AND c.name = ?"
        params.append(country)
    if manufacturer:
        sql += " AND m.name LIKE ?"
        params.append(f"%{manufacturer}%")
    sql += " ORDER BY p.confidence_score DESC, p.id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return query(sql, params, conn)


def acquire_for_platform(
    platform: sqlite3.Row,
    *,
    conn: sqlite3.Connection,
    max_candidates: int = 8,
) -> dict[str, Any]:
    """Try to obtain one licensed, validated image for a single platform."""
    settings = get_settings()
    name = clean_text(platform["canonical_name"])
    result: dict[str, Any] = {"platform": name, "status": "none", "reason": ""}

    try:
        candidates = wikimedia.search_images(
            name,
            manufacturer=platform["manufacturer"],
            country=platform["country"],
            limit=max_candidates,
        )
    except FetchError as exc:
        result.update(status="blocked", reason=str(exc)[:300])
        add_unresolved(
            item_type="image_missing",
            subject=name,
            detail=f"image search unavailable: {exc}",
            severity="high",
            entity_type="platforms",
            entity_id=int(platform["id"]),
            suggested_action=(
                "Run the image pass from a network that permits Wikimedia Commons, or "
                f"sideload a licensed file. Search: {wikimedia.media_search_url(name)}"
            ),
            blocker="network egress policy blocks the image provider",
            conn=conn,
        )
        return result

    screened = image_license_agent.run(candidates)
    rejected: list[str] = []

    for candidate, licence in screened:
        if not licence.acceptable:
            rejected.append(f"{candidate.title}: {licence.reason}")
            continue
        if candidate.width and candidate.width < settings.image_min_width:
            rejected.append(f"{candidate.title}: below minimum width")
            continue

        directory = image_directory(platform["country"], name)
        extension = image_validation_agent.ACCEPTED_MIME.get(candidate.mime_type, ".jpg")
        stem = slugify(candidate.title or name)[:60] or slugify(name)
        local_path = directory / f"{stem}{extension}"

        try:
            response = get_client().download(candidate.source_url, local_path)
        except FetchError as exc:
            rejected.append(f"{candidate.title}: download failed ({exc})")
            note_url(candidate.source_url, status=f"error: {exc}"[:200], conn=conn)
            continue

        verdict = image_validation_agent.validate_bytes(
            response.content, declared_mime=candidate.mime_type
        )
        if not verdict.ok:
            rejected.append(f"{candidate.title}: {verdict.reason}")
            local_path.unlink(missing_ok=True)
            continue

        exact = image_validation_agent.find_exact_duplicate(
            verdict.sha256, exclude_platform_id=int(platform["id"])
        )
        if exact:
            rejected.append(f"{candidate.title}: identical file already used elsewhere")
            local_path.unlink(missing_ok=True)
            continue

        near = image_validation_agent.find_perceptual_duplicate(
            verdict.perceptual_hash, exclude_platform_id=int(platform["id"])
        )
        if near:
            rejected.append(
                f"{candidate.title}: perceptual duplicate of image used for "
                f"{near.get('canonical_name')}"
            )
            local_path.unlink(missing_ok=True)
            continue

        identity = metadata_identity(
            name, platform["manufacturer"], platform["country"], candidate
        )
        if identity[0] == IDENTITY_UNCERTAIN and identity[1] < 0.35:
            rejected.append(f"{candidate.title}: identity too weak ({identity[1]:.2f})")
            local_path.unlink(missing_ok=True)
            continue

        paths = image_validation_agent.build_derivatives(
            local_path, destination_dir=local_path.parent, stem=local_path.stem
        )
        license_row = image_license_agent.verdict_to_row(licence)
        image_id = _store_image_row(
            conn,
            platform_id=int(platform["id"]),
            candidate=candidate,
            license_row=license_row,
            verdict=verdict,
            paths=paths,
            identity=identity,
            local_path=local_path,
        )
        _select_for_atlas(conn, int(platform["id"]), image_id)
        note_url(candidate.source_url, status="ok", content_sha256=verdict.sha256, conn=conn)

        result.update(
            status="ok",
            image_id=image_id,
            license=licence.license_name,
            identity=identity[0],
            confidence=identity[1],
            width=verdict.width,
        )
        LOG.event(
            "image_acquired",
            platform=name,
            license=licence.license_name,
            identity=identity[0],
            confidence=identity[1],
            source_page=candidate.source_page_url,
        )
        return result

    result.update(status="none", reason="; ".join(rejected[:5]) or "no candidates returned")
    add_unresolved(
        item_type="image_missing",
        subject=name,
        detail=result["reason"][:500],
        severity="medium",
        entity_type="platforms",
        entity_id=int(platform["id"]),
        suggested_action=(
            "Locate a licensed photograph and sideload it. Commons search: "
            f"{wikimedia.media_search_url(name)}"
        ),
        conn=conn,
    )
    return result


def run(
    *,
    limit: int | None = None,
    country: str | None = None,
    manufacturer: str | None = None,
) -> dict[str, Any]:
    """Acquire images for every platform that still lacks one."""
    conn = connect()
    targets = platforms_needing_images(
        conn, limit=limit, country=country, manufacturer=manufacturer
    )
    stats = {"attempted": 0, "acquired": 0, "none": 0, "blocked": 0, "errors": 0}

    for platform in targets:
        stats["attempted"] += 1
        try:
            outcome = acquire_for_platform(platform, conn=conn)
        except Exception as exc:
            stats["errors"] += 1
            LOG.error("image acquisition failed for %s: %s", platform["canonical_name"], exc)
            LOG.event(
                "image_acquisition_error",
                status="error",
                platform=platform["canonical_name"],
                error=str(exc)[:300],
            )
            continue
        if outcome["status"] == "ok":
            stats["acquired"] += 1
        elif outcome["status"] == "blocked":
            stats["blocked"] += 1
        else:
            stats["none"] += 1

        # Once the provider is unreachable, stop hammering it for every platform.
        if stats["blocked"] >= 3 and stats["acquired"] == 0:
            LOG.warning(
                "image provider unreachable for %d consecutive platforms - "
                "stopping the image pass and recording the blocker",
                stats["blocked"],
            )
            add_unresolved(
                item_type="pipeline_blocker",
                subject="Image acquisition unavailable in this environment",
                detail=(
                    "Wikimedia Commons and all other configured image hosts were refused by "
                    "the network egress policy (HTTP 403 at the proxy). No image bytes could "
                    "be retrieved. Every affected platform has an individual image_missing "
                    "item carrying its Commons media-search URL."
                ),
                severity="high",
                suggested_action=(
                    "Re-run `python run.py --images` where commons.wikimedia.org and "
                    "upload.wikimedia.org are reachable, or sideload files with "
                    "`python run.py --sideload-images`."
                ),
                blocker="network egress policy",
                conn=conn,
            )
            break

    LOG.info("image discovery: %s", stats)
    LOG.event("image_discovery_complete", **stats)
    return stats


# ---------------------------------------------------------------------------
# Sideload path (for restricted-network environments)
# ---------------------------------------------------------------------------

SIDELOAD_MANIFEST_COLUMNS = (
    "platform_name",
    "file",
    "source_url",
    "source_page_url",
    "photographer",
    "license_name",
    "license_url",
)


def sideload(manifest_path: Path | None = None) -> dict[str, Any]:
    """Ingest locally provided images described by a CSV manifest.

    The manifest must carry full provenance; files without a licence and a
    source page are rejected exactly as network-sourced images would be.
    """
    from crawlers.extract import parse_csv

    settings = get_settings()
    manifest = manifest_path or (settings.paths.imports / "images" / "manifest.csv")
    conn = connect()
    stats = {"rows": 0, "ingested": 0, "rejected": 0, "missing_file": 0}
    if not manifest.is_file():
        LOG.warning("no sideload manifest at %s", manifest)
        return stats | {"skipped": True}

    rows = parse_csv(manifest.read_text(encoding="utf-8-sig"))
    for row in rows:
        stats["rows"] += 1
        platform_name = clean_text(row.get("platform_name"))
        platform = query_one(
            "SELECT p.id, p.canonical_name, COALESCE(c.name,'Unknown') AS country, "
            "COALESCE(m.name,'') AS manufacturer FROM platforms p "
            "LEFT JOIN countries c ON c.id=p.country_id "
            "LEFT JOIN manufacturers m ON m.id=p.manufacturer_id "
            "WHERE p.canonical_name=? AND p.is_merged_into IS NULL",
            (platform_name,),
            conn,
        )
        if platform is None:
            stats["rejected"] += 1
            LOG.warning("sideload: unknown platform %r", platform_name)
            continue

        file_path = Path(clean_text(row.get("file")))
        if not file_path.is_absolute():
            file_path = manifest.parent / file_path
        if not file_path.is_file():
            stats["missing_file"] += 1
            continue

        candidate = ImageCandidate(
            platform_id=int(platform["id"]),
            platform_name=platform_name,
            source_url=clean_text(row.get("source_url")),
            source_page_url=clean_text(row.get("source_page_url")),
            title=file_path.stem,
            photographer=clean_text(row.get("photographer")),
            license_name=clean_text(row.get("license_name")),
            license_url=clean_text(row.get("license_url")),
            provider=clean_text(row.get("provider")) or "sideloaded",
        )
        licence = image_license_agent.evaluate(candidate)
        if not licence.acceptable:
            stats["rejected"] += 1
            LOG.warning("sideload rejected %s: %s", file_path.name, licence.reason)
            continue

        data = file_path.read_bytes()
        verdict = image_validation_agent.validate_bytes(data)
        if not verdict.ok:
            stats["rejected"] += 1
            LOG.warning("sideload rejected %s: %s", file_path.name, verdict.reason)
            continue

        directory = image_directory(platform["country"], platform["canonical_name"])
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{slugify(file_path.stem)}{file_path.suffix.lower()}"
        destination.write_bytes(data)

        paths = image_validation_agent.build_derivatives(
            destination, destination_dir=directory, stem=destination.stem
        )
        identity = metadata_identity(
            platform["canonical_name"], platform["manufacturer"], platform["country"], candidate
        )
        image_id = _store_image_row(
            conn,
            platform_id=int(platform["id"]),
            candidate=candidate,
            license_row=image_license_agent.verdict_to_row(licence),
            verdict=verdict,
            paths=paths,
            identity=(identity[0], identity[1], identity[2] + "; sideloaded with manifest provenance"),
            local_path=destination,
        )
        _select_for_atlas(conn, int(platform["id"]), image_id)
        stats["ingested"] += 1

    LOG.info("sideload: %s", stats)
    LOG.event("image_sideload_complete", **stats)
    return stats


def coverage() -> dict[str, Any]:
    conn = connect()
    total = query("SELECT COUNT(*) AS n FROM platforms WHERE is_merged_into IS NULL", conn=conn)[0]["n"]
    with_image = query(
        "SELECT COUNT(DISTINCT platform_id) AS n FROM images WHERE selected_for_atlas=1", conn=conn
    )[0]["n"]
    return {
        "platforms": total,
        "with_image": with_image,
        "without_image": total - with_image,
        "coverage_pct": round(100.0 * with_image / total, 2) if total else 0.0,
    }
