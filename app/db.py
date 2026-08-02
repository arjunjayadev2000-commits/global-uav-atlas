"""SQLite access layer: connection management, migrations and upsert helpers.

Every write goes through this module so that provenance (``update_history``) and
resume state (``pipeline_state``) stay consistent.  The connection is configured
with WAL and enforced foreign keys; all helpers are safe to call repeatedly which
is what makes the whole pipeline resumable.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.logging import audit, get_logger, run_id, utc_now
from app.schemas import MIGRATIONS, REQUIRED_TABLES
from app.utils import normalize_name, stable_id

LOG = get_logger("db")
_LOCAL = threading.local()


# ---------------------------------------------------------------------------
# Connection & migrations
# ---------------------------------------------------------------------------


def connect(path: Path | str | None = None, *, fresh: bool = False) -> sqlite3.Connection:
    """Open (or reuse) a configured connection."""
    settings = get_settings()
    db_path = Path(path) if path is not None else settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    cached: sqlite3.Connection | None = getattr(_LOCAL, "conn", None)
    cached_path: str | None = getattr(_LOCAL, "path", None)
    if cached is not None and cached_path == str(db_path) and not fresh:
        return cached

    conn = sqlite3.connect(str(db_path), timeout=60.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=60000")
    _LOCAL.conn = conn
    _LOCAL.path = str(db_path)
    return conn


def close() -> None:
    conn: sqlite3.Connection | None = getattr(_LOCAL, "conn", None)
    if conn is not None:
        conn.close()
    _LOCAL.conn = None
    _LOCAL.path = None


@contextmanager
def transaction(conn: sqlite3.Connection | None = None) -> Iterator[sqlite3.Connection]:
    """Explicit transaction wrapper (the connection runs in autocommit mode)."""
    con = conn or connect()
    con.execute("BEGIN")
    try:
        yield con
    except Exception:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def migrate(conn: sqlite3.Connection | None = None) -> list[int]:
    """Apply any outstanding migrations; returns the versions applied."""
    con = conn or connect()
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            applied_at  TEXT NOT NULL
        )
        """
    )
    applied = {row["version"] for row in con.execute("SELECT version FROM schema_migrations")}
    performed: list[int] = []
    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        LOG.info("applying migration %03d %s", migration.version, migration.name)
        con.executescript(migration.sql)
        con.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
            (migration.version, migration.name, utc_now()),
        )
        performed.append(migration.version)
    if performed:
        audit(
            "migrations_applied",
            agent="db",
            versions=performed,
            database=str(getattr(_LOCAL, "path", "")),
        )
    verify_schema(con)
    return performed


def verify_schema(conn: sqlite3.Connection | None = None) -> None:
    con = conn or connect()
    present = {
        row["name"]
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = [t for t in REQUIRED_TABLES if t not in present]
    if missing:
        raise RuntimeError(f"schema incomplete, missing tables: {missing}")


def table_counts(conn: sqlite3.Connection | None = None) -> dict[str, int]:
    con = conn or connect()
    counts: dict[str, int] = {}
    for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ):
        name = row["name"]
        if name.startswith("sqlite_"):
            continue
        counts[name] = con.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"]
    return counts


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def query(sql: str, params: Sequence[Any] = (), conn: sqlite3.Connection | None = None) -> list[sqlite3.Row]:
    con = conn or connect()
    return list(con.execute(sql, tuple(params)))


def query_one(
    sql: str, params: Sequence[Any] = (), conn: sqlite3.Connection | None = None
) -> sqlite3.Row | None:
    con = conn or connect()
    return con.execute(sql, tuple(params)).fetchone()


def scalar(sql: str, params: Sequence[Any] = (), conn: sqlite3.Connection | None = None) -> Any:
    row = query_one(sql, params, conn)
    return None if row is None else row[0]


def execute(sql: str, params: Sequence[Any] = (), conn: sqlite3.Connection | None = None) -> sqlite3.Cursor:
    con = conn or connect()
    return con.execute(sql, tuple(params))


def insert(table: str, values: Mapping[str, Any], conn: sqlite3.Connection | None = None) -> int:
    con = conn or connect()
    cols = list(values.keys())
    placeholders = ",".join("?" for _ in cols)
    sql = f'INSERT INTO "{table}" ({",".join(cols)}) VALUES ({placeholders})'
    cur = con.execute(sql, tuple(values[c] for c in cols))
    return int(cur.lastrowid or 0)


def insert_ignore(table: str, values: Mapping[str, Any], conn: sqlite3.Connection | None = None) -> int | None:
    con = conn or connect()
    cols = list(values.keys())
    placeholders = ",".join("?" for _ in cols)
    sql = f'INSERT OR IGNORE INTO "{table}" ({",".join(cols)}) VALUES ({placeholders})'
    cur = con.execute(sql, tuple(values[c] for c in cols))
    return int(cur.lastrowid) if cur.rowcount else None


