"""Open catalogue crawler (tier 3): community datasets and encyclopedia indexes.

Two capabilities live here:

``crawl_dataset``       fetch a registry-declared CSV/JSON dataset and project it
                        onto :class:`~app.models.RawDiscovery` objects.
``crawl_mediawiki_list`` pull the link list out of a MediaWiki "List of ..." page
                        and treat each blue link as a *lead* only.

Nothing here is authoritative.  Records sourced solely from this module stay at
``Needs Verification`` - that policy is enforced in the metadata agent, not here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.logging import AgentLogger
from app.models import RawDiscovery
from app.utils import clean_text
from crawlers import extract
from crawlers.http import FetchError, HttpClient, get_client

LOG = AgentLogger("crawler.public_sources")

REGISTRY_PATH = get_settings().paths.seed / "source_registry.json"


def load_registry(path: Path | None = None) -> dict[str, Any]:
    target = path or REGISTRY_PATH
    if not target.is_file():
        LOG.warning("source registry missing at %s", target)
        return {"sources": [], "manufacturer_sites": [], "government_sources": []}
    return json.loads(target.read_text(encoding="utf-8"))


def sources_for_crawler(name: str, registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    reg = registry if registry is not None else load_registry()
    return [
        s
        for s in reg.get("sources", [])
        if s.get("crawler") == name and s.get("enabled", True)
    ]


# ---------------------------------------------------------------------------
# Declarative dataset crawling
# ---------------------------------------------------------------------------


def crawl_dataset(
    source: dict[str, Any],
    *,
    client: HttpClient | None = None,
    limit: int | None = None,
) -> list[RawDiscovery]:
    """Fetch one registry source and return raw discoveries.

    Raises :class:`~crawlers.http.FetchError` on network/policy failure so the
    discovery agent can isolate the failure to this source alone.
    """
    http = client or get_client()
    fmt = source.get("format", "csv")
    url = source["url"]
    title = source.get("title", source.get("id", url))

    response = http.get(url)
    records: list[dict[str, Any]]
    if fmt == "csv":
        records = list(extract.parse_csv(response.text))
    elif fmt == "json":
        records = extract.parse_json_records(response.text, source.get("record_path", ""))
    elif fmt == "html_table":
        tables = extract.parse_html_tables(response.text)
        records = []
        for table in tables:
            records.extend(extract.table_to_dicts(table))
    else:
        raise FetchError(f"unsupported format {fmt!r} for source {title}", retryable=False)

    if limit is not None:
        records = records[:limit]

    field_map = source.get("field_map", {})
    defaults = source.get("defaults", {})
    discoveries: list[RawDiscovery] = []
    for record in records:
        mapped = extract.map_fields(record, field_map) if field_map else {
            k: clean_text(v) for k, v in record.items()
        }
        model = mapped.get("model", "")
        manufacturer = mapped.get("manufacturer", "")
        name = extract.join_name(manufacturer, model)
        if not name or len(name) < 2:
            continue
        payload = {k: v for k, v in mapped.items() if v}
        payload["_raw"] = {k: v for k, v in record.items() if v not in ("", None)}
        discoveries.append(
            RawDiscovery(
                raw_name=name,
                source_dataset=title,
                source_url=source.get("landing_page") or url,
                external_ref=str(record.get("id") or record.get("uuid") or ""),
                raw_country=mapped.get("country", ""),
                raw_manufacturer=manufacturer,
                domain=mapped.get("domain") or defaults.get("domain", ""),
                category=mapped.get("category") or defaults.get("category", ""),
                status=mapped.get("status", ""),
                payload=payload,
            )
        )
    LOG.info("%s -> %d candidate records", title, len(discoveries))
    return discoveries


# ---------------------------------------------------------------------------
# MediaWiki list pages (discovery leads only)
# ---------------------------------------------------------------------------

_API_TIMEOUT_PARAMS = {"format": "json", "formatversion": "2"}

#: Wiki links that are never a platform.
_LINK_BLOCKLIST = re.compile(
    r"^(list of|category:|file:|template:|help:|portal:|wikipedia:|talk:|special:|"
    r"united states|china|russia|see also|references|external links)",
    re.IGNORECASE,
)


def crawl_mediawiki_list(
    source: dict[str, Any],
    *,
    client: HttpClient | None = None,
    limit: int | None = None,
) -> list[RawDiscovery]:
    """Extract candidate platform names from MediaWiki list articles."""
    http = client or get_client()
    api = source["url"]
    title = source.get("title", source.get("id", api))
    discoveries: list[RawDiscovery] = []

    for page in source.get("pages", []):
        params = {
            **_API_TIMEOUT_PARAMS,
            "action": "parse",
            "page": page,
            "prop": "links",
            "redirects": "1",
        }
        try:
            document = http.get_json(api, params=params)
        except FetchError as exc:
            LOG.warning("mediawiki list %s unavailable: %s", page, exc)
            raise

        links = extract.json_path(document, "parse.links") or []
        for link in links:
            if not isinstance(link, dict):
                continue
            if link.get("ns") != 0 or not link.get("exists"):
                continue
            name = clean_text(link.get("title", ""))
            if not name or _LINK_BLOCKLIST.match(name):
                continue
            if len(name) < 3 or len(name) > 80:
                continue
            discoveries.append(
                RawDiscovery(
                    raw_name=name,
                    source_dataset=title,
                    source_url=f"https://en.wikipedia.org/wiki/{name.replace(' ', '_')}",
                    external_ref=page,
                    payload={"list_page": page, "lead_only": True},
                )
            )
            if limit is not None and len(discoveries) >= limit:
                return discoveries
    LOG.info("%s -> %d leads", title, len(discoveries))
    return discoveries


def crawl(
    source: dict[str, Any],
    *,
    client: HttpClient | None = None,
    limit: int | None = None,
) -> list[RawDiscovery]:
    """Dispatch on the declared format."""
    if source.get("format") == "mediawiki_list":
        return crawl_mediawiki_list(source, client=client, limit=limit)
    return crawl_dataset(source, client=client, limit=limit)
