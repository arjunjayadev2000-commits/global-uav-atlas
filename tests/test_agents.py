"""Agent-level tests for image acquisition, vision verification and updates."""

from __future__ import annotations

import json

import pytest

from agents import (
    country_classifier_agent,
    image_discovery_agent,
    update_agent,
    vision_verification_agent,
)
from app.db import insert
from app.logging import utc_now
from app.models import ImageCandidate
from app.utils import normalize_name
from crawlers import government, manufacturer
from crawlers.http import FetchError, Response


def make_platform(conn, name="MQ-9A Reaper", country="United States", manufacturer_name="General Atomics"):
    from app.db import get_or_create_country, get_or_create_manufacturer

    now = utc_now()
    country_id = get_or_create_country(country, conn=conn)
    manufacturer_id = get_or_create_manufacturer(manufacturer_name, conn=conn)
    pid = insert(
        "platforms",
        {
            "public_id": "UAV-TEST01",
            "canonical_name": name,
            "normalized_name": normalize_name(name),
            "country_id": country_id,
            "manufacturer_id": manufacturer_id,
            "domain": "Military",
            "category": "MALE fixed-wing",
            "verification_status": "Probable",
            "confidence_score": 0.6,
            "created_at": now,
            "updated_at": now,
        },
        conn,
    )
    return pid


def commons_candidate(**kwargs) -> ImageCandidate:
    defaults = dict(
        platform_id=0,
        platform_name="MQ-9A Reaper",
        source_url="https://upload.invalid/MQ-9_Reaper.jpg",
        source_page_url="https://commons.invalid/File:MQ-9_Reaper.jpg",
        title="File:MQ-9 Reaper in flight.jpg",
        photographer="Jane Photographer",
        license_name="CC BY-SA 4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        width=1600,
        height=1000,
        mime_type="image/jpeg",
        description="An MQ-9 Reaper of the United States Air Force in flight",
        provider="Wikimedia Commons",
        score=0.9,
    )
    defaults.update(kwargs)
    return ImageCandidate(**defaults)


class _DownloadClient:
    """Stub HTTP client that writes real image bytes to the requested path."""

    def __init__(self, payload: bytes):
        self.payload = payload
        self.downloads: list[str] = []

    def download(self, url, destination, max_bytes=None):
        self.downloads.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.payload)
        return Response(url=url, status=200, headers={"content-type": "image/png"}, content=self.payload)


