"""End-to-end tests: seed import, promotion, verification, exports, atlas, resume."""

from __future__ import annotations

import json

import pytest

from agents import (
    atlas_builder_agent,
    country_classifier_agent,
    deduplication_agent,
    discovery_agent,
    export_agent,
    metadata_agent,
    orchestrator,
    source_verification_agent,
)
from app import db


@pytest.fixture()
def imported(database, seed_dir):
    return discovery_agent.import_seed(seed_dir=seed_dir)


class TestSeedImport:
    def test_imports_both_layers(self, imported, database):
        assert imported["new"] > 0
        total = database.execute("SELECT COUNT(*) AS n FROM raw_discoveries").fetchone()["n"]
        assert total == imported["new"]

    def test_is_idempotent(self, imported, seed_dir, database):
        again = discovery_agent.import_seed(seed_dir=seed_dir)
        assert again["new"] == 0

    def test_registers_sources_with_tiers(self, imported, database):
        rows = {r["title"]: r["credibility_tier"] for r in database.execute("SELECT title, credibility_tier FROM sources")}
        assert "Global UAV Database 2026 seed package" in rows

    def test_missing_seed_is_not_fatal(self, database, tmp_path):
        result = discovery_agent.import_seed(seed_dir=tmp_path / "nothing")
        assert result["skipped"] is True

    def test_raw_records_keep_their_source(self, imported, database):
        row = database.execute(
            "SELECT source_dataset FROM raw_discoveries WHERE raw_name LIKE '%Reaper%' LIMIT 1"
        ).fetchone()
        assert row["source_dataset"]


class TestPromotion:
    def test_creates_canonical_platforms(self, imported, database):
        stats = metadata_agent.promote()
        assert stats["created"] >= 3
        names = {r["canonical_name"] for r in database.execute("SELECT canonical_name FROM platforms")}
        assert "MQ-9A Reaper" in names

    def test_marks_raw_rows_processed(self, imported, database):
        metadata_agent.promote()
        pending = database.execute(
            "SELECT COUNT(*) AS n FROM raw_discoveries WHERE processed=0"
        ).fetchone()["n"]
        assert pending == 0

    def test_links_platform_to_sources(self, imported, database):
        metadata_agent.promote()
        count = database.execute("SELECT COUNT(*) AS n FROM platform_sources").fetchone()["n"]
        assert count > 0

    def test_resolves_country_of_origin(self, imported, database):
        metadata_agent.promote()
        row = database.execute(
            "SELECT c.name FROM platforms p JOIN countries c ON c.id=p.country_id "
            "WHERE p.canonical_name='MQ-9A Reaper'"
        ).fetchone()
        assert row["name"] == "United States"

    def test_running_twice_does_not_duplicate(self, imported, database):
        metadata_agent.promote()
        before = database.execute("SELECT COUNT(*) AS n FROM platforms").fetchone()["n"]
        metadata_agent.promote()
        after = database.execute("SELECT COUNT(*) AS n FROM platforms").fetchone()["n"]
        assert before == after


class TestCombinedNameSplitting:
    def test_splits_genuine_variant_pairs(self):
        result = metadata_agent.split_combined_name("MQ-9B SkyGuardian/SeaGuardian")
        assert result.names == ["MQ-9B SkyGuardian", "MQ-9B SeaGuardian"]

    def test_splits_designation_pairs(self):
        result = metadata_agent.split_combined_name("Malloy T150/T400")
        assert result.names == ["Malloy T150", "Malloy T400"]

    def test_keeps_export_names_as_aliases(self):
        result = metadata_agent.split_combined_name("Heron TP / Eitan")
        assert result.names == ["Heron TP"]
        assert result.aliases == ["Eitan"]

    def test_multiword_alternate_is_an_alias(self):
        result = metadata_agent.split_combined_name("ASN-209 / Silver Eagle")
        assert result.names == ["ASN-209"]
        assert "Silver Eagle" in result.aliases

    def test_plain_name_is_untouched(self):
        result = metadata_agent.split_combined_name("Bayraktar TB2")
        assert result.names == ["Bayraktar TB2"]
        assert result.aliases == []


class TestCountryClassification:
    def test_joint_programme(self):
        decision = country_classifier_agent.classify(
            [
                country_classifier_agent.OriginEvidence("France", 1, "MoD FR"),
                country_classifier_agent.OriginEvidence("Germany", 1, "MoD DE"),
            ]
        )
        assert decision.country == "Multinational"
        assert set(decision.participants) == {"France", "Germany"}

    def test_registration_alone_is_not_origin(self):
        decision = country_classifier_agent.classify(
            [country_classifier_agent.OriginEvidence("Germany", 1, "EASA", registration_only=True)]
        )
        assert decision.country == "Unknown"
        assert decision.production_country == "Germany"

    def test_no_evidence_yields_unknown(self):
        decision = country_classifier_agent.classify([])
        assert decision.country == "Unknown"
        assert decision.confidence == "None"

    def test_strongest_tier_wins(self):
        decision = country_classifier_agent.classify(
            [
                country_classifier_agent.OriginEvidence("Israel", 1, "IAI official"),
                country_classifier_agent.OriginEvidence("India", 3, "open catalogue"),
            ]
        )
        assert decision.country == "Israel"
        assert decision.confidence == "High"

    def test_aggregator_evidence_is_discounted(self):
        decision = country_classifier_agent.classify(
            [
                country_classifier_agent.OriginEvidence("China", 3, "catalogue"),
                country_classifier_agent.OriginEvidence("China", 3, "seed package", is_aggregator=True),
            ]
        )
        # One independent tier-3 source only: not enough for High.
        assert decision.country == "China"
        assert decision.confidence == "Medium"

    def test_same_source_counted_once(self):
        decision = country_classifier_agent.classify(
            [
                country_classifier_agent.OriginEvidence("China", 3, "catalogue"),
                country_classifier_agent.OriginEvidence("China", 3, "catalogue"),
            ]
        )
        assert decision.confidence == "Medium"


