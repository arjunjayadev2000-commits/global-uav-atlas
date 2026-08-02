"""Discovery agent: seed import plus resumable multi-pass source crawling.

Raw discoveries are stored verbatim in ``raw_discoveries`` and are never edited.
Canonicalisation happens later (metadata agent), which keeps the evidence trail
intact and makes it possible to re-derive the atlas from raw material at any
time.

A *pass* is one sweep over the configured strategies.  The agent records the
number of new candidates per pass in ``discovery_runs``; the orchestrator stops
once three consecutive passes add nothing new.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    set_state,
)
from app.logging import AgentLogger, run_id, utc_now
from app.models import RawDiscovery
from app.utils import clean_text
from crawlers import extract, government, manufacturer, public_sources, regulatory
from crawlers.http import FetchError, get_client
from crawlers.public_sources import load_registry

LOG = AgentLogger("discovery_agent")
AGENT = "discovery_agent"

SEED_CANONICAL_CSV = "Global_UAV_Database_2026.csv"
SEED_SOURCE_CSV = "Global_UAV_Database_2026_Source_Records.csv"
SEED_SQLITE = "Global_UAV_Database_2026.sqlite"

#: Credibility tier for each seed sub-dataset (see docs/DATA_SOURCES.md).
SEED_DATASET_TIERS = {
    "Curated UAV Seed 2026": 3,
    "EASA Drones for EU Operations": 1,
    "OpenDroneList": 3,
    "Bard Drone Databook 2019": 2,
}


# ---------------------------------------------------------------------------
# Seed import
# ---------------------------------------------------------------------------


def _register_seed_sources(conn: sqlite3.Connection, seed_dir: Path) -> dict[str, int]:
    """Create ``sources`` rows for every dataset described by the seed package."""
    source_ids: dict[str, int] = {}
    sqlite_path = seed_dir / SEED_SQLITE
    described: list[dict[str, Any]] = []
    if sqlite_path.is_file():
        seed_conn = sqlite3.connect(str(sqlite_path))
        seed_conn.row_factory = sqlite3.Row
        try:
            described = [dict(r) for r in seed_conn.execute("SELECT * FROM sources")]
        except sqlite3.Error as exc:
            LOG.warning("seed sources table unreadable: %s", exc)
        finally:
            seed_conn.close()

    for row in described:
        name = clean_text(row.get("source_name"))
        if not name:
            continue
        source_ids[name] = get_or_create_source(
            title=name,
            url=clean_text(row.get("source_url")),
            publisher=clean_text(row.get("source_url")) or "seed package",
            source_type="seed dataset",
            credibility_tier=SEED_DATASET_TIERS.get(name, 3),
            notes=clean_text(row.get("description"))
            + (f" Limitations: {clean_text(row.get('limitations'))}" if row.get("limitations") else ""),
            retrieved_at=clean_text(row.get("source_date")) or utc_now(),
            conn=conn,
        )

    source_ids.setdefault(
        "Global UAV Database 2026 seed package",
        get_or_create_source(
            title="Global UAV Database 2026 seed package",
            url="local://data/seed/Global_UAV_Database_2026.sqlite",
            publisher="Uploaded seed package",
            source_type="seed dataset",
            credibility_tier=3,
            notes=(
                "Consolidated research database supplied as the project seed. "
                "Compiled 2 August 2026; 591 canonical records over 647 source records. "
                "Aggregator: republishes the four datasets below, so it corroborates "
                "nothing on its own."
            ),
            is_aggregator=True,
            conn=conn,
        ),
    )
    return source_ids


def _split_seed_datasets(value: str) -> list[str]:
    return [clean_text(p) for p in str(value or "").split("|") if clean_text(p)]


def import_seed(*, seed_dir: Path | None = None, force: bool = False) -> dict[str, Any]:
    """Import the uploaded seed package into ``raw_discoveries``.

    Idempotent: raw discoveries are keyed by a fingerprint over
    ``(dataset, normalized name, variant, external ref)``, so re-running the
    import inserts nothing new.
    """
    settings = get_settings()
    directory = seed_dir or settings.paths.seed
    conn = connect()

    canonical_csv = directory / SEED_CANONICAL_CSV
    source_csv = directory / SEED_SOURCE_CSV
    if not canonical_csv.is_file() and not source_csv.is_file():
        LOG.warning("no seed package found in %s", directory)
        LOG.event("seed_import_skipped", status="warning", directory=str(directory))
        return {"imported": 0, "skipped": True}

    source_ids = _register_seed_sources(conn, directory)
    seed_source_id = source_ids.get("Global UAV Database 2026 seed package")

    run_row = insert(
        "discovery_runs",
        {
            "run_id": run_id(),
            "pass_number": 0,
            "strategy": "seed_import",
            "source_name": "Global UAV Database 2026 seed package",
            "started_at": utc_now(),
            "status": "running",
        },
        conn,
    )

    seen = 0
    new = 0

    # --- source-record layer (the seed's own raw evidence) --------------
    if source_csv.is_file():
        rows = extract.parse_csv(source_csv.read_text(encoding="utf-8-sig"))
        for row in rows:
            seen += 1
            dataset = clean_text(row.get("source_dataset")) or "Global UAV Database 2026 seed package"
            discovery = RawDiscovery(
                raw_name=clean_text(row.get("platform_name")),
                source_dataset=dataset,
                source_url=clean_text(row.get("source_url")),
                external_ref=clean_text(row.get("source_record_id")),
                raw_country=clean_text(row.get("country_of_origin")),
                raw_manufacturer=clean_text(row.get("manufacturer"))
                or clean_text(row.get("design_organisation")),
                domain=clean_text(row.get("domain")),
                category=clean_text(row.get("category")),
                status=clean_text(row.get("status")),
                payload={
                    k: v
                    for k, v in row.items()
                    if v and k not in {"platform_name", "country_of_origin", "manufacturer"}
                }
                | {"credibility_tier": SEED_DATASET_TIERS.get(dataset, 3), "layer": "source_record"},
            )
            if not discovery.raw_name:
                continue
            if _store_raw(discovery, run_row, source_ids.get(dataset, seed_source_id), conn):
                new += 1

    # --- canonical layer (curated aggregate: aliases, specs, notes) -----
    if canonical_csv.is_file():
        rows = extract.parse_csv(canonical_csv.read_text(encoding="utf-8-sig"))
        for row in rows:
            seen += 1
            datasets = _split_seed_datasets(row.get("source_datasets", ""))
            tier = min(
                (SEED_DATASET_TIERS.get(d, 3) for d in datasets), default=3
            )
            discovery = RawDiscovery(
                raw_name=clean_text(row.get("platform_name")),
                source_dataset="Global UAV Database 2026 seed package",
                source_url=clean_text(row.get("source_urls")),
                external_ref=clean_text(row.get("record_id")),
                raw_country=clean_text(row.get("country_of_origin")),
                raw_manufacturer=clean_text(row.get("manufacturer")),
                domain=clean_text(row.get("domain")),
                category=clean_text(row.get("category")),
                status=clean_text(row.get("status")),
                payload={
                    k: v for k, v in row.items() if v
                }
                | {
                    "credibility_tier": tier,
                    "layer": "canonical_seed",
                    "seed_datasets": datasets,
                },
            )
            if not discovery.raw_name:
                continue
            if _store_raw(discovery, run_row, seed_source_id, conn):
                new += 1

    conn.execute(
        "UPDATE discovery_runs SET finished_at=?, candidates_seen=?, new_candidates=?, "
        "status='complete' WHERE id=?",
        (utc_now(), seen, new, run_row),
    )
    set_state("seed_imported_at", utc_now(), conn)
    result = {"seen": seen, "new": new, "directory": str(directory)}
    LOG.info("seed import: %s", result)
    LOG.event("seed_imported", **result)
    return result


def _store_raw(
    discovery: RawDiscovery,
    discovery_run_id: int | None,
    source_id: int | None,
    conn: sqlite3.Connection,
) -> bool:
    row = discovery.to_row(
        discovery_run_id=discovery_run_id, source_id=source_id, created_at=utc_now()
    )
    return insert_ignore("raw_discoveries", row, conn) is not None


# ---------------------------------------------------------------------------
# Live discovery passes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Strategy:
    name: str
    description: str
    runner: Callable[..., list[RawDiscovery]]
    kwargs: dict[str, Any]
    source_title: str
    credibility_tier: int
    source_url: str = ""


def build_strategies(
    *,
    country: str | None = None,
    manufacturer_filter: str | None = None,
    limit: int | None = None,
) -> list[Strategy]:
    """Assemble the discovery strategies described in the specification."""
    registry = load_registry()
    strategies: list[Strategy] = []

    for source in registry.get("sources", []):
        if not source.get("enabled", True):
            continue
        crawler_name = source.get("crawler")
        if crawler_name == "public_sources":
            runner = public_sources.crawl
        elif crawler_name == "regulatory":
            runner = regulatory.crawl_register
        else:
            continue  # image providers are driven by the image agents
        strategies.append(
            Strategy(
                name=source.get("strategy", source.get("id", "unknown")),
                description=source.get("title", ""),
                runner=runner,
                kwargs={"source": source, "limit": limit},
                source_title=source.get("title", source.get("id", "")),
                credibility_tier=int(source.get("credibility_tier", 3)),
                source_url=source.get("landing_page") or source.get("url", ""),
            )
        )

    for site in registry.get("manufacturer_sites", []):
        if manufacturer_filter and manufacturer_filter.lower() not in site.get("manufacturer", "").lower():
            continue
        strategies.append(
            Strategy(
                name="global_manufacturers",
                description=f"{site.get('manufacturer')} official product pages",
                runner=manufacturer.crawl_site,
                kwargs={"site": site, "limit": limit},
                source_title=f"{site.get('manufacturer')} official product pages",
                credibility_tier=int(site.get("credibility_tier", 1)),
                source_url=site.get("url", ""),
            )
        )

    for source in registry.get("government_sources", []):
        if country and country.lower() not in source.get("country", "").lower():
            continue
        strategies.append(
            Strategy(
                name="national_programs",
                description=source.get("title", ""),
                runner=government.crawl_source,
                kwargs={"source": source, "limit": limit},
                source_title=source.get("title", source.get("id", "")),
                credibility_tier=int(source.get("credibility_tier", 1)),
                source_url=source.get("url", ""),
            )
        )

    if manufacturer_filter:
        strategies = [
            s for s in strategies if manufacturer_filter.lower() in s.description.lower()
        ] or strategies
    return strategies


def run_pass(
    pass_number: int,
    *,
    country: str | None = None,
    manufacturer_filter: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Execute one discovery pass over every strategy.

    Failure of a single strategy is isolated: it is logged, recorded as an
    unresolved item with the precise blocker, and the pass continues.
    """
    conn = connect()
    client = get_client()
    strategies = build_strategies(
        country=country, manufacturer_filter=manufacturer_filter, limit=limit
    )
    totals: dict[str, Any] = {
        "pass": pass_number,
        "strategies": len(strategies),
        "seen": 0,
        "new": 0,
        "failed": 0,
        "blocked_hosts": [],
    }

    for strategy in strategies:
        source_id = get_or_create_source(
            title=strategy.source_title,
            url=strategy.source_url,
            source_type="crawled source",
            credibility_tier=strategy.credibility_tier,
            conn=conn,
        )
        run_row = insert(
            "discovery_runs",
            {
                "run_id": run_id(),
                "pass_number": pass_number,
                "strategy": strategy.name,
                "source_name": strategy.source_title,
                "started_at": utc_now(),
                "status": "running",
            },
            conn,
        )
        try:
            discoveries = strategy.runner(client=client, **strategy.kwargs)
        except FetchError as exc:
            totals["failed"] += 1
            host = _host_of(strategy.source_url)
            if host and host not in totals["blocked_hosts"]:
                totals["blocked_hosts"].append(host)
            conn.execute(
                "UPDATE discovery_runs SET finished_at=?, status='failed', error=? WHERE id=?",
                (utc_now(), str(exc)[:500], run_row),
            )
            note_url(strategy.source_url or strategy.source_title, status=f"error: {exc}"[:200], conn=conn)
            add_unresolved(
                item_type="source_unreachable",
                subject=strategy.source_title,
                detail=str(exc)[:500],
                severity="high" if strategy.credibility_tier <= 2 else "medium",
                suggested_action=(
                    "Re-run discovery from an environment whose egress policy permits this host."
                ),
                blocker=f"network: {host or 'unknown host'}",
                conn=conn,
            )
            LOG.warning("strategy %s failed: %s", strategy.source_title, exc)
            LOG.event(
                "strategy_failed",
                status="error",
                strategy=strategy.name,
                source=strategy.source_title,
                error=str(exc)[:300],
                host=host,
            )
            continue
        except Exception as exc:
            totals["failed"] += 1
            conn.execute(
                "UPDATE discovery_runs SET finished_at=?, status='failed', error=? WHERE id=?",
                (utc_now(), str(exc)[:500], run_row),
            )
            LOG.error("strategy %s raised: %s", strategy.source_title, exc)
            LOG.event(
                "strategy_error",
                status="error",
                strategy=strategy.name,
                source=strategy.source_title,
                error=str(exc)[:300],
            )
            continue

        new = 0
        for discovery in discoveries:
            if not discovery.raw_name:
                continue
            payload_tier = discovery.payload.setdefault(
                "credibility_tier", strategy.credibility_tier
            )
            _ = payload_tier
            if _store_raw(discovery, run_row, source_id, conn):
                new += 1
        note_url(strategy.source_url or strategy.source_title, status="ok", conn=conn)

        totals["seen"] += len(discoveries)
        totals["new"] += new
        conn.execute(
            "UPDATE discovery_runs SET finished_at=?, candidates_seen=?, new_candidates=?, "
            "status='complete' WHERE id=?",
            (utc_now(), len(discoveries), new, run_row),
        )
        LOG.info(
            "pass %d | %-46s seen=%-5d new=%d",
            pass_number,
            strategy.source_title[:46],
            len(discoveries),
            new,
        )

    set_state(f"discovery_pass_{pass_number}", totals, conn)
    LOG.event("discovery_pass_complete", **totals)
    return totals