class TestImageAcquisition:
    def test_happy_path_stores_full_provenance(self, database, monkeypatch, png_bytes):
        pid = make_platform(database)
        payload = png_bytes(1400, 900)

        monkeypatch.setattr(
            image_discovery_agent.wikimedia, "search_images", lambda *a, **k: [commons_candidate()]
        )
        monkeypatch.setattr(image_discovery_agent, "get_client", lambda: _DownloadClient(payload))

        row = database.execute(
            "SELECT p.id, p.canonical_name, COALESCE(c.name,'') country, COALESCE(m.name,'') manufacturer "
            "FROM platforms p LEFT JOIN countries c ON c.id=p.country_id "
            "LEFT JOIN manufacturers m ON m.id=p.manufacturer_id WHERE p.id=?",
            (pid,),
        ).fetchone()
        result = image_discovery_agent.acquire_for_platform(row, conn=database)

        assert result["status"] == "ok"
        image = database.execute("SELECT * FROM images WHERE platform_id=?", (pid,)).fetchone()
        assert image["selected_for_atlas"] == 1
        assert image["license_verified"] == 1
        assert image["license_name"] == "CC BY-SA 4.0"
        assert image["attribution_text"]
        assert image["source_page_url"].startswith("https://commons.invalid/")
        assert image["identity_verdict"] in ("match", "probable match")
        assert len(image["sha256"]) == 64
        assert image["perceptual_hash"]
        assert image["atlas_path"] and image["thumbnail_path"]

        link = database.execute("SELECT COUNT(*) AS n FROM image_sources").fetchone()["n"]
        assert link == 1
        event = database.execute(
            "SELECT COUNT(*) AS n FROM verification_events WHERE entity_type='images'"
        ).fetchone()["n"]
        assert event == 1

    def test_unlicensed_candidate_is_rejected_and_queued(self, database, monkeypatch, png_bytes):
        pid = make_platform(database)
        monkeypatch.setattr(
            image_discovery_agent.wikimedia,
            "search_images",
            lambda *a, **k: [commons_candidate(license_name="All rights reserved")],
        )
        monkeypatch.setattr(image_discovery_agent, "get_client", lambda: _DownloadClient(png_bytes()))

        row = database.execute(
            "SELECT p.id, p.canonical_name, '' country, '' manufacturer FROM platforms p WHERE p.id=?",
            (pid,),
        ).fetchone()
        result = image_discovery_agent.acquire_for_platform(row, conn=database)

        assert result["status"] == "none"
        assert database.execute("SELECT COUNT(*) AS n FROM images").fetchone()["n"] == 0
        queued = database.execute(
            "SELECT suggested_action FROM unresolved_items WHERE item_type='image_missing'"
        ).fetchone()
        assert "commons.wikimedia.org" in queued["suggested_action"]

    def test_corrupt_download_is_rejected(self, database, monkeypatch):
        pid = make_platform(database)
        monkeypatch.setattr(
            image_discovery_agent.wikimedia, "search_images", lambda *a, **k: [commons_candidate()]
        )
        monkeypatch.setattr(
            image_discovery_agent, "get_client", lambda: _DownloadClient(b"not an image at all")
        )
        row = database.execute(
            "SELECT p.id, p.canonical_name, '' country, '' manufacturer FROM platforms p WHERE p.id=?",
            (pid,),
        ).fetchone()
        result = image_discovery_agent.acquire_for_platform(row, conn=database)
        assert result["status"] == "none"
        assert "does not decode" in result["reason"]

    def test_blocked_provider_is_recorded_with_the_blocker(self, database, monkeypatch):
        pid = make_platform(database)

        def blocked(*args, **kwargs):
            raise FetchError("host refused by network egress policy", status=403, retryable=False)

        monkeypatch.setattr(image_discovery_agent.wikimedia, "search_images", blocked)
        row = database.execute(
            "SELECT p.id, p.canonical_name, '' country, '' manufacturer FROM platforms p WHERE p.id=?",
            (pid,),
        ).fetchone()
        result = image_discovery_agent.acquire_for_platform(row, conn=database)

        assert result["status"] == "blocked"
        item = database.execute(
            "SELECT blocker, severity FROM unresolved_items WHERE item_type='image_missing'"
        ).fetchone()
        assert "egress" in item["blocker"]
        assert item["severity"] == "high"

    def test_run_stops_hammering_a_blocked_provider(self, database, monkeypatch):
        for index in range(6):
            from app.db import get_or_create_country

            now = utc_now()
            insert(
                "platforms",
                {
                    "public_id": f"UAV-{index}",
                    "canonical_name": f"Platform {index}",
                    "normalized_name": f"platform {index}",
                    "country_id": get_or_create_country("United States", conn=database),
                    "domain": "Military",
                    "verification_status": "Probable",
                    "confidence_score": 0.5,
                    "created_at": now,
                    "updated_at": now,
                },
                database,
            )

        def blocked(*args, **kwargs):
            raise FetchError("refused by network egress policy", status=403, retryable=False)

        monkeypatch.setattr(image_discovery_agent.wikimedia, "search_images", blocked)
        stats = image_discovery_agent.run()

        assert stats["blocked"] == 3  # stops after three consecutive refusals
        assert stats["attempted"] == 3
        blocker = database.execute(
            "SELECT COUNT(*) AS n FROM unresolved_items WHERE item_type='pipeline_blocker'"
        ).fetchone()["n"]
        assert blocker == 1

    def test_perceptual_duplicate_is_refused(self, database, monkeypatch, png_bytes):
        first = make_platform(database)
        now = utc_now()
        second = insert(
            "platforms",
            {
                "public_id": "UAV-TEST02",
                "canonical_name": "Bayraktar TB2",
                "normalized_name": "bayraktar tb2",
                "domain": "Military",
                "verification_status": "Probable",
                "confidence_score": 0.5,
                "created_at": now,
                "updated_at": now,
            },
            database,
        )
        payload = png_bytes(1400, 900)
        monkeypatch.setattr(
            image_discovery_agent.wikimedia, "search_images", lambda *a, **k: [commons_candidate()]
        )
        monkeypatch.setattr(image_discovery_agent, "get_client", lambda: _DownloadClient(payload))

        for pid, name in ((first, "MQ-9A Reaper"), (second, "Bayraktar TB2")):
            row = database.execute(
                "SELECT p.id, p.canonical_name, '' country, '' manufacturer FROM platforms p WHERE p.id=?",
                (pid,),
            ).fetchone()
            image_discovery_agent.acquire_for_platform(row, conn=database)

        images = database.execute("SELECT COUNT(*) AS n FROM images").fetchone()["n"]
        assert images == 1  # the same photo cannot serve two platforms

    def test_coverage_reporting(self, database):
        make_platform(database)
        coverage = image_discovery_agent.coverage()
        assert coverage["platforms"] == 1
        assert coverage["with_image"] == 0
        assert coverage["coverage_pct"] == 0.0


