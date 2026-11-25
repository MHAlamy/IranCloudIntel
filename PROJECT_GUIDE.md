# Iranian Cloud Intelligence Dashboard

Current architecture, product scope and deployment direction. See
[MILESTONES.md](MILESTONES.md) for progress and [the pricing guide](price_gathering_guide.md)
for collection and comparison rules.

## Purpose and scope

A personal dashboard tracking Iranian cloud prices with auditable source evidence
and history. VM, Object Storage, PaaS/CNAP, DBaaS and KaaS panels exist. CDN is
planned separately and does not block the first Darkube launch. PaaS and DBaaS
are compute-shaped and reuse the VM observation table with `service_type='paas'`
and `service_type='dbaas'`; Liara is compared on its silver tier, while Hamravesh
and Arvan are calculated from
their published monthly resource rates. DBaaS compares two infrastructure
classes (local/premium and shared/network) over four shared reference sizes.
KaaS compares four offerings over six node-count scenarios; worker tariffs and
management-fee ladders are stored as component rates, and all totals are
calculated by `comparison/kaas_pricing.py`.

V2 may expand services and add reviewed AI-assisted scraper repairs. V3 may track
features from official documentation and later authorized read-only consoles.
Neither roadmap stage justifies extra infrastructure or autonomous production edits.

## Architecture

- Develop natively on Windows with Python and the project `.venv`; no WSL or
  local Docker required. Validate the Linux container on a Linux CI runner and
  verify disk and restart behavior in a Darkube test deployment.
- One Python application: HTTPX/BeautifulSoup for public pages, Playwright only
  where rendering or calculators require it, deterministic normalization and
  comparisons, configurable Arvan AIaaS for remaining unstructured extraction.
- Prefer structured public data, then deterministic parsing, then LLM extraction.
  No assumption that an endpoint supports structured output without verification.
- SQLite with versioned migrations, WAL and exact Decimal/text money; snapshots
  on disk. One-shot sequential collection, with an exclusive collection lock.
- FastAPI/Jinja2 and shared CSS, Persian RTL interface and Jalali display dates;
  UTC timestamps in storage. No separate frontend service or microservices.
- Product pages share a validated catalogue (`config/products.yaml`) and a
  three-section shell; schema v5 allows `service_type='paas'` for compute-shaped
  PaaS offerings while VM/OS keep their service-specific data rules. Schema v6
  adds manual (offline) sources with per-run document provenance. Schema v7
  allows `service_type='dbaas'`; DBaaS stores the infrastructure class and price
  basis in `product_family` (`dbaas_<class>_<basis>`). Schema v8 allows
  `service_type='kaas'`; KaaS keeps worker/fee components in `resource_rates`
  and gets its identical-worker, separate-fee Hamravesh v1/v2 offerings from
  `benchmarks.yaml` plus the collected tariff rows.
## Planned Darkube deployment

- **First launch:** One app, one replica. Use Darkube for HTTPS and verify that
  dashboard access is protected. Mount an app disk for SQLite, evidence and the
  collection lock. The disk is persistent across redeploys but node-local and
  not shared with a separate collector app. Expect brief downtime on updates.
- **Recovery from day one:** Keep consistent SQLite backups and copies of the
  evidence in private storage outside the app disk. Test restore separately from
  release rollback; rolling back the image doesn't undo database migrations.
- **Collect manually first:** Run the one-shot CLI from the app terminal. Then
  test one supervised scheduler in the same app, separate from the web process,
  using the same disk-backed lock as manual runs. Keep collection manual if the
  scheduler isn't reliable. No Redis or Celery is needed.
- **V2 storage:** Move collection evidence to private Object Storage. Keep SQLite
  unless separate apps or multiple web replicas justify moving to PostgreSQL.
  Object Storage integration is deferred; backups are not.

## Dashboard structure

