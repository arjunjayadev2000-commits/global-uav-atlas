"""Normalisation, country handling and filesystem-safety tests."""

from __future__ import annotations

import pytest

from app.utils import (
    MULTINATIONAL,
    UNKNOWN_COUNTRY,
    clean_text,
    coerce_float,
    coerce_year,
    country_iso3,
    extract_model_codes,
    jaccard,
    name_similarity,
    normalize_country,
    normalize_key,
    normalize_name,
    safe_filename,
    safe_join,
    sha256_bytes,
    slugify,
    stable_id,
)


class TestNormalizeName:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("MQ-9A Reaper", "mq 9a reaper"),
            ("  MQ-9A   Reaper  ", "mq 9a reaper"),
            ("Bayraktar TB2 UAV", "bayraktar tb2"),
            ("Heron TP (Eitan)", "heron tp eitan"),
            ("Türkiye Anka-S", "turkiye anka s"),
            ("CH-4 unmanned aerial vehicle", "ch 4"),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert normalize_name(raw) == expected

    def test_noise_only_name_is_not_emptied(self):
        # "drone" is a noise token, but a name made only of noise must survive.
        assert normalize_name("Drone") == "drone"

    def test_roman_numerals_become_digits(self):
        assert normalize_name("Hermes III") == normalize_name("Hermes 3")

    def test_key_removes_whitespace(self):
        assert normalize_key("MQ-9A Reaper") == "mq9areaper"

    def test_distinct_designations_do_not_collapse(self):
        assert normalize_name("MQ-1 Predator") != normalize_name("MQ-9 Reaper")


class TestCleanText:
    def test_strips_bom_and_placeholders(self):
        assert clean_text("﻿  Hello  ") == "Hello"
        assert clean_text("N/A") == ""
        assert clean_text("unknown") == "Unknown"
        assert clean_text(None) == ""

    def test_repairs_pdf_hyphenation(self):
        assert clean_text("Northrop Grum- man") == "Northrop Grumman"

    def test_leaves_real_designations_alone(self):
        assert clean_text("MQ- 9") == "MQ- 9"
        assert clean_text("X-47B") == "X-47B"


class TestModelCodes:
    def test_extracts_designations(self):
        assert "mq-9" in extract_model_codes("MQ-9A Reaper") or "mq-9a" in extract_model_codes(
            "MQ-9A Reaper"
        )
        assert extract_model_codes("Bayraktar TB2") == ["tb2"]

    def test_returns_empty_for_plain_names(self):
        assert extract_model_codes("Global Hawk") == []


class TestSimilarity:
    def test_identical_names_score_one(self):
        assert name_similarity("MQ-9 Reaper", "MQ-9  Reaper") == 1.0

    def test_different_model_numbers_are_not_identical(self):
        assert name_similarity("MQ-1 Predator", "MQ-9 Reaper") < 0.8

    def test_empty_inputs(self):
        assert name_similarity("", "anything") == 0.0

    def test_jaccard(self):
        assert jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)
        assert jaccard([], ["a"]) == 0.0


class TestCountries:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("USA", "United States"),
            ("U.S.A.", "United States"),
            ("Great Britain", "United Kingdom"),
            ("Turkey", "Türkiye"),
            ("türkiye", "Türkiye"),
            ("Republic of Korea", "South Korea"),
            ("Czechia", "Czech Republic"),
            ("PRC", "China"),
            ("USSR", "Soviet Union"),
        ],
    )
    def test_aliases_resolve(self, raw, expected):
        assert normalize_country(raw)[0] == expected

    def test_joint_programme_becomes_multinational_with_participants(self):
        country, participants = normalize_country("France/Germany/Spain")
        assert country == MULTINATIONAL
        assert participants == ["France", "Germany", "Spain"]

    def test_european_consortium(self):
        assert normalize_country("European consortium")[0] == MULTINATIONAL

    def test_unknown_is_never_guessed(self):
        assert normalize_country("Atlantis")[0] == UNKNOWN_COUNTRY
        assert normalize_country("")[0] == UNKNOWN_COUNTRY
        assert normalize_country(None)[0] == UNKNOWN_COUNTRY

    def test_iso3_lookup(self):
        assert country_iso3("United States") == "USA"
        assert country_iso3("Türkiye") == "TUR"
        assert country_iso3(MULTINATIONAL) is None


class TestFilesystemSafety:
    def test_slugify(self):
        assert slugify("MQ-9A Reaper") == "mq-9a-reaper"
        assert slugify("///") == "unnamed"
        assert slugify("Türkiye Anka") == "turkiye-anka"

    def test_safe_join_blocks_traversal(self, tmp_path):
        result = safe_join(tmp_path, "../../etc", "passwd")
        assert str(result).startswith(str(tmp_path.resolve()))

    def test_safe_join_nests_normally(self, tmp_path):
        result = safe_join(tmp_path, "United States", "MQ-9A Reaper")
        assert result == tmp_path.resolve() / "united-states" / "mq-9a-reaper"

    def test_safe_filename_strips_dangerous_characters(self):
        assert safe_filename("../../etc/passwd") == "etc_passwd"
        assert safe_filename("") == "file"
        assert "/" not in safe_filename("a/b/c")


class TestMisc:
    def test_stable_id_is_deterministic(self):
        assert stable_id("MQ-9", "US") == stable_id("mq-9", "us")
        assert stable_id("MQ-9") != stable_id("MQ-1")

    def test_sha256(self):
        assert len(sha256_bytes(b"abc")) == 64

    def test_coerce_year(self):
        assert coerce_year("introduced 2007") == 2007
        assert coerce_year("circa 1899") == 1899
        assert coerce_year("no year here") is None
        assert coerce_year("3050") is None

    def test_coerce_float(self):
        assert coerce_float("1 200,5 kg") == pytest.approx(1200.5) or coerce_float("1 200,5 kg") == pytest.approx(1200.5)
        assert coerce_float("about 4.5") == pytest.approx(4.5)
        assert coerce_float("n/a") is None
