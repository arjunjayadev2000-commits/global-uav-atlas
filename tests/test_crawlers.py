"""Source parsing, HTTP policy and network-failure behaviour."""

from __future__ import annotations

import json

import pytest
import requests

from crawlers import extract, public_sources, regulatory, wikimedia
from crawlers.http import FetchError, HttpClient, Response

# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------


class TestCsvParsing:
    def test_parses_and_strips_bom(self):
        rows = extract.parse_csv("﻿manufacturer,name\nDJI,Mavic 3\n")
        assert rows == [{"manufacturer": "DJI", "name": "Mavic 3"}]

    def test_handles_empty_document(self):
        assert extract.parse_csv("") == []

    def test_ignores_blank_values(self):
        rows = extract.parse_csv("a,b\n1,\n")
        assert rows[0]["b"] == ""


class TestJsonParsing:
    def test_record_path(self):
        document = json.dumps({"data": {"items": [{"model": "X"}, {"model": "Y"}]}})
        assert extract.parse_json_records(document, "data.items") == [{"model": "X"}, {"model": "Y"}]

    def test_missing_path_returns_empty(self):
        assert extract.parse_json_records(json.dumps({"a": 1}), "b.c") == []


class TestHtmlParsing:
    HTML = """
    <html><body>
      <table>
        <tr><th>Manufacturer</th><th>Model</th><th>Class</th></tr>
        <tr><td>Parrot</td><td>Anafi USA</td><td>C1</td></tr>
        <tr><td>DJI</td><td>Mavic 3</td><td>C1</td></tr>
      </table>
      <a href="/products/tb2">Bayraktar TB2</a>
      <a href="/about">About us</a>
    </body></html>
    """

    def test_table_to_dicts(self):
        tables = extract.parse_html_tables(self.HTML)
        rows = extract.table_to_dicts(tables[0])
        assert rows[0] == {"manufacturer": "Parrot", "model": "Anafi USA", "class": "C1"}
        assert len(rows) == 2

    def test_links(self):
        links = extract.parse_links(self.HTML)
        assert ("/products/tb2", "Bayraktar TB2") in links

    def test_strip_tags(self):
        assert extract.strip_tags("<p>Hello <b>world</b></p>") == "Hello world"

    def test_malformed_html_does_not_raise(self):
        extract.parse_html_tables("<table><tr><td>unclosed")


class TestFieldMapping:
    def test_maps_and_falls_back(self):
        mapped = extract.map_fields(
            {"Manufacturer": "DJI", "Product": "Mavic 3"},
            {"manufacturer": "manufacturer", "model": ["model", "product"], "domain": "const:Civilian"},
        )
        assert mapped == {"manufacturer": "DJI", "model": "Mavic 3", "domain": "Civilian"}

    def test_join_name_avoids_duplication(self):
        assert extract.join_name("DJI", "DJI Mavic 3") == "DJI Mavic 3"
        assert extract.join_name("DJI GmbH", "DJI Matrice 400") == "DJI Matrice 400"
        assert extract.join_name("Parrot", "Anafi") == "Parrot Anafi"
        assert extract.join_name("", "Anafi") == "Anafi"


# ---------------------------------------------------------------------------
# HTTP client policy
# ---------------------------------------------------------------------------


