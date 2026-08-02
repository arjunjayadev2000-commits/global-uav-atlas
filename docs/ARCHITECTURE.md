# Architecture

## The problem this design solves

There is no authoritative worldwide registry of unmanned aircraft. Any global
UAV dataset is therefore a *consolidation* whose value rests entirely on whether
each row can be traced back to evidence. The architecture is built around that
single constraint: **every canonical record must be re-derivable from stored raw
evidence, and every image must carry a defensible reuse basis.**

Two consequences follow, and they shape everything else:

1. **Raw evidence is immutable and separate from canonical records.** Sources
   write into `raw_discoveries` verbatim. Canonicalisation happens downstream and
   can be re-run, corrected and re-run again without losing the original
   observation.
2. **The pipeline never guesses.** Where evidence is absent (country of origin,
   image identity, whether two names are one aircraft) the record is marked,
   queued in `unresolved_items` with a precise blocker, and left for a human.

## Layers

```
                    ┌───────────────────────────────────────────┐
   sources  ──────► │ crawlers/       polite HTTP + extractors   │
                    └───────────────────┬───────────────────────┘
                                        │ RawDiscovery objects
                    ┌───────────────────▼───────────────────────┐
                    │ raw_discoveries   (immutable evidence)     │
                    └───────────────────┬───────────────────────┘
                                        │
   ┌────────────────────────────────────▼──────────────────────────────────┐
   │ agents/                                                               │
   │  metadata → dedup → country classifier → source verification          │
   │  image discovery → licence → validation → vision verification         │
   └────────────────────────────────────┬──────────────────────────────────┘
                                        │
                    ┌───────────────────▼───────────────────────┐
                    │ platforms / images / sources (canonical)   │
                    └───────────────────┬───────────────────────┘
                                        │
                    ┌───────────────────▼───────────────────────┐
                    │ atlas builder + export agent               │
                    │ PDF · HTML · CSV · XLSX · SQLite · stats   │
                    └───────────────────────────────────────────┘
```

### `app/` — foundation

| Module | Responsibility |
| --- | --- |
| `config.py` | Environment-driven settings; secrets only ever come from the environment. |
| `schemas.py` | Forward-only SQL migrations in the SQLite∩PostgreSQL subset. |
| `db.py` | Connections, migrations, upserts, resume state, `update_history` tracking. |
| `models.py` | Transport dataclasses (`RawDiscovery`, `PlatformRecord`, `ImageCandidate`, verdicts) and the controlled vocabularies. |
| `logging.py` | Human log (`logs/run.log`) plus the append-only audit trail (`logs/audit.jsonl`). |
| `utils.py` | Normalisation, country canonicalisation, similarity, hashing, path safety, retry, rate limiting. |

### `crawlers/` — getting data in

`http.py` is the only module that touches the network. It enforces per-host rate
limiting, a descriptive user agent, `robots.txt`, a TTL disk cache, hard
timeouts, a response size ceiling, and exponential backoff — and it distinguishes
*transient* failures (retry) from *policy* refusals (never retry, remember the
host, fail fast). That distinction matters: without it, a blocked egress policy
turns a 30-second run into a 40-minute retry storm.

The other modules are thin: `extract.py` holds declarative CSV/JSON/HTML
extractors, and each crawler maps a source onto `RawDiscovery` objects. New
sources are added by editing `data/seed/source_registry.json`, not by writing
code.

### `agents/` — turning evidence into records

Each agent is idempotent and safe to re-run; that property *is* the resume
mechanism.

- **discovery** — imports the seed package, then sweeps sources in passes,
  recording new-candidate counts per pass so convergence is measurable.
- **metadata** — groups raw observations by normalised name, takes each field
  from the highest-credibility source that supplies it, splits genuinely combined
  designations (`Malloy T150/T400`) while keeping export names as aliases
  (`Heron TP / Eitan`).
- **deduplication** — veto rules first, similarity second. See below.
- **country classifier** — weighs design-origin evidence by source tier, counts
  each independent dataset once, and refuses registration addresses as origin.
- **source verification** — recomputes `verification_status` from the sources
  currently linked, so records upgrade automatically as corroboration arrives.
- **image discovery / licence / validation / vision** — the four-stage image
  pipeline described below.
- **atlas builder / export** — rendering and serialisation only; no business
  logic, so the outputs can always be regenerated from the database.
- **orchestrator** — stage sequencing, failure isolation, stop-condition checks.

