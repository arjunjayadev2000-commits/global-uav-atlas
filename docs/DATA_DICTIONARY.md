# Data dictionary

Tables are listed in dependency order. `Nullable` reflects the DDL in
`app/schemas.py`; `Set by` names the agent that owns the field.

## `countries`

| Field | Type | Nullable | Set by | Meaning |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | no | db | Surrogate key. |
| `name` | TEXT | no | country classifier | Canonical spelling: `United States`, `United Kingdom`, `Türkiye`, `South Korea`, `Czech Republic`, plus the two synthetic buckets `Multinational` and `Unknown`. |
| `normalized_name` | TEXT | no | db | Comparison key; unique. |
| `iso3` | TEXT | yes | db | ISO 3166-1 alpha-3. Null for `Multinational` and `Unknown`. |
| `is_multinational` | INTEGER | no | db | 1 for the joint-programme bucket. |
| `is_unknown` | INTEGER | no | db | 1 for the unresolved-origin bucket. |

## `manufacturers`

| Field | Type | Nullable | Set by | Meaning |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | no | db | Surrogate key. |
| `name` | TEXT | no | metadata | Manufacturer or design organisation as reported by the strongest source. |
| `normalized_name` | TEXT | no | db | Unique comparison key. |
| `country_id` | INTEGER FK | yes | metadata | Inherited from the first platform that supplies one; never overwritten. |
| `organisation_type` | TEXT | yes | metadata | e.g. company, state design bureau, university. |
| `website` | TEXT | yes | metadata | Official site when known. |

## `platform_families`

| Field | Type | Nullable | Set by | Meaning |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | no | db | Surrogate key. |
| `name` | TEXT | no | metadata | Family stem shared by split variants (`Malloy T150`/`T400` → `Malloy`). |
| `manufacturer_id`, `country_id` | INTEGER FK | yes | metadata | Inherited from the first member. |

## `platforms`

The canonical record. One row per distinct aircraft; officially separate variants
get their own rows.

| Field | Type | Nullable | Set by | Meaning |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | no | db | Surrogate key. |
| `public_id` | TEXT | no | metadata | Stable `UAV-<hash>` identifier derived from the normalised name; survives re-runs and appears in every export. |
| `canonical_name` | TEXT | no | metadata | Display name; the value shown in the atlas. |
| `normalized_name` | TEXT | no | metadata | Unique comparison key: accent-folded, punctuation-stripped, noise words removed, roman numerals expanded. |
| `manufacturer_id` | INTEGER FK | yes | metadata | Builder / design organisation. |
| `country_id` | INTEGER FK | yes | country classifier | **Design origin**, never merely an operator. |
| `family_id` | INTEGER FK | yes | metadata | Set when the record came from a split combined designation. |
| `domain` | TEXT | no | metadata | `Military`, `Civilian / Commercial`, `Dual-use`, `Research / Experimental`, `Unknown`. Drives the atlas sections. |
| `category` | TEXT | yes | metadata | Role classification as reported (MALE fixed-wing, agricultural multirotor, loitering munition, …). |
| `airframe_type` | TEXT | yes | metadata | Fixed-wing, rotary, hybrid VTOL, … where the source supplies it. |
| `status` | TEXT | yes | metadata | Programme/service status verbatim from the source. |
| `first_seen_year` | INTEGER | yes | metadata | Earliest year any source attests the platform. |
| `introduced_year` | INTEGER | yes | metadata | Entry into service where documented. |
| `retired_year` | INTEGER | yes | metadata | Withdrawal where documented. |
| `description_short` | TEXT | yes | metadata | ≤240 chars. Held in the database for governance; **not** printed in the atlas entry table. |
| `verification_status` | TEXT | no | source verification | `Verified` (≥2 independent sources, best tier ≤2, origin resolved) · `Probable` · `Needs Verification`. |
| `confidence_score` | REAL | no | source verification | 0–1 from best source tier, independent source count, origin resolution, manufacturer completeness. |
| `origin_confidence` | TEXT | yes | country classifier | `High` · `Medium` · `Low` · `Low (inferred from manufacturer)` · `None`. |
| `participating_countries` | TEXT | yes | country classifier | Comma-separated partners for `Multinational` programmes. |
| `production_country` | TEXT | yes | country classifier | Licensed-production or registration country when it differs from design origin. |
| `is_merged_into` | INTEGER FK | yes | deduplication | Set when this row was folded into another. **Every atlas and export query filters on `is_merged_into IS NULL`.** |

