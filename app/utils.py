"""Shared primitives: normalisation, country handling, hashing, safe paths, retry.

Everything here is pure-python and dependency free so it can be unit tested in
isolation and reused by every agent.
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

# ---------------------------------------------------------------------------
# String normalisation
# ---------------------------------------------------------------------------

#: Words that carry no discriminating power when comparing platform names.
_NOISE_TOKENS = {
    "uav",
    "uas",
    "ua",
    "drone",
    "drones",
    "aircraft",
    "system",
    "systems",
    "vehicle",
    "unmanned",
    "aerial",
    "air",
    "the",
    "rpas",
    "rpa",
    "ucav",
    "loitering",
    "munition",
    "quadcopter",
    "multirotor",
}

_ROMAN = {
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "x": "10",
}

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RE = re.compile(r"\s+")

#: Hyphenation artefact from PDF-extracted sources: "Northrop Grum- man".
#: Only fires between two lowercase letters so real designations ("MQ- 9",
#: "X- 47B") and hyphenated proper nouns are left alone.
_PDF_HYPHEN_RE = re.compile(r"(?<=[a-z])-\s+(?=[a-z])")


def strip_accents(text: str) -> str:
    """Fold accents to ASCII while keeping non-latin scripts intact."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def clean_text(value: Any) -> str:
    """Trim, collapse whitespace and drop the BOM/placeholder values."""
    if value is None:
        return ""
    text = str(value).replace("﻿", "").strip()
    if text.lower() in {"n/a", "na", "none", "null", "-", "--", "unknown"}:
        return "" if text.lower() != "unknown" else "Unknown"
    text = _PDF_HYPHEN_RE.sub("", text)
    return _WS_RE.sub(" ", text)


def normalize_name(name: str) -> str:
    """Canonical comparison key for a platform name.

    Lowercases, folds accents, removes punctuation, expands common separators and
    drops generic noise words.  Digits are preserved because model numbers carry
    most of the identity signal (``MQ-9`` vs ``MQ-1``).
    """
    text = strip_accents(clean_text(name)).lower()
    text = text.replace("&", " and ")
    text = _PUNCT_RE.sub(" ", text)
    tokens = [t for t in _WS_RE.split(text) if t]
    kept: list[str] = []
    for token in tokens:
        if token in _NOISE_TOKENS:
            continue
        kept.append(_ROMAN.get(token, token))
    if not kept:  # every token was noise - fall back to the raw form
        kept = tokens
    return " ".join(kept)


def normalize_key(name: str) -> str:
    """Whitespace-free variant of :func:`normalize_name` for exact bucketing."""
    return normalize_name(name).replace(" ", "")


def tokenize(name: str) -> list[str]:
    return [t for t in normalize_name(name).split(" ") if t]


_MODEL_CODE_RE = re.compile(r"\b([a-z]{1,4}[- ]?\d{1,4}[a-z]?)\b")


def extract_model_codes(name: str) -> list[str]:
    """Pull out designations such as ``MQ-9``, ``TB2``, ``CH-4``."""
    text = strip_accents(clean_text(name)).lower()
    found = {m.group(1).replace(" ", "-").replace("--", "-") for m in _MODEL_CODE_RE.finditer(text)}
    return sorted(found)


