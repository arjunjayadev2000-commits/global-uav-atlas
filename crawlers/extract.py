"""Dependency-free extraction helpers shared by the crawlers.

Sources arrive in three shapes and each has a declarative extractor here:

``csv``   delimited text with a column map
``json``  a JSON document plus a dotted record path and a field map
``html``  HTML tables / definition lists parsed with :mod:`html.parser`

Keeping the extractors declarative means a new source is a data change (an entry
in ``data/seed/source_registry.json``) rather than a code change.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable
from html.parser import HTMLParser
from typing import Any

from app.utils import clean_text

# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def parse_csv(text: str, *, delimiter: str = ",") -> list[dict[str, str]]:
    """Parse delimited text into dicts, tolerating a UTF-8 BOM."""
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows: list[dict[str, str]] = []
    for row in reader:
        rows.append({(k or "").strip(): clean_text(v) for k, v in row.items() if k is not None})
    return rows


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def json_path(document: Any, path: str) -> Any:
    """Resolve a dotted path such as ``data.items`` (``[]`` walks a list)."""
    current = document
    if not path:
        return current
    for part in path.split("."):
        if part == "[]":
            if isinstance(current, list):
                continue
            return []
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def parse_json_records(text: str, record_path: str = "") -> list[dict[str, Any]]:
    document = json.loads(text)
    records = json_path(document, record_path)
    if isinstance(records, dict):
        records = list(records.values())
    if not isinstance(records, list):
        return []
    return [r for r in records if isinstance(r, dict)]


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


class _TableParser(HTMLParser):
    """Collect every ``<table>`` on a page as a list of row-cell lists."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(clean_text("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(c for c in self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table":
            if self._depth == 1 and self._table is not None:
                self.tables.append(self._table)
                self._table = None
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def parse_html_tables(html: str) -> list[list[list[str]]]:
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    return parser.tables


def table_to_dicts(table: list[list[str]]) -> list[dict[str, str]]:
    """Treat the first row as the header row."""
    if len(table) < 2:
        return []
    header = [clean_text(h).lower() for h in table[0]]
    out: list[dict[str, str]] = []
    for row in table[1:]:
        if not row:
            continue
        record = {header[i]: clean_text(row[i]) for i in range(min(len(header), len(row)))}
        if any(record.values()):
            out.append(record)
    return out


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, clean_text("".join(self._text))))
            self._href = None
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)


def parse_links(html: str) -> list[tuple[str, str]]:
    parser = _LinkParser()
    parser.feed(html)
    parser.close()
    return parser.links


_TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(html: str) -> str:
    return clean_text(_TAG_RE.sub(" ", html))


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------


def map_fields(record: dict[str, Any], field_map: dict[str, str | list[str]]) -> dict[str, str]:
    """Project a source record onto our vocabulary.

    ``field_map`` maps *our* field name to one source key or a list of
    candidates tried in order.  A value of the form ``"const:Military"`` injects
    a literal.
    """
    lowered = {str(k).strip().lower(): v for k, v in record.items()}
    out: dict[str, str] = {}
    for target, spec in field_map.items():
        candidates: Iterable[str] = [spec] if isinstance(spec, str) else spec
        value = ""
        for candidate in candidates:
            if candidate.startswith("const:"):
                value = candidate.split(":", 1)[1]
                break
            got = lowered.get(candidate.strip().lower())
            if got not in (None, ""):
                value = clean_text(got)
                break
        out[target] = value
    return out


def join_name(manufacturer: str, model: str) -> str:
    """Build a display name, avoiding ``DJI DJI Mavic 3``-style duplication."""
    manufacturer = clean_text(manufacturer)
    model = clean_text(model)
    if not manufacturer:
        return model
    if not model:
        return manufacturer
    if model.lower().startswith(manufacturer.lower()):
        return model
    # "DJI GmbH" + "DJI Matrice 400" must not become "DJI GmbH DJI Matrice 400".
    manufacturer_head = manufacturer.split()[0].lower()
    if model.split()[0].lower() == manufacturer_head:
        return model
    return f"{manufacturer} {model}"