class TestSideload:
    def test_ingests_a_manifest_with_provenance(self, database, _isolated_paths, png_bytes, tmp_path):
        make_platform(database)
        directory = _isolated_paths.paths.imports / "images"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "reaper.png").write_bytes(png_bytes(1200, 800))
        (directory / "manifest.csv").write_text(
            "platform_name,file,source_url,source_page_url,photographer,license_name,license_url\n"
            "MQ-9A Reaper,reaper.png,https://upload.invalid/r.png,"
            "https://commons.invalid/File:r.png,Jane Photographer,CC BY 4.0,"
            "https://creativecommons.org/licenses/by/4.0/\n",
            encoding="utf-8",
        )
        stats = image_discovery_agent.sideload()
        assert stats["ingested"] == 1
        image = database.execute("SELECT * FROM images").fetchone()
        assert image["selected_for_atlas"] == 1
        assert image["license_verified"] == 1
        assert "sideloaded" in image["identity_explanation"]

    def test_rejects_a_row_without_a_licence(self, database, _isolated_paths, png_bytes):
        make_platform(database)
        directory = _isolated_paths.paths.imports / "images"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "reaper.png").write_bytes(png_bytes(1200, 800))
        (directory / "manifest.csv").write_text(
            "platform_name,file,source_url,source_page_url,photographer,license_name,license_url\n"
            "MQ-9A Reaper,reaper.png,https://upload.invalid/r.png,https://x.invalid/p,Anon,,\n",
            encoding="utf-8",
        )
        stats = image_discovery_agent.sideload()
        assert stats["ingested"] == 0
        assert stats["rejected"] == 1

    def test_missing_manifest_is_not_fatal(self, database):
        stats = image_discovery_agent.sideload()
        assert stats.get("skipped") is True


