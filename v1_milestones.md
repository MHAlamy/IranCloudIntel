# V1 release milestones

Based on `PROJECT_GUIDE.md`; complete one milestone together at a time. Agreed change: develop directly on Windows; defer Linux and Docker execution to the Ubuntu server stage. This overrides the guide's WSL/local Docker setup.

**V1:** a private dashboard comparing official public VM, Object Storage and CDN prices across an agreed small set of Iranian providers, with daily collection, source evidence and price history. All prices are displayed and compared as **monthly Toman (Toman/month)**, with original values preserved. VM providers as implemented: **Arvan, Liara, ParsPack, Kubit** (Cloud.ir and Hamravesh dropped by owner decision; see `price_gathering_guide.md`).

**Status (2026-11-15/16):** Milestones 1–4 essentially complete — four VM sources collected/validated (Arvan bundles+rates with deterministic verification, Liara bundles, ParsPack calculator quotes, Kubit rate table; zero-LLM collection for three of four), SQLite history, matching engine, and the Persian RTL dashboard running at `http://localhost:8000`. **Object Storage first version live (2026-11-16):** all four OS providers collected and compared at `/object-storage` — Hamravesh (baseline, published plans), Arvan (PAYG-calculated), Kubit (free base plan + PAYG tables, deterministic HTTP, 0 tokens), ParsPack (storage-only calculator quotes, Playwright, 0 tokens). Remaining for V1: CDN coverage, then deployment (M5) and automation (M6).

## Audit remediation ? publication and freshness (2026-11-16)

- [x] Stage collection writes and atomically publish through successful run status; hide failed/running observations and rates from dashboard reads and history.
- [x] Reject empty results and missing previously accepted identities; preserve last accepted prices. Genuine removals require analyst review.
- [x] Show latest attempt, successful verification and stale status on both comparison panels; unchanged rechecks refresh verification.
- [x] Regression checks for cross-connection visibility, incomplete/empty attempts, failed fallback and unchanged recovery. Full non-browser suite: 159 passed.
- No live collection or migration of the existing runtime database performed. Earlier successful runs remain trusted.

## Current PC baseline

- Windows 11 Enterprise, ~24 GB RAM; native **Python 3.14.6** (via `py` launcher) with project `.venv`; Git 2.54; VS Code with the `.venv` interpreter configured.
- WSL2 unusable on this machine — irrelevant: everything (collection incl. Playwright, dashboard, tests) runs natively on Windows. Playwright uses the bundled Chromium (installed via the npmmirror CDN because the official one is geo-blocked) or system Edge via `BROWSER_CHANNEL=msedge`.
- Private GitHub repository: `https://github.com/MHAlamy/IranCloudIntel` (branch `main`, all work pushed).
- Local runtime artifacts (never committed): `data/cloud_intel.db` (SQLite), `evidence/` snapshots, `.env` (Arvan AIaaS key).

## 1. Prepare local development — ✅ DONE 2026-11-14

- [x] Verify or install a supported native Windows Python version; create a project `.venv` and verify `python` and `pip` through it. — Native Python 3.14.6 via the `py` launcher; `.venv` created and verified.
- [x] Open this Windows workspace in VS Code, select the `.venv` interpreter and verify Git and PowerShell development commands. — `.vscode/settings.json` uses a relative interpreter path; Git 2.54 verified.
- [x] Create `.gitignore`, `.env.example`, concise `AGENTS.md` rules and a Python project with pinned dependencies; initialize Git and create/connect a private GitHub repository. — Private repo `MHAlamy/IranCloudIntel`, all work pushed.
- **Done when:** Python, dependencies and a smoke test run natively on Windows; VS Code uses `.venv`, and secrets/data are excluded from Git. — **Met 2026-11-14. Milestone 1 complete.**

## 2. Prove one pricing collector