class _FakeRaw:
    def __init__(self, status=200, body=b"ok", headers=None, url="https://example.invalid/"):
        self.status_code = status
        self._body = body
        self.headers = headers or {"content-type": "text/plain"}
        self.url = url
        self.text = body.decode("utf-8", "replace")

    def iter_content(self, size):
        yield self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestHttpPolicy:
    def test_cache_hit_avoids_second_request(self, _isolated_paths, monkeypatch):
        client = HttpClient()
        calls = {"n": 0}

        def fake_get(url, **kwargs):
            calls["n"] += 1
            return _FakeRaw(body=b"payload")

        monkeypatch.setattr(client.session, "get", fake_get)
        monkeypatch.setattr(client, "robots_allows", lambda url: True)

        first = client.get("https://example.invalid/data")
        second = client.get("https://example.invalid/data")
        assert first.content == second.content == b"payload"
        assert second.from_cache is True
        assert calls["n"] == 1

    def test_offline_mode_refuses_network(self, _isolated_paths, monkeypatch):
        from app import config

        monkeypatch.setattr(
            config, "get_settings", lambda: config.Settings(paths=_isolated_paths.paths, offline=True)
        )
        import crawlers.http as http_module

        monkeypatch.setattr(http_module, "get_settings", lambda: config.get_settings())
        client = HttpClient()
        with pytest.raises(FetchError, match="offline mode"):
            client.get("https://example.invalid/x")

    def test_robots_disallow_is_not_retried(self, _isolated_paths, monkeypatch):
        client = HttpClient()
        monkeypatch.setattr(client, "robots_allows", lambda url: False)
        with pytest.raises(FetchError) as excinfo:
            client.get("https://example.invalid/blocked")
        assert excinfo.value.retryable is False

    def test_policy_refusal_fails_fast_and_is_remembered(self, _isolated_paths, monkeypatch):
        client = HttpClient()
        attempts = {"n": 0}

        def refuse(url, **kwargs):
            attempts["n"] += 1
            raise requests.exceptions.ProxyError(
                "Unable to connect to proxy", OSError("Tunnel connection failed: 403 Forbidden")
            )

        monkeypatch.setattr(client.session, "get", refuse)
        monkeypatch.setattr(client, "robots_allows", lambda url: True)

        with pytest.raises(FetchError) as first:
            client.get("https://blocked.invalid/a")
        assert first.value.retryable is False
        assert attempts["n"] == 1  # no retry storm on a policy decision

        with pytest.raises(FetchError, match="egress policy"):
            client.get("https://blocked.invalid/b")
        assert attempts["n"] == 1  # second call short-circuits

    def test_transient_error_is_retried_then_raises(self, _isolated_paths, monkeypatch):
        client = HttpClient()
        client.settings = client.settings  # keep reference explicit
        attempts = {"n": 0}

        def flaky(url, **kwargs):
            attempts["n"] += 1
            return _FakeRaw(status=503)

        monkeypatch.setattr(client.session, "get", flaky)
        monkeypatch.setattr(client, "robots_allows", lambda url: True)
        monkeypatch.setattr("crawlers.http.retry_call", _immediate_retry_call)

        with pytest.raises(FetchError, match="503"):
            client.get("https://example.invalid/flaky")
        assert attempts["n"] > 1

    def test_oversize_response_is_rejected(self, _isolated_paths, monkeypatch):
        client = HttpClient()
        monkeypatch.setattr(client.session, "get", lambda url, **kw: _FakeRaw(body=b"x" * 5000))
        monkeypatch.setattr(client, "robots_allows", lambda url: True)
        with pytest.raises(FetchError, match="exceeds"):
            client.get("https://example.invalid/big", max_bytes=100)

    def test_404_is_not_retried(self, _isolated_paths, monkeypatch):
        client = HttpClient()
        monkeypatch.setattr(client.session, "get", lambda url, **kw: _FakeRaw(status=404))
        monkeypatch.setattr(client, "robots_allows", lambda url: True)
        with pytest.raises(FetchError) as excinfo:
            client.get("https://example.invalid/missing")
        assert excinfo.value.retryable is False


def _immediate_retry_call(func, *, attempts, base_delay, retry_on, should_retry=None, on_retry=None, sleep=None):
    from app.utils import retry_call

    return retry_call(
        func,
        attempts=attempts,
        base_delay=base_delay,
        retry_on=retry_on,
        should_retry=should_retry,
        on_retry=on_retry,
        sleep=lambda _: None,
    )


# ---------------------------------------------------------------------------
# Source crawlers
# ---------------------------------------------------------------------------


class _StubClient:
    def __init__(self, body: str):
        self.body = body

    def get(self, url, **kwargs):
        return Response(url=url, status=200, headers={"content-type": "text/plain"}, content=self.body.encode())

    def get_json(self, url, **kwargs):
        return json.loads(self.body)