class TestSourceVerification:
    def test_tier4_only_never_verifies(self):
        status, score, reason = source_verification_agent.evaluate_record(
            tiers=[4], distinct_sources=3, country="United States", has_manufacturer=True
        )
        assert status == "Needs Verification"
        assert "tier-4" in reason

    def test_no_source_is_flagged(self):
        status, score, reason = source_verification_agent.evaluate_record(
            tiers=[], distinct_sources=0, country="United States", has_manufacturer=True
        )
        assert status == "Needs Verification"
        assert score == 0.0

    def test_two_strong_independent_sources_verify(self):
        status, _, _ = source_verification_agent.evaluate_record(
            tiers=[1, 2], distinct_sources=2, country="Türkiye", has_manufacturer=True
        )
        assert status == "Verified"

    def test_single_tier3_source_needs_verification(self):
        status, _, _ = source_verification_agent.evaluate_record(
            tiers=[3], distinct_sources=1, country="China", has_manufacturer=True
        )
        assert status == "Needs Verification"

    def test_aggregators_do_not_corroborate(self, imported, database):
        metadata_agent.promote()
        source_verification_agent.run()
        row = database.execute(
            "SELECT verification_status FROM platforms WHERE canonical_name='Bayraktar TB2'"
        ).fetchone()
        # Backed by the curated seed only, republished by the aggregator.
        assert row["verification_status"] in ("Needs Verification", "Probable")


class TestExports:
    def test_writes_every_required_file(self, imported, _isolated_paths):
        metadata_agent.promote()
        deduplication_agent.run()
        source_verification_agent.run()
        result = export_agent.run()

        out = _isolated_paths.paths.output
        for name in (
            "uav_database.csv",
            "uav_source_records.csv",
            "photo_attribution.csv",
            "unresolved_records.csv",
            "coverage_statistics.json",
            "coverage_report.md",
            "uav_database.sqlite",
            "uav_database.xlsx",
        ):
            assert (out / name).is_file(), f"missing export: {name}"
        assert result["stats"]["canonical_platforms"] >= 3

    def test_coverage_statistics_are_consistent(self, imported):
        metadata_agent.promote()
        stats = export_agent.coverage_statistics()
        assert stats["canonical_platforms"] == sum(stats["by_domain"].values())
        assert stats["images"]["platforms_without_image"] == stats["canonical_platforms"]

    def test_sqlite_export_is_readable(self, imported, _isolated_paths):
        import sqlite3

        metadata_agent.promote()
        export_agent.run()
        path = _isolated_paths.paths.output / "uav_database.sqlite"
        conn = sqlite3.connect(str(path))
        count = conn.execute("SELECT COUNT(*) FROM platforms").fetchone()[0]
        conn.close()
        assert count >= 3

    def test_unresolved_doc_is_written(self, imported, _isolated_paths):
        metadata_agent.promote()
        export_agent.run()
        assert (_isolated_paths.paths.docs / "UNRESOLVED.md").is_file()


