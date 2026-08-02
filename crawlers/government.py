"""Tier-1 government / armed-forces / programme-office crawler.

Government pages are used for two purposes:

* **corroboration** - confirming that a platform named by a tier-3 source is a
  real programme, which is what lets a record move off ``Needs Verification``;
* **origin evidence** - a defence ministry describing a system as indigenous is
  strong evidence for country of origin.

The crawler harvests candidate designations from an official index page and
always attaches the publishing government as the origin *hint* - never as a
decided fact.  The country classifier makes that decision separately.
"""

from __future__ import annotations

from typing import Any

from app.logging import AgentLogger
from app.models import RawDiscovery
from app.utils import clean_text
from crawlers import extract
from crawlers.http import HttpClient, get_client
from crawlers.manufacturer import looks_like_platform_name
from crawlers.public_sources import load_registry

LOG = AgentLogger("crawler.government")


def crawl_source(
    source: dict[str, Any],
    *,
    client: HttpClient | None = None,
    limit: int | None = None,
) -> list[RawDiscovery]:
    http = client or get_client()
    url = source["url"]
    title = source.get("title", url)
    country = source.get("country", "")

    response = http.get(url)

    discoveries: list[RawDiscovery] = []
    seen: set[str] = set()

    # Tables first (programme lists are usually tabular), then links.
    for table in extract.parse_html_tables(response.text):
        for record in extract.table_to_dicts(table):
            name = ""
            for key in ("system", "platform", "aircraft", "name", "designation", "type"):
                if record.get(key):
                    name = record[key]
                    break
            if not looks_like_platform_name(name) or name.lower() in seen:
                continue
            seen.add(name.lower())
            discoveries.append(
                RawDiscovery(
                    raw_name=clean_text(name),
                    source_dataset=title,
                    source_url=url,
                    external_ref=source.get("id", ""),
                    raw_country=country,
                    raw_manufacturer=clean_text(
                        record.get("manufacturer") or record.get("contractor") or ""
                    ),
                    domain="Military",
                    status=clean_text(record.get("status", "")),
                    payload={
                        "origin_hint_only": True,
                        "credibility_tier": source.get("credibility_tier", 1),
                        "row": record,
                    },
                )
            )

    if not discoveries:
        for href, text in extract.parse_links(response.text):
            name = clean_text(text)
            if not looks_like_platform_name(name) or name.lower() in seen:
                continue
            seen.add(name.lower())
            discoveries.append(
                RawDiscovery(
                    raw_name=name,
                    source_dataset=title,
                    source_url=href if href.startswith("http") else url,
                    external_ref=source.get("id", ""),
                    raw_country=country,
                    domain="Military",
                    payload={
                        "origin_hint_only": True,
                        "needs_review": True,
                        "credibility_tier": source.get("credibility_tier", 1),
                    },
                )
            )
            if limit is not None and len(discoveries) >= limit:
                break

    if limit is not None:
        discoveries = discoveries[:limit]
    LOG.info("%s -> %d candidates", title, len(discoveries))
    return discoveries


def crawl_all(
    *,
    client: HttpClient | None = None,
    country: str | None = None,
    limit: int | None = None,
) -> list[RawDiscovery]:
    registry = load_registry()
    out: list[RawDiscovery] = []
    for source in registry.get("government_sources", []):
        if country and country.lower() not in source.get("country", "").lower():
            continue
        try:
            out.extend(crawl_source(source, client=client, limit=limit))
        except Exception as exc:  # failure isolation
            LOG.warning("government source %s failed: %s", source.get("id"), exc)
    return out


def registered_sources() -> list[dict[str, Any]]:
    return list(load_registry().get("government_sources", []))