class TestPublicSources:
    def test_csv_dataset_becomes_raw_discoveries(self):
        source = {
            "id": "odl",
            "title": "OpenDroneList",
            "url": "https://example.invalid/list.csv",
            "format": "csv",
            "field_map": {"manufacturer": "manufacturer", "model": "name"},
            "defaults": {"domain": "Civilian / Commercial"},
        }
        client = _StubClient("manufacturer,name\nDJI,Mavic 3\nParrot,Anafi\n")
        results = public_sources.crawl_dataset(source, client=client)
        assert [r.raw_name for r in results] == ["DJI Mavic 3", "Parrot Anafi"]
        assert results[0].domain == "Civilian / Commercial"
        assert results[0].fingerprint != results[1].fingerprint

    def test_skips_rows_without_a_name(self):
        source = {
            "title": "T",
            "url": "https://example.invalid/x.csv",
            "format": "csv",
            "field_map": {"manufacturer": "manufacturer", "model": "name"},
        }
        results = public_sources.crawl_dataset(_stub_source(source), client=_StubClient("manufacturer,name\n,\n"))
        assert results == []

    def test_mediawiki_list_filters_navigation(self):
        document = json.dumps(
            {
                "parse": {
                    "links": [
                        {"ns": 0, "exists": True, "title": "Bayraktar TB2"},
                        {"ns": 0, "exists": True, "title": "List of drones"},
                        {"ns": 14, "exists": True, "title": "Category:UAVs"},
                        {"ns": 0, "exists": False, "title": "Nonexistent Thing"},
                    ]
                }
            }
        )
        source = {"title": "wiki", "url": "https://example.invalid/api", "pages": ["List of UAVs"]}
        results = public_sources.crawl_mediawiki_list(source, client=_StubClient(document))
        assert [r.raw_name for r in results] == ["Bayraktar TB2"]
        assert results[0].payload["lead_only"] is True


class TestRegulatory:
    def test_registration_country_is_not_treated_as_origin(self):
        source = {
            "title": "FAA DoC",
            "url": "https://example.invalid/api",
            "format": "json",
            "record_path": "items",
            "field_map": {"manufacturer": "manufacturer", "model": "model"},
            "defaults": {"domain": "Civilian / Commercial"},
        }
        body = json.dumps({"items": [{"manufacturer": "Skydio", "model": "X10", "country": "United States"}]})
        results = regulatory.crawl_register(source, client=_StubClient(body))
        assert results[0].raw_country == ""
        assert results[0].payload["origin_is_registration_only"] is True
        assert results[0].payload["registered_country"] == "United States"


class TestWikimediaScoring:
    def _candidate(self, **kwargs):
        from app.models import ImageCandidate

        defaults = dict(
            platform_id=0,
            platform_name="MQ-9A Reaper",
            source_url="https://upload.invalid/MQ-9_Reaper.jpg",
            title="File:MQ-9 Reaper in flight.jpg",
            license_name="CC BY-SA 4.0",
            width=1600,
            height=1000,
            mime_type="image/jpeg",
            provider="Wikimedia Commons",
        )
        defaults.update(kwargs)
        return ImageCandidate(**defaults)

    def test_good_candidate_scores_high(self):
        score = wikimedia.score_candidate(self._candidate(), "MQ-9A Reaper", "United States")
        assert score > 0.6

    def test_small_image_scores_lower(self):
        big = wikimedia.score_candidate(self._candidate(), "MQ-9A Reaper")
        small = wikimedia.score_candidate(self._candidate(width=320, height=200), "MQ-9A Reaper")
        assert small < big

    def test_all_rights_reserved_scores_zero_licence(self):
        restricted = wikimedia.score_candidate(
            self._candidate(license_name="All rights reserved"), "MQ-9A Reaper"
        )
        free = wikimedia.score_candidate(self._candidate(), "MQ-9A Reaper")
        assert restricted < free

    def test_unrelated_title_scores_low(self):
        score = wikimedia.score_candidate(
            self._candidate(title="File:Cessna 172 landing.jpg"), "MQ-9A Reaper"
        )
        assert score < 0.6

    def test_search_terms_ladder(self):
        terms = wikimedia._search_terms("Heron TP (Eitan)", "IAI")
        assert terms[0] == "IAI Heron TP (Eitan)"
        assert "Heron TP" in terms

    def test_media_search_url_is_escaped(self):
        url = wikimedia.media_search_url("MQ-9A Reaper")
        assert "MQ-9A%20Reaper" in url or "MQ-9A+Reaper" in url


def _stub_source(source):
    return source
