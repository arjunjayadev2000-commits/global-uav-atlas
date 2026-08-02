# Operations

## Setup

### Local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt      # or requirements.txt for runtime only
cp .env.example .env                     # optional; edit as needed
python run.py --all
```

Python 3.11+. First run takes a few minutes: seed import, discovery passes,
deduplication, then rendering.

### Docker

```bash
docker compose up --build
```

That single command builds the image, applies migrations, runs the full pipeline
with `--resume`, and writes into the mounted `output/`, `images/`, `logs/` and
`docs/` directories. The database lives in the named volume `atlas-data` so it
survives `docker compose down`.

To pass an API key without baking it into the image:

```bash
ANTHROPIC_API_KEY=sk-... docker compose up --build
```

For a container that keeps refreshing on a schedule:

```bash
docker compose --profile scheduled up -d updater
```

## Environment variables

All are optional; defaults are in `app/config.py` and documented in
`.env.example`. The ones that matter most in practice:

| Variable | Default | Effect |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | *(unset)* | Enables vision verification of image identity. Without it the pipeline uses metadata-based verification and flags low-confidence images. |
| `UAV_DB_PATH` | `data/uav_atlas.sqlite` | Database location. |
| `UAV_OFFLINE` | `0` | `1` forbids all outbound requests — rebuild the atlas from the existing database with no network. |
| `UAV_RATE_LIMIT_RPS` | `1` | Requests per second per host. Lower it when crawling politely at scale. |
| `UAV_RESPECT_ROBOTS` | `1` | Honour `robots.txt`. Leave on. |
| `UAV_HTTP_CACHE_TTL` | `604800` | Seconds before a cached response is refetched. |
| `UAV_IMAGE_MIN_WIDTH` | `500` | Absolute minimum image width; below this an image is rejected. |
| `UAV_ALLOW_NC_LICENSES` | `0` | `1` permits NonCommercial images. Leave at `0` if the atlas may be distributed commercially. |
| `UAV_DEDUPE_AUTO` / `UAV_DEDUPE_REVIEW` | `0.94` / `0.86` | Auto-merge and review thresholds. |
| `UAV_DISCOVERY_EMPTY_PASSES` | `3` | Consecutive empty passes before discovery is considered converged. |

## Running partial jobs

```bash
python run.py --all                     # everything
python run.py --discover                # seed import + discovery passes + promotion
python run.py --dedupe                  # deduplication only
python run.py --dedupe --dry-run        # report merges without performing them
python run.py --classify                # re-derive country of origin
python run.py --images                  # acquire images for platforms that lack one
python run.py --verify                  # source verification + image identity
python run.py --build                   # regenerate PDF + HTML
python run.py --export                  # regenerate CSV/XLSX/SQLite/stats
python run.py --update                  # incremental refresh (the weekly job)

