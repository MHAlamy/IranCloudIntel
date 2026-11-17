# Iranian Cloud Intelligence Dashboard

Personal public-price intelligence for Iranian cloud services, with source evidence,
SQLite history and a Persian RTL dashboard. VM, Object Storage and PaaS/CNAP are
implemented; CDN and production operations remain unfinished. See
`v1_milestones.md` for status.

## Develop on Windows

Python 3.14 and Git; no WSL or local Docker. From the repository root:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Open `/` for the homepage product map, `/vm`, `/object-storage`, `/paas` or
`/status`. Restart an already-running server before using changed Python code
unless it was launched with `--reload`.
Repository initialization applies pending migrations; back up persistent data
before running a newer release. Do not use the real database for test seeding.
Production images will install `requirements.txt`; dev requirements add pytest.

## Dashboard structure

- `/` is a static homepage: title «رصد بازار خدمات ابری ایران», a subtitle
  explaining the price/capabilities/performance comparison, a layered
  IaaS/CaaS/PaaS product map, and a methodology summary. VM, Object Storage and
  CNAP are links; CDN, GPUaaS, KaaS, DBaaS, DevOps tools and AIaaS are disabled
  with «به‌زودی».
- `/vm`, `/object-storage` and `/paas` share one shell: a centered product title,
  then «مقایسه قیمت» (selectors, shared chart, provider-row table, details,
  freshness), «مقایسه قابلیت‌ها» and «مقایسه عملکرد». Capability comparison is a
  «به‌زودی» placeholder everywhere; Object Storage has the first performance
  section (offline benchmark table and notes), while VM and PaaS keep the
  placeholder.
- `/status` shows collection health and `/plan/{id}` shows one offering's
  history. The catalogue and routes live in `config/products.yaml`; a product
  becomes a link only when it has a real page.

## Tests and inspection

Default pytest runs deterministic/offline tests; browser launches are opt-in:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -q
.\.venv\Scripts\python.exe -m pytest -m browser tests/test_waits.py
.\.venv\Scripts\python.exe -m scripts.inspect_data summary
.\.venv\Scripts\python.exe -m scripts.inspect_data runs --limit 10
```

Browser tests use synthetic local pages (no provider or API calls); they require
an installed browser. `tests/test_browser.py` also has an explicit Edge smoke test.
`BROWSER_CHANNEL=msedge` selects Edge; otherwise use bundled Chromium. The current
machine used a mirror for the Chromium download; deployment must verify its own
browser installation. Do not repeat downloads or run archived scripts casually.
The inspection CLI opens SQLite read-only and does not migrate or collect.

## Collection and data

Copy `.env.example` to ignored `.env` and configure credentials privately. A live
collection is deliberate: Arvan may call a paid LLM, and code/config changes can
invalidate cached extraction. After approval:

```powershell
.\.venv\Scripts\python.exe -m collectors.cli --source liara_vm_cloud_server
```

Omitting `--source` collects all enabled sources; `--force` bypasses cache skipping.
Config: `providers.yaml`, `tiers.yaml`, `benchmarks.yaml`, `rate_mappings.yaml`,
`analyst_facts.yaml`, `products.yaml`. Runtime artifacts: ignored `.env`, `data/`,
`evidence/`.
Do not commit secrets, evidence or databases. Use exact Decimal/text money.

Accepted-run publication hides running/failed rows. Empty/incomplete results retain
last accepted prices; source verification becomes stale after 48 hours or a failed
latest attempt. Genuine plan removal/renaming requires review. Schema v5 adds the
PaaS service type; schema v4 records hourly conversion hours. OS and PaaS totals
remain partial and assumption-dependent: Liara silver is a published plan price,
while Hamravesh Darakub and Arvan PaaS are calculated from monthly resource rates.

## Documentation and visual design

`PROJECT_GUIDE.md` describes architecture and dashboard structure;
`price_gathering_guide.md` governs pricing. `docs/CODE_MAP.md` maps tasks to
code/tests; `AUDIT_HANDOFF.md` records audit work. Archived docs/scripts preserve
history but are not routine context or entry points.

All three product pages share `price_chart.html`: one selected scenario,
provider-labelled bars, price-basis colors, cheapest-first chart and a
provider-row table, inside the price-comparison section. Future products use the
same shell and VM visual standard unless the user explicitly requests otherwise.