def update_fields(
    table: str,
    entity_id: int,
    values: Mapping[str, Any],
    *,
    reason: str = "",
    agent: str = "system",
    track_history: bool = True,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Update a row, recording every changed field in ``update_history``."""
    con = conn or connect()
    if not values:
        return 0
    current = con.execute(f'SELECT * FROM "{table}" WHERE id=?', (entity_id,)).fetchone()
    if current is None:
        return 0
    changed = {k: v for k, v in values.items() if current[k] != v}
    if not changed:
        return 0
    if "updated_at" in current.keys():
        changed.setdefault("updated_at", utc_now())
    assignments = ",".join(f"{k}=?" for k in changed)
    con.execute(
        f'UPDATE "{table}" SET {assignments} WHERE id=?',
        (*changed.values(), entity_id),
    )
    if track_history:
        now = utc_now()
        for field, new_value in changed.items():
            if field == "updated_at":
                continue
            con.execute(
                """
                INSERT INTO update_history
                    (entity_type, entity_id, field, old_value, new_value, reason,
                     agent, run_id, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    table,
                    entity_id,
                    field,
                    None if current[field] is None else str(current[field]),
                    None if new_value is None else str(new_value),
                    reason,
                    agent,
                    run_id(),
                    now,
                ),
            )
    return len(changed)


# ---------------------------------------------------------------------------
# Resume state
# ---------------------------------------------------------------------------