## Three decisions worth explaining

### 1. Deduplication is asymmetric on purpose

Merging two spellings of one aircraft is a small win. Merging `MQ-9B SkyGuardian`
into `MQ-9B SeaGuardian` is a data-integrity failure. So similarity scoring never
runs until four vetoes have passed: differing model codes, differing trailing
variant markers on an identical stem, role words present on one side only, and
differing known manufacturers.

After the vetoes, the decision is driven by **token sets**, not character
similarity:

| Token-set relationship | Verdict | Why |
| --- | --- | --- |
| Identical after removing a manufacturer prefix | merge | `DJI Mavic 3 Pro` == `Mavic 3 Pro` |
| One side is a strict superset, and only one side carries a model code | review | `Global Hawk` vs `RQ-4 Global Hawk` — probably one aircraft, but a human decides |
| One side is a strict superset otherwise | distinct | `Mavic 3` vs `Mavic 3 Cine` are different products |
| Each side has tokens the other lacks | distinct | `Camera AG` vs `Camera IR` are separate variants |

Character similarity alone gets the first row wrong (0.85, below any sane
auto-merge threshold) and the third row wrong in the opposite direction (0.95,
above it). Token-set analysis gets both right.

### 2. Aggregators do not corroborate

The seed package republishes four underlying datasets. Counting it as an
independent source would have let almost every seed record reach "Verified" on
what is really a single observation. `sources.is_aggregator` marks republishers;
they satisfy the "at least one supporting source" rule but never contribute to
the independence count, in either the verification agent or the origin
classifier. Turning this on moved 288 records from *Verified* to *Probable* —
a less impressive number and a more honest one.

### 3. Country of origin means design origin

An EASA class-mark declaration proves a product is on the EU market; it says
nothing about where the aircraft was designed. Such evidence is tagged
`origin_is_registration_only` and can populate `production_country` but never
`country_id`. Joint programmes collapse to `Multinational` with participants
preserved in metadata. When the strongest sources disagree, the answer is
`Unknown` plus an unresolved item — not a coin flip.

One inference *is* permitted, because it rests on evidence already in the
database: a platform with no origin data whose manufacturer already has sourced
platforms resolving to one country inherits that country, labelled
`Low (inferred from manufacturer)` and queued under `country_inferred`. It is
visible, reversible and never silent.

## The image pipeline

```
search (Wikimedia Commons, scored & pre-filtered)
  └─► licence screen ── reject NC / ND / ARR / no provenance
        └─► download (atomic, size-capped)
              └─► validate ── decode, ≥500 px, aspect sanity, SHA-256 + perceptual hash
                    └─► duplicate check ── exact and near-duplicate across platforms
                          └─► identity ── metadata score, then optional vision verdict
                                └─► derivatives ── atlas / thumbnail / WebP
                                      └─► one image selected per platform
```

Any stage may reject; a rejection is recorded with its reason and the platform
gets an `image_missing` unresolved item carrying a Commons media-search URL, so
the gap is actionable rather than invisible. Identity gates the candidate score
before download — a perfectly licensed, high-resolution photograph of the wrong
aircraft is worth nothing here.

Where outbound access to image hosts is blocked, `--sideload-images` ingests
locally supplied files through the *same* licence, validation and provenance
rules. There is no path into the atlas that bypasses them.

## Resumability

`pipeline_state` records each completed stage; `--resume` skips them. Below that,
resumability is structural rather than bolted on:

- raw discoveries are keyed by a fingerprint, so re-importing inserts nothing;
- platforms upsert on `normalized_name`;
- images are keyed by platform and only re-fetched when none is selected;
- HTTP responses are cached on disk with a TTL;
- downloads are atomic (`.part` then rename), so a kill leaves no torn file.

An interrupted run resumes with `python run.py --all --resume`, and a *corrupted*
run recovers by re-running the affected stage — no manual cleanup, because every
stage is a function of the database rather than of the previous run's memory.

## Portability

The DDL stays inside the SQLite∩PostgreSQL subset: `TEXT`/`INTEGER`/`REAL`,
explicit foreign keys, named unique constraints, plain indexes. Porting means
swapping `INTEGER PRIMARY KEY AUTOINCREMENT` for `BIGSERIAL` and pointing
`app/db.py` at a different driver; no query in the codebase uses SQLite-only
syntax beyond `INSERT OR IGNORE`, which maps to `ON CONFLICT DO NOTHING`.
