# Offline datasets

Versioned, hand-transcribed observations taken from documents instead of live
pages. They are inputs for the dashboard, not runtime state: they live here
rather than in `data/` (local database) or `evidence/` (fetched snapshots),
because they are small, reviewable and belong in Git.

## Rules

- **Offline is not live.** Every package records the document, its version and
  its validity window. Offline prices must never render as freshly verified
  prices; the dashboard shows them with their source document and date.
- **Transcription, not OCR.** Values were read from the rendered documents and
  checked by hand. Each package carries `manual_review_status`; nothing is
  published while it is `draft_for_user_verification`.
- **Provenance is preserved.** Every row keeps `source_id` and the one-based
  `source_pdf_page`. Do not strip them when loading.
- **Originals stay local.** `_originals/` is gitignored because the source
  documents may be confidential. Only the transcription and its checksum are
  committed.
- **No LLM needed.** These files are already structured; loading them is
  deterministic parsing, so they never trigger a model call.
- **Currency is explicit.** Sotoon prices are IRR; the canonical dashboard unit
  is monthly Toman (IRR / 10). Never mix rial and toman in one column.

## Packages

| `source_id` | Kind | Provider(s) | Feeds |
|---|---|---|---|
| `sotoon-price-1405-v3` | price catalogue | Sotoon | VM prices (imported); OS, KaaS, DBaaS, CDN prices (available, not imported) |
| `object-storage-benchmark-v6` | benchmark report | Hamravesh, Arvan, Sotoon, Kubit | Object Storage performance and capabilities |

## Layout

```
datasets/offline/<source_id>/
  manifest.json     source document, version, validity, file checksums, caveats
  README.md         what the package contains and what to review
  <kind>/           the CSVs, grouped by what they measure
```

No derived files are stored: wide or pivoted tables are presentation and are
built in code from the long-format source, so there is one source of truth.

Adding a package means creating one folder named after its `source_id`, a
`manifest.json` with real checksums, a `README.md`, and a row in the table above.
A newer version of the same document gets a new `source_id` (for example
`sotoon-price-1406-v1`) so history stays comparable.