## `platform_aliases`

| Field | Type | Nullable | Set by | Meaning |
| --- | --- | --- | --- | --- |
| `platform_id` | INTEGER FK | no | metadata | Owner. |
| `alias` | TEXT | no | metadata | Alternate name: export name, service name, transliteration, marketing name. |
| `normalized_alias` | TEXT | no | metadata | Unique per platform. |
| `alias_type` | TEXT | no | metadata | `alias` · `model_code` · `merged` (left behind by a deduplication merge so the old name stays searchable). |

## `platform_variants`

| Field | Type | Nullable | Set by | Meaning |
| --- | --- | --- | --- | --- |
| `platform_id` | INTEGER FK | no | metadata | The variant's own platform row. |
| `parent_platform_id` | INTEGER FK | yes | metadata | The first variant of the split, acting as the family anchor. |
| `variant_name` | TEXT | no | metadata | Variant designation. |
| `variant_role` | TEXT | yes | metadata | Why the variant exists, e.g. "split from combined designation". |

## `sources`

| Field | Type | Nullable | Set by | Meaning |
| --- | --- | --- | --- | --- |
| `title` | TEXT | no | discovery | Source name; unique together with `url`. |
| `publisher` | TEXT | yes | discovery | Publishing organisation. |
| `url` | TEXT | yes | discovery | Canonical URL, or `local://…` for the seed package. |
| `source_type` | TEXT | yes | discovery | `seed dataset` · `regulatory register` · `open dataset` · `image repository` · `crawled source`. |
| `retrieved_at` | TEXT | yes | discovery | ISO-8601 UTC retrieval time. |
| `credibility_tier` | INTEGER | no | discovery | 1 official · 2 established institution · 3 open catalogue · 4 leads only. |
| `is_aggregator` | INTEGER | no | discovery | 1 = republishes other datasets. Satisfies "has a source" but never counts toward independence, and its origin evidence is weighted at half. |
| `notes` | TEXT | yes | discovery | Scope and limitations, carried through from the publisher where stated. |

## `platform_sources` / `image_sources`

Join tables. `relation` is `supports` for platforms and `hosts` for images;
`excerpt` keeps the specific URL or snippet that backs the link.

## `images`

| Field | Type | Nullable | Set by | Meaning |
| --- | --- | --- | --- | --- |
| `platform_id` | INTEGER FK | no | image discovery | Owner. |
| `local_path` | TEXT | yes | image discovery | Original downloaded file, under `images/<country>/<platform>/`. |
| `thumbnail_path` / `atlas_path` / `webp_path` | TEXT | yes | image validation | Derivatives. `atlas_path` is what the PDF embeds and the HTML lazy-loads. |
| `source_url` | TEXT | yes | image discovery | Direct file URL. |
| `source_page_url` | TEXT | yes | image discovery | The page carrying the licence statement. **Required** — an image without one is rejected for missing provenance. |
| `photographer` | TEXT | yes | image discovery | Author/credit as published. |
| `license_name` | TEXT | yes | licence agent | Licence short name exactly as published. |
| `license_url` | TEXT | yes | licence agent | Licence deed URL. |
| `attribution_text` | TEXT | yes | licence agent | Ready-to-print credit line; reproduced in the PDF attribution appendix. |
| `is_public_domain` | INTEGER | no | licence agent | 1 for CC0/PD/government works. |
| `commercial_use` / `modification_allowed` | INTEGER | yes | licence agent | Both must be true unless `UAV_ALLOW_NC_LICENSES=1`; the atlas resizes every image, which is a modification. |
| `width` / `height` | INTEGER | yes | image validation | Pixel dimensions of the original. Minimum width 500 px; 800 px preferred. |
| `mime_type` | TEXT | yes | image validation | Determined by decoding, not by the declared header. |
| `sha256` | TEXT | yes | image validation | Exact-duplicate detection. |
| `perceptual_hash` | TEXT | yes | image validation | Near-duplicate detection; stops one photograph serving two unrelated platforms. |
| `identity_verdict` | TEXT | no | image discovery / vision | `match` · `probable match` · `uncertain` · `mismatch` · `unverified`. |
| `identity_confidence` | REAL | no | image discovery / vision | 0–1 behind the verdict. |
| `identity_explanation` | TEXT | yes | image discovery / vision | Why. Prefixed `[vision]` when a vision model produced it. |
| `license_verified` | INTEGER | no | licence agent | 1 = licence permits redistribution, commercial use and modification. |
| `validation_status` | TEXT | no | image validation | `ok` · `invalid` · `missing` · `pending`. |
| `rejection_reason` | TEXT | yes | image validation / vision | Why an image was rejected or deselected. |
| `selected_for_atlas` | INTEGER | no | image discovery | At most one per platform; `scripts/verify_outputs.py` asserts this. |

