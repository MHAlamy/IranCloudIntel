-- Cloud Intelligence Dashboard schema, version 1.
-- Design rules (PROJECT_GUIDE.md 4.3, price_gathering_guide.md 5.3):
-- - timestamps stored as UTC ISO-8601 text; displayed as Jalali (Shamsi) in UI
-- - money stored as Decimal text, never floats
-- - price_observations is append-only history; last-known-good is never overwritten
-- - identity fields use '' (not NULL) so UNIQUE constraints deduplicate properly

CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS providers (
    id           INTEGER PRIMARY KEY,
    slug         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    official_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id               INTEGER PRIMARY KEY,
    provider_id      INTEGER NOT NULL REFERENCES providers(id),
    service_type     TEXT NOT NULL CHECK (service_type IN ('vm', 'object_storage', 'cdn')),
    url              TEXT NOT NULL,
    region_scope     TEXT NOT NULL DEFAULT '',
    collection_method TEXT NOT NULL CHECK (collection_method IN ('http', 'playwright')),
    UNIQUE (provider_id, service_type, url)
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id                    INTEGER PRIMARY KEY,
    source_id             INTEGER NOT NULL REFERENCES sources(id),
    started_at            TEXT NOT NULL,
    finished_at           TEXT,
    status                TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    http_status           INTEGER,
    content_hash          TEXT,
    extractor_config_hash TEXT,
    evidence_path         TEXT,
    model                 TEXT,
    schema_version        TEXT,
    prompt_tokens         INTEGER NOT NULL DEFAULT 0,
    completion_tokens     INTEGER NOT NULL DEFAULT 0,
    error                 TEXT
);

CREATE TABLE IF NOT EXISTS offerings (
    id                INTEGER PRIMARY KEY,
    provider_id       INTEGER NOT NULL REFERENCES providers(id),
    service_type      TEXT NOT NULL CHECK (service_type IN ('vm', 'object_storage', 'cdn')),
    product_family    TEXT NOT NULL DEFAULT '',
    plan_name         TEXT NOT NULL,
    provider_tier_raw TEXT NOT NULL DEFAULT '',
    region            TEXT NOT NULL DEFAULT '',
    UNIQUE (provider_id, service_type, product_family, plan_name, provider_tier_raw, region)
);

CREATE TABLE IF NOT EXISTS price_observations (
    id                   INTEGER PRIMARY KEY,
    offering_id          INTEGER NOT NULL REFERENCES offerings(id),
    run_id               INTEGER NOT NULL REFERENCES collection_runs(id),
    observed_at          TEXT NOT NULL,
    price_value          TEXT NOT NULL,      -- source value, Decimal text
    price_in_toman       TEXT,               -- canonical monthly Toman; NULL when unknown
    currency             TEXT NOT NULL,      -- toman | rial | unknown
    billing_period       TEXT NOT NULL,      -- monthly | hourly | unknown
    price_raw            TEXT NOT NULL,
    currency_raw         TEXT NOT NULL,
    billing_period_raw   TEXT NOT NULL,
    vcpu                 INTEGER,
    ram_gb               TEXT,
    disk_gb              TEXT,
    disk_type            TEXT,
    plan_url             TEXT,
    validation_status    TEXT NOT NULL CHECK (validation_status IN ('valid', 'suspect')),
    validation_issues    TEXT NOT NULL DEFAULT '[]',  -- JSON array
    evidence             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observations_offering_time
    ON price_observations (offering_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_runs_source_time
    ON collection_runs (source_id, started_at DESC);
