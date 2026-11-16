# Iranian Cloud Intelligence Dashboard

A personal competitive-intelligence dashboard for Iranian cloud services:
collects, validates and compares official public VM pricing across a small
set of providers, keeping historical observations and source evidence.

See `PROJECT_GUIDE.md` for the full specification, `price_gathering_guide.md`
for the collection/comparison methodology, `v1_milestones.md` for progress,
and `AGENTS.md` for agent working rules.

## Status (2026-11-15/16)

Milestones 1–4 essentially complete: four VM providers collected, validated
and visualized in a Persian RTL dashboard at `http://localhost:8000`. Object
Storage comparison is live for all four providers (Hamravesh's published
plans as the comparison baseline; Arvan and Kubit calculated from documented
PAYG rates; ParsPack storage-only calculator quotes).

| Provider | Collection mode | What the dashboard shows |
|---|---|---|
| ArvanCloud | Playwright (JS challenge) + LLM extraction (GPT-5-Mini via Arvan AIaaS) | VM: published bundles (3 tiers) verified against their PAYG rate table, plus calculated baseline prices. Object Storage: 4 plans + full PAYG overage tables; scenario prices calculated from documented rates |
| Liara | Plain HTTP, deterministic parser | Published fixed bundles (all four baselines match exactly; +200,000/mo documented IPv4) |
| ParsPack | Playwright drives their calculator | VM: baseline quotes (daily × 30 × 0.95 + fixed 150,000/mo IPv4). Object Storage: storage-only calculator quotes (HDD, ایران, ۱ ماهه; no traffic allowance) |
| Kubit | Plain HTTP, deterministic parser | VM: calculated from per-component rates (gen-3→Economy, gen-4→Standard). Object Storage: free base plan (zero quotas) + PAYG tables; scenario prices calculated from documented rates |
| Hamravesh | Playwright (client-side service tab), deterministic parser | Object Storage: 5 plans with included storage/traffic and documented overage rates (baseline provider) |

Every price row carries a basis badge: منتشرشده (published) / محاسبه‌شده
(calculated from documented rates) / تقریبی (nearest config) / در دسترس نیست.
A pure-CSS bar chart above the comparison table visualizes provider prices
for the current tier/size selection, cheapest first, color-coded by basis.
Dates display in the Jalali calendar; all prices in monthly Toman; Iranian
regions only (owner decisions recorded in `v1_milestones.md` and
`price_gathering_guide.md`). Tier mapping (owner decision 2026-11-15):
Liara and ParsPack compare under Economy; Standard holds Arvan and Kubit
gen-4; Premium is Arvan-only.

## Local development (Windows, native)

Requires Python 3.14 (via the `py` launcher) and Git. No WSL, no local Docker.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests          # 114 tests, all mocked (no cost)
```

Run the dashboard:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run a collection (one-shot, locked; honours the skip-unchanged cache):

```powershell
.\.venv\Scripts\python.exe -m collectors.cli                 # all enabled sources
.\.venv\Scripts\python.exe -m collectors.cli --source liara_vm_cloud_server
.\.venv\Scripts\python.exe -m collectors.cli --force         # re-extract even if unchanged
```

Useful inspection scripts: `scripts/db_report.py`, `scripts/check_verification.py`,
`scripts/check_aiaas.py`.

## Configuration (all validated on startup)

- `config/providers.yaml` — source registry (URLs, collection method, navigation hints)
- `config/tiers.yaml` — analyst-maintained tier normalization
- `config/benchmarks.yaml` — reference sizes, matching rules, region scope
- `config/rate_mappings.yaml` — family→rate-class mappings + calculated-price factors
- `config/analyst_facts.yaml` — owner-approved facts not scrapable from pages

## Data layout

- `data/cloud_intel.db` — SQLite (gitignored): providers, sources, runs,
  offerings, price observations (append-only), resource rates
- `evidence/` — rendered pages, cleaned content, quotes, LLM outputs (gitignored)
- `.env` — Arvan AIaaS credentials (gitignored; see `.env.example`)

## Remaining for V1

CDN coverage. Then deployment to one Ubuntu VM (Docker Compose, Nginx,
HTTPS), scheduling, backups to Object Storage, and CI/CD via GitHub Actions —
see `v1_milestones.md` milestones 5–6.

## Publication and freshness

Collectors stage rows under a running collection attempt. Dashboard reads expose
only successful runs; `Repository.publish_run` validates completeness before the
single status update that makes a collection visible. Failed/staged rows remain
available for diagnosis but cannot affect prices, rates or displayed history.
Unchanged successful rechecks refresh verification time without duplicating prices.

Empty collections and collections missing previously accepted plan/rate identities
are rejected. This is deliberately conservative: genuine removals or renamed plans
require analyst review; automatic retirement is not implemented. First collections
cannot detect a plausible omitted plan without a source-specific expected inventory.
Existing historical successes are trusted, not retroactively revalidated.

VM and Object Storage pages show per-source latest attempt, successful verification,
and stale status (48-hour verification threshold, or latest attempt not successful).
A running attempt is provisionally marked stale until it completes.

## Price semantics

VM hourly observations are converted using `vm.monthly_hours`; original values
and periods remain preserved, with conversion hours recorded per observation
(schema v4). Legacy hourly rows without monthly normalization are excluded from
comparison until recollected. Unknown billing periods cannot supply monthly totals.
Liara collection requires a known IPv4 surcharge rather than silently using zero.

Object Storage scenario figures are subtotals excluding request charges and tax;
provider notes retain the approved billing-period/traffic assumptions and the
ParsPack storage-only caveat. They are not full equivalent purchase costs.
Progressive tariff intervals must be contiguous, ordered and nonoverlapping;
unknown rates, malformed intervals and uncovered consumption produce no price.
Only progressive tariffs are supported; volume tariffs require an explicit adapter.

## Regression checks and extraction cache

Collection cache keys include source settings, relevant runtime options, public YAML
configuration and collection/normalization/schema code. This intentionally favors
safe reprocessing over narrowly optimized invalidation: editing relevant code may
re-extract multiple providers on their next scheduled check. Credentials and `.env`
are never fingerprint inputs. Use mocked extraction for routine verification.

Audit regression tests cover mid-tab failure after staged writes, empty/suspect-only
results, omitted OS plans, preservation of accepted rates, stale sources, configuration
changes on unchanged content, monthly conversion and invalid tariff intervals.
Run the portable suite with `python -m pytest tests --ignore=tests/test_browser.py`;
browser-launch smoke tests remain separate and require installed browsers.

## Panel visual standard

VM and Object Storage share the VM chart design: one selected configuration, horizontal provider-labelled bars sorted cheapest first, colors by price basis, and a matching provider-row comparison table. Object Storage uses `?scenario=base|growth|pro|dedicated` pills; raw plans and tariffs remain below. Future panels follow this design unless explicitly overridden.