- [x] Select one provider/service pricing page: **Arvan cloud-server pricing** (agreed; see `price_gathering_guide.md`). Verify Arvan AIaaS endpoint, authentication and available models — done: endpoint and `apikey` auth confirmed, 102 models listed, end-to-end inference tested (~46 tokens); structured-output support still to verify.
- [x] Store credentials in ignored `.env`; make one bounded API connectivity test and choose an initial configurable model using manually checked examples. — Done 2026-11-14: endpoint/auth/models verified, model set to `GPT-5-Mini`, gateway rate limit configured (50 req/5 min).
- [x] Implement HTTP fetching, Playwright rendering with independent capture of all three Arvan pricing tabs (per-tab snapshots and content hashes), and LLM extraction into a service-specific schema. — Done: JS challenge requires Playwright; all three Alpine panels are server-rendered in one DOM and parsed independently; per-tab snapshots saved.
- [x] Validate evidence, completeness, numbers, units and currency; normalize Persian numerals and Rial/Toman deterministically using exact money arithmetic. — Done: `normalization/` with Decimal arithmetic; unknown ≠ zero; suspect flagging.
- [x] Test saved fixtures and mocked responses, including malformed output and fetch failures; manually verify every extracted row and record token cost. — Done: 36 mocked tests; live extraction PASSED 8/8 vs hand-verified rows (2,210 tokens/call, ~4,420 total incl. one rerun after a reporting bug).
- **Done when:** one page produces accurate, evidence-backed prices and visible failures without invented values. — **Met 2026-11-14. Milestone 2 complete.**

## 3. Store history and build the dashboard

- [x] Add a versioned SQLite schema for providers, sources, runs, offerings and price observations, with source-evidence references. — Done: `storage/` (WAL, Decimal-text money, append-only history, skip-unchanged logic, raw values preserved); 48 tests pass. Dates stored UTC, displayed in Jalali/Tehran via `util/jalali.py`.
- [x] Add versioned analyst-maintained YAML configuration (`tiers.yaml`, `benchmarks.yaml`) defining the three normalized VM tiers (Economy/Standard/Premium) and the four reference sizes (1/2/20, 4/8/80, 16/32/320, 32/64/640 GB), validated on startup. — Done: plus `providers.yaml` source registry and `config/loader.py` startup validation.
- [x] One-shot collector CLI (`collectors/cli.py`): fetch → clean → combined content hash → skip-unchanged check → per-tab LLM extraction → validation → persistence, with run lock, evidence snapshots, suspect-row review queue and token accounting. Mock-tested (63 tests); first real e2e run pending owner approval.
- [x] Save valid observations transactionally; retain last valid prices on failure. Track last checked, last successfully verified, errors and extraction versions. — Done: `storage/repository.py` (append-only history; failed runs record attempts but never touch observations).
- [x] Skip extraction for unchanged successful content under the same extractor configuration; reprocess failed or changed configurations and support forced verification. — Done: content-hash + extractor-config-hash skip logic, verified in production (second Arvan run: 0 tokens, 0 LLM calls).
- [x] Build FastAPI/Jinja2 comparison tables showing specifications, original/normalized prices, units, provider links, timestamps, stale/uncertain/missing states, tier/size selectors and exact-versus-approximate matching distinctions. All prices displayed in monthly Toman (hourly sources converted with the configurable 730-hour month and labeled as standardized equivalents). — **Done 2026-11-15:** Persian RTL dashboard at `localhost:8000` (`app/`, Vazirmatn font, dark Hamravesh-style theme), VM view with tier/size selectors, plan-detail history and status pages, Jalali dates, pending-provider placeholders.
- [x] Rate-table extraction + bundle verification (owner decision 2026-11-15): parse Arvan's PAYG rate table deterministically, store as `resource_rates`, verify every bundle against documented rates in code; AIaaS used only for label interpretation and mismatch diagnosis (review-only). Iran regions only; IPv4 not added on top of bundles (already included).
- **Done when:** the local dashboard shows current prices and stored history; failed runs preserve valid data and expose stale status.

## 4. Complete V1 coverage on Windows

