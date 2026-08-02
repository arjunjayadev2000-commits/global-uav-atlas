# Progress

Running record of what was built, run and measured. Numbers are from actual
executions, not estimates.

---

## Phase 0 — Repository inspection and environment survey

**Status: complete.**

The repository was empty apart from `.git` (no commits). The uploaded
`Global_UAV_Database_2026_Package.zip` was extracted to `data/imports/extracted/`
and inspected:

| Asset | Contents |
| --- | --- |
| `Global_UAV_Database_2026.csv` | 591 canonical records, 31 columns |
| `Global_UAV_Database_2026_Source_Records.csv` | 647 source records, 29 columns |
| `Global_UAV_Database_2026.sqlite` | `platforms` (591), `source_records` (647), `sources` (4) |
| `Global_UAV_Database_2026.xlsx` | Same data in workbook form |
| `README.txt` | Coverage summary, scope limit, dataset provenance |

Seed composition: 56 country values, 175 manufacturers, 256 military / 307
civilian / 28 dual-use, 3 unknown-origin, **0 photo URLs**. Its four underlying
datasets (Curated UAV Seed 2026, OpenDroneList, EASA Drones for EU Operations,
Bard Drone Databook 2019) were recorded with their descriptions and stated
limitations.

**Network survey — the finding that shaped the build.** The environment's egress
policy permits only GitHub and PyPI. Every other host returns HTTP 403 at the
proxy:

| Host | Result |
| --- | --- |
| `raw.githubusercontent.com` | reachable |
| `commons.wikimedia.org`, `upload.wikimedia.org`, `en.wikipedia.org` | 403 |
| `www.easa.europa.eu`, `uasdoc.faa.gov` | 403 |
| `*.mil`, `defense.gov`, `nasa.gov`, `dvidshub.net`, `archive.org` | 403 |
| all six manufacturer sites, all three government sources | 403 |

This is an organisation policy decision, not a transient failure, so it is
reported rather than routed around. It has one hard consequence — no image bytes
could be retrieved — and one useful one: OpenDroneList is GitHub-hosted, so live
discovery was genuinely exercised rather than simulated.

---

## Phase 1 — Schema, migrations, seed import

**Status: complete.**

**Files:** `app/{__init__,config,logging,utils,schemas,db,models}.py`,
`data/seed/source_registry.json`.

Three forward-only migrations create 19 tables covering all 13 required by the
specification plus `platform_families`, `raw_discoveries`, `merge_decisions`,
`pipeline_state`, `url_ledger`, `schema_migrations` and the `v_atlas_entries`
view. DDL stays inside the SQLite∩PostgreSQL subset.

`app/utils.py` carries the primitives everything else depends on: name
normalisation (accent folding, punctuation stripping, noise-word removal, roman
numeral expansion), a 130-entry country canonicalisation table with alias
resolution and multinational handling, blended name similarity, model-code
extraction, traversal-safe path joining, hashing, rate limiting and exponential
backoff.

**Run:** seed import produced **1,394 raw discoveries** across both layers
(source-record and canonical), registered 5 sources, and is idempotent — a second
import inserts 0 rows.

---

## Phase 2 — Crawlers, discovery, deduplication, metadata

**Status: complete.**

**Files:** `crawlers/{http,extract,public_sources,wikimedia,manufacturer,government,regulatory}.py`,
`agents/{discovery,metadata,deduplication,country_classifier,source_verification}_agent.py`.

`crawlers/http.py` enforces per-host rate limiting, a descriptive user agent,
`robots.txt`, a TTL disk cache, hard timeouts, a size ceiling, atomic downloads
and exponential backoff — and distinguishes transient failures from policy
refusals. That distinction was added after the first full run spent minutes
retrying blocked hosts 4× each: policy refusals are now remembered per host and
fail fast. Run time dropped from 8 minutes to 8 seconds.

Sources are declarative (`data/seed/source_registry.json`), so adding one is a
data change.

**Defects found and fixed in this phase:**

1. *Bad auto-merges.* `DJI MAVIC 3 Cine V2.0` merged into `DJI MAVIC 3 V2.0`;
   `Delair UX11 … Caméra AG` merged into `… Caméra IR`. Character similarity
   above 0.94 cannot tell a spelling variation from a different product.
   Replaced with token-set analysis: identical tokens modulo a manufacturer
   prefix → merge; strict superset with a model-code asymmetry → review; anything
   else → distinct. Merges went 11 → 156 (all correct), reviews 75 → 7.