def slugify(value: str, *, max_length: int = 80) -> str:
    """Filesystem-safe slug. Never empty, never traversal capable."""
    text = strip_accents(clean_text(value)).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    if not text:
        text = "unnamed"
    return text[:max_length].strip("-") or "unnamed"


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def name_similarity(a: str, b: str) -> float:
    """Blended similarity tuned for aircraft designations.

    Character ratio alone merges ``MQ-1`` with ``MQ-9``; token Jaccard alone
    merges every ``DJI Mavic`` model.  The blend, combined with the model-code
    guard in the dedup agent, keeps distinct variants apart.
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    char = ratio(na, nb)
    token = jaccard(na.split(), nb.split())
    return round(0.55 * char + 0.45 * token, 4)


# ---------------------------------------------------------------------------
# Countries
# ---------------------------------------------------------------------------

MULTINATIONAL = "Multinational"
UNKNOWN_COUNTRY = "Unknown"

#: Canonical spelling -> ISO 3166-1 alpha-3 (best effort; ``None`` for the two
#: synthetic buckets).  Used for the country index and coverage statistics.
COUNTRY_ISO3: dict[str, str | None] = {
    "Afghanistan": "AFG",
    "Albania": "ALB",
    "Algeria": "DZA",
    "Angola": "AGO",
    "Argentina": "ARG",
    "Armenia": "ARM",
    "Australia": "AUS",
    "Austria": "AUT",
    "Azerbaijan": "AZE",
    "Bahrain": "BHR",
    "Bangladesh": "BGD",
    "Belarus": "BLR",
    "Belgium": "BEL",
    "Bolivia": "BOL",
    "Bosnia and Herzegovina": "BIH",
    "Botswana": "BWA",
    "Brazil": "BRA",
    "Brunei": "BRN",
    "Bulgaria": "BGR",
    "Cambodia": "KHM",
    "Cameroon": "CMR",
    "Canada": "CAN",
    "Chile": "CHL",
    "China": "CHN",
    "Colombia": "COL",
    "Costa Rica": "CRI",
    "Côte d'Ivoire": "CIV",
    "Croatia": "HRV",
    "Cuba": "CUB",
    "Cyprus": "CYP",
    "Czech Republic": "CZE",
    "Denmark": "DNK",
    "Dominican Republic": "DOM",
    "Ecuador": "ECU",
    "Egypt": "EGY",
    "Estonia": "EST",
    "Ethiopia": "ETH",
    "Fiji": "FJI",
    "Finland": "FIN",
    "France": "FRA",
    "Georgia": "GEO",
    "Germany": "DEU",
    "Ghana": "GHA",
    "Greece": "GRC",
    "Guatemala": "GTM",
    "Honduras": "HND",
    "Hungary": "HUN",
    "Iceland": "ISL",
    "India": "IND",
    "Indonesia": "IDN",
    "Iran": "IRN",
    "Iraq": "IRQ",
    "Ireland": "IRL",
    "Israel": "ISR",
    "Italy": "ITA",
    "Jamaica": "JAM",
    "Japan": "JPN",
    "Jordan": "JOR",
    "Kazakhstan": "KAZ",
    "Kenya": "KEN",
    "Kuwait": "KWT",
    "Kyrgyzstan": "KGZ",
    "Laos": "LAO",
    "Latvia": "LVA",
    "Lebanon": "LBN",
    "Libya": "LBY",
    "Liechtenstein": "LIE",
    "Lithuania": "LTU",
    "Luxembourg": "LUX",
    "Madagascar": "MDG",
    "Malaysia": "MYS",
    "Maldives": "MDV",
    "Mali": "MLI",
    "Malta": "MLT",
    "Mauritius": "MUS",
    "Mexico": "MEX",
    "Moldova": "MDA",
    "Mongolia": "MNG",
    "Montenegro": "MNE",
    "Morocco": "MAR",
    "Mozambique": "MOZ",
    "Multinational": None,
    "Myanmar": "MMR",
    "Namibia": "NAM",
    "Nepal": "NPL",
    "Netherlands": "NLD",
    "New Zealand": "NZL",
    "Nicaragua": "NIC",
    "Nigeria": "NGA",
    "North Korea": "PRK",
    "North Macedonia": "MKD",
    "Norway": "NOR",
    "Oman": "OMN",
    "Pakistan": "PAK",
    "Panama": "PAN",
    "Papua New Guinea": "PNG",
    "Paraguay": "PRY",
    "Peru": "PER",
    "Philippines": "PHL",
    "Poland": "POL",
    "Portugal": "PRT",
    "Qatar": "QAT",
    "Romania": "ROU",
    "Russia": "RUS",
    "Rwanda": "RWA",
    "Saudi Arabia": "SAU",
    "Senegal": "SEN",
    "Serbia": "SRB",
    "Singapore": "SGP",
    "Slovakia": "SVK",
    "Slovenia": "SVN",
    "Somalia": "SOM",
    "South Africa": "ZAF",
    "South Korea": "KOR",
    "Soviet Union": "SUN",
    "Spain": "ESP",
    "Sri Lanka": "LKA",
    "Sudan": "SDN",
    "Sweden": "SWE",
    "Switzerland": "CHE",
    "Syria": "SYR",
    "Taiwan": "TWN",
    "Tajikistan": "TJK",
    "Tanzania": "TZA",
    "Thailand": "THA",
    "Trinidad and Tobago": "TTO",
    "Tunisia": "TUN",
    "Türkiye": "TUR",
    "Turkmenistan": "TKM",
    "Uganda": "UGA",
    "Ukraine": "UKR",
    "United Arab Emirates": "ARE",
    "United Kingdom": "GBR",
    "United States": "USA",
    "Unknown": None,
    "Uruguay": "URY",
    "Uzbekistan": "UZB",
    "Venezuela": "VEN",
    "Vietnam": "VNM",
    "Yemen": "YEM",
    "Yugoslavia": "YUG",
    "Zambia": "ZMB",
    "Zimbabwe": "ZWE",
}

#: Everything we have observed in the wild mapped onto the canonical spelling.
_COUNTRY_ALIASES: dict[str, str] = {
    "us": "United States",
    "usa": "United States",
    "u s a": "United States",
    "u s": "United States",
    "united states of america": "United States",
    "america": "United States",
    "uk": "United Kingdom",
    "u k": "United Kingdom",
    "great britain": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "turkey": "Türkiye",
    "turkiye": "Türkiye",
    "türkiye": "Türkiye",
    "republic of turkey": "Türkiye",
    "republic of korea": "South Korea",
    "korea south": "South Korea",
    "korea, south": "South Korea",
    "south korea": "South Korea",
    "korea": "South Korea",
    "dprk": "North Korea",
    "korea north": "North Korea",
    "korea, north": "North Korea",
    "czechia": "Czech Republic",
    "czech republic": "Czech Republic",
    "czechoslovakia": "Czech Republic",
    "prc": "China",
    "peoples republic of china": "China",
    "people's republic of china": "China",
    "china prc": "China",
    "roc": "Taiwan",
    "republic of china": "Taiwan",
    "chinese taipei": "Taiwan",
    "uae": "United Arab Emirates",
    "u a e": "United Arab Emirates",
    "emirates": "United Arab Emirates",
    "russian federation": "Russia",
    "ussr": "Soviet Union",
    "soviet union": "Soviet Union",
    "union of soviet socialist republics": "Soviet Union",
    "west germany": "Germany",
    "east germany": "Germany",
    "frg": "Germany",
    "deutschland": "Germany",
    "holland": "Netherlands",
    "the netherlands": "Netherlands",
    "netherlands": "Netherlands",
    "iran islamic republic of": "Iran",
    "islamic republic of iran": "Iran",
    "viet nam": "Vietnam",
    "republic of south africa": "South Africa",
    "rsa": "South Africa",
    "swiss": "Switzerland",
    "espana": "Spain",
    "españa": "Spain",
    "brasil": "Brazil",
    "eu": MULTINATIONAL,
    "europe": MULTINATIONAL,
    "european union": MULTINATIONAL,
    "european consortium": MULTINATIONAL,
    "european": MULTINATIONAL,
    "pan european": MULTINATIONAL,
    "consortium": MULTINATIONAL,
    "burma": "Myanmar",
    "macedonia": "North Macedonia",
    "ivory coast": "Côte d'Ivoire",
    "cote d ivoire": "Côte d'Ivoire",
    "bosnia": "Bosnia and Herzegovina",
    "uae emirates": "United Arab Emirates",
    "nato": MULTINATIONAL,
    "international": MULTINATIONAL,
    "multi national": MULTINATIONAL,
    "multinational": MULTINATIONAL,
    "multi-national": MULTINATIONAL,
    "joint": MULTINATIONAL,
    "various": MULTINATIONAL,
    "unknown": UNKNOWN_COUNTRY,
    "not specified": UNKNOWN_COUNTRY,
    "unspecified": UNKNOWN_COUNTRY,
    "n a": UNKNOWN_COUNTRY,
    "": UNKNOWN_COUNTRY,
}

_MULTI_SPLIT_RE = re.compile(r"\s*(?:/|\||;|,| and | & |\+)\s*", re.IGNORECASE)


def normalize_country(value: Any) -> tuple[str, list[str]]:
    """Return ``(canonical_country, participating_countries)``.

    A joint programme such as ``"France/Germany/Spain"`` collapses to
    ``("Multinational", ["France", "Germany", "Spain"])``.  Anything we cannot
    place becomes ``("Unknown", [])`` - we never guess.
    """
    raw = clean_text(value)
    if not raw:
        return UNKNOWN_COUNTRY, []

    parts = [p for p in _MULTI_SPLIT_RE.split(raw) if p.strip()]
    resolved: list[str] = []
    unresolved = False
    for part in parts:
        canon = _resolve_single_country(part)
        if canon in (UNKNOWN_COUNTRY, None):
            unresolved = True
            continue
        if canon == MULTINATIONAL:
            return MULTINATIONAL, []
        if canon not in resolved:
            resolved.append(canon)

    if len(resolved) == 1:
        return resolved[0], []
    if len(resolved) > 1:
        return MULTINATIONAL, resolved
    return UNKNOWN_COUNTRY, [] if unresolved else []


def _resolve_single_country(value: str) -> str:
    text = clean_text(value)
    if not text:
        return UNKNOWN_COUNTRY
    if text in COUNTRY_ISO3:
        return text
    key = _PUNCT_RE.sub(" ", strip_accents(text).lower()).strip()
    key = _WS_RE.sub(" ", key)
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    for canonical in COUNTRY_ISO3:
        if _PUNCT_RE.sub(" ", strip_accents(canonical).lower()).strip() == key:
            return canonical
    return UNKNOWN_COUNTRY


def country_iso3(country: str) -> str | None:
    return COUNTRY_ISO3.get(country)


# ---------------------------------------------------------------------------
# Hashing & filesystem safety
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def stable_id(*parts: Any) -> str:
    """Deterministic 16-hex-char identifier - keeps runs reproducible."""
    joined = "␟".join(clean_text(p).lower() for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def safe_join(base: Path, *parts: str) -> Path:
    """Join under ``base`` refusing any traversal outside of it."""
    base = base.resolve()
    candidate = base
    for part in parts:
        cleaned = slugify(part) if part not in ("", None) else "unnamed"
        candidate = candidate / cleaned
    resolved = candidate.resolve()
    if base != resolved and base not in resolved.parents:
        raise ValueError(f"unsafe path outside base: {candidate!r}")
    return resolved


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str, *, default: str = "file", max_length: int = 120) -> str:
    stem = strip_accents(clean_text(name))
    stem = _SAFE_FILENAME_RE.sub("_", stem).strip("._-")
    stem = re.sub(r"_{2,}", "_", stem)
    if not stem:
        stem = default
    return stem[:max_length]


# ---------------------------------------------------------------------------
# Retry / rate limiting
# ---------------------------------------------------------------------------


class RateLimiter:
    """Simple per-key minimum-interval limiter (polite crawling)."""

    def __init__(self, rate_per_second: float) -> None:
        self.min_interval = 1.0 / rate_per_second if rate_per_second > 0 else 0.0
        self._last: dict[str, float] = {}

    def wait(self, key: str = "default") -> float:
        if self.min_interval <= 0:
            return 0.0
        now = time.monotonic()
        last = self._last.get(key)
        delay = 0.0
        if last is not None:
            elapsed = now - last
            if elapsed < self.min_interval:
                delay = self.min_interval - elapsed
                time.sleep(delay)
        self._last[key] = time.monotonic()
        return delay


def retry_call(
    func: Callable[[], T],
    *,
    attempts: int = 4,
    base_delay: float = 2.0,
    retry_on: Sequence[type[BaseException]] = (Exception,),
    should_retry: Callable[[BaseException], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Call ``func`` with exponential backoff (2s, 4s, 8s, 16s by default)."""
    last: BaseException | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return func()
        except retry_on as exc:  # type: ignore[misc]
            last = exc
            if should_retry is not None and not should_retry(exc):
                raise
            if attempt >= attempts:
                break
            delay = base_delay ** attempt if base_delay > 1 else base_delay * attempt
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            sleep(delay)
    assert last is not None
    raise last


def chunked(items: Sequence[T], size: int) -> Iterable[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def coerce_year(value: Any) -> int | None:
    """Pull a plausible 4-digit year out of messy source text."""
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"\b(1[89]\d{2}|20\d{2}|21\d{2})\b", text)
    if not match:
        return None
    year = int(match.group(1))
    return year if 1850 <= year <= 2100 else None


def coerce_float(value: Any) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", text.replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None
