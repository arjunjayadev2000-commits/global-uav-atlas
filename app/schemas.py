"""Database schema and forward-only migrations.

The DDL is intentionally written in the SQL subset shared by SQLite and
PostgreSQL: ``TEXT``/``INTEGER``/``REAL`` columns, explicit foreign keys, named
unique constraints and plain ``CREATE INDEX``.  Porting to PostgreSQL therefore
requires only swapping ``INTEGER PRIMARY KEY AUTOINCREMENT`` for ``BIGSERIAL``.

Migrations are append-only: never edit an applied migration, add a new one.
"""

from __future__ import annotations

from typing import NamedTuple


class Migration(NamedTuple):
    version: int
    name: str
    sql: str


_M001 = """
CREATE TABLE IF NOT EXISTS countries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    normalized_name     TEXT NOT NULL,
    iso3                TEXT,
    is_multinational    INTEGER NOT NULL DEFAULT 0,
    is_unknown          INTEGER NOT NULL DEFAULT 0,
    notes               TEXT,
    created_at          TEXT NOT NULL,
    CONSTRAINT uq_countries_normalized UNIQUE (normalized_name)
);
CREATE INDEX IF NOT EXISTS ix_countries_name ON countries(name);

CREATE TABLE IF NOT EXISTS manufacturers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    normalized_name     TEXT NOT NULL,
    country_id          INTEGER,
    organisation_type   TEXT,
    website             TEXT,
    notes               TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CONSTRAINT uq_manufacturers_normalized UNIQUE (normalized_name),
    FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_manufacturers_country ON manufacturers(country_id);

CREATE TABLE IF NOT EXISTS platform_families (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    normalized_name     TEXT NOT NULL,
    manufacturer_id     INTEGER,
    country_id          INTEGER,
    notes               TEXT,
    created_at          TEXT NOT NULL,
    CONSTRAINT uq_families_normalized UNIQUE (normalized_name),
    FOREIGN KEY (manufacturer_id) REFERENCES manufacturers(id) ON DELETE SET NULL,
    FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS platforms (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id           TEXT NOT NULL,
    canonical_name      TEXT NOT NULL,
    normalized_name     TEXT NOT NULL,
    manufacturer_id     INTEGER,
    country_id          INTEGER,
    family_id           INTEGER,
    domain              TEXT NOT NULL DEFAULT 'Unknown',
    category            TEXT,
    airframe_type       TEXT,
    status              TEXT,
    first_seen_year     INTEGER,
    introduced_year     INTEGER,
    retired_year        INTEGER,
    description_short   TEXT,
    verification_status TEXT NOT NULL DEFAULT 'Needs Verification',
    confidence_score    REAL NOT NULL DEFAULT 0.0,
    origin_confidence   TEXT,
    participating_countries TEXT,
    production_country  TEXT,
    is_merged_into      INTEGER,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CONSTRAINT uq_platforms_public_id UNIQUE (public_id),
    CONSTRAINT uq_platforms_normalized UNIQUE (normalized_name),
    FOREIGN KEY (manufacturer_id) REFERENCES manufacturers(id) ON DELETE SET NULL,
    FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE SET NULL,
    FOREIGN KEY (family_id) REFERENCES platform_families(id) ON DELETE SET NULL,
    FOREIGN KEY (is_merged_into) REFERENCES platforms(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_platforms_country ON platforms(country_id);
CREATE INDEX IF NOT EXISTS ix_platforms_manufacturer ON platforms(manufacturer_id);
CREATE INDEX IF NOT EXISTS ix_platforms_domain ON platforms(domain);
CREATE INDEX IF NOT EXISTS ix_platforms_status ON platforms(verification_status);
CREATE INDEX IF NOT EXISTS ix_platforms_family ON platforms(family_id);

CREATE TABLE IF NOT EXISTS sources (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    publisher           TEXT,
    url                 TEXT,
    source_type         TEXT,
    retrieved_at        TEXT,
    credibility_tier    INTEGER NOT NULL DEFAULT 3,
    notes               TEXT,
    content_sha256      TEXT,
    created_at          TEXT NOT NULL,
    CONSTRAINT uq_sources_title_url UNIQUE (title, url)
);
CREATE INDEX IF NOT EXISTS ix_sources_tier ON sources(credibility_tier);
CREATE INDEX IF NOT EXISTS ix_sources_url ON sources(url);

CREATE TABLE IF NOT EXISTS platform_aliases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id         INTEGER NOT NULL,
    alias               TEXT NOT NULL,
    normalized_alias    TEXT NOT NULL,
    alias_type          TEXT NOT NULL DEFAULT 'alias',
    source_id           INTEGER,
    created_at          TEXT NOT NULL,
    CONSTRAINT uq_alias_per_platform UNIQUE (platform_id, normalized_alias),
    FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_alias_normalized ON platform_aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS platform_variants (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id         INTEGER NOT NULL,
    parent_platform_id  INTEGER,
    variant_name        TEXT NOT NULL,
    normalized_variant  TEXT NOT NULL,
    variant_role        TEXT,
    notes               TEXT,
    created_at          TEXT NOT NULL,
    CONSTRAINT uq_variant UNIQUE (platform_id, normalized_variant),
    FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_platform_id) REFERENCES platforms(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS platform_sources (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id         INTEGER NOT NULL,
    source_id           INTEGER NOT NULL,
    relation            TEXT NOT NULL DEFAULT 'supports',
    excerpt             TEXT,
    created_at          TEXT NOT NULL,
    CONSTRAINT uq_platform_source UNIQUE (platform_id, source_id, relation),
    FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS images (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id         INTEGER NOT NULL,
    local_path          TEXT,
    thumbnail_path      TEXT,
    atlas_path          TEXT,
    webp_path           TEXT,
    source_url          TEXT,
    source_page_url     TEXT,
    photographer        TEXT,
    license_name        TEXT,
    license_url         TEXT,
    attribution_text    TEXT,
    is_public_domain    INTEGER NOT NULL DEFAULT 0,
    commercial_use      INTEGER,
    modification_allowed INTEGER,
    width               INTEGER,
    height              INTEGER,
    mime_type           TEXT,
    file_size           INTEGER,
    sha256              TEXT,
    perceptual_hash     TEXT,
    identity_confidence REAL NOT NULL DEFAULT 0.0,
    identity_verdict    TEXT NOT NULL DEFAULT 'unverified',
    identity_explanation TEXT,
    license_verified    INTEGER NOT NULL DEFAULT 0,
    validation_status   TEXT NOT NULL DEFAULT 'pending',
    rejection_reason    TEXT,
    selected_for_atlas  INTEGER NOT NULL DEFAULT 0,
    retrieved_at        TEXT,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_images_platform ON images(platform_id);
CREATE INDEX IF NOT EXISTS ix_images_sha ON images(sha256);
CREATE INDEX IF NOT EXISTS ix_images_phash ON images(perceptual_hash);
CREATE INDEX IF NOT EXISTS ix_images_selected ON images(selected_for_atlas);

CREATE TABLE IF NOT EXISTS image_sources (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id            INTEGER NOT NULL,
    source_id           INTEGER NOT NULL,
    relation            TEXT NOT NULL DEFAULT 'hosts',
    created_at          TEXT NOT NULL,
    CONSTRAINT uq_image_source UNIQUE (image_id, source_id, relation),
    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS discovery_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT NOT NULL,
    pass_number         INTEGER NOT NULL,
    strategy            TEXT NOT NULL,
    source_name         TEXT,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    candidates_seen     INTEGER NOT NULL DEFAULT 0,
    new_candidates      INTEGER NOT NULL DEFAULT 0,
    new_platforms       INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'running',
    error               TEXT
);
CREATE INDEX IF NOT EXISTS ix_discovery_runs_run ON discovery_runs(run_id);

CREATE TABLE IF NOT EXISTS raw_discoveries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    discovery_run_id    INTEGER,
    source_id           INTEGER,
    source_dataset      TEXT,
    source_url          TEXT,
    external_ref        TEXT,
    raw_name            TEXT NOT NULL,
    normalized_name     TEXT NOT NULL,
    raw_country         TEXT,
    raw_manufacturer    TEXT,
    domain              TEXT,
    category            TEXT,
    status              TEXT,
    variant             TEXT,
    payload_json        TEXT,
    fingerprint         TEXT NOT NULL,
    promoted_platform_id INTEGER,
    processed           INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    CONSTRAINT uq_raw_fingerprint UNIQUE (fingerprint),
    FOREIGN KEY (discovery_run_id) REFERENCES discovery_runs(id) ON DELETE SET NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL,
    FOREIGN KEY (promoted_platform_id) REFERENCES platforms(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_raw_normalized ON raw_discoveries(normalized_name);
CREATE INDEX IF NOT EXISTS ix_raw_processed ON raw_discoveries(processed);

CREATE TABLE IF NOT EXISTS verification_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type         TEXT NOT NULL,
    entity_id           INTEGER NOT NULL,
    agent               TEXT NOT NULL,
    verdict             TEXT NOT NULL,
    confidence          REAL,
    explanation         TEXT,
    evidence_json       TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_verification_entity
    ON verification_events(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS update_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type         TEXT NOT NULL,
    entity_id           INTEGER NOT NULL,
    field               TEXT NOT NULL,
    old_value           TEXT,
    new_value           TEXT,
    reason              TEXT,
    agent               TEXT,
    run_id              TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_update_entity ON update_history(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS unresolved_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type           TEXT NOT NULL,
    entity_type         TEXT,
    entity_id           INTEGER,
    subject             TEXT NOT NULL,
    detail              TEXT,
    severity            TEXT NOT NULL DEFAULT 'medium',
    suggested_action    TEXT,
    blocker             TEXT,
    status              TEXT NOT NULL DEFAULT 'open',
    fingerprint         TEXT NOT NULL,
    run_id              TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CONSTRAINT uq_unresolved_fingerprint UNIQUE (fingerprint)
);
CREATE INDEX IF NOT EXISTS ix_unresolved_status ON unresolved_items(status);
CREATE INDEX IF NOT EXISTS ix_unresolved_type ON unresolved_items(item_type);

CREATE TABLE IF NOT EXISTS merge_decisions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    kept_platform_id    INTEGER,
    merged_platform_id  INTEGER,
    kept_name           TEXT,
    merged_name         TEXT,
    score               REAL,
    decision            TEXT NOT NULL,
    reason              TEXT,
    run_id              TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_merge_decision ON merge_decisions(decision);

CREATE TABLE IF NOT EXISTS pipeline_state (
    key                 TEXT PRIMARY KEY,
    value               TEXT,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS url_ledger (
    url                 TEXT PRIMARY KEY,
    first_fetched_at    TEXT,
    last_fetched_at     TEXT,
    fetch_count         INTEGER NOT NULL DEFAULT 0,
    last_status         TEXT,
    content_sha256      TEXT,
    notes               TEXT
);
"""

