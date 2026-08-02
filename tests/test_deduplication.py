"""Deduplication tests.

The asymmetry matters: merging two spellings of one aircraft is desirable,
merging two officially distinct variants is a defect. Most of these tests pin
down the "must not merge" side.
"""

from __future__ import annotations

import pytest

from agents import deduplication_agent as dedup
from app.utils import extract_model_codes, tokenize


def make(name: str, *, manufacturer: str = "", country: str = "", confidence: float = 0.5, pid: int = 1):
    return dedup.Candidate(
        id=pid,
        name=name,
        normalized=__import__("app.utils", fromlist=["normalize_name"]).normalize_name(name),
        manufacturer=manufacturer,
        country=country,
        domain="Military",
        codes=tuple(extract_model_codes(name)),
        tokens=tuple(tokenize(name)),
        confidence=confidence,
    )


class TestMustNotMerge:
    def test_distinct_model_codes(self):
        verdict = dedup.compare(make("MQ-9A Reaper", pid=1), make("MQ-9B SkyGuardian", pid=2))
        assert verdict.decision == "distinct"

    def test_sea_and_sky_guardian_stay_separate(self):
        verdict = dedup.compare(make("MQ-9B SkyGuardian", pid=1), make("MQ-9B SeaGuardian", pid=2))
        assert verdict.decision == "distinct"

    def test_variant_suffix_letters(self):
        verdict = dedup.compare(make("Anka-S", pid=1), make("Anka-A", pid=2))
        assert verdict.decision == "distinct"

    def test_different_manufacturers_never_merge(self):
        verdict = dedup.compare(
            make("Falcon 100", manufacturer="Alpha Aerospace", pid=1),
            make("Falcon 100", manufacturer="Beta Dynamics", pid=2),
        )
        assert verdict.decision == "distinct"

    def test_sensor_variants_stay_separate(self):
        verdict = dedup.compare(
            make("Delair UX11 Camera AG", pid=1), make("Delair UX11 Camera IR", pid=2)
        )
        assert verdict.decision == "distinct"

    def test_sub_variant_extension_is_not_auto_merged(self):
        verdict = dedup.compare(make("DJI Mavic 3", pid=1), make("DJI Mavic 3 Cine", pid=2))
        assert verdict.decision != "merge"

    def test_country_conflict_goes_to_review(self):
        verdict = dedup.compare(
            make("Skylark", country="Israel", pid=1),
            make("Skylark", country="India", pid=2),
        )
        assert verdict.decision == "review"


class TestShouldMerge:
    def test_identical_normalised_names(self):
        verdict = dedup.compare(make("MQ-9A Reaper", pid=1), make("MQ-9A  Reaper", pid=2))
        assert verdict.decision == "merge"
        assert verdict.score == 1.0

    def test_manufacturer_prefix_is_cosmetic(self, monkeypatch):
        monkeypatch.setattr(dedup, "_MANUFACTURER_HEADS", {"dji"})
        verdict = dedup.compare(
            make("Mavic 3 Pro", pid=1), make("DJI Mavic 3 Pro", manufacturer="DJI", pid=2)
        )
        assert verdict.decision == "merge"

    def test_prefix_merge_works_without_manufacturer_field(self, monkeypatch):
        monkeypatch.setattr(dedup, "_MANUFACTURER_HEADS", {"baykar"})
        verdict = dedup.compare(make("TB2", pid=1), make("Baykar TB2", pid=2))
        assert verdict.decision == "merge"


class TestDesignationExtension:
    def test_name_with_designation_vs_without_is_reviewed(self, monkeypatch):
        monkeypatch.setattr(dedup, "_MANUFACTURER_HEADS", set())
        verdict = dedup.compare(make("Global Hawk", pid=1), make("RQ-4 Global Hawk", pid=2))
        assert verdict.decision == "review"


class TestMergeExecution:
    def test_merge_moves_relationships_and_marks_survivor(self, database):
        from app.db import add_alias, get_or_create_source, insert, link_platform_source
        from app.logging import utc_now

        now = utc_now()
        keep = insert(
            "platforms",
            {
                "public_id": "UAV-KEEP",
                "canonical_name": "Bayraktar TB2",
                "normalized_name": "bayraktar tb2",
                "domain": "Military",
                "verification_status": "Probable",
                "confidence_score": 0.6,
                "created_at": now,
                "updated_at": now,
            },
            database,
        )
        drop = insert(
            "platforms",
            {
                "public_id": "UAV-DROP",
                "canonical_name": "TB2",
                "normalized_name": "tb2",
                "domain": "Military",
                "verification_status": "Probable",
                "confidence_score": 0.4,
                "created_at": now,
                "updated_at": now,
            },
            database,
        )
        source_id = get_or_create_source(title="Test source", url="https://example.invalid", conn=database)
        link_platform_source(drop, source_id, conn=database)
        add_alias(drop, "Bayraktar Tactical", conn=database)

        dedup.merge_platforms(keep, drop, score=0.97, reason="test", conn=database)

        survivor = database.execute("SELECT is_merged_into FROM platforms WHERE id=?", (keep,)).fetchone()
        merged = database.execute("SELECT is_merged_into FROM platforms WHERE id=?", (drop,)).fetchone()
        assert survivor["is_merged_into"] is None
        assert merged["is_merged_into"] == keep

        aliases = {
            r["alias"]
            for r in database.execute("SELECT alias FROM platform_aliases WHERE platform_id=?", (keep,))
        }
        assert "TB2" in aliases and "Bayraktar Tactical" in aliases

        sources = database.execute(
            "SELECT COUNT(*) AS n FROM platform_sources WHERE platform_id=?", (keep,)
        ).fetchone()["n"]
        assert sources == 1

        decision = database.execute("SELECT decision, score FROM merge_decisions").fetchone()
        assert decision["decision"] == "merged"
        assert decision["score"] == pytest.approx(0.97)

    def test_dry_run_makes_no_changes(self, database):
        from app.db import insert
        from app.logging import utc_now

        now = utc_now()
        for index, name in enumerate(["Mavic 3", "Mavic 3"], start=1):
            insert(
                "platforms",
                {
                    "public_id": f"UAV-{index}",
                    "canonical_name": f"{name} {'x' * index}",
                    "normalized_name": f"mavic 3 {'x' * index}",
                    "domain": "Civilian / Commercial",
                    "verification_status": "Probable",
                    "confidence_score": 0.5,
                    "created_at": now,
                    "updated_at": now,
                },
                database,
            )
        dedup.run(dry_run=True)
        merged = database.execute(
            "SELECT COUNT(*) AS n FROM platforms WHERE is_merged_into IS NOT NULL"
        ).fetchone()["n"]
        assert merged == 0
