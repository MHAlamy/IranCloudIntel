# Project milestones

**Current status:** The dashboard runs locally on Windows and compares VM, Object
Storage, PaaS/CNAP, DBaaS and KaaS prices, with SQLite history, source evidence and
an offline Object Storage benchmark. Darkube deployment and scheduled collection
are not yet implemented.

## 1. Prepare the container

- [ ] Add a production Dockerfile and exclude secrets, databases, evidence and
  backups from the build context.
- [ ] On a Linux CI runner, run the offline tests and a synthetic Chromium smoke
  test against the container. No change to the Windows development setup.
- [ ] Make the web app and collector use the intended persistent paths. Run
  migrations before serving traffic and add a database-aware readiness check.

## 2. Launch on Darkube with manual collection

- [ ] Verify plan costs and connectivity. After approval, deploy one replica with
  a mounted app disk for SQLite, evidence and the collection lock. Keep automatic
  deployment off and verify HTTPS and protected dashboard access.
- [ ] Restore a consistent copy of the existing SQLite history and preserve its
  evidence. Verify that both survive a restart and a redeploy.
- [ ] Before relying on the deployment, test recovery from a private backup kept
  outside the app disk. Test release rollback separately from database recovery.
- [ ] After approval, run a bounded collection manually from the app terminal and
  verify the result, evidence and source status. Document the operating steps.

## 3. Automate collection after launch

- [ ] Verify a single supervised scheduler can run the existing one-shot collector
  daily alongside the web process in the same app. Set a timezone, bound runtime and
  spend, keep the disk-backed lock, and check logs and failure visibility. Keep
  collection manual if this setup isn't reliable.

## Later

- [ ] **V2 storage:** Move collection evidence to private Object Storage. Revisit
  PostgreSQL only if the collector needs its own app or the dashboard needs
  multiple replicas.
- [ ] **Product coverage:** Define CDN pricing scenarios and add collection and
  comparison. This is separate from the Darkube launch.
