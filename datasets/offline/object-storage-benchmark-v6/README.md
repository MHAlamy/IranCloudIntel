# Object Storage benchmark, four Iranian providers (v6)

Structured observations from a Persian benchmark report (report version 6,
1405-07) measured with MinIO Warp. This package is the first data source for the
Object Storage «مقایسه عملکرد» and «مقایسه قابلیت‌ها» sections.

- **`source_id`**: `object-storage-benchmark-v6`
- **Providers**: Hamravesh (HS3 / SeaweedFS), Arvan (ir-thr-at1 / Ceph RGW),
  Sotoon (archive.thr1 / Ceph RGW), Kubit (s3.afra.kubit.cloud / Ceph RGW)
- **Review status**: `draft_for_user_verification` in `manifest.json`.

## Files

| File | Page | Contents |
|---|---|---|
| `benchmark/observations.csv` | 3–14 | Long format: one row per `run_id`, provider, workload, metric, object size, aggregation (214 rows) |
| `benchmark/capabilities.csv` | 15–16 | S3 API compatibility matrix, one row per provider and capability (44 rows) |

`manifest.json` holds the run conditions, metric definitions, provider aliases
and comparability rules. Read `conditions_by_run` before plotting anything.

Wide, one-column-per-provider tables are **built in code** from
`observations.csv` (`comparison/benchmarks.py`). No derived CSV is committed, so
there is a single source of truth and nothing to drift.

## This is not one controlled experiment

The four providers were **never measured together**:

| `run_id` | Date | Participants |
|---|---|---|
| `2026-07-23-hs3-direct-v-proxy` | 2026-07-23 | Hamravesh direct vs international proxy (network-path only) |
| `2026-08-12-put-arvan-hs3` | 2026-08-12 | Hamravesh, Arvan (PUT) |
| `2026-08-13-arvan-hs3` | 2026-08-13 | Hamravesh, Arvan (GET/MIXED/LIST/STAT/DELETE) |
| `2026-08-23-24-sotoon-hs3` | 2026-08-23/24 | Hamravesh, Sotoon |
| `2026-08-24-put-size-sweep` | 2026-08-24 | Hamravesh, Sotoon (64 KiB / 512 KiB / 4 MiB) |
| `2026-09-27-trio` | 2026-09-27 | Hamravesh, Sotoon, Kubit |
| `2026-09-27-put-size-sweep` | 2026-09-27 | Hamravesh, Sotoon, Kubit (64 KiB / 4 MiB) |
| `2026-09-27-diagnostics` | 2026-09-27 | Kubit spot checks |

Arvan values come from August, everything else from September. A four-provider
chart is a **display** of cross-session data, not a ranking; filter by `run_id`
for a valid within-session comparison, and never compute a global winner.

## Known comparability traps

- Sotoon was measured on an archive-labelled endpoint and a cold bucket, so its
  tier is not the same as the other providers' standard storage.
- Arvan LIST produced 23 `SlowDown` errors, and the report later corrected
  Arvan LIST p50 latency from ~3243 ms to ~575 ms from raw traces.
- Warp text percentiles were found to be biased; section 9.5 corrections apply.
- The 27 Sep GET result (~19.6 MiB/s) is near the client's bandwidth ceiling,
  so it measures the client, not the provider.
- `Hamravesh HS3 (direct)` and `(via proxy)` are one provider, not two.

## Before ingestion

- Normalize the metric vocabulary: 28 labels currently mix base metrics with
  run-level aggregates (`throughput_run_min`) and one-off diagnostics
  (`list_empty_bucket_latency_p50_low`).
- Six rows have an empty `object_size`; define how such rows are identified.
- Arvan capability rows are mostly `not_tested` or `blocked_by_account`. Show
  them as unknown, never as unsupported.
- The wide provider table is a display pivot, not stored data; build it from
  `observations.csv` and pick each provider's run explicitly.

The original PDF is not committed. Its path and SHA-256 are recorded in
`manifest.json` under `original_document`.