- `/` is a static homepage titled «رصد بازار خدمات ابری ایران» with the subtitle
  «مقایسه‌ی قیمت، قابلیت‌ها و عملکرد محصولات ابری تأمین‌کنندگان ایرانی».
  It contains a layered IaaS/CaaS/PaaS product map — IaaS: VM, Object Storage,
  CDN, GPUaaS; CaaS: KaaS; PaaS: CNAP, DBaaS, DevOps tools, AIaaS — followed by
  a short methodology summary (official pages, structured sources, price
  catalogues, periodic automated performance checks, evidence and timestamps,
  unknown ≠ zero). Only products with a real page are links; all others are
  visibly disabled with «به‌زودی».
- Product pages exist at `/vm`, `/object-storage`, `/paas`, `/dbaas` and
  `/kaas`; `/status` shows source collection health and `/plan/{id}` shows one
  offering's history.
- Every product page has a centered product title, followed by three sections:
  1. «مقایسه قیمت» — all existing price content: selectors, the shared chart,
     the provider-row table, plan/rate details, legend and freshness.
  2. «مقایسه قابلیت‌ها» — a «به‌زودی» placeholder.
  3. «مقایسه عملکرد» — implemented for Object Storage (offline benchmark table
     plus its provenance notes); a «به‌زودی» placeholder on the VM, PaaS, DBaaS
     and KaaS pages.
  Sections without a data model stay explicit placeholders and must not
  fabricate data.
- The topbar brand links to the homepage; the nav links the implemented product
  pages and source status. The product catalogue and routes are defined in
  `config/products.yaml`; enabling a product requires a real route.

## Offline datasets

- Data that cannot be collected live — price-list PDFs and vendor benchmark
  reports — is transcribed into `datasets/offline/<source_id>/`, one folder per
  source document. Each package has a `manifest.json` (document, version,
  validity, per-file SHA-256, caveats, review status) and a `README.md`.
- The source documents themselves stay in `datasets/offline/_originals/`, which
  is gitignored because they may be confidential; only the transcription and its
  checksums are committed.
- Offline observations are not live observations. They keep `source_id` and
  `source_pdf_page` on every row, render with their document, version and
  validity date, and must never appear as freshly verified prices.
- Import is deterministic and reuses the normal run/observation path
  (`collectors/offline_pipeline.py`). Schema v6 allows `collection_method:
  manual` and stores `source_document`/`valid_until` on the run; the VM dashboard
  shows a «دستی» badge, the source document and the validity date for those rows.
  VM, Object Storage, DBaaS and KaaS imports all preserve this provenance.

## Reliability and operating constraints

- Record every collection attempt and preserve source evidence. Staged/failed
  rows never affect published prices. Publish only accepted complete results;
  retain last valid data on failure and show source freshness separately.
- Cache extraction only under matching content and code/config fingerprints.
  Fail visibly on empty results or missing previously accepted identities.
- Treat webpages as untrusted data. No login, resource purchase, access-control
  bypass or sensitive console content in V1. Respect source access/rate limits.
- Use fixture/mocked tests by default; bound and explicitly authorize paid calls.
  Log available usage/errors without credentials. Do not commit `.env`, databases,
  unsanitized evidence, cookies, SSH keys or backups.
- Obtain approval before billable resources/calls, production changes, data deletion,
  push/merge or deployment. Explain a step before implementing; report its checks.
- No employer infrastructure, credentials or private data are assumed available.
- Verify current prices, model availability and connectivity before provisioning;
  archived tariffs are planning history, never current quotations.

## Visual contract

VM is the visual reference for all panels unless explicitly overridden. Use the
shared `price_chart.html`, one selected scenario via pills, horizontal provider
labels, price-basis colors and cheapest-first bars scaled within that selection.
Place the chart above a provider-row table. Keep missing data, calculation basis,
subtotals, assumptions and freshness visible. Raw plan/rate details remain separate.

The homepage and product-page structure are defined in “Dashboard structure”
above; the visual rules here apply inside the price-comparison section.