def _host_of(url: str) -> str:
    import urllib.parse

    try:
        return urllib.parse.urlparse(url).netloc
    except ValueError:
        return ""


def run(
    *,
    passes: int | None = None,
    country: str | None = None,
    manufacturer_filter: str | None = None,
    limit: int | None = None,
    import_seed_first: bool = True,
) -> dict[str, Any]:
    """Run seed import (once) then discovery passes until they stop yielding."""
    settings = get_settings()
    conn = connect()
    summary: dict[str, Any] = {"seed": None, "passes": []}

    if import_seed_first:
        summary["seed"] = import_seed()

    max_passes = passes if passes is not None else settings.discovery_max_passes
    empty_streak = 0
    last_pass = query_one("SELECT COALESCE(MAX(pass_number),0) AS p FROM discovery_runs", conn=conn)
    start_pass = int(last_pass["p"] if last_pass else 0) + 1

    for offset in range(max_passes):
        pass_number = start_pass + offset
        result = run_pass(
            pass_number,
            country=country,
            manufacturer_filter=manufacturer_filter,
            limit=limit,
        )
        summary["passes"].append(result)
        if result["new"] == 0:
            empty_streak += 1
        else:
            empty_streak = 0
        if empty_streak >= settings.discovery_stop_after_empty_passes:
            LOG.info(
                "stopping discovery: %d consecutive passes with no new candidates",
                empty_streak,
            )
            break

    summary["empty_streak"] = empty_streak
    summary["converged"] = empty_streak >= settings.discovery_stop_after_empty_passes
    set_state("discovery_summary", summary, conn)
    LOG.event("discovery_complete", converged=summary["converged"], passes=len(summary["passes"]))
    return summary


def stats() -> dict[str, Any]:
    conn = connect()

    def count(sql: str) -> int:
        row = query_one(sql, conn=conn)
        return int(row["n"]) if row else 0

    return {
        "raw_discoveries": count("SELECT COUNT(*) AS n FROM raw_discoveries"),
        "unprocessed": count("SELECT COUNT(*) AS n FROM raw_discoveries WHERE processed=0"),
        "by_dataset": {
            r["source_dataset"]: r["n"]
            for r in query(
                "SELECT source_dataset, COUNT(*) AS n FROM raw_discoveries "
                "GROUP BY source_dataset ORDER BY n DESC",
                conn=conn,
            )
        },
        "passes": [
            dict(r)
            for r in query(
                "SELECT pass_number, strategy, source_name, candidates_seen, new_candidates, "
                "status FROM discovery_runs ORDER BY id",
                conn=conn,
            )
        ],
    }


def load_payload(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