_M002 = """
CREATE VIEW IF NOT EXISTS v_atlas_entries AS
SELECT
    p.id                AS platform_id,
    p.public_id         AS public_id,
    p.canonical_name    AS uav_name,
    COALESCE(c.name, 'Unknown')  AS country_of_origin,
    COALESCE(m.name, '')         AS manufacturer,
    p.domain            AS domain,
    COALESCE(p.category, '')     AS category,
    COALESCE(p.status, '')       AS status,
    p.verification_status        AS verification_status,
    p.confidence_score           AS confidence_score,
    i.atlas_path        AS atlas_image,
    i.thumbnail_path    AS thumbnail_image,
    i.attribution_text  AS image_attribution,
    i.license_name      AS image_license,
    i.identity_verdict  AS image_identity_verdict
FROM platforms p
LEFT JOIN countries c      ON c.id = p.country_id
LEFT JOIN manufacturers m  ON m.id = p.manufacturer_id
LEFT JOIN images i         ON i.platform_id = p.id AND i.selected_for_atlas = 1
WHERE p.is_merged_into IS NULL;
"""

_M003 = """
-- An aggregator republishes other datasets. It proves a record exists but it is
-- not an *independent* source, so it must not inflate corroboration counts.
ALTER TABLE sources ADD COLUMN is_aggregator INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS ix_sources_aggregator ON sources(is_aggregator);
"""

MIGRATIONS: list[Migration] = [
    Migration(1, "core_schema", _M001),
    Migration(2, "atlas_view", _M002),
    Migration(3, "source_aggregator_flag", _M003),
]

#: Tables the specification requires to exist.
REQUIRED_TABLES = (
    "platforms",
    "manufacturers",
    "countries",
    "platform_aliases",
    "platform_variants",
    "images",
    "sources",
    "platform_sources",
    "image_sources",
    "discovery_runs",
    "verification_events",
    "update_history",
    "unresolved_items",
)
