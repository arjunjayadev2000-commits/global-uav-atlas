"""Image licence screening, validation, duplicate detection and derivatives."""

from __future__ import annotations

import pytest

from agents import image_discovery_agent, image_license_agent, image_validation_agent
from app.models import ImageCandidate


def candidate(**kwargs) -> ImageCandidate:
    defaults = dict(
        platform_id=1,
        platform_name="MQ-9A Reaper",
        source_url="https://upload.invalid/MQ-9.jpg",
        source_page_url="https://commons.invalid/File:MQ-9.jpg",
        title="File:MQ-9 Reaper in flight.jpg",
        photographer="Jane Photographer",
        license_name="CC BY-SA 4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        width=1600,
        height=1000,
        mime_type="image/jpeg",
        provider="Wikimedia Commons",
    )
    defaults.update(kwargs)
    return ImageCandidate(**defaults)


class TestLicenceScreening:
    @pytest.mark.parametrize(
        "licence",
        ["CC BY 4.0", "CC BY-SA 3.0", "CC0", "Public domain", "PD-USGov", "Attribution"],
    )
    def test_accepts_redistributable_licences(self, licence):
        verdict = image_license_agent.evaluate(candidate(license_name=licence))
        assert verdict.acceptable is True
        assert verdict.commercial_use is True
        assert verdict.modification_allowed is True

    @pytest.mark.parametrize(
        "licence",
        ["CC BY-NC 4.0", "CC BY-NC-SA 4.0", "Noncommercial use only"],
    )
    def test_rejects_noncommercial(self, licence):
        verdict = image_license_agent.evaluate(candidate(license_name=licence))
        assert verdict.acceptable is False
        assert "NonCommercial" in verdict.reason

    def test_rejects_no_derivatives(self):
        verdict = image_license_agent.evaluate(candidate(license_name="CC BY-ND 4.0"))
        assert verdict.acceptable is False
        assert "NoDerivatives" in verdict.reason

    def test_rejects_all_rights_reserved(self):
        verdict = image_license_agent.evaluate(candidate(license_name="All rights reserved"))
        assert verdict.acceptable is False

    def test_rejects_fair_use(self):
        verdict = image_license_agent.evaluate(candidate(license_name="Fair use"))
        assert verdict.acceptable is False

    def test_rejects_missing_licence(self):
        verdict = image_license_agent.evaluate(candidate(license_name=""))
        assert verdict.acceptable is False
        assert "no licence metadata" in verdict.reason

    def test_rejects_missing_provenance(self):
        verdict = image_license_agent.evaluate(candidate(source_page_url="", source_url=""))
        assert verdict.acceptable is False
        assert "provenance" in verdict.reason

    def test_us_government_host_is_public_domain(self):
        verdict = image_license_agent.evaluate(
            candidate(
                license_name="",
                source_page_url="https://www.dvidshub.net/image/123/mq-9",
                provider="DVIDS",
            )
        )
        assert verdict.acceptable is True
        assert verdict.is_public_domain is True

    def test_attribution_includes_author_licence_and_page(self):
        verdict = image_license_agent.evaluate(candidate())
        assert "Jane Photographer" in verdict.attribution_text
        assert "CC BY-SA 4.0" in verdict.attribution_text
        assert "commons.invalid" in verdict.attribution_text

    def test_noncommercial_can_be_allowed_by_configuration(self, monkeypatch, _isolated_paths):
        from app import config

        relaxed = config.Settings(paths=_isolated_paths.paths, allow_noncommercial_licenses=True)
        monkeypatch.setattr(image_license_agent, "get_settings", lambda: relaxed)
        verdict = image_license_agent.evaluate(candidate(license_name="CC BY-NC 4.0"))
        assert verdict.acceptable is True

    def test_verdict_to_row_maps_columns(self):
        row = image_license_agent.verdict_to_row(image_license_agent.evaluate(candidate()))
        assert row["license_verified"] == 1
        assert row["commercial_use"] == 1
        assert row["license_name"] == "CC BY-SA 4.0"


