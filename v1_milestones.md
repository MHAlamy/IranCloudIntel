# V1 release milestones

Based on `PROJECT_GUIDE.md`; complete one milestone together at a time. Agreed change: develop directly on Windows; defer Linux and Docker execution to the Ubuntu server stage. This overrides the guide's WSL/local Docker setup.

**V1:** a private dashboard comparing official public VM, Object Storage and CDN prices across an agreed small set of Iranian providers, with daily collection, source evidence and price history. All prices are displayed and compared as **monthly Toman (Toman/month)**, with original values preserved. The VM provider list is now agreed per `price_gathering_guide.md` (Arvan, Liara, ParsPack, Cloud.ir); model and deployment details remain open until verified.

## Current PC baseline

- Windows 11 Enterprise, approximately 24 GB RAM; about 168 GB free on C: at inspection.
- Git 2.54.0 works; VS Code 1.144.0 is installed. Python app aliases exist, but a usable Python installation remains unverified.
- WSL installed, but Ubuntu is absent and WSL2 setup encountered Windows component problems. Further WSL troubleshooting and Windows repairs are paused; neither is required for this development path.
- No application or Git repository exists here. Docker is not available on PATH and will not be installed locally for this plan.

## 1. Prepare local development

- [ ] Verify or install a supported native Windows Python version; create a project `.venv` and verify `python` and `pip` through it.
- [ ] Open this Windows workspace in VS Code, select the `.venv` interpreter and verify Git and PowerShell development commands.
- [ ] Create `.gitignore`, `.env.example`, concise `AGENTS.md` rules and a Python project with pinned dependencies; initialize Git and create/connect a private GitHub repository.
- **Done when:** Python, dependencies and a smoke test run natively on Windows; VS Code uses `.venv`, and secrets/data are excluded from Git.

## 2. Prove one pricing collector

- [x] Select one provider/service pricing page: **Arvan cloud-server pricing** (agreed; see `price_gathering_guide.md`). Verify Arvan AIaaS endpoint, authentication and available models — done: endpoint and `apikey` auth confirmed, 102 models listed, end-to-end inference tested (~46 tokens); structured-output support still to verify.
- [x] Store credentials in ignored `.env`; make one bounded API connectivity test and choose an initial configurable model using manually checked examples. — Done 2026-11-14: endpoint/auth/models verified, model set to `GPT-5-Mini`, gateway rate limit configured (50 req/5 min).
- [x] Implement HTTP fetching, Playwright rendering with independent capture of all three Arvan pricing tabs (per-tab snapshots and content hashes), and LLM extraction into a service-specific schema. — Done: JS challenge requires Playwright; all three Alpine panels are server-rendered in one DOM and parsed independently; per-tab snapshots saved.
- [x] Validate evidence, completeness, numbers, units and currency; normalize Persian numerals and Rial/Toman deterministically using exact money arithmetic. — Done: `normalization/` with Decimal arithmetic; unknown ≠ zero; suspect flagging.
- [x] Test saved fixtures and mocked responses, including malformed output and fetch failures; manually verify every extracted row and record token cost. — Done: 36 mocked tests; live extraction PASSED 8/8 vs hand-verified rows (2,210 tokens/call, ~4,420 total incl. one rerun after a reporting bug).
- **Done when:** one page produces accurate, evidence-backed prices and visible failures without invented values. — **Met 2026-11-14. Milestone 2 complete.**

## 3. Store history and build the dashboard

- [x] Add a versioned SQLite schema for providers, sources, runs, offerings and price observations, with source-evidence references. — Done: `storage/` (WAL, Decimal-text money, append-only history, skip-unchanged logic, raw values preserved); 48 tests pass. Dates stored UTC, displayed in Jalali/Tehran via `util/jalali.py`.
- [ ] Add versioned analyst-maintained YAML configuration (`tiers.yaml`, `benchmarks.yaml`) defining the three normalized VM tiers (Economy/Standard/Premium) and the four reference sizes (1/2/20, 4/8/80, 16/32/320, 32/64/640 GB), validated on startup.
- [ ] Save valid observations transactionally; retain last valid prices on failure. Track last checked, last successfully verified, errors and extraction versions.
- [ ] Skip extraction for unchanged successful content under the same extractor configuration; reprocess failed or changed configurations and support forced verification.
- [ ] Build FastAPI/Jinja2 comparison tables showing specifications, original/normalized prices, units, provider links, timestamps, stale/uncertain/missing states, tier/size selectors and exact-versus-approximate matching distinctions. All prices displayed in monthly Toman (hourly sources converted with the configurable 730-hour month and labeled as standardized equivalents).
- **Done when:** the local dashboard shows current prices and stored history; failed runs preserve valid data and expose stale status.

## 4. Complete V1 coverage on Windows

- [ ] Finalize providers (VM: **Arvan, Liara, ParsPack, Cloud.ir** — Hamravesh dropped per `price_gathering_guide.md`), official URLs and schemas for VM, Object Storage and CDN; configure only offerings that actually exist.
- [ ] Add all agreed sources, service-specific component comparisons and representative labeled fixtures; show resource, region, tier and included-charge differences explicitly. Display base monthly price and an optional comparable cost including one public IPv4, with bundled IPv4 never double-charged and unknown totals marked unknown rather than zero.
- [ ] Run the web app and one-shot collector directly with Python; document PowerShell commands and use portable paths/configuration for later Linux deployment.
- [ ] Test collection and dashboard end to end, failed/partial extraction, concurrent-run locking and SQLite/evidence persistence after process restarts.
- **Done when:** all agreed sources work natively on Windows and pass a manual pricing accuracy review.

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