python run.py --limit 25                # cap records per stage (pilot runs)
python run.py --country "India"         # restrict to one country
python run.py --manufacturer "DJI"      # restrict to one manufacturer
python run.py --passes 3                # fix the number of discovery passes
python run.py --skip-images             # build without touching image hosts
```

Inspection commands never modify data:

```bash
python run.py --status                  # which stages are done, coverage, discovery passes
python run.py --stats                   # coverage statistics
python run.py --stop-conditions         # evaluate the completion criteria
python run.py --status --json           # machine-readable
```

## Restarting after an interruption

```bash
python run.py --all --resume
```

`--resume` skips stages already recorded complete in `pipeline_state`. Below
that, everything is idempotent by construction: raw discoveries dedupe on a
fingerprint, platforms upsert on their normalised name, images are only fetched
for platforms with none selected, and downloads are atomic. Re-running a stage
without `--resume` is always safe — it recomputes from the database rather than
from the previous run's memory.

To force a stage to run again even under `--resume`:

```bash
python -c "from app.db import connect, set_state; set_state('step:images', {'status':'pending'})"
python run.py --images --resume
```

## Images when the network blocks the providers

If `commons.wikimedia.org` and the other image hosts are unreachable (corporate
egress policy, air-gapped build), the image stage records the blocker and stops
after three consecutive refusals rather than retrying 600 times. Two ways
forward:

**First, find out exactly what is blocked:**

```bash
python run.py --check-network
```

It probes every host in the source registry plus the two Wikimedia hosts the
image pipeline needs, and prints a copy-pasteable allowlist. Exit code 0 means
everything is reachable. `commons.wikimedia.org` and `upload.wikimedia.org` are
the two that unblock photographs; the rest extend platform coverage.

**Re-run where the hosts are reachable:**

```bash
python run.py --images --verify --build --export --resume
```

**Or sideload files you have licensed yourself.** Generate a fill-in manifest:

```bash
python run.py --prepare-image-manifest                    # every platform lacking an image
python run.py --prepare-image-manifest --country India    # or narrow it down
python run.py --prepare-image-manifest --limit 50
```

That writes `data/imports/images/manifest.csv` pre-populated with the platform
name, country, manufacturer and a Commons media-search URL per row. Put the image
files in the same directory and fill in the remaining columns from each file's
own source page:

```csv
platform_name,country_of_origin,manufacturer,commons_search_url,file,source_url,source_page_url,photographer,license_name,license_url
MQ-9A Reaper,United States,General Atomics,https://commons.wikimedia.org/…,mq9.jpg,https://…/mq9.jpg,https://commons.wikimedia.org/wiki/File:…,Jane Photographer,CC BY-SA 4.0,https://creativecommons.org/licenses/by/4.0/
```

```bash
python run.py --sideload-images
python run.py --build --export
```

Sideloaded files go through the same licence, resolution, duplicate and identity
checks as network-sourced ones. Rows without a licence and a source page are
rejected — there is no bypass.

## Backing up the database

```bash
scripts/backup_database.sh                 # → data/backups/uav_atlas-<timestamp>.sqlite.gz
scripts/backup_database.sh /mnt/backups    # custom destination
```

Uses the SQLite backup API, so a snapshot taken while the pipeline is running is
still consistent. The ten most recent backups are retained.

Restore:

```bash
gunzip -c data/backups/uav_atlas-20260802T154600Z.sqlite.gz > data/uav_atlas.sqlite
python run.py --status
```

`output/uav_database.sqlite` is also a complete, consistent copy written on every
export.

## Regenerating the outputs

The database is the source of truth; every output is derived from it.

```bash
python run.py --build --export           # PDF, HTML, CSV, XLSX, SQLite, stats
python scripts/verify_outputs.py         # prove the outputs are real, not just present
```

`verify_outputs.py` checks that the PDF opens and contains searchable atlas text,
that the HTML payload parses, that CSV row counts match the database, that no
platform has two selected images, and that every atlas image has a source,
licence, attribution and identity status. Exit code 0 means all checks passed.

## Troubleshooting

**`FetchError: host … refused by network egress policy`**
Your network blocks that host. The pipeline remembers it and fails fast rather
than retrying. Check `output/unresolved_records.csv` for the full list of blocked
sources, then re-run from a permitted network. Do not disable TLS verification or
route around the policy.

**`schema incomplete, missing tables: [...]`**
The database predates a migration or was truncated. Run `python run.py --status`
(applies migrations) or restore a backup.

**`database is locked`**
Another process holds the write lock. The connection uses WAL with a 60-second
busy timeout, so this usually resolves itself; if it persists, check for a
stray `run.py` process.

**PDF build fails with a missing-destination error**
A table-of-contents entry pointed at a bookmark that was not emitted. The
builder now uses page references rather than internal links; if you add heading
types, keep them on the 3-tuple `TOCEntry` form.

**No images in the atlas**
Expected when the image hosts are unreachable. Check
`docs/UNRESOLVED.md` → `pipeline_blocker`, and the per-platform `image_missing`
items in `output/unresolved_records.csv`, each of which carries a Commons
media-search URL.

**Vision verification is skipped**
No `ANTHROPIC_API_KEY`, or the `anthropic` package is not installed
(`pip install anthropic`). The pipeline continues on metadata-based verification
and queues low-confidence images for manual review; this is by design, not a
failure.

**Too many duplicate-review items**
Inspect them before changing thresholds:
```bash
sqlite3 data/uav_atlas.sqlite \
  "SELECT kept_name, merged_name, score, reason FROM merge_decisions
   WHERE decision='review' ORDER BY score DESC LIMIT 40;"
```
If they are genuinely distinct variants, that is correct behaviour, not noise.

**Disk filling up**
`data/cache/` holds cached HTTP responses and `images/` holds originals plus
three derivatives each. Both are safe to delete; the pipeline re-creates what it
needs.

## What "done" means

`python run.py --stop-conditions` evaluates the completion criteria: pipeline ran
end to end, all required outputs present, discovery converged (three consecutive
passes with no new candidates), unresolved items documented, every atlas image
carrying source + licence + attribution + identity status, duplicate review rate
below threshold, PDF and HTML present, coverage statistics generated. It reports
each condition separately so a partially-blocked environment still gives an
honest answer.
