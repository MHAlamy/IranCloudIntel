# V1 release milestones

Based on `PROJECT_GUIDE.md`; complete one milestone together at a time. Agreed change: develop directly on Windows; defer Linux and Docker execution to the Ubuntu server stage. This overrides the guide's WSL/local Docker setup.

**V1:** a private dashboard comparing official public VM, Object Storage and CDN prices across an agreed small set of Iranian providers, with daily collection, source evidence and price history. All prices are displayed and compared as **monthly Toman (Toman/month)**, with original values preserved. VM providers as implemented: **Arvan, Liara, ParsPack, Kubit** (Cloud.ir and Hamravesh dropped by owner decision; see `price_gathering_guide.md`).

**Status (2026-11-15):** Milestones 1–4 essentially complete — four VM sources collected/validated (Arvan bundles+rates with deterministic verification, Liara bundles, ParsPack calculator quotes, Kubit rate table; zero-LLM collection for three of four), SQLite history, matching engine, and the Persian RTL dashboard running at `http://localhost:8000`. Remaining for V1: Object Storage + CDN coverage, then deployment (M5) and automation (M6).

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

- [x] Finalize providers (VM: **Arvan, Liara, ParsPack, Kubit** — owner decisions 2026-11-15: Liara unreachable then restored and added; Kubit added as rates-only provider with gen-3→Economy, gen-4→Standard, no premium; **Cloud.ir removed from scope**; Hamravesh dropped earlier per `price_gathering_guide.md`). All four VM sources collected, validated and visualized.
- [x] Add all agreed VM sources with representative labeled fixtures; show resource, region, tier and included-charge differences explicitly. Display base monthly price in Toman/month. (Owner decisions 2026-11-15: Iran regions only; IPv4 included in the comparable price where the provider charges it separately — Arvan bundles include it, Kubit rates add 173,000, ParsPack quotes add a fixed 150,000, Liara adds its documented 200,000; Arvan's assumed 30% eco discount is labeled on economy rows.)
- [x] Run the web app and one-shot collector directly with Python; document PowerShell commands and use portable paths/configuration for later Linux deployment. — README documents commands; all paths/config are environment-portable.
- [x] Test collection and dashboard end to end, failed/partial extraction, concurrent-run locking and SQLite/evidence persistence after process restarts. — 114 tests; real e2e runs for all four providers.
- **Done when (VM part):** all agreed VM sources work natively on Windows and pass a manual pricing accuracy review. — **Met for VM 2026-11-15. Object Storage/CDN remain open.**

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