## `raw_discoveries`

The immutable evidence layer. Never edited after insert.

| Field | Type | Nullable | Set by | Meaning |
| --- | --- | --- | --- | --- |
| `discovery_run_id` | INTEGER FK | yes | discovery | Which pass produced it. |
| `source_id` | INTEGER FK | yes | discovery | Which source produced it. |
| `raw_name` | TEXT | no | discovery | The name exactly as the source gave it. |
| `normalized_name` | TEXT | no | discovery | Grouping key for promotion. |
| `raw_country` / `raw_manufacturer` | TEXT | yes | discovery | As given. Blank for regulatory sources, where the declared country is a registration address, not an origin. |
| `payload_json` | TEXT | yes | discovery | The full source record plus flags: `credibility_tier`, `layer`, `lead_only`, `origin_is_registration_only`, `registered_country`, `needs_review`, `origin_hint_only`. |
| `fingerprint` | TEXT | no | discovery | Unique over source + normalised name + variant + external ref. Makes re-import a no-op. |
| `promoted_platform_id` | INTEGER FK | yes | metadata | The canonical record this observation fed. |
| `processed` | INTEGER | no | metadata | 0 until promoted. |

## `discovery_runs`

One row per strategy per pass: `pass_number`, `strategy`, `source_name`,
`candidates_seen`, `new_candidates`, `status` (`running`/`complete`/`failed`) and
`error`. `new_candidates` per pass is what the convergence stop condition reads.

## `verification_events`

Append-only verdict history: `entity_type`, `entity_id`, `agent`, `verdict`,
`confidence`, `explanation`, `evidence_json`. Never updated, so the full
verification history of any image or platform is reconstructable.

## `update_history`

Every field change written through `app.db.update_fields`: `entity_type`,
`entity_id`, `field`, `old_value`, `new_value`, `reason`, `agent`, `run_id`.
This is what makes "why does this row say Türkiye?" answerable.

## `unresolved_items`

| Field | Meaning |
| --- | --- |
| `item_type` | `image_missing` · `image_identity_unverified` · `country_of_origin` · `country_inferred` · `possible_duplicate` · `missing_source` · `source_unreachable` · `pipeline_blocker` · `pipeline_stage_failure`. |
| `subject` | Platform name or source title. |
| `detail` | What exactly is unresolved. |
| `severity` | `high` · `medium` · `low`. |
| `suggested_action` | The concrete next step, including a Commons media-search URL for missing images. |
| `blocker` | The precise reason it cannot be closed automatically (e.g. `network egress policy`, `no vision API key configured`). |
| `fingerprint` | Deduplicating key, so re-runs update rather than pile up. |
| `status` | `open` · `resolved`. Resolved automatically when the underlying condition clears. |

## `merge_decisions`

Every deduplication verdict that was not "distinct": `kept_platform_id`,
`merged_platform_id`, both names, `score`, `decision` (`merged`/`review`) and
`reason`. Reviews are the human queue; merges are the audit trail.

## `pipeline_state` / `url_ledger`

`pipeline_state` is the resume ledger (`step:<stage>` keys plus run summaries).
`url_ledger` records every URL fetched with its status, content hash and fetch
count, so a source is not needlessly reprocessed.

## Export column mapping

`output/uav_database.csv` flattens the above: `record_id` ← `platforms.public_id`,
`uav_name` ← `canonical_name`, `country_of_origin` ← `countries.name`, plus
`manufacturer`, `family`, `domain`, `category`, `airframe_type`, `status`,
`introduced_year`, `retired_year`, `description_short`, `verification_status`,
`confidence_score`, `origin_confidence`, `participating_countries`,
`production_country`, `aliases` (pipe-separated), `source_count`, `sources`,
`photo_path`, `photo_source_page`, `photo_license`, `photo_identity_status`,
`created_at`, `updated_at`.

The atlas itself shows only **Photo · UAV Name · Country of Origin**; everything
else exists for governance, provenance and verification.