- [x] Finalize providers (VM: **Arvan, Liara, ParsPack, Kubit** — owner decisions 2026-11-15: Liara unreachable then restored and added; Kubit added as rates-only provider with gen-3→Economy, gen-4→Standard, no premium; **Cloud.ir removed from scope**; Hamravesh dropped earlier per `price_gathering_guide.md`). All four VM sources collected, validated and visualized. **Owner decision 2026-11-15 (later same day): Liara and ParsPack moved from Standard to Economy** in `config/tiers.yaml` — stored raw tier labels unchanged; the Standard view now contains only Arvan and Kubit gen-4.
- [x] Add all agreed VM sources with representative labeled fixtures; show resource, region, tier and included-charge differences explicitly. Display base monthly price in Toman/month. (Owner decisions 2026-11-15: Iran regions only; IPv4 included in the comparable price where the provider charges it separately — Arvan bundles include it, Kubit rates add 173,000, ParsPack quotes add a fixed 150,000, Liara adds its documented 200,000; Arvan's assumed 30% eco discount is labeled on economy rows.)
- [x] Run the web app and one-shot collector directly with Python; document PowerShell commands and use portable paths/configuration for later Linux deployment. — README documents commands; all paths/config are environment-portable.
- [x] Test collection and dashboard end to end, failed/partial extraction, concurrent-run locking and SQLite/evidence persistence after process restarts. — 114 tests; real e2e runs for all four providers.
- **Done when (VM part):** all agreed VM sources work natively on Windows and pass a manual pricing accuracy review. — **Met for VM 2026-11-15. Object Storage/CDN remain open.**
- **Object Storage first version — DONE 2026-11-16 (Arvan + Hamravesh):**
  - Owner decisions: Hamravesh's published plans are the comparison baseline; intended OS provider set is Arvan, Hamravesh, Kubit, ParsPack (latter two pending).
  - Schema v3 (`storage/migrations/v3__object_storage.sql`): service-specific `os_observations` (plan_status priced/free/quote_only, storage/traffic allowances, overage rates) and `os_rates` (tiered PAYG rows with parsed GB bounds); plan identity still via the generic `offerings` table.
  - Sources: `arvan_object_storage` (Playwright + one bounded LLM call: 1,981/803 tokens first run) and `hamravesh_object_storage` (Playwright with client-side tab click; fully deterministic, 0 tokens).
  - Deterministic cross-check of LLM plan rows against Arvan's own comparison matrix; findings go to `review_queue.json` — it caught a real page inconsistency: Arvan's سازمانی card claims unlimited requests while its matrix says ۱۰۰٬۰۰۰.
  - Arvan's FAQ overage figures (1,400/GB storage, 850/GB traffic) contradict its rate table (3,600/965): both are stored and the dashboard shows a deterministic review banner instead of silently choosing one.
  - Assumptions visible in the dashboard notes: TB=1024 GB (configurable); Arvan PAYG rates treated as monthly (the page states no billing period); request charges excluded from scenarios (Hamravesh publishes no request allowance).
  - 150 tests total (36 new), all mocked; live dashboard at `localhost:8000/object-storage`.
- **Object Storage Kubit + ParsPack — DONE 2026-11-16 (all four OS providers now covered):**
  - `kubit_object_storage` (static HTTP, 0 tokens): free base plan with explicitly zero quotas recorded as a valid source claim; the negotiable plan (توافقی/قابل مذاکره) normalizes as suspect and goes to review, never silently recorded. PAYG tables parsed deterministically with chained tier bounds (تا X → 0..X, مازاد تا X continues from the previous bound, بیش از X unbounded).
  - Scenario traffic for Kubit = egress outside the location (خروجی خارج موقعیت, 750/GB) — explicitly chosen as the analog of the baseline's unspecified «ترافیک», labeled on the dashboard; ingress, inside-egress and request charges excluded. Kubit's 10% VAT note stored as a dashboard note.
  - `parspack_object_storage` (Playwright calculator, 0 tokens): no published bundles; the calculator prices storage only. Owner-selected configuration: HDD, ایران, ۱ ماهه. All 18 slider stops recorded as storage-only observations (no traffic allowance; caveat shown on the dashboard). Interaction quirks documented in the collector: radios need JS `click()`, the slider is disabled until options are chosen and must be walked with keyboard arrows.
  - Dashboard generalized to N providers from `providers.yaml`: scenario columns per provider, per-provider plan tables and PAYG rate sections, one legend. Cell precedence: exact published bundle → PAYG calculation → exact storage-only quote → nearest larger quote marked تقریبی with its real capacity.
  - Kubit calculated scenario totals (live): پایه ۵۷۰٬۰۰۰ · رشد ۲٬۸۸۶٬۰۰۰ · حرفه‌ای ۲۹٬۱۸۴٬۰۰۰ · اختصاصی ۲۷۹٬۵۵۲٬۰۰۰. ParsPack: exact quotes at 100/500 GB, تقریبی above.
  - 162 tests total (9 new), all mocked; both sources collected live against the real DB.

## 5. Deploy to one VM

- [ ] Verify current costs, VM capacity and connectivity to pricing sites, AIaaS, GitHub and GHCR; choose an accessible deployment alternative if required.
- [ ] Provision one Ubuntu Arvan VM only after the local prototype works; configure SSH keys, administrative/deployment users, firewall and updates.
- [ ] Add a Dockerfile and Compose services for the web app and one-shot collector, with persistent SQLite/evidence storage, health checks and bounded resource/log usage.
- [ ] Install Docker/Compose on the VM; build and test the Linux containers against fixtures and an isolated test database before production use. Verify browser dependencies, paths, file permissions, locking and data persistence after container recreation.
- [ ] Deploy persistent storage and separate production secrets. Configure Nginx, HTTPS and private or authenticated dashboard access.
- [ ] Perform the first deployment manually; verify health, collection and persistence, and document the commands.
- **Done when:** the protected dashboard works on the VM and retains data across a restart/redeployment.

## 6. Automate collection, backups and releases

- [ ] Schedule daily collection and consistent SQLite backups with cron, explicit timezone, locking, timeouts and limited retries.
- [ ] Upload backups and source evidence to private Arvan Object Storage with retention limits; restore a backup into an isolated local environment.
- [ ] Expose collection failures, stale sources, backup freshness, disk/RAM usage and API spending; add a spend limit or alert and a documented collector stop procedure.
- [ ] Configure GitHub Actions for lint/tests/build checks, reviewed merges, immutable image publishing and serialized SSH deployment with health checks and rollback.
- [ ] Back up before migrations; test deployment rollback separately from database recovery and document both procedures.
- **Done when:** scheduled collection succeeds, failures are visible, a backup restore succeeds, and a tested release/rollback preserves historical data.

## V1 release gate

- [ ] All agreed sources update automatically and pass manual accuracy checks against labeled examples.
- [ ] Failed collection preserves evidence and last valid prices with clear stale status.
- [ ] Production access is protected; history survives releases; backup restoration and release rollback have been demonstrated.
- [ ] README documents local setup, deployment, routine operation and recovery.

**Working agreement:** before each step, describe exactly what will be checked, installed or changed; wait for confirmation, then implement and report results. Obtain explicit approval for installations/system changes, credentials changes, paid calls/resources, pushes/merges and production deployment. Keep V2 scraper repair and V3 feature/console monitoring outside this release.

- [x] Audit item 2: monthly VM conversion with persisted basis (schema v4), strict progressive tariffs, unknown IPv4 handling and OS subtotal warnings. Local fixtures only; production DB not migrated.

- [x] Audit item 3: regression coverage for failed/partial/empty extraction, stale sources, missing tariff intervals and cache invalidation on parser/config changes. Conservative fingerprints and suspect-only publication guards added.

- [x] Visual consistency: VM and Object Storage share the VM chart template; OS selects one scenario and uses provider-row tables. Basis colors and cheapest-first bars are the default for future charts.
