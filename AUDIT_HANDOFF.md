# Audit changes — agent handoff

## Completed

- Publication/freshness (`ff52d71`): collectors publish through one accepted-run
  status change. Running/failed observations and rates are hidden; incomplete or
  empty results preserve accepted data. Both panels show attempts, verification
  and a 48-hour stale threshold. Historical successful runs remain trusted.
- Price semantics (`a2fe33a`): schema v4 records hourly-to-monthly conversion
  hours, preserving original inputs. Invalid progressive tariffs return unknown;
  unknown Liara IPv4 blocks a comparable price. OS totals are explicit subtotals.
- Regression/cache work (`c77fe56`): failure after staged writes, empty/suspect
  results, stale sources and omitted OS plans are covered. Public config and
  collection code changes invalidate extraction caches conservatively.
- Visual consistency (`0b02152`): VM and OS share `price_chart.html`; select one
  scenario, color by price basis, sort chart prices cheapest first. OS uses
  provider-row comparison tables. Persian labels were repaired.
- Audit item 4: service view builders moved to `app/vm_view.py`, `os_view.py`
  and `status_view.py`; pure tariff arithmetic is in `comparison/tariffs.py`.
  `app/data.py` remains a compatibility facade.
- Collection orchestration is in `collectors/vm_pipeline.py` and `os_pipeline.py`;
  `pipeline.py` is a compatibility facade. Shared types, attempt/evidence/failure
  handling live in `common.py`; acquisition dispatch is in `fetching.py`.
- Runtime modules no longer patch `sys.path`. Use `python -m` entry points.
- Browser collection waits for markers, selected controls, resource labels and
  changed quotes instead of fixed settle sleeps. Bounded 100ms polling remains.
  Local delayed-calculator smoke tests verify both VM and OS state/price updates.

## Operational notes

- No paid calls or provider collection were run for the audit changes. Tests use
  isolated databases; never use the live DB for test seeding.
- Genuine plan removals/renames require analyst review. A first collection still
  needs a source-specific inventory to detect plausible omissions. Volume tariffs
  and full OS cost equivalence are not implemented.
- Code/config changes can cause fresh paid extraction at the next collection.
- The local server was previously restarted with a SQLite backup after stale
  Python code and new templates caused HTTP 500. Restart it after code changes
  unless using Uvicorn `--reload`; do not start another server on the same port.
- Provider-site compatibility of revised waits still requires an explicitly
  authorized live check. Local browser smoke tests do not establish that.

Item 4 validation: 177 non-browser tests passed, plus 2 synthetic local browser tests (no provider requests).