2. *Duplicate review items.* Reviews were queued against records merged away
   moments later, filing the same ambiguity under several names. Deduplication
   now merges in one sweep and reviews survivors in a second: 37 → 7 items.
3. *`air` treated as a noise word*, collapsing `DJI Air 3` to `{3}` and matching
   it against half the catalogue. Removed from the noise list.
4. *PDF-extraction hyphenation* from the Bard Databook (`Northrop Grum- man`)
   repaired in `clean_text`, guarded so real designations (`MQ- 9`) are untouched.
5. *Name duplication* — `DJI GmbH` + `DJI Matrice 400` → `DJI GmbH DJI Matrice
   400`. Fixed in `join_name`.
6. *Aggregator inflation.* The seed package was counted as an independent source
   alongside the datasets it republishes, pushing 340 records to *Verified* on
   what is really one observation. Added `sources.is_aggregator`; verification and
   origin classification now exclude republishers from independence counts.
   Verified 342 → 52. A worse-looking number and a true one.

**Run:** 1,394 raw → 749 promoted → 156 merged → **593 canonical platforms**.

---

## Phase 3–4 — Image pipeline, vision verification, unresolved queue

**Status: code complete; acquisition blocked by egress policy.**

**Files:** `agents/{image_discovery,image_license,image_validation,vision_verification}_agent.py`.

Licence screening accepts CC0, public domain, CC BY, CC BY-SA, plain
Attribution and US government works; rejects all-rights-reserved, fair-use,
NonCommercial (configurable), NoDerivatives, and anything without a licence or a
source page. Validation decodes the bytes (catching truncated files that pass a
header check), enforces ≥500 px width and aspect sanity, and computes SHA-256
plus a perceptual hash so one photograph cannot serve two platforms. Derivatives:
atlas, thumbnail, optional WebP.

Identity gates the candidate score *before* download — a perfectly licensed,
high-resolution photograph of the wrong aircraft scores 0.17, not 0.61 (fixed
after a test caught the original weighting). Vision verification runs when
`ANTHROPIC_API_KEY` is present and degrades to metadata verification when it is
not, flagging low-confidence images rather than stopping.

**Run:** 3 platforms attempted, 3 refused by egress policy, then the circuit
breaker stopped the pass and filed one `pipeline_blocker` item rather than
repeating the same failure 593 times. The three platforms reached before the
breaker tripped carry individual `image_missing` items with their Commons
media-search URLs; the remaining 590 are represented by the blocker item and by
`platforms_without_image: 593` in the coverage statistics.

`--sideload-images` provides the offline path; it applies the same licence,
validation, duplicate and identity rules.

---

## Phase 5 — Exports and atlas generation

**Status: complete.**

**Files:** `agents/{export,atlas_builder,update}_agent.py`, `agents/orchestrator.py`, `run.py`.

The PDF is built with ReportLab: each entry row is its own flowable, so nothing
is ever clipped and exact page numbers can be captured for the indexes. Cover,
table of contents, entries grouped by section then country, unverified appendix,
country index with compressed page ranges, alphabetical index, photo attribution
appendix, coverage statistics.

The HTML edition is self-contained, responsive, theme-aware, with live search,
sortable columns, four filters and lazy-loaded images.

**Defect fixed:** the first PDF build failed with *"format not resolved …
undefined destination target"* — table-of-contents entries emitted internal
links without matching bookmarks. Switched to the 3-tuple `TOCEntry` page-
reference form.

**Run:** 104-page PDF (154 KB), HTML with 593 entries, plus CSV, XLSX (8 sheets),
SQLite, attribution, unresolved and coverage outputs.

---

## Phase 6 — Docker, CI, tests, documentation

**Status: complete.**

**Files:** `Dockerfile`, `docker-compose.yml`, `.github/workflows/{tests,lint,weekly-discovery,weekly-atlas-rebuild}.yml`,
`tests/{conftest,test_normalization,test_deduplication,test_database,test_crawlers,test_images,test_pipeline,test_agents}.py`,
`scripts/{backup_database.sh,verify_outputs.py}`, `docs/*`.

**207 tests, all passing, 82 % statement coverage.** They found six real defects
(listed above), which is the point of writing them. Coverage:

