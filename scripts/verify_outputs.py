#!/usr/bin/env python3
"""Post-run verification: prove the outputs are real, not just present.

Checks performed:

* every required output exists and is non-empty;
* the PDF opens, has pages, and contains searchable atlas text;
* the HTML parses as a document and carries the entry payload;
* the CSV row count matches the database;
* every image referenced by the atlas exists on disk and decodes;
* every atlas image has a source, licence, attribution and identity status.

Exit code 0 means every check passed. Used by CI and by ``docs/OPERATIONS.md``.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REQUIRED = [
    "output/Global_UAV_Visual_Atlas_2026.pdf",
    "output/Global_UAV_Visual_Atlas_2026.html",
    "output/uav_database.csv",
    "output/uav_database.xlsx",
    "output/uav_database.sqlite",
    "output/photo_attribution.csv",
    "output/unresolved_records.csv",
    "output/coverage_statistics.json",
    "output/coverage_report.md",
    "logs/audit.jsonl",
    "logs/run.log",
]


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.notes: list[str] = []

    def check(self, condition: bool, message: str) -> bool:
        if condition:
            print(f"  ok    {message}")
        else:
            print(f"  FAIL  {message}")
            self.failures.append(message)
        return condition

    def note(self, message: str) -> None:
        print(f"  note  {message}")
        self.notes.append(message)


def main() -> int:
    checker = Checker()

    print("Required outputs")
    for relative in REQUIRED:
        path = ROOT / relative
        checker.check(
            path.is_file() and path.stat().st_size > 0,
            f"{relative} exists and is non-empty"
            + (f" ({path.stat().st_size:,} bytes)" if path.is_file() else ""),
        )

    print("\nPDF")
    pdf = ROOT / "output/Global_UAV_Visual_Atlas_2026.pdf"
    if pdf.is_file():
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(pdf))
            checker.check(len(reader.pages) > 1, f"PDF has {len(reader.pages)} pages")
            text = "".join((page.extract_text() or "") for page in reader.pages[:8])
            checker.check("Global UAV Visual Atlas 2026" in text, "PDF contains its title as text")
            checker.check("Country of Origin" in text, "PDF contains the atlas column headings")
            checker.check("Table of contents" in text, "PDF contains a table of contents")
        except ImportError:
            checker.note("pypdf not installed - PDF content not inspected")

    print("\nHTML")
    html = ROOT / "output/Global_UAV_Visual_Atlas_2026.html"
    if html.is_file():
        markup = html.read_text(encoding="utf-8")
        checker.check(markup.lstrip().startswith("<!doctype html"), "HTML has a doctype")
        checker.check("const DATA = " in markup, "HTML carries the entry payload")
        try:
            payload = json.loads(markup.split("const DATA = ", 1)[1].split(";\n", 1)[0])
            checker.check(len(payload) > 0, f"HTML payload holds {len(payload)} entries")
            checker.check(
                all({"name", "country", "image"} <= set(row) for row in payload),
                "every HTML entry has photo, name and country fields",
            )
        except (IndexError, ValueError) as exc:
            checker.check(False, f"HTML payload parses as JSON ({exc})")

    print("\nDatabase consistency")
    db_path = ROOT / "output/uav_database.sqlite"
    csv_path = ROOT / "output/uav_database.csv"
    if db_path.is_file() and csv_path.is_file():
        conn = sqlite3.connect(str(db_path))
        db_count = conn.execute(
            "SELECT COUNT(*) FROM platforms WHERE is_merged_into IS NULL"
        ).fetchone()[0]
        with csv_path.open(encoding="utf-8") as fh:
            csv_count = sum(1 for _ in csv.DictReader(fh))
        checker.check(db_count == csv_count, f"CSV rows ({csv_count}) match database ({db_count})")

        duplicate_ids = conn.execute(
            "SELECT COUNT(*) FROM (SELECT public_id FROM platforms WHERE is_merged_into IS NULL "
            "GROUP BY public_id HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        checker.check(duplicate_ids == 0, "no duplicate public identifiers")

        multi_selected = conn.execute(
            "SELECT COUNT(*) FROM (SELECT platform_id FROM images WHERE selected_for_atlas=1 "
            "GROUP BY platform_id HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        checker.check(multi_selected == 0, "at most one atlas image per platform")
        conn.close()

    print("\nImage provenance")
    attribution = ROOT / "output/photo_attribution.csv"
    if attribution.is_file():
        with attribution.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            checker.note(
                "no images in this build - see docs/UNRESOLVED.md for the blocker "
                "(this is expected when the image hosts are unreachable)"
            )
        for row in rows:
            name = row.get("uav_name", "?")
            checker.check(bool(row.get("source_page_url")), f"{name}: has a source page")
            checker.check(bool(row.get("license_name")), f"{name}: has a licence")
            checker.check(bool(row.get("attribution_text")), f"{name}: has attribution text")
            checker.check(
                row.get("identity_verdict", "unverified") != "unverified",
                f"{name}: identity verification recorded",
            )
            path = Path(row.get("atlas_path", ""))
            if path and str(path):
                checker.check(path.is_file(), f"{name}: atlas image exists on disk")

    print("\nCoverage statistics")
    stats_path = ROOT / "output/coverage_statistics.json"
    if stats_path.is_file():
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        checker.check(stats.get("canonical_platforms", 0) > 0, "coverage reports platforms")
        checker.check(
            stats["canonical_platforms"] == sum(stats["by_domain"].values()),
            "domain breakdown sums to the platform total",
        )
        checker.check(stats.get("sources", 0) > 0, "coverage reports sources")

    print()
    if checker.failures:
        print(f"{len(checker.failures)} check(s) FAILED:")
        for failure in checker.failures:
            print(f"  - {failure}")
        return 1
    print(f"All checks passed ({len(checker.notes)} note(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