class TestVisionVerification:
    def test_parses_a_well_formed_reply(self):
        verdict = vision_verification_agent.parse_response(
            json.dumps({"verdict": "match", "confidence": 0.91, "explanation": "Clearly an MQ-9."})
        )
        assert verdict.verdict == "match"
        assert verdict.confidence == pytest.approx(0.91)

    def test_extracts_json_from_surrounding_prose(self):
        verdict = vision_verification_agent.parse_response(
            'Here you go: {"verdict": "mismatch", "confidence": 0.8, "explanation": "A Cessna."} Thanks!'
        )
        assert verdict.verdict == "mismatch"

    def test_unparseable_reply_becomes_uncertain(self):
        verdict = vision_verification_agent.parse_response("I am not sure at all")
        assert verdict.verdict == "uncertain"
        assert verdict.confidence == 0.0

    def test_invalid_verdict_value_becomes_uncertain(self):
        verdict = vision_verification_agent.parse_response(
            json.dumps({"verdict": "definitely yes", "confidence": 2.0})
        )
        assert verdict.verdict == "uncertain"
        assert verdict.confidence == 1.0

    def test_unavailable_api_flags_low_confidence_images(self, database, monkeypatch, png_bytes, tmp_path):
        pid = make_platform(database)
        image_path = tmp_path / "img.png"
        image_path.write_bytes(png_bytes())
        insert(
            "images",
            {
                "platform_id": pid,
                "local_path": str(image_path),
                "atlas_path": str(image_path),
                "identity_confidence": 0.2,
                "identity_verdict": "uncertain",
                "validation_status": "ok",
                "selected_for_atlas": 1,
                "created_at": utc_now(),
            },
            database,
        )
        monkeypatch.setattr(vision_verification_agent, "available", lambda: False)
        stats = vision_verification_agent.run()

        assert stats["available"] is False
        assert stats["flagged_for_review"] == 1
        item = database.execute(
            "SELECT blocker FROM unresolved_items WHERE item_type='image_identity_unverified'"
        ).fetchone()
        assert "vision API" in item["blocker"]

    def test_mismatch_deselects_the_image(self, database, monkeypatch, png_bytes, tmp_path):
        pid = make_platform(database)
        image_path = tmp_path / "img.png"
        image_path.write_bytes(png_bytes())
        insert(
            "images",
            {
                "platform_id": pid,
                "local_path": str(image_path),
                "atlas_path": str(image_path),
                "identity_confidence": 0.5,
                "identity_verdict": "probable match",
                "validation_status": "ok",
                "selected_for_atlas": 1,
                "created_at": utc_now(),
            },
            database,
        )

        class _Message:
            content = [type("Block", (), {"type": "text", "text": json.dumps({"verdict": "mismatch", "confidence": 0.95, "explanation": "Different aircraft."})})()]

        class _Api:
            class messages:
                @staticmethod
                def create(**kwargs):
                    return _Message()

        monkeypatch.setattr(vision_verification_agent, "available", lambda: True)
        monkeypatch.setattr(vision_verification_agent, "_client", lambda: _Api())

        stats = vision_verification_agent.run()
        assert stats["mismatch"] == 1
        row = database.execute("SELECT selected_for_atlas, identity_verdict FROM images").fetchone()
        assert row["selected_for_atlas"] == 0
        assert row["identity_verdict"] == "mismatch"


class TestManufacturerCrawler:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Bayraktar TB2", True),
            ("MQ-9B SeaGuardian", True),
            ("About us", False),
            ("Read more", False),
            ("This is a long marketing sentence about our capabilities.", False),
            ("", False),
        ],
    )
    def test_platform_name_heuristic(self, text, expected):
        assert manufacturer.looks_like_platform_name(text) is expected

    def test_crawl_site_extracts_product_links(self):
        html = """
        <a href="/uav/tb2">Bayraktar TB2</a>
        <a href="/uav/akinci">Bayraktar Akinci</a>
        <a href="/about">About</a>
        """

        class _Client:
            def get(self, url, **kwargs):
                return Response(url=url, status=200, headers={}, content=html.encode())

        site = {
            "id": "baykar",
            "manufacturer": "Baykar",
            "country": "Türkiye",
            "url": "https://baykar.invalid/uav/",
            "credibility_tier": 1,
        }
        results = manufacturer.crawl_site(site, client=_Client())
        names = [r.raw_name for r in results]
        # Product anchors are qualified with the manufacturer; the dedup agent
        # later treats that leading manufacturer token as cosmetic.
        assert "Baykar Bayraktar TB2" in names
        assert all("About" not in n for n in names)
        assert [r.payload["anchor_text"] for r in results] == ["Bayraktar TB2", "Bayraktar Akinci"]
        assert results[0].payload["needs_review"] is True
        assert results[0].raw_country == "Türkiye"


