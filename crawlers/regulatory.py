"""Tier-1 civil-aviation regulator crawler (EASA, FAA and equivalents).

Regulatory registers are the best available *completeness* source for the
civilian side of the atlas: a class-marked or Remote-ID-declared product is,
by construction, a real product that a real company placed on a real market.

They are weak on country of origin - the declared address is the manufacturer's
registered seat, not necessarily the design origin - so every discovery from
here carries ``origin_is_registration_only`` and the country classifier refuses
to treat it as design origin evidence on its own.
"""

from __future__ import annotations

from typing import Any

from app.logging import AgentLogger
from app.models import RawDiscovery
from app.utils import clean_text
from crawlers import extract
from crawlers.http import FetchError, HttpClient, get_client
from crawlers.public_sources import load_registry, sources_for_crawler

LOG = AgentLogger("crawler.regulatory")


def crawl_register(
    source: dict[str, Any],
    *,
    client: HttpClient | None = None,
    limit: int | None = None,
) -> list[RawDiscovery]:
    """Fetch and project one regulatory register."""
    http = client or get_client()
    url = source["url"]
    title = source.get("title", url)
    fmt = source.get("format", "html_table")

    response = http.get(url)

    records: list[dict[str, Any]]
    if fmt == "json":
        records = extract.parse_json_records(response.text, source.get("record_path", ""))
    elif fmt == "csv":
        records = list(extract.parse_csv(response.text))
    elif fmt == "html_table":
        records = []
        for table in extract.parse_html_tables(response.text):
            records.extend(extract.table_to_dicts(table))
    else:
        raise FetchError(f"unsupported regulatory format {fmt!r}", retryable=False)

    if limit is not None:
        records = records[:limit]

    field_map = source.get("field_map", {})
    defaults = source.get("defaults", {})
    out: list[RawDiscovery] = []
    for record in records:
        mapped = extract.map_fields(record, field_map)
        name = extract.join_name(mapped.get("manufacturer", ""), mapped.get("model", ""))
        if not name or len(name) < 2:
            continue
        out.append(
            RawDiscovery(
                raw_name=name,
                source_dataset=title,
                source_url=source.get("landing_page") or url,
                external_ref=clean_text(record.get("id") or record.get("docId") or ""),
                raw_country="",  # deliberately blank: registration != design origin
                raw_manufacturer=mapped.get("manufacturer", ""),
                domain=defaults.get("domain", "Civilian / Commercial"),
                category=mapped.get("class_mark") or defaults.get("category", ""),
                status=mapped.get("status", ""),
                payload={
                    "origin_is_registration_only": True,
                    "registered_country": clean_text(
                        record.get("country") or record.get("countryName") or ""
                    ),
                    "class_mark": mapped.get("class_mark", ""),
                    "credibility_tier": source.get("credibility_tier", 1),
                },
            )
        )
    LOG.info("%s -> %d register entries", title, len(out))
    return out


def crawl_all(
    *,
    client: HttpClient | None = None,
    limit: int | None = None,
) -> list[RawDiscovery]:
    out: list[RawDiscovery] = []
    for source in sources_for_crawler("regulatory", load_registry()):
        try:
            out.extend(crawl_register(source, client=client, limit=limit))
        except Exception as exc:  # failure isolation
            LOG.warning("regulatory source %s failed: %s", source.get("id"), exc)
    return out


def registered_sources() -> list[dict[str, Any]]:
    return sources_for_crawler("regulatory", load_registry())
