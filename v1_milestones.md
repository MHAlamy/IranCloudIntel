# V1 milestone tracker

**Status (2026-11-17):** native Windows development; four VM sources and four
Object Storage sources implemented, plus Sotoon VM and Object Storage (HiCap)
from a manually imported price list. PaaS/CNAP added with three sources
(Hamravesh Darakub, Arvan PaaS, Liara silver). The homepage layered product map
and the shared three-section product shell are implemented. CDN, production
deployment and automation remain open. Audit actions 1-4 completed; action 5
documentation/tooling cleanup completed. Historical detail is preserved in
`docs/archive/2026-11-16_v1_milestones.md`.

- [x] 1. Local environment: Python 3.14, `.venv`, Git, VS Code and private repository.
- [x] 2. First collector: Arvan public VM page, evidence, LLM extraction and fixtures.
- [x] 3. SQLite history, comparison logic, source status and Persian dashboard.
- [ ] 4. V1 coverage: VM, OS and PaaS/CNAP complete; CDN remains to implement.
- [ ] 5. Deploy one Ubuntu VM: verify pricing/connectivity, approve provisioning,
  configure SSH/firewall, Docker/Compose, persistent data, secrets, Nginx/HTTPS
  and protected access. Test Linux collectors/containers, health and persistence.
- [ ] 6. Operations/releases: daily locked collection, consistent SQLite backups,
  private Object Storage retention, restore test, resource/failure/spend monitoring,
  then CI image publishing, serialized deployment, health checks and rollback.

## Audit remediation

- [x] 1. Atomic accepted-run publication, completeness gates and freshness display.
- [x] 2. Monthly conversion basis, tariff validation and explicit unknown/subtotal costs.
- [x] 3. Failure/partial/empty/cache/stale regressions and conservative invalidation.
- [x] 4. Service-specific boundaries, shared collection helpers and observable waits.
- [x] 5. Concise active docs/code map, archived one-offs, unified read-only inspection,
  explicit runtime/dev dependencies and opt-in browser smoke tests.
- [x] VM/OS visual consistency using a shared chart template and selected scenarios.

## Post-audit additions

- [x] Homepage with a layered IaaS/CaaS/PaaS product map and method summary;
  only implemented products link, the rest are disabled with «به‌زودی».
- [x] Shared three-section product shell: price comparison, capabilities and
  performance placeholders. Product pages use a centered product title.
- [x] PaaS/CNAP comparison: four compute selections, Liara silver, Hamravesh
  Darakub and Arvan calculated from published monthly resource rates.
- [x] Sotoon VM from an offline price list: schema v6 manual sources, Neda
  datacenter, dedicated/shared mapped to Premium/Standard, reference sizes built
  from the 1 vCPU + 2 GB unit plus the دیسک مانا نوع ۲ (premium) disk, with
  document/validity provenance in the UI.
- [x] Offline benchmark package keeps only the long-format table; wide provider
  pivots are built in code (`comparison/benchmarks.py`).
- [x] Sotoon Object Storage (HiCap, Neda) imported as manual rates: capacity,
  nine egress bands and requests; scenarios carry a low-end request estimate and
  the row is marked «دستی» with document and validity.
- [x] Sotoon CDN offload: a second Sotoon result prices only 20% of scenario
  traffic (80% served through Sotoon CDN, not billed as storage egress), with
  the assumption explained in both rows.

## Release gates

- [ ] Agreed VM/OS/PaaS/CDN sources update daily with checked accuracy and visible failures.
- [ ] Price history survives releases; protected access and restore are demonstrated.
- [ ] Deployment rollback and database recovery are tested/documented separately.
- [ ] Runbooks cover setup, migrations, operations, spending and collector shutdown.

Work one agreed step at a time. Explain actions, obtain confirmation, implement,
and report validation/limitations. No paid calls/resources, production changes,
push/merge, data deletion or deployment without explicit authorization.
See `AUDIT_HANDOFF.md` for audit changes/limits and `docs/CODE_MAP.md` for code lookup.

Audit cleanup validation: 183 default tests passed (4 browser tests deselected); two synthetic browser tests passed separately. Dependency consistency check passed. No paid/provider collection or deployment performed.

Current validation (2026-11-17): 234 default tests passed (4 browser tests deselected). Sotoon VM and Object Storage prices imported from the offline package with no network calls and no LLM.
