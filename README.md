# Global UAV Visual Atlas 2026

A resumable, auditable pipeline that consolidates military, civilian, commercial,
research, experimental, retired, prototype and cancelled UAV platforms into a
single registry, and renders it as a visual atlas whose entry format is
deliberately simple:

| Photo | UAV Name | Country of Origin |

Everything else — manufacturers, categories, aliases, variants, sources, licences,
verification verdicts — lives in the database for governance and provenance, not
in the atlas table.

> **Scope.** This is the largest defensible consolidated registry generated from
> the configured sources. It is not, and does not claim to be, every drone ever
> built. No authoritative worldwide registry of every UAV, FPV design, one-off
> research airframe, cancelled prototype, local modification, white-label
> commercial model or battlefield-built drone exists.

## Current build

| Metric | Value |
| --- | ---: |
| Canonical platforms | **593** |
| Duplicates merged | 156 |
| Raw source records retained | 1,394 |
| Manufacturers / design organisations | 173 |
| Countries of origin represented | 45 (+ Multinational, + Unknown) |
| Platform families / recorded variants | 7 / 14 |
| Aliases | 560 |
| Sources cited | 18 |
| Platform↔source links | 1,557 |
| Open unresolved items | 27 |
| Duplicate review rate | 1.18 % |
| Atlas images embedded | **0 — image hosts blocked in this environment, see below** |

Domain split: 310 civilian/commercial · 254 military · 29 dual-use.
Verification: 52 Verified · 425 Probable · 116 Needs Verification.

### The one thing that is not finished

Image acquisition could not run here. The build environment's egress policy
permits only GitHub and PyPI; `commons.wikimedia.org`, `upload.wikimedia.org`,
government imagery hosts and every manufacturer site returned **HTTP 403 at the
proxy**. No image bytes were retrievable, so the atlas renders a neutral
"no verified image" tile — never a substitute photograph, never generated
artwork.

The image pipeline itself is complete and tested (licence screening, download,
decode/resolution/aspect validation, SHA-256 and perceptual duplicate detection,
derivative generation, identity verification, full attribution capture). It is
exercised end to end by the test suite against stubbed providers. Two ways to
fill it in:

```bash
# 1. See exactly which hosts your network refuses, and the allowlist to request
python run.py --check-network

# 2a. Once commons.wikimedia.org and upload.wikimedia.org are permitted:
python run.py --images --verify --build --export --resume

# 2b. Or, without changing the network, source the files yourself:
python run.py --prepare-image-manifest   # fill-in CSV, one row per platform,
                                         # pre-filled with Commons search URLs
python run.py --sideload-images
python run.py --build --export
```

`data/imports/images/manifest.csv` is already generated and committed: 593 rows,
each carrying the platform name, country, manufacturer and a Commons media-search
URL, with the licence columns left blank for you to fill from each file's own
source page.

Both paths apply identical licence, resolution, duplicate and identity rules —
there is no route into the atlas that bypasses them.

The image pass stops after three consecutive provider refusals rather than
repeating the same failure 593 times, so `output/unresolved_records.csv` holds
3 per-platform `image_missing` items (each with its Commons media-search URL)
plus one `pipeline_blocker` item covering the rest. The full gap is the
`platforms_without_image: 593` figure in `output/coverage_statistics.json`.

## Quick start

```bash
pip install -r requirements.txt
python run.py --all
```

or

```bash
docker compose up --build
```

Then open `output/Global_UAV_Visual_Atlas_2026.html` or the PDF.

## Outputs

