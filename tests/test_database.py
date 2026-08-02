"""Migration, schema-integrity and resume-state tests."""

from __future__ import annotations

import sqlite3

import pytest

from app import db
from app.schemas import MIGRATIONS, REQUIRED_TABLES


class TestMigrations:
    def test_applies_all_migrations(self, _isolated_paths):
        conn = db.connect(fresh=True)
        applied = db.migrate(conn)
        assert applied == [m.version for m in MIGRATIONS]

    def test_is_idempotent(self, database):
        assert db.migrate(database) == []

    def test_creates_every_required_table(self, database):
        present = {
            r["name"] for r in database.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert set(REQUIRED_TABLES) <= present

    def test_verify_schema_detects_damage(self, database):
        database.execute("DROP TABLE images")
        with pytest.raises(RuntimeError, match="schema incomplete"):
            db.verify_schema(database)

    def test_foreign_keys_are_enforced(self, database):
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                "INSERT INTO platform_sources(platform_id, source_id, relation, created_at) "
                "VALUES (99999, 88888, 'supports', '2026-01-01')"
            )

    def test_atlas_view_exists(self, database):
        rows = list(database.execute("SELECT * FROM v_atlas_entries"))
        assert rows == []


class TestUpserts:
    def test_country_is_created_once(self, database):
        first = db.get_or_create_country("United States", conn=database)
        second = db.get_or_create_country("United States", conn=database)
        assert first == second

    def test_manufacturer_inherits_country_when_missing(self, database):
        country = db.get_or_create_country("Türkiye", conn=database)
        mid = db.get_or_create_manufacturer("Baykar", conn=database)
        db.get_or_create_manufacturer("Baykar", country_id=country, conn=database)
        row = database.execute("SELECT country_id FROM manufacturers WHERE id=?", (mid,)).fetchone()
        assert row["country_id"] == country

    def test_blank_manufacturer_returns_none(self, database):
        assert db.get_or_create_manufacturer("   ", conn=database) is None

    def test_alias_uniqueness(self, database):
        pid = _platform(database, "MQ-9A Reaper")
        db.add_alias(pid, "Predator B", conn=database)
        db.add_alias(pid, "predator  b", conn=database)
        count = database.execute(
            "SELECT COUNT(*) AS n FROM platform_aliases WHERE platform_id=?", (pid,)
        ).fetchone()["n"]
        assert count == 1


class TestUpdateHistory:
    def test_changes_are_recorded(self, database):
        pid = _platform(database, "Test UAV")
        changed = db.update_fields(
            "platforms", pid, {"category": "MALE"}, reason="unit test", agent="test", conn=database
        )
        assert changed >= 1
        row = database.execute(
            "SELECT field, old_value, new_value, reason FROM update_history WHERE field='category'"
        ).fetchone()
        assert row["new_value"] == "MALE"
        assert row["reason"] == "unit test"

    def test_no_op_update_writes_no_history(self, database):
        pid = _platform(database, "Test UAV")
        db.update_fields("platforms", pid, {"canonical_name": "Test UAV"}, conn=database)
        assert database.execute("SELECT COUNT(*) AS n FROM update_history").fetchone()["n"] == 0


class TestResumeState:
    def test_state_round_trip(self, database):
        db.set_state("k", {"a": 1}, database)
        assert db.get_state("k", conn=database) == {"a": 1}

    def test_mark_done_and_is_done(self, database):
        assert db.is_done("discover", database) is False
        db.mark_done("discover", {"new": 3}, database)
        assert db.is_done("discover", database) is True

    def test_unknown_state_returns_default(self, database):
        assert db.get_state("missing", "fallback", database) == "fallback"


class TestUnresolvedQueue:
    def test_deduplicates_by_fingerprint(self, database):
        first = db.add_unresolved(item_type="image_missing", subject="MQ-9A", conn=database)
        second = db.add_unresolved(
            item_type="image_missing", subject="MQ-9A", detail="updated", conn=database
        )
        assert first == second
        row = database.execute("SELECT detail FROM unresolved_items WHERE id=?", (first,)).fetchone()
        assert row["detail"] == "updated"

    def test_url_ledger_counts_fetches(self, database):
        db.note_url("https://example.invalid/a", conn=database)
        db.note_url("https://example.invalid/a", conn=database)
        row = database.execute("SELECT fetch_count FROM url_ledger").fetchone()
        assert row["fetch_count"] == 2
        assert db.url_seen("https://example.invalid/a", database) is True


def _platform(conn, name: str) -> int:
    from app.logging import utc_now
    from app.utils import normalize_name

    now = utc_now()
    return db.insert(
        "platforms",
        {
            "public_id": f"UAV-{abs(hash(name)) % 10**8}",
            "canonical_name": name,
            "normalized_name": normalize_name(name),
            "domain": "Military",
            "verification_status": "Needs Verification",
            "confidence_score": 0.0,
            "created_at": now,
            "updated_at": now,
        },
        conn,
    )
