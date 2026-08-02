#!/usr/bin/env python3
"""Generate a ready-to-fill sideload manifest for every platform without an image.

Produces ``data/imports/images/manifest.csv`` with one row per platform that
still needs a photograph, pre-populated with the platform name, its country and
manufacturer (as search context) and a Wikimedia Commons media-search URL.

The licence-bearing columns are left blank on purpose: they are what makes an
image usable, and they must be copied from the file's own source page rather
than guessed. `python run.py --sideload-images` rejects any row whose
``license_name`` or ``source_page_url`` is empty.

Usage
-----
    python scripts/prepare_image_manifest.py                  # all platforms without an image
    python scripts/prepare_image_manifest.py --country India
    python scripts/prepare_image_manifest.py --domain Military --limit 50
    python scripts/prepare_image_manifest.py --verified-only  # highest-confidence records first
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.db import connect, migrate, query  # noqa: E402
from crawlers.wikimedia import media_search_url  # noqa: E402

COLUMNS = [
    # Filled in for you:
    "platform_name",
    "country_of_origin",
    "manufacturer",
    "commons_search_url",
    # Fill these in yourself - the pipeline rejects the row without them:
    "file",
    "source_url",
    "source_page_url",
    "photographer",
    "license_name",
    "license_url",
]

SQL = """
SELECT p.canonical_name,
       COALESCE(c.name, 'Unknown')  AS country,
       COALESCE(m.name, '')         AS manufacturer,
       p.domain                     AS domain,
       p.verification_status        AS verification_status,
       p.confidence_score           AS confidence_score
FROM platforms p
LEFT JOIN countries c     ON c.id = p.country_id
LEFT JOIN manufacturers m ON m.id = p.manufacturer_id
WHERE p.is_merged_into IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM images i
      WHERE i.platform_id = p.id AND i.selected_for_atlas = 1
  )
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--country", help="restrict to one country of origin")
    parser.add_argument("--domain", help="restrict to one domain, e.g. Military")
    parser.add_argument("--manufacturer", help="restrict to one manufacturer")
    parser.add_argument("--limit", type=int, help="cap the number of rows")
    parser.add_argument(
        "--verified-only",
        action="store_true",
        help="only platforms already Verified or Probable (best use of sourcing effort)",
    )
    parser.add_argument("--output", type=Path, help="destination CSV (default data/imports/images/manifest.csv)")
    args = parser.parse_args(argv)

    settings = get_settings()
    conn = connect()
    migrate(conn)

    sql = SQL
    params: list[object] = []
    if args.country:
        sql += " AND c.name = ?"
        params.append(args.country)
    if args.domain:
        sql += " AND p.domain = ?"
        params.append(args.domain)
    if args.manufacturer:
        sql += " AND m.name LIKE ?"
        params.append(f"%{args.manufacturer}%")
    if args.verified_only:
        sql += " AND p.verification_status IN ('Verified', 'Probable')"
    sql += " ORDER BY p.confidence_score DESC, c.name, p.canonical_name"
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"

    rows = query(sql, params, conn)

    destination = args.output or (settings.paths.imports / "images" / "manifest.csv")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "platform_name": row["canonical_name"],
                    "country_of_origin": row["country"],
                    "manufacturer": row["manufacturer"],
                    "commons_search_url": media_search_url(row["canonical_name"]),
                    "file": "",
                    "source_url": "",
                    "source_page_url": "",
                    "photographer": "",
                    "license_name": "",
                    "license_url": "",
                }
            )

    print(f"wrote {len(rows)} row(s) to {destination}")
    print()
    print("Next steps:")
    print(f"  1. Put image files next to the manifest, in {destination.parent}")
    print("  2. Fill in file, source_url, source_page_url, photographer, license_name, license_url")
    print("     (copy them from the file's own source page - the pipeline rejects blanks)")
    print("  3. python run.py --sideload-images")
    print("  4. python run.py --build --export")
    return 0


if __name__ == "__main__":
    sys.exit(main())