def set_state(key: str, value: Any, conn: sqlite3.Connection | None = None) -> None:
    con = conn or connect()
    payload = value if isinstance(value, str) else json.dumps(value, default=str)
    con.execute(
        """
        INSERT INTO pipeline_state(key, value, updated_at) VALUES (?,?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, payload, utc_now()),
    )


def get_state(key: str, default: Any = None, conn: sqlite3.Connection | None = None) -> Any:
    row = query_one("SELECT value FROM pipeline_state WHERE key=?", (key,), conn)
    if row is None:
        return default
    raw = row["value"]
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def mark_done(step: str, detail: Any = None, conn: sqlite3.Connection | None = None) -> None:
    set_state(f"step:{step}", {"status": "done", "at": utc_now(), "detail": detail}, conn)


def is_done(step: str, conn: sqlite3.Connection | None = None) -> bool:
    state = get_state(f"step:{step}", None, conn)
    return isinstance(state, dict) and state.get("status") == "done"


# ---------------------------------------------------------------------------
# Domain-specific upserts
# ---------------------------------------------------------------------------


def get_or_create_country(
    name: str,
    *,
    iso3: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    from app.utils import UNKNOWN_COUNTRY, country_iso3, MULTINATIONAL

    con = conn or connect()
    clean = name or UNKNOWN_COUNTRY
    normalized = normalize_name(clean) or clean.lower()
    row = con.execute(
        "SELECT id FROM countries WHERE normalized_name=?", (normalized,)
    ).fetchone()
    if row:
        return int(row["id"])
    return insert(
        "countries",
        {
            "name": clean,
            "normalized_name": normalized,
            "iso3": iso3 if iso3 is not None else country_iso3(clean),
            "is_multinational": 1 if clean == MULTINATIONAL else 0,
            "is_unknown": 1 if clean == UNKNOWN_COUNTRY else 0,
            "created_at": utc_now(),
        },
        con,
    )


def get_or_create_manufacturer(
    name: str,
    *,
    country_id: int | None = None,
    organisation_type: str | None = None,
    website: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> int | None:
    con = conn or connect()
    clean = (name or "").strip()
    if not clean:
        return None
    normalized = normalize_name(clean) or clean.lower()
    row = con.execute(
        "SELECT id, country_id FROM manufacturers WHERE normalized_name=?", (normalized,)
    ).fetchone()
    now = utc_now()
    if row:
        mid = int(row["id"])
        if row["country_id"] is None and country_id is not None:
            update_fields(
                "manufacturers",
                mid,
                {"country_id": country_id},
                reason="country inferred from platform record",
                agent="db",
                conn=con,
            )
        return mid
    return insert(
        "manufacturers",
        {
            "name": clean,
            "normalized_name": normalized,
            "country_id": country_id,
            "organisation_type": organisation_type,
            "website": website,
            "created_at": now,
            "updated_at": now,
        },
        con,
    )


def get_or_create_source(
    *,
    title: str,
    url: str | None = None,
    publisher: str | None = None,
    source_type: str | None = None,
    credibility_tier: int = 3,
    notes: str | None = None,
    retrieved_at: str | None = None,
    is_aggregator: bool = False,
    conn: sqlite3.Connection | None = None,
) -> int:
    con = conn or connect()
    url_value = url or ""
    row = con.execute(
        "SELECT id FROM sources WHERE title=? AND url=?", (title, url_value)
    ).fetchone()
    if row:
        return int(row["id"])
    return insert(
        "sources",
        {
            "title": title,
            "publisher": publisher,
            "url": url_value,
            "source_type": source_type,
            "retrieved_at": retrieved_at or utc_now(),
            "credibility_tier": credibility_tier,
            "notes": notes,
            "is_aggregator": int(is_aggregator),
            "created_at": utc_now(),
        },
        con,
    )


def link_platform_source(
    platform_id: int,
    source_id: int,
    *,
    relation: str = "supports",
    excerpt: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    insert_ignore(
        "platform_sources",
        {
            "platform_id": platform_id,
            "source_id": source_id,
            "relation": relation,
            "excerpt": excerpt,
            "created_at": utc_now(),
        },
        conn,
    )


def add_alias(
    platform_id: int,
    alias: str,
    *,
    alias_type: str = "alias",
    source_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    clean = (alias or "").strip()
    if not clean:
        return
    normalized = normalize_name(clean)
    if not normalized:
        return
    insert_ignore(
        "platform_aliases",
        {
            "platform_id": platform_id,
            "alias": clean,
            "normalized_alias": normalized,
            "alias_type": alias_type,
            "source_id": source_id,
            "created_at": utc_now(),
        },
        conn,
    )


def add_unresolved(
    *,
    item_type: str,
    subject: str,
    detail: str = "",
    severity: str = "medium",
    entity_type: str | None = None,
    entity_id: int | None = None,
    suggested_action: str = "",
    blocker: str = "",
    conn: sqlite3.Connection | None = None,
) -> int | None:
    """Record an unresolved item; deduplicated by a stable fingerprint."""
    con = conn or connect()
    fingerprint = stable_id(item_type, subject, entity_type or "", str(entity_id or ""))
    now = utc_now()
    existing = con.execute(
        "SELECT id FROM unresolved_items WHERE fingerprint=?", (fingerprint,)
    ).fetchone()
    if existing:
        con.execute(
            "UPDATE unresolved_items SET detail=?, severity=?, suggested_action=?, "
            "blocker=?, updated_at=? WHERE id=?",
            (detail, severity, suggested_action, blocker, now, existing["id"]),
        )
        return int(existing["id"])
    return insert(
        "unresolved_items",
        {
            "item_type": item_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "subject": subject,
            "detail": detail,
            "severity": severity,
            "suggested_action": suggested_action,
            "blocker": blocker,
            "status": "open",
            "fingerprint": fingerprint,
            "run_id": run_id(),
            "created_at": now,
            "updated_at": now,
        },
        con,
    )


def resolve_unresolved(fingerprint: str, conn: sqlite3.Connection | None = None) -> None:
    con = conn or connect()
    con.execute(
        "UPDATE unresolved_items SET status='resolved', updated_at=? WHERE fingerprint=?",
        (utc_now(), fingerprint),
    )


def record_verification(
    *,
    entity_type: str,
    entity_id: int,
    agent: str,
    verdict: str,
    confidence: float | None = None,
    explanation: str = "",
    evidence: Any = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    return insert(
        "verification_events",
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "agent": agent,
            "verdict": verdict,
            "confidence": confidence,
            "explanation": explanation,
            "evidence_json": json.dumps(evidence, default=str) if evidence is not None else None,
            "created_at": utc_now(),
        },
        conn,
    )


def note_url(
    url: str,
    *,
    status: str = "ok",
    content_sha256: str | None = None,
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    con = conn or connect()
    now = utc_now()
    con.execute(
        """
        INSERT INTO url_ledger(url, first_fetched_at, last_fetched_at, fetch_count,
                               last_status, content_sha256, notes)
        VALUES (?,?,?,1,?,?,?)
        ON CONFLICT(url) DO UPDATE SET
            last_fetched_at=excluded.last_fetched_at,
            fetch_count=url_ledger.fetch_count + 1,
            last_status=excluded.last_status,
            content_sha256=COALESCE(excluded.content_sha256, url_ledger.content_sha256),
            notes=COALESCE(excluded.notes, url_ledger.notes)
        """,
        (url, now, now, status, content_sha256, notes),
    )


def url_seen(url: str, conn: sqlite3.Connection | None = None) -> bool:
    return query_one("SELECT 1 FROM url_ledger WHERE url=?", (url,), conn) is not None
