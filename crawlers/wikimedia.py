"""Wikimedia Commons integration - the primary image provider.

The Commons API is used in two steps:

1. ``action=query&generator=search&gsrnamespace=6`` finds candidate *File:* pages
   for a platform name.
2. ``prop=imageinfo&iiprop=url|size|mime|extmetadata`` returns the direct file
   URL, pixel dimensions, MIME type and the full licence block
   (``LicenseShortName``, ``Artist``, ``Credit``, ``UsageTerms``, ``AttributionRequired``).

Candidates are scored before download so that the best licensed, highest
resolution, most plausibly-matching file is tried first, and obvious rejects
(logos, diagrams, patches, insignia, screenshots) are dropped up front.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from app.config import get_settings
from app.logging import AgentLogger
from app.models import ImageCandidate
from app.utils import clean_text, name_similarity, normalize_name, tokenize
from crawlers import extract
from crawlers.http import FetchError, HttpClient, get_client

LOG = AgentLogger("crawler.wikimedia")

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_FILE_PAGE = "https://commons.wikimedia.org/wiki/"

#: File-name fragments that are never an airframe photograph.
REJECT_PATTERNS = re.compile(
    r"(logo|insignia|roundel|patch|emblem|coat[_ ]of[_ ]arms|flag|badge|crest|"
    r"diagram|schematic|drawing|blueprint|silhouette|map|chart|graph|"
    r"screenshot|infobox|icon|banner|stub|orthographic|"
    r"3d[_ ]model|render|artist.?s?[_ ]impression|concept[_ ]art)",
    re.IGNORECASE,
)

#: Extensions we will not attempt to use in a print atlas.
REJECT_EXTENSIONS = (".svg", ".pdf", ".gif", ".tif", ".tiff", ".ogv", ".webm", ".djvu")

#: Licence short names that are unambiguously acceptable for redistribution.
ACCEPTABLE_LICENSE_RE = re.compile(
    r"(^|\b)(cc0|public domain|pd-|pdm|cc[ -]?by(?![ -]?nc)([ -]?sa)?"
    r"|attribution([ -]share ?alike)?)",
    re.IGNORECASE,
)

NONCOMMERCIAL_RE = re.compile(r"(non[- ]?commercial|\bnc\b|cc[ -]?by[ -]?nc)", re.IGNORECASE)
NODERIV_RE = re.compile(r"(no[- ]?deriv|\bnd\b|cc[ -]?by[ -]?nd)", re.IGNORECASE)
FAIR_USE_RE = re.compile(r"(fair ?use|non[- ]?free|all rights reserved)", re.IGNORECASE)


def _search_terms(platform_name: str, manufacturer: str = "") -> list[str]:
    """Query ladder: most specific first, then progressively looser."""
    name = clean_text(platform_name)
    terms = [f"{name} UAV", name]
    if manufacturer and manufacturer.lower() not in name.lower():
        terms.insert(0, f"{manufacturer} {name}")
    # Drop a trailing parenthetical or slash-variant for a broader retry.
    stripped = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if stripped and stripped != name:
        terms.append(stripped)
    if "/" in name:
        terms.append(name.split("/")[0].strip())
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            ordered.append(term)
    return ordered


def search_images(
    platform_name: str,
    *,
    manufacturer: str = "",
    country: str = "",
    limit: int = 12,
    client: HttpClient | None = None,
) -> list[ImageCandidate]:
    """Return scored, pre-filtered Commons candidates for one platform."""
    http = client or get_client()
    settings = get_settings()
    candidates: dict[str, ImageCandidate] = {}

    for term in _search_terms(platform_name, manufacturer):
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "generator": "search",
            "gsrsearch": f"{term} filetype:bitmap",
            "gsrnamespace": "6",
            "gsrlimit": str(min(limit, 25)),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata|user",
            "iiurlwidth": str(max(settings.atlas_image_width, 1024)),
        }
        try:
            document = http.get_json(COMMONS_API, params=params)
        except FetchError as exc:
            LOG.warning("commons search failed for %r: %s", term, exc)
            raise

        pages = extract.json_path(document, "query.pages") or []
        if isinstance(pages, dict):
            pages = list(pages.values())
        for page in pages:
            candidate = _page_to_candidate(page, platform_name, country)
            if candidate is None:
                continue
            existing = candidates.get(candidate.source_url)
            if existing is None or candidate.score > existing.score:
                candidates[candidate.source_url] = candidate

        if len([c for c in candidates.values() if c.score >= 0.5]) >= 3:
            break  # enough good material, stop widening the query

    ranked = sorted(candidates.values(), key=lambda c: c.score, reverse=True)
    LOG.debug("commons: %s -> %d candidates", platform_name, len(ranked))
    return ranked[:limit]


def _page_to_candidate(
    page: dict[str, Any], platform_name: str, country: str
) -> ImageCandidate | None:
    infos = page.get("imageinfo") or []
    if not infos:
        return None
    info = infos[0]
    file_title = clean_text(page.get("title", ""))
    url = info.get("url") or ""
    if not url:
        return None
    lowered = url.lower()
    if lowered.endswith(REJECT_EXTENSIONS):
        return None
    if REJECT_PATTERNS.search(file_title) or REJECT_PATTERNS.search(urllib.parse.unquote(lowered)):
        return None

    meta = info.get("extmetadata") or {}

    def m(key: str) -> str:
        value = meta.get(key)
        if isinstance(value, dict):
            return extract.strip_tags(str(value.get("value", "")))
        return ""

    width = int(info.get("width") or 0)
    height = int(info.get("height") or 0)
    mime = clean_text(info.get("mime", ""))

    candidate = ImageCandidate(
        platform_id=0,
        platform_name=platform_name,
        source_url=url,
        source_page_url=info.get("descriptionurl")
        or COMMONS_FILE_PAGE + urllib.parse.quote(file_title.replace(" ", "_")),
        title=file_title,
        photographer=m("Artist") or clean_text(info.get("user", "")),
        license_name=m("LicenseShortName") or m("License"),
        license_url=(meta.get("LicenseUrl", {}) or {}).get("value", "")
        if isinstance(meta.get("LicenseUrl"), dict)
        else "",
        attribution_text=m("Attribution") or m("Credit"),
        width=width,
        height=height,
        mime_type=mime,
        file_size=int(info.get("size") or 0),
        description=m("ImageDescription"),
        categories=[c for c in m("Categories").split("|") if c],
        provider="Wikimedia Commons",
    )
    candidate.score = score_candidate(candidate, platform_name, country)
    return candidate


def score_candidate(candidate: ImageCandidate, platform_name: str, country: str = "") -> float:
    """Heuristic pre-download score in ``[0, 1]``.

    Signals: name overlap between the file title/description and the platform,
    licence acceptability, pixel width, and landscape-ish aspect ratio (photos of
    aircraft in the atlas read better than portrait crops).
    """
    settings = get_settings()
    haystack = " ".join(
        [candidate.title, candidate.description, " ".join(candidate.categories)]
    )
    name_score = name_similarity(platform_name, candidate.title)
    tokens = set(tokenize(platform_name))
    hay_tokens = set(tokenize(haystack))
    overlap = len(tokens & hay_tokens) / len(tokens) if tokens else 0.0
    identity = max(name_score, overlap)

    licence_text = f"{candidate.license_name} {candidate.attribution_text}"
    if FAIR_USE_RE.search(licence_text):
        licence_score = 0.0
    elif ACCEPTABLE_LICENSE_RE.search(candidate.license_name):
        licence_score = 1.0
    elif NONCOMMERCIAL_RE.search(licence_text) or NODERIV_RE.search(licence_text):
        licence_score = 0.15
    else:
        licence_score = 0.4

    if candidate.width >= settings.image_preferred_width:
        size_score = 1.0
    elif candidate.width >= settings.image_min_width:
        size_score = 0.6
    else:
        size_score = 0.0

    aspect = (candidate.width / candidate.height) if candidate.height else 0.0
    aspect_score = 1.0 if 0.9 <= aspect <= 2.6 else (0.5 if 0.5 <= aspect <= 3.5 else 0.1)

    country_bonus = 0.05 if country and country.lower() in haystack.lower() else 0.0

    quality = (
        0.45 * identity
        + 0.30 * licence_score
        + 0.15 * size_score
        + 0.10 * aspect_score
        + country_bonus
    )
    # Identity gates the whole score. A perfectly licensed, high-resolution
    # photograph of the wrong aircraft is worthless here, so weak name evidence
    # must not be able to ride on licence and resolution alone.
    identity_gate = 0.3 + 0.7 * min(1.0, identity / 0.4)
    return round(min(1.0, quality * identity_gate), 4)


def fetch_file_metadata(
    file_title: str, *, client: HttpClient | None = None
) -> dict[str, Any] | None:
    """Re-read the licence block for a known ``File:`` page (verification pass)."""
    http = client or get_client()
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "titles": file_title,
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata|user",
    }
    document = http.get_json(COMMONS_API, params=params)
    pages = extract.json_path(document, "query.pages") or []
    if isinstance(pages, dict):
        pages = list(pages.values())
    return pages[0] if pages else None


def media_search_url(platform_name: str) -> str:
    """Human-facing Commons search URL kept with every unresolved image item."""
    query = urllib.parse.quote(f"{clean_text(platform_name)} UAV")
    return (
        "https://commons.wikimedia.org/w/index.php?"
        f"search={query}&title=Special:MediaSearch&type=image"
    )


def normalized_title(candidate: ImageCandidate) -> str:
    return normalize_name(candidate.title)