| File | What it is |
| --- | --- |
| `output/Global_UAV_Visual_Atlas_2026.pdf` | 104-page atlas: cover, table of contents, entries by section and country, unverified appendix, country index, alphabetical index, photo attribution appendix, coverage statistics. Searchable text, page numbers, embedded images. |
| `output/Global_UAV_Visual_Atlas_2026.html` | Responsive edition with live search, sortable columns, filters for country / manufacturer / category / domain, lazy-loaded images and attribution links. |
| `output/uav_database.csv` | Canonical records. |
| `output/uav_source_records.csv` | The raw evidence layer, one row per source observation. |
| `output/uav_database.xlsx` | Eight sheets: Summary · UAV Database · Simple Visual Index · Source Records · Images · Sources · Unresolved · Data Dictionary. |
| `output/uav_database.sqlite` | Complete normalised database. |
| `output/photo_attribution.csv` | Per-image licence chain: source URL, source page, photographer, licence, licence URL, attribution text, PD/commercial/modification flags, hashes, identity verdict. |
| `output/unresolved_records.csv` | Everything still open, each with a precise blocker and a suggested action. |
| `output/coverage_statistics.json` · `coverage_report.md` | Coverage, machine- and human-readable. |
| `images/` | Downloaded originals plus atlas/thumbnail/WebP derivatives, organised by country and platform. |
| `logs/audit.jsonl` · `logs/run.log` | Append-only provenance trail and the human log. |

## How it works

```
sources ─► crawlers ─► raw_discoveries ─► metadata ─► dedup ─► country ─► verification
                                                                              │
                              images ─► licence ─► validation ─► vision ──────┤
                                                                              ▼
                                                       atlas builder + export agent
```

Raw evidence is immutable and stored separately from canonical records, so every
row in the atlas is re-derivable from what a source actually said. The pipeline
never guesses: missing country of origin becomes `Unknown` and enters the
unresolved queue; an ambiguous merge becomes a review item, not a merge; an image
without a licence and a source page is rejected.

Three design decisions are worth knowing about before reading the code —
asymmetric deduplication, aggregators that do not corroborate, and design origin
versus registration address. They are explained in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Commands

```bash
python run.py --all                  # full pipeline
python run.py --discover             # seed import + discovery passes + promotion
python run.py --dedupe [--dry-run]   # deduplication
python run.py --images               # image acquisition
python run.py --verify               # source + image identity verification
python run.py --build                # PDF + HTML
python run.py --export               # CSV / XLSX / SQLite / statistics
python run.py --update               # incremental refresh (weekly job)
python run.py --resume               # skip stages already completed
python run.py --limit 25             # cap records per stage
python run.py --country "India"
python run.py --manufacturer "DJI"
python run.py --status | --stats | --stop-conditions [--json]
```

`--json` prints machine-readable results on stdout; diagnostics go to stderr.

## Verification

```bash
pytest -q                      # 207 tests
ruff check .                   # clean
mypy app agents crawlers run.py
python scripts/verify_outputs.py
```

`scripts/verify_outputs.py` proves the outputs are real rather than merely
present: the PDF opens and contains searchable atlas text, the HTML payload
parses, CSV row counts match the database, no platform carries two selected
images, and every atlas image has a source, licence, attribution and identity
status.

`python run.py --stop-conditions` evaluates the project's completion criteria
individually, so a partially blocked environment still gets an honest answer
rather than a single pass/fail.

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layers, the three decisions worth explaining, the image pipeline, resumability, PostgreSQL portability. |
| [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) | Credibility tiers, the seed package, live sources, image licence policy, compliance, and what was reachable in this build. |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Setup, environment variables, partial jobs, restarting, sideloading images, backups, regenerating outputs, troubleshooting. |
| [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) | Every table and column, who sets it, and what it means. |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Phase-by-phase record of what was built, run and measured. |
| [`docs/UNRESOLVED.md`](docs/UNRESOLVED.md) | Open items grouped by type, with blockers and suggested actions (regenerated on every export). |

## Licensing and attribution

Code is MIT. Data records carry the licence terms of their sources, recorded per
record in `sources`. Photographs are reproduced only under licences permitting
redistribution, commercial use and modification (CC0, public domain, CC BY,
CC BY-SA, US government works); NonCommercial and NoDerivatives material is
rejected because the atlas is redistributable and resizes every image. The full
licence chain for every embedded photograph is in
`output/photo_attribution.csv` and reproduced in the PDF's attribution appendix.

Secrets are never committed. `ANTHROPIC_API_KEY` enables optional vision
verification of image identity; without it the pipeline runs on metadata-based
verification and flags low-confidence images for review.
