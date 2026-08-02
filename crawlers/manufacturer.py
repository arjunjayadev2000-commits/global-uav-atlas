"""Tier-1 manufacturer product-page crawler.

Manufacturer sites are the strongest evidence for *what a company actually
builds*, but they have no common markup.  Rather than pretending a universal
parser exists, this crawler does the two things that generalise:

1. Harvest product links from the declared product-index URL and keep those whose
   anchor text looks like a platform designation.
2. Record the page itself as a tier-1 :class:`Source` so every discovery it
   yields carries defensible provenance.

Anything ambiguous is emitted with ``needs_review`` set in the payload so the
metadata agent keeps it at ``Needs Verification`` instead of silently promoting
marketing copy into the atlas.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from app.logging import AgentLogger
from app.models import RawDiscovery
from app.utils import clean_text
from crawlers import extract
from crawlers.http import HttpClient, get_client
from crawlers.public_sources import load_registry

LOG = AgentLogger("crawler.manufacturer")

#: Anchor text that is navigation rather than a product.
_NAV_RE = re.compile(
    r"^(home|about|about us|contact|careers|news|media|investors|privacy|terms|"
    r"cookies|sitemap|search|login|register|support|downloads?|events|blog|"
    r"products?|solutions?|services?|technolog(y|ies)|company|legal|"
    r"all products|view all|read more|learn more|next|previous|menu|share)$",
    re.IGNORECASE,
)

#: An anchor that plausibly names an airframe: has a digit, or 2-5 capitalised
#: words, and is not obviously a sentence.
_DESIGNATION_RE = re.compile(r"^[A-Za-z0-9][\w\-\.' ]{1,58}$")


def looks_like_platform_name(text: str) -> bool:
    value = clean_text(text)
    if not value or len(value) < 2 or len(value) > 60:
        return False
    if _NAV_RE.match(value):
        return False
    if not _DESIGNATION_RE.match(value):
        return False
    words = value.split()
    if len(words) > 6:
        return False
    if value.endswith((".", "?", "!")):
        return False
    has_digit = any(ch.isdigit() for ch in value)
    capitalised = sum(1 for w in words if w[:1].isupper())
    return has_digit or capitalised >= 1


def crawl_site(
    site: dict[str, Any],
    *,
    client: HttpClient | None = None,
    limit: int | None = None,
) -> list[RawDiscovery]:
    """Harvest product links from one manufacturer product index."""
    http = client or get_client()
    url = site["url"]
    manufacturer = site.get("manufacturer", "")
    country = site.get("country", "")

    response = http.get(url)
    links = extract.parse_links(response.text)
    base = f"{urllib.parse.urlparse(url).scheme}://{urllib.parse.urlparse(url).netloc}"

    seen: set[str] = set()
    discoveries: list[RawDiscovery] = []
    for href, text in links:
        name = clean_text(text)
        if not looks_like_platform_name(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        absolute = urllib.parse.urljoin(base, href)
        discoveries.append(
            RawDiscovery(
                raw_name=extract.join_name(manufacturer, name),
                source_dataset=f"{manufacturer} official product pages",
                source_url=absolute,
                external_ref=site.get("id", ""),
                raw_country=country,
                raw_manufacturer=manufacturer,
                payload={
                    "anchor_text": name,
                    "product_index": url,
                    "needs_review": True,
                    "credibility_tier": site.get("credibility_tier", 1),
                },
            )
        )
        if limit is not None and len(discoveries) >= limit:
            break

    LOG.info("%s -> %d product leads", manufacturer or url, len(discoveries))
    return discoveries


def crawl_all(
    *,
    client: HttpClient | None = None,
    manufacturer: str | None = None,
    limit: int | None = None,
) -> list[RawDiscovery]:
    """Crawl every registered manufacturer site (optionally filtered by name)."""
    registry = load_registry()
    out: list[RawDiscovery] = []
    for site in registry.get("manufacturer_sites", []):
        if manufacturer and manufacturer.lower() not in site.get("manufacturer", "").lower():
            continue
        try:
            out.extend(crawl_site(site, client=client, limit=limit))
        except Exception as exc:  # failure isolation: one site must not stop the pass
            LOG.warning("manufacturer site %s failed: %s", site.get("id"), exc)
    return out


def registered_sites() -> list[dict[str, Any]]:
    return list(load_registry().get("manufacturer_sites", []))
