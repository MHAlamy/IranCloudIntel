-- Schema version 3: Object Storage (price_gathering_guide.md 7).
-- Service-specific observation schema: object-storage pricing must not be
-- forced into the VM-shaped columns of price_observations. Plan identity is
-- still shared via the generic `offerings` table (provider, service_type,
-- plan_name, region), so history/identity handling stays uniform.
-- Money remains Decimal text; observations are append-only.

CREATE TABLE IF NOT EXISTS os_observations (
    id                    INTEGER PRIMARY KEY,
    offering_id           INTEGER NOT NULL REFERENCES offerings(id),
    run_id                INTEGER NOT NULL REFERENCES collection_runs(id),
    observed_at           TEXT NOT NULL,
    -- price (NULL when the plan is quote-only; 0 only when source says رایگان)
    plan_status           TEXT NOT NULL CHECK (plan_status IN ('priced', 'free', 'quote_only')),
    price_value           TEXT,
    price_in_toman        TEXT,
    currency              TEXT NOT NULL DEFAULT 'toman',
    billing_period        TEXT NOT NULL DEFAULT 'monthly',
    price_raw             TEXT NOT NULL,
    currency_raw          TEXT NOT NULL DEFAULT '',
    billing_period_raw    TEXT NOT NULL DEFAULT '',
    -- included allowances; Decimal text in GB (1 TB = 1024 GB, configurable);
    -- NULL = unknown or unlimited (see *_unlimited flags)
    storage_included_gb   TEXT,
    traffic_included_gb   TEXT,
    requests_included     INTEGER,          -- read+write request allowance (count)
    storage_unlimited     INTEGER NOT NULL DEFAULT 0,
    traffic_unlimited     INTEGER NOT NULL DEFAULT 0,
    requests_unlimited    INTEGER NOT NULL DEFAULT 0,
    -- documented overage (PAYG) rates when the plan page states them
    overage_storage_toman_gb  TEXT,
    overage_traffic_toman_gb  TEXT,
    plan_url              TEXT,
    validation_status     TEXT NOT NULL CHECK (validation_status IN ('valid', 'suspect')),
    validation_issues     TEXT NOT NULL DEFAULT '[]',
    evidence              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_os_observations_offering_time
    ON os_observations (offering_id, observed_at DESC);

-- PAYG / overage component rate tables (e.g. Arvan's مصرف مازاد section).
-- Tiered ranges are stored with raw labels AND parsed numeric bounds so
-- scenario calculations are deterministic. `amount_toman` NULL + is_free=1
-- marks a documented free allowance.
CREATE TABLE IF NOT EXISTS os_rates (
    id            INTEGER PRIMARY KEY,
    provider_id   INTEGER NOT NULL REFERENCES providers(id),
    run_id        INTEGER NOT NULL REFERENCES collection_runs(id),
    observed_at   TEXT NOT NULL,
    category      TEXT NOT NULL,   -- storage | traffic | requests_read | requests_write | feature | faq_overage
    unit          TEXT NOT NULL,   -- 'هر گیگابایت' | 'هر ۱۰٬۰۰۰ درخواست' | ...
    tier_label    TEXT NOT NULL DEFAULT '',  -- storage class or plan label (استاندارد, بسته رشد, ...)
    range_label   TEXT NOT NULL DEFAULT '',  -- verbatim range text, e.g. '۵ گیگابایت تا ۵ ترابایت'
    range_min_gb  TEXT,            -- parsed inclusive lower bound (GB), NULL = unbounded
    range_max_gb  TEXT,            -- parsed inclusive upper bound (GB), NULL = unbounded
    amount_toman  TEXT,            -- Decimal text; NULL when is_free
    is_free       INTEGER NOT NULL DEFAULT 0,
    region        TEXT NOT NULL DEFAULT 'iran',
    evidence      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_os_rates_provider
    ON os_rates (provider_id, category, tier_label);