class TestGovernmentCrawler:
    def test_table_rows_become_military_discoveries(self):
        html = """
        <table>
          <tr><th>System</th><th>Manufacturer</th><th>Status</th></tr>
          <tr><td>Watchkeeper WK450</td><td>Thales</td><td>In service</td></tr>
        </table>
        """

        class _Client:
            def get(self, url, **kwargs):
                return Response(url=url, status=200, headers={}, content=html.encode())

        source = {
            "id": "mod_uk",
            "title": "UK MoD RPAS",
            "url": "https://gov.invalid/rpas",
            "country": "United Kingdom",
            "credibility_tier": 1,
        }
        results = government.crawl_source(source, client=_Client())
        assert results[0].raw_name == "Watchkeeper WK450"
        assert results[0].domain == "Military"
        assert results[0].payload["origin_hint_only"] is True


class TestUpdateAgent:
    def test_reports_deltas(self, database, monkeypatch):
        from agents import (
            country_classifier_agent,
            deduplication_agent,
            discovery_agent,
            image_validation_agent,
            metadata_agent,
            source_verification_agent,
        )

        monkeypatch.setattr(discovery_agent, "run", lambda **kw: {"passes": []})
        monkeypatch.setattr(metadata_agent, "promote", lambda **kw: {"created": 0})
        monkeypatch.setattr(deduplication_agent, "run", lambda **kw: {"merged": 0})
        monkeypatch.setattr(country_classifier_agent, "run", lambda **kw: {"examined": 0})
        monkeypatch.setattr(source_verification_agent, "run", lambda **kw: {"examined": 0})
        monkeypatch.setattr(image_validation_agent, "revalidate_stored", lambda: {"checked": 0})

        result = update_agent.run(skip_images=True)
        assert result["delta"] == {"platforms": 0, "raw": 0, "images": 0, "unresolved": 0}
        assert "before" in result and "after" in result


class TestWikimediaSearch:
    API_RESPONSE = {
        "query": {
            "pages": [
                {
                    "title": "File:MQ-9 Reaper in flight.jpg",
                    "imageinfo": [
                        {
                            "url": "https://upload.invalid/MQ-9_Reaper.jpg",
                            "descriptionurl": "https://commons.invalid/File:MQ-9_Reaper.jpg",
                            "width": 1800,
                            "height": 1200,
                            "mime": "image/jpeg",
                            "size": 400000,
                            "user": "Photographer",
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                "Artist": {"value": "<a href='#'>Jane Photographer</a>"},
                                "ImageDescription": {"value": "MQ-9 Reaper of the USAF"},
                                "Categories": {"value": "MQ-9 Reaper|Unmanned aerial vehicles"},
                            },
                        }
                    ],
                },
                {
                    "title": "File:MQ-9 Reaper insignia logo.svg",
                    "imageinfo": [
                        {
                            "url": "https://upload.invalid/logo.svg",
                            "width": 900,
                            "height": 900,
                            "mime": "image/svg+xml",
                            "extmetadata": {"LicenseShortName": {"value": "CC0"}},
                        }
                    ],
                },
            ]
        }
    }

    class _Client:
        def __init__(self, payload):
            self.payload = payload
            self.calls = 0

        def get_json(self, url, params=None, **kwargs):
            self.calls += 1
            return self.payload

    def test_parses_candidates_and_drops_logos_and_svg(self):
        from crawlers import wikimedia

        client = self._Client(self.API_RESPONSE)
        results = wikimedia.search_images("MQ-9A Reaper", manufacturer="General Atomics", client=client)
        assert len(results) == 1
        candidate = results[0]
        assert candidate.title == "File:MQ-9 Reaper in flight.jpg"
        assert candidate.license_name == "CC BY-SA 4.0"
        assert candidate.photographer == "Jane Photographer"
        assert candidate.source_page_url == "https://commons.invalid/File:MQ-9_Reaper.jpg"
        assert candidate.width == 1800
        assert candidate.score > 0.5

    def test_search_error_propagates_for_failure_isolation(self):
        from crawlers import wikimedia
        from crawlers.http import FetchError

        class _Failing:
            def get_json(self, *args, **kwargs):
                raise FetchError("blocked", status=403, retryable=False)

        with pytest.raises(FetchError):
            wikimedia.search_images("MQ-9A Reaper", client=_Failing())