| Area | Tests |
| --- | --- |
| Normalisation, countries, path safety | 40 |
| Deduplication (mostly "must not merge") | 16 |
| Migrations, upserts, history, resume state | 19 |
| Source parsing, HTTP policy, network failure | 28 |
| Image licence, validation, duplicates, derivatives | 35 |
| End-to-end pipeline, atlas, exports, resume | 43 |
| Image acquisition, vision, sideload, update | 26 |

`ruff check .` clean; `mypy app agents crawlers run.py` clean across 30 files.

CI: tests on every push (3.11 and 3.12) plus an offline build smoke test that
asserts the PDF opens and contains atlas text; lint and type checks with a
credential scan; weekly discovery and weekly atlas rebuild with state caching and
artifact upload. `docker compose up --build` runs the whole pipeline with a
healthcheck and persistent volumes.

---

## Phases 7–9 — Pilot, full run, final outputs

**Status: complete.**

Pilot (25 records) surfaced the retry-storm, TOC and merge defects. After fixes,
the full run was executed end to end four times as defects were corrected; the
final run:

| Metric | Value |
| --- | ---: |
| Canonical platforms | 593 |
| Duplicates merged | 156 |
| Raw source records | 1,394 |
| Manufacturers | 173 |
| Countries represented | 45 (+ Multinational, + Unknown) |
| Aliases · families · variants | 560 · 7 · 14 |
| Sources · platform↔source links | 18 · 1,557 |
| Field-change history entries | 471 |
| Audit events | 247 |
| Open unresolved items | 27 |
| Duplicate review rate | 1.18 % |

Domains: 310 civilian/commercial · 254 military · 29 dual-use.
Verification: 52 Verified · 425 Probable · 116 Needs Verification.
Origin confidence: High 186 · Medium 402 · None 4.

**Discovery converged** — three consecutive passes with zero new candidates.

### Stop conditions

| Condition | Met |
| --- | --- |
| Pipeline ran end to end | yes |
| Database and outputs generated | yes |
| Discovery converged (3 empty passes) | yes |
| Unresolved records documented | yes |
| Every atlas image fully documented | yes (vacuously — there are none) |
| **Atlas contains real images** | **no — egress policy blocks every image host** |
| Duplicates below threshold (1.18 % ≤ 2 %) | yes |
| PDF present and opens | yes (104 pages, searchable) |
| HTML present and loads | yes (593 entries) |
| Coverage statistics generated | yes |

Nine of ten. The tenth is a documented environmental blocker, not an
implementation gap: the image pipeline is complete and tested, and both recovery
paths (`--images` from a permitted network, `--sideload-images` from local files)
are implemented and covered by tests.

### Coverage against the original targets

| Target | Actual | Assessment |
| --- | --- | --- |
| 350–500 military UAVs | 254 | Below target. The seed contributes 256 military records; the tier‑1/2 sources that would extend this (defence ministries, IISS, SIPRI, manufacturer sites) were all unreachable. |
| 250–400 civilian/commercial | 310 | **Met.** |
| 600–900+ total platforms | 593 | Just below. Reachable sources are exhausted — discovery converged. |
| 120+ countries | 45 | Below target, and the seed's own ceiling was 56. Adding countries requires national programme sources, all of which were blocked. |
| 200+ manufacturers | 173 | Below target; same cause. |

These gaps are single-caused and stated plainly rather than papered over: the
registry is as large as the *reachable* sources support. Running the same
pipeline where the configured tier‑1 and tier‑2 sources are permitted is the
direct remedy, and requires no code change.

### Remaining unresolved items (27)

| Type | Count | Blocker |
| --- | ---: | --- |
| `source_unreachable` | 12 | Network egress policy (named host per item) |
| `possible_duplicate` | 7 | Genuine ambiguity — V2 revisions and `RQ-20 Puma (AE)` / `Puma AE` |
| `country_of_origin` | 4 | No design-origin evidence in any reachable source |
| `image_missing` | 3 | Image provider unreachable |
| `pipeline_blocker` | 1 | Image acquisition unavailable in this environment |

Full detail in `docs/UNRESOLVED.md` and `output/unresolved_records.csv`.

---

## Next steps

1. Re-run `python run.py --all --resume` where the configured tier‑1/2 sources
   and `commons.wikimedia.org` are reachable. This is the single change that
   moves every remaining metric.
2. Set `ANTHROPIC_API_KEY` to enable vision verification of image identity.
3. Adjudicate the 7 duplicate reviews (SQL in `docs/OPERATIONS.md`).
4. Resolve the 4 unknown origins against manufacturer or ministry pages.
