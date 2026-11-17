-- Schema version 6: manually imported (offline) sources and their provenance.
--
-- A manual source is a transcribed document, not a fetched page, so it needs
-- its own collection method. The document version and its validity belong to
-- the run, because they change independently of the import time. SQLite cannot
-- alter a CHECK constraint in place, so `sources` is rebuilt with identical
-- columns, IDs and constraints (same approach as v5).

PRAGMA foreign_keys=OFF;
DROP TABLE IF EXISTS sources_new;

CREATE TABLE sources_new (
    id               INTEGER PRIMARY KEY,
    provider_id      INTEGER NOT NULL REFERENCES providers(id),
    service_type     TEXT NOT NULL CHECK (service_type IN ('vm', 'object_storage', 'cdn', 'paas')),
    url              TEXT NOT NULL,
    region_scope     TEXT NOT NULL DEFAULT '',
    collection_method TEXT NOT NULL CHECK (collection_method IN ('http', 'playwright', 'manual')),
    UNIQUE (provider_id, service_type, url)
);
INSERT INTO sources_new (id, provider_id, service_type, url, region_scope, collection_method)
SELECT id, provider_id, service_type, url, region_scope, collection_method FROM sources;
DROP TABLE sources;
ALTER TABLE sources_new RENAME TO sources;

PRAGMA foreign_keys=ON;

-- Provenance of a manual import: which document, and until when it is valid.
ALTER TABLE collection_runs ADD COLUMN source_document TEXT NOT NULL DEFAULT '';
ALTER TABLE collection_runs ADD COLUMN valid_until TEXT;