class TestValidation:
    def test_accepts_a_good_image(self, png_bytes):
        verdict = image_validation_agent.validate_bytes(png_bytes(1200, 800))
        assert verdict.ok is True
        assert verdict.width == 1200
        assert verdict.mime_type == "image/png"
        assert len(verdict.sha256) == 64
        assert verdict.perceptual_hash

    def test_rejects_corrupt_bytes(self):
        verdict = image_validation_agent.validate_bytes(b"this is not an image")
        assert verdict.ok is False
        assert "does not decode" in verdict.reason

    def test_rejects_truncated_file(self, png_bytes):
        data = png_bytes(1000, 700)
        verdict = image_validation_agent.validate_bytes(data[: len(data) // 2])
        assert verdict.ok is False

    def test_rejects_empty_body(self):
        assert image_validation_agent.validate_bytes(b"").ok is False

    def test_rejects_below_minimum_width(self, png_bytes):
        verdict = image_validation_agent.validate_bytes(png_bytes(320, 240))
        assert verdict.ok is False
        assert "below absolute minimum" in verdict.reason

    def test_rejects_implausible_aspect_ratio(self, png_bytes):
        verdict = image_validation_agent.validate_bytes(png_bytes(2000, 200))
        assert verdict.ok is False
        assert "aspect ratio" in verdict.reason

    def test_hashes_are_stable_and_distinct(self, png_bytes):
        first = image_validation_agent.validate_bytes(png_bytes(900, 600, (10, 20, 30)))
        again = image_validation_agent.validate_bytes(png_bytes(900, 600, (10, 20, 30)))
        other = image_validation_agent.validate_bytes(png_bytes(900, 600, (200, 40, 40)))
        assert first.sha256 == again.sha256
        assert first.sha256 != other.sha256

    def test_hamming_distance(self):
        assert image_validation_agent.hamming("ffff", "ffff") == 0
        assert image_validation_agent.hamming("0000", "000f") == 4
        assert image_validation_agent.hamming("", "abcd") == 64


class TestDuplicateDetection:
    def _store(self, database, platform_name, sha, phash):
        from app.db import insert
        from app.logging import utc_now
        from app.utils import normalize_name

        now = utc_now()
        pid = insert(
            "platforms",
            {
                "public_id": f"UAV-{platform_name[:6]}",
                "canonical_name": platform_name,
                "normalized_name": normalize_name(platform_name),
                "domain": "Military",
                "verification_status": "Probable",
                "confidence_score": 0.5,
                "created_at": now,
                "updated_at": now,
            },
            database,
        )
        insert(
            "images",
            {
                "platform_id": pid,
                "local_path": f"/tmp/{sha}.jpg",
                "sha256": sha,
                "perceptual_hash": phash,
                "validation_status": "ok",
                "selected_for_atlas": 1,
                "created_at": now,
            },
            database,
        )
        return pid

    def test_detects_exact_duplicate_across_platforms(self, database):
        self._store(database, "MQ-9A Reaper", "a" * 64, "ffffffffffffffff")
        found = image_validation_agent.find_exact_duplicate("a" * 64, exclude_platform_id=999)
        assert found is not None

    def test_same_platform_is_not_a_duplicate(self, database):
        pid = self._store(database, "MQ-9A Reaper", "a" * 64, "ffffffffffffffff")
        assert image_validation_agent.find_exact_duplicate("a" * 64, exclude_platform_id=pid) is None

    def test_detects_perceptual_near_duplicate(self, database):
        self._store(database, "MQ-9A Reaper", "b" * 64, "ffffffffffffffff")
        near = image_validation_agent.find_perceptual_duplicate(
            "fffffffffffffffe", exclude_platform_id=999
        )
        assert near is not None
        assert near["canonical_name"] == "MQ-9A Reaper"

    def test_distant_hash_is_not_a_duplicate(self, database):
        self._store(database, "MQ-9A Reaper", "c" * 64, "ffffffffffffffff")
        assert (
            image_validation_agent.find_perceptual_duplicate("0000000000000000", exclude_platform_id=999)
            is None
        )


class TestDerivatives:
    def test_builds_thumbnail_and_atlas_images(self, tmp_path, png_bytes):
        source = tmp_path / "original.png"
        source.write_bytes(png_bytes(1600, 1000))
        outputs = image_validation_agent.build_derivatives(
            source, destination_dir=tmp_path / "out", stem="mq9"
        )
        from PIL import Image

        assert "atlas_path" in outputs and "thumbnail_path" in outputs
        with Image.open(outputs["atlas_path"]) as atlas:
            assert atlas.width <= 640
        with Image.open(outputs["thumbnail_path"]) as thumb:
            assert thumb.width <= 320


class TestRevalidation:
    def test_missing_file_is_flagged_and_deselected(self, database):
        from app.db import insert
        from app.logging import utc_now
        from app.utils import normalize_name

        now = utc_now()
        pid = insert(
            "platforms",
            {
                "public_id": "UAV-X",
                "canonical_name": "Ghost",
                "normalized_name": normalize_name("Ghost"),
                "domain": "Military",
                "verification_status": "Probable",
                "confidence_score": 0.5,
                "created_at": now,
                "updated_at": now,
            },
            database,
        )
        insert(
            "images",
            {
                "platform_id": pid,
                "local_path": "/nonexistent/gone.jpg",
                "validation_status": "ok",
                "selected_for_atlas": 1,
                "created_at": now,
            },
            database,
        )
        stats = image_validation_agent.revalidate_stored()
        assert stats["missing"] == 1
        row = database.execute("SELECT validation_status, selected_for_atlas FROM images").fetchone()
        assert row["validation_status"] == "missing"
        assert row["selected_for_atlas"] == 0


class TestMetadataIdentity:
    def test_matching_metadata_scores_high(self):
        verdict, score, _ = image_discovery_agent.metadata_identity(
            "MQ-9A Reaper", "General Atomics", "United States", candidate()
        )
        assert verdict in ("match", "probable match")
        assert score > 0.5

    def test_unrelated_metadata_scores_low(self):
        verdict, score, _ = image_discovery_agent.metadata_identity(
            "Bayraktar TB2", "Baykar", "Türkiye", candidate(title="File:Cessna 172.jpg")
        )
        assert verdict == "uncertain"
        assert score < 0.35

    def test_image_directory_is_traversal_safe(self, _isolated_paths):
        path = image_discovery_agent.image_directory("../../etc", "../passwd")
        assert str(path).startswith(str(_isolated_paths.paths.images.resolve()))
