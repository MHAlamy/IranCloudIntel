# Iranian Cloud Intelligence Dashboard

A personal competitive-intelligence dashboard for Iranian cloud services:
collects, validates and compares official public VM pricing across a small
set of providers, keeping historical observations and source evidence.

See `PROJECT_GUIDE.md` for the full specification, `price_gathering_guide.md`
for the collection/comparison methodology, `v1_milestones.md` for progress,
and `AGENTS.md` for agent working rules.

## Status (2026-11-15)

Milestones 1–4 essentially complete: four VM providers collected, validated
and visualized in a Persian RTL dashboard at `http://localhost:8000`.

| Provider | Collection mode | What the dashboard shows |
|---|---|---|
| ArvanCloud | Playwright (JS challenge) + LLM extraction (GPT-5-Mini via Arvan AIaaS) | Published bundles (3 tiers) verified against their PAYG rate table, plus calculated baseline prices |
| Liara | Plain HTTP, deterministic parser | Published fixed bundles (all four baselines match exactly; +200,000/mo documented IPv4) |
| ParsPack | Playwright drives their calculator | Baseline quotes (daily × 30 × 0.95 + fixed 150,000/mo IPv4) |
| Kubit | Plain HTTP, deterministic parser | Calculated from per-component rates (gen-3→Economy, gen-4→Standard) |

Every price row carries a basis badge: منتشرشده (published) / محاسبه‌شده
(calculated from documented rates) / تقریبی (nearest config) / در دسترس نیست.
Dates display in the Jalali calendar; all prices in monthly Toman; Iranian
regions only (owner decisions recorded in `v1_milestones.md` and
`price_gathering_guide.md`).

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

Object Storage + CDN coverage, then deployment to one Ubuntu VM (Docker
Compose, Nginx, HTTPS), scheduling, backups to Object Storage, and CI/CD via
GitHub Actions — see `v1_milestones.md` milestones 5–6.
