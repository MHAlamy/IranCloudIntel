-- Schema version 8: allow KaaS sources and offerings.
-- SQLite cannot alter a CHECK constraint in place, so the two identity tables
-- are rebuilt with identical columns, IDs and constraints (same approach as
-- v5/v6/v7). Foreign-key enforcement is disabled for the rebuild.

PRAGMA foreign_keys=OFF;
DROP TABLE IF EXISTS sources_new;
DROP TABLE IF EXISTS offerings_new;

CREATE TABLE sources_new (
    id               INTEGER PRIMARY KEY,
    provider_id      INTEGER NOT NULL REFERENCES providers(id),
    service_type     TEXT NOT NULL CHECK (service_type IN ('vm', 'object_storage', 'cdn', 'paas', 'dbaas', 'kaas')),
    url              TEXT NOT NULL,
    region_scope     TEXT NOT NULL DEFAULT '',
    collection_method TEXT NOT NULL CHECK (collection_method IN ('http', 'playwright', 'manual')),
    UNIQUE (provider_id, service_type, url)
);
INSERT INTO sources_new (id, provider_id, service_type, url, region_scope, collection_method)
SELECT id, provider_id, service_type, url, region_scope, collection_method FROM sources;
DROP TABLE sources;
ALTER TABLE sources_new RENAME TO sources;

CREATE TABLE offerings_new (
    id                INTEGER PRIMARY KEY,
    provider_id       INTEGER NOT NULL REFERENCES providers(id),
    service_type      TEXT NOT NULL CHECK (service_type IN ('vm', 'object_storage', 'cdn', 'paas', 'dbaas', 'kaas')),
    product_family    TEXT NOT NULL DEFAULT '',
    plan_name         TEXT NOT NULL,
    provider_tier_raw TEXT NOT NULL DEFAULT '',
    region            TEXT NOT NULL DEFAULT '',
    UNIQUE (provider_id, service_type, product_family, plan_name, provider_tier_raw, region)
);
INSERT INTO offerings_new (id, provider_id, service_type, product_family, plan_name, provider_tier_raw, region)
SELECT id, provider_id, service_type, product_family, plan_name, provider_tier_raw, region FROM offerings;
DROP TABLE offerings;
ALTER TABLE offerings_new RENAME TO offerings;

PRAGMA foreign_keys=ON;