class TestCountryClassifierRun:
    def _seed(self, database):
        from app.db import get_or_create_country, get_or_create_manufacturer, get_or_create_source

        now = utc_now()
        source = get_or_create_source(
            title="Curated seed", url="internal", credibility_tier=3, conn=database
        )
        unknown = get_or_create_country("Unknown", conn=database)
        china = get_or_create_country("China", conn=database)
        dji = get_or_create_manufacturer("DJI", conn=database)

        known = insert(
            "platforms",
            {
                "public_id": "UAV-KNOWN",
                "canonical_name": "DJI Mavic 3",
                "normalized_name": "dji mavic 3",
                "country_id": china,
                "manufacturer_id": dji,
                "domain": "Civilian / Commercial",
                "origin_confidence": "High",
                "verification_status": "Probable",
                "confidence_score": 0.6,
                "created_at": now,
                "updated_at": now,
            },
            database,
        )
        blank = insert(
            "platforms",
            {
                "public_id": "UAV-BLANK",
                "canonical_name": "DJI Matrice 400",
                "normalized_name": "dji matrice 400",
                "country_id": unknown,
                "manufacturer_id": dji,
                "domain": "Civilian / Commercial",
                "verification_status": "Needs Verification",
                "confidence_score": 0.2,
                "created_at": now,
                "updated_at": now,
            },
            database,
        )
        insert(
            "raw_discoveries",
            {
                "source_id": source,
                "source_dataset": "Curated seed",
                "raw_name": "DJI Mavic 3",
                "normalized_name": "dji mavic 3",
                "raw_country": "China",
                "payload_json": "{}",
                "fingerprint": "fp-known",
                "promoted_platform_id": known,
                "processed": 1,
                "created_at": now,
            },
            database,
        )
        return known, blank

    def test_run_reclassifies_from_raw_evidence(self, database):
        known, _ = self._seed(database)
        stats = country_classifier_agent.run()
        assert stats["examined"] >= 1
        row = database.execute(
            "SELECT c.name FROM platforms p JOIN countries c ON c.id=p.country_id WHERE p.id=?",
            (known,),
        ).fetchone()
        assert row["name"] == "China"

    def test_manufacturer_inference_fills_unknown_origins(self, database):
        _, blank = self._seed(database)
        stats = country_classifier_agent.infer_from_manufacturer()
        assert stats["inferred"] == 1
        row = database.execute(
            "SELECT c.name, p.origin_confidence FROM platforms p "
            "JOIN countries c ON c.id=p.country_id WHERE p.id=?",
            (blank,),
        ).fetchone()
        assert row["name"] == "China"
        assert "inferred" in row["origin_confidence"]

    def test_inference_is_queued_for_review(self, database):
        self._seed(database)
        country_classifier_agent.infer_from_manufacturer()
        item = database.execute(
            "SELECT subject FROM unresolved_items WHERE item_type='country_inferred'"
        ).fetchone()
        assert item["subject"] == "DJI Matrice 400"

    def test_no_inference_without_a_sourced_sibling(self, database):
        from app.db import get_or_create_country, get_or_create_manufacturer

        now = utc_now()
        insert(
            "platforms",
            {
                "public_id": "UAV-LONE",
                "canonical_name": "Mystery UAV",
                "normalized_name": "mystery",
                "country_id": get_or_create_country("Unknown", conn=database),
                "manufacturer_id": get_or_create_manufacturer("Nobody Ltd", conn=database),
                "domain": "Unknown",
                "verification_status": "Needs Verification",
                "confidence_score": 0.1,
                "created_at": now,
                "updated_at": now,
            },
            database,
        )
        stats = country_classifier_agent.infer_from_manufacturer()
        assert stats["inferred"] == 0
        assert stats["still_unknown"] == 1
