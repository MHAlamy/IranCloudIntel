-- Schema version 2: component rate tables + bundle-vs-rates verification.
-- Rate tables are stored only for providers that publish them (e.g. Arvan);
-- providers with only fixed bundles keep using price_observations alone.

CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resource_rates (
    id            INTEGER PRIMARY KEY,
    provider_id   INTEGER NOT NULL REFERENCES providers(id),
    run_id        INTEGER NOT NULL REFERENCES collection_runs(id),
    category      TEXT NOT NULL,   -- cpu | ram | storage | gpu | ipv4 | traffic | dedicated
    region        TEXT NOT NULL,   -- iran | europe | ''
    unit          TEXT NOT NULL,   -- e.g. 'هر vCore', 'هر گیگابایت', 'هر آدرس'
    tier_label    TEXT NOT NULL DEFAULT '',  -- Basic/Standard/... or storage class label
    amount_toman  TEXT NOT NULL,   -- Decimal text, monthly Toman
    billing_period TEXT NOT NULL DEFAULT 'monthly',
    observed_at   TEXT NOT NULL,
    evidence      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_rates_provider_category
    ON resource_rates (provider_id, category, region, tier_label);

-- Verification of each bundle price against the provider's documented rates:
-- verified | mismatch | not_applicable | review
ALTER TABLE price_observations ADD COLUMN rate_verification TEXT NOT NULL DEFAULT 'not_applicable';
ALTER TABLE price_observations ADD COLUMN rate_verification_detail TEXT NOT NULL DEFAULT '';