class TestAtlas:
    def test_html_contains_the_three_columns(self, imported, _isolated_paths):
        metadata_agent.promote()
        data = atlas_builder_agent.load_atlas_data()
        path = atlas_builder_agent.build_html(data)
        text = path.read_text(encoding="utf-8")
        assert "Photo" in text and "UAV Name" in text and "Country of Origin" in text
        assert "MQ-9A Reaper" in text

    def test_html_payload_is_valid_json(self, imported, _isolated_paths):
        metadata_agent.promote()
        text = atlas_builder_agent.build_html(atlas_builder_agent.load_atlas_data()).read_text()
        blob = text.split("const DATA = ", 1)[1].split(";\n", 1)[0]
        rows = json.loads(blob)
        assert rows and {"name", "country", "image"} <= set(rows[0])

    def test_pdf_is_generated_and_searchable(self, imported, _isolated_paths):
        pytest.importorskip("reportlab")
        metadata_agent.promote()
        data = atlas_builder_agent.load_atlas_data()
        path = atlas_builder_agent.build_pdf(data)
        assert path is not None and path.is_file()
        assert path.stat().st_size > 2000

        reader = pytest.importorskip("pypdf")
        document = reader.PdfReader(str(path))
        text = "".join((page.extract_text() or "") for page in document.pages)
        assert "Global UAV Visual Atlas 2026" in text
        assert "MQ-9A Reaper" in text
        assert "Country of Origin" in text

    def test_entries_are_sorted_by_country_then_manufacturer(self):
        entries = [
            atlas_builder_agent.Entry(1, "a", "Zeta", "Germany", "Zeta Corp", "Military", "", "", "Probable", "", "", "", "", "", "", "unverified", 0.0),
            atlas_builder_agent.Entry(2, "b", "Alpha", "France", "Alpha SA", "Military", "", "", "Probable", "", "", "", "", "", "", "unverified", 0.0),
            atlas_builder_agent.Entry(3, "c", "Beta", "France", "Beta SA", "Military", "", "", "Probable", "", "", "", "", "", "", "unverified", 0.0),
        ]
        ordered = atlas_builder_agent.sort_entries(entries)
        assert [e.name for e in ordered] == ["Alpha", "Beta", "Zeta"]

    def test_unknown_country_sorts_last(self):
        entries = [
            atlas_builder_agent.Entry(1, "a", "A", "Unknown", "", "Military", "", "", "Probable", "", "", "", "", "", "", "unverified", 0.0),
            atlas_builder_agent.Entry(2, "b", "B", "Australia", "", "Military", "", "", "Probable", "", "", "", "", "", "", "unverified", 0.0),
        ]
        assert atlas_builder_agent.sort_entries(entries)[-1].country == "Unknown"

    def test_placeholder_is_created(self, _isolated_paths):
        path = atlas_builder_agent.ensure_placeholder()
        assert path.is_file()

    def test_page_ranges_are_compressed(self):
        assert atlas_builder_agent._page_ranges([3, 4, 5, 9]) == "3–5, 9"
        assert atlas_builder_agent._page_ranges([]) == "—"


class TestOrchestratorResume:
    def test_completed_stage_is_skipped_on_resume(self, database, seed_dir, monkeypatch):
        calls = {"n": 0}

        def counting_promote():
            calls["n"] += 1
            return {"created": 0}

        monkeypatch.setattr(metadata_agent, "promote", counting_promote)
        orchestrator.run_pipeline(stages=("migrate", "promote"), skip_images=True)
        assert calls["n"] == 1
        orchestrator.run_pipeline(stages=("migrate", "promote"), resume=True, skip_images=True)
        assert calls["n"] == 1  # skipped second time

    def test_stage_failure_is_isolated_and_recorded(self, database, monkeypatch):
        def explode():
            raise RuntimeError("simulated stage failure")

        monkeypatch.setattr(metadata_agent, "promote", explode)
        results = orchestrator.run_pipeline(stages=("migrate", "promote", "export"), skip_images=True)
        assert "error" in results["promote"]
        assert "export" in results  # later stages still ran
        row = database.execute(
            "SELECT COUNT(*) AS n FROM unresolved_items WHERE item_type='pipeline_stage_failure'"
        ).fetchone()
        assert row["n"] == 1

    def test_stop_conditions_report_missing_outputs(self, database):
        result = orchestrator.check_stop_conditions()
        assert result["all_met"] is False
        assert result["detail"]["missing_outputs"]

    def test_status_reports_stage_flags(self, database):
        status = orchestrator.status()
        assert set(status["stages"]) == set(orchestrator.STAGES)


class TestDiscoveryFailureIsolation:
    def test_unreachable_source_does_not_stop_the_pass(self, database, monkeypatch):
        from crawlers.http import FetchError

        def failing_strategy(**kwargs):
            raise FetchError("host blocked by egress policy", status=403, retryable=False)

        def working_strategy(**kwargs):
            from app.models import RawDiscovery

            return [RawDiscovery(raw_name="Test UAV 1", source_dataset="working source")]

        strategies = [
            discovery_agent.Strategy(
                name="s1", description="failing", runner=failing_strategy, kwargs={},
                source_title="Failing source", credibility_tier=1,
                source_url="https://blocked.invalid/x",
            ),
            discovery_agent.Strategy(
                name="s2", description="working", runner=working_strategy, kwargs={},
                source_title="Working source", credibility_tier=3,
                source_url="https://ok.invalid/y",
            ),
        ]
        monkeypatch.setattr(discovery_agent, "build_strategies", lambda **kw: strategies)

        result = discovery_agent.run_pass(1)
        assert result["failed"] == 1
        assert result["new"] == 1
        assert "blocked.invalid" in result["blocked_hosts"]

        unresolved = database.execute(
            "SELECT item_type, blocker FROM unresolved_items WHERE item_type='source_unreachable'"
        ).fetchone()
        assert unresolved is not None
        assert "blocked.invalid" in unresolved["blocker"]

    def test_pass_records_counts(self, database, monkeypatch):
        monkeypatch.setattr(discovery_agent, "build_strategies", lambda **kw: [])
        result = discovery_agent.run_pass(1)
        assert result["new"] == 0
        assert db.get_state("discovery_pass_1") is not None
