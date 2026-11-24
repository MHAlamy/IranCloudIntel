# Price gathering and comparison contract

Current pricing rules; overrides `PROJECT_GUIDE.md` on pricing methodology.
Historical discussion is preserved in `docs/archive/`; do not load it by default.
Source URLs/navigation: `config/providers.yaml`. Analyst decisions: YAML config.

## Acquisition and acceptance

- Prefer accessible official structured data, then HTTP/parsing, then Playwright;
  use an LLM only for content not already reliably structured. Never invent data.
- VM: Arvan browser + LLM bundles and deterministic rates; Liara HTTP bundles;
  Kubit HTTP component rates; ParsPack browser calculator quotes. Cloud.ir is out.
- OS: Hamravesh browser/matrix baseline, Arvan browser + LLM cards/deterministic
  PAYG, Kubit HTTP PAYG, ParsPack browser storage-only quotes.
- PaaS/CNAP: Liara browser + silver plan cards, Hamravesh Darakub browser rate
  matrix, Arvan browser + deterministic PAYG rates. No LLM.
- DBaaS: Liara browser + silver plan cards, Hamravesh managed browser rate
  matrix, Arvan browser + deterministic premium/standard and local/SSD rates,
  Sotoon offline Gen2 price list. No LLM.
- KaaS: Hamravesh browser resource/fee tables, Kubit HTTP licence ladder + IaaS
  worker rates, Sotoon offline Gen2 KaaS/VM price list. No LLM.
- CDN is pending.
- Manual (offline) documents: transcribed price lists are imported from
  `datasets/offline/<source_id>/` under `collection_method: manual`. There is no
  fetch and no LLM. The import records the source document and its validity, and
  the dashboard marks those prices as manual; they never count as verified live.
- Record source URL, navigation/configuration, timestamp, content hash and evidence.
  Keep regions, native tiers, units, inclusions, taxes and qualifiers where known.
- LLM output is source-grounded JSON with evidence, not instructions or computed
  comparisons. Validate with Pydantic and deterministic rules; unknown is not zero.
- Stage results under a running attempt. Accepted run status publishes atomically;
  failed/running rows remain hidden from observations, rates and displayed history.
- Reject empty/suspect-only results or missing accepted identities; genuine removals
  or renamed plans require review. First-run completeness still needs an inventory.
- Source contradictions/cross-check findings currently go to review evidence;
  this is not a complete field-level adjudication system. Prior successes are trusted.
- Skip unchanged extraction only under matching content and code/config fingerprint.
  Changes to collectors, schemas, normalization, comparison rules or public YAML
  conservatively trigger reprocessing. Never include secrets in hashes/prompts.

## Money, time and freshness

Use Decimal for money; normalize Persian/Arabic digits and separators. Convert
Rial to Toman only with explicit currency (10:1). Preserve original values/periods.
Published monthly VM prices remain monthly. Hourly prices use configurable
`vm.monthly_hours` (default 730); schema v4 records conversion hours and retains
raw inputs. Label the result a standardized equivalent, not a monthly package.
Unknown periods cannot supply a monthly total. Legacy hourly rows need recollection.
Do not silently equate GB/GiB. OS TB-to-GB=1024 is an explicit configurable assumption.
Latest attempt and last successful verification are distinct from price observation
or change time. Unchanged checks refresh verification; 48 hours without verification
or a latest unsuccessful/running attempt produces stale status.

## Manual (offline) sources

An offline document is imported, not collected. The importer reads a versioned
package (`manifest.json` + CSV), derives the configured reference plans, and
publishes them through the same observation/run path as the network collectors
(`collectors/offline_pipeline.py`). It is deterministic: no fetch, no LLM.

- The run stores `source_document` and `valid_until`; every row keeps
  `source_id` and `source_pdf_page` in its evidence.
- Manual prices do not age like a live fetch. A manual source is stale only when
  the document's validity date has passed, not after 48 hours.
- Re-importing unchanged data is skipped by content/config hash. A new document
  version is a new dataset package (new `source_id`), not an edit of the old one.
- The dashboard shows a «دستی» badge next to the basis badge, plus the source
  document and validity date in the row notes, the freshness panel and the plan
  detail page.
- Sotoon (owner decisions 2026-11-17): Neda datacenter; dedicated compute is
  Premium and shared compute is Standard (`tiers.yaml`); larger configurations
  are built from the 1 vCPU + 2 GB unit at `unit price × vCPU`, because the
  price list publishes only 1-vCPU bundles. Disk is billed separately by Sotoon,
  so the reference disk is added at the دیسک مانا نوع ۲ (premium) rate
  (`mana_2_premium`); the disk class is shown in the row note and the plan
  detail. All of this is labelled calculated, never published.

## VM comparison

- Three analyst tiers: Economy, Standard, Premium, not performance benchmarks.
  `tiers.yaml` maps Liara/ParsPack to Economy, Kubit gen-3 to Economy and gen-4 to
  Standard; Arvan retains the mapped public tiers. Preserve native labels.
- Four CPU/RAM/disk references from `benchmarks.yaml`: 1/2/20, 4/8/80,
  16/32/320, 32/64/640. CPU/RAM are owner requirements; disk targets are defaults.
- Exact resources first; show disk deviations. Nearest larger plans are approximate,
  never silently equivalent; undersized plans cannot rank as exact matches.
- Iranian/Linux scope. Keep actual resources/region visible. Compare known IPv4
  costs without double-counting inclusions. Liara rejects an unknown surcharge.
- ParsPack's daily x 30 x 0.95 + 150,000 IPv4 comes from owner-approved facts;
  it is an estimate. Arvan Economy's empirical 0.7 compute factor is provisional.
  Rate-based calculations and their assumptions must remain explicit.
- Sotoon's VM rows are calculated from a manually imported price list: unit
  price × vCPU plus the reference disk (دیسک مانا نوع ۲). They are compared at
  exact reference resources, so they rank as calculated matches and carry the
  «دستی» badge.

## Object Storage

Use Hamravesh's configured capacity/traffic scenarios as the baseline; reference
amounts are in `benchmarks.yaml`, not duplicated here. Prefer an exact published
bundle, then documented PAYG calculation, then exact storage-only quote, then
nearest larger quote with actual capacity and an approximation label.
These are subtotals: tax is excluded and unknown extra charges are not zero.
Requests are excluded for every provider that publishes no request allowance
(the Hamravesh baseline included); they are included only where the provider
bills requests separately, using the scenario's estimated request count. Arvan
PAYG period is assumed monthly; the published rate table is the
authoritative tariff and the marketing FAQ is not collected (owner decision
2026-11-16). Kubit uses egress outside location as the explicitly provisional traffic
analog. ParsPack HDD/Iran/one-month quotes omit traffic and are not complete totals.
Only progressive tariffs are implemented: contiguous, nonoverlapping intervals,
known nonnegative rates and coverage of usage are required. Volume tariffs need
an explicit adapter. Preserve free quotas, classes, minimums and geography.

### Request estimates

`benchmarks.yaml` gives each scenario a monthly request count. It assumes large
objects (about 4 MiB on average), which keeps the request charge at the low end:
underestimating the request price is preferred over overestimating it. The
estimate is shown next to the scenario reference and in the calculated row note,
so it is never mistaken for a measured value.

### Sotoon (HiCap)

Only the HiCap class in the Neda datacenter is compared (owner decision
2026-11-17). Capacity, egress and request rates come from the manually imported
price list; there is no published Sotoon Object Storage bundle, so the price is
always calculated. Egress bands are transcribed with textual labels
(`first_50_GB`, `next_450_GB`, …) and converted to contiguous numeric bounds
using the configured `tb_to_gb`; the document does not say decimal or binary, but
the four scenarios fall well inside the same bands under either reading. Sotoon
has a single request rate for HiCap, charged per 1,000 requests. Inbound traffic
and tax are excluded.

### Sotoon CDN offload

Sotoon does not bill Object Storage egress for traffic served through its own
CDN (the brochure states that storage-origin CDN traffic is free). The dashboard
therefore shows **two Sotoon results per scenario**: the full-traffic price, and
a CDN-assisted price that charges only the remaining share (default: 80% of
traffic via CDN, so 20% is priced). The CDN's own traffic tariff is a separate
product and is not included in either number; both rows carry a note saying so.
The share is configured in `benchmarks.yaml` (`traffic_offloads`) and applies
only to providers listed there.

## PaaS (CNAP)

Four compute references (owner decision 2026-11-16): 1 vCPU + 2 GB RAM / 20 GB
SSD, 4/8/80, 16/32/320 and 32/64/640. CPU/RAM are requirements; SSD follows
Liara silver's published plan sizes (20/80/320 GB). The 640 GB value for the
32/64 reference is the same doubling pattern because Liara does not offer that
size; Liara is shown as unavailable there, not approximated.

- Liara: compare only the middle silver tier. Plan monthly prices are published
  bundles (مشتری، اورانوس، پلوتون). The selected tier must be visible on the page.
- Hamravesh: Darakub Iran datacenter monthly resource rates (vCore/RAM/SSD)
  form a calculated subtotal. Traffic, IPv4 and monitoring are excluded.
- Arvan: published PaaS PAYG monthly rates (vCore/RAM/SSD) form a calculated
  subtotal. Traffic, IPv4, backup and snapshot are excluded. The public
  calculator cannot select the smallest 1/2 combination or storage above
  200 GB; those quotes are calculated from the published per-unit rates and
  must say so.
- No LLM is used. Basis badges distinguish published (Liara) from calculated
  (Hamravesh/Arvan); missing is not a zero price.

## DBaaS

Two infrastructure classes share the same four reference sizes (owner request
2026-11-21): 1 vCPU + 2 GB RAM / 20 GB, 2/4/40, 4/8/80 and 8/16/160. The
dashboard selects a class and a size; class membership lives in
`benchmarks.yaml`.

- Class A — local/premium: Hamravesh managed rates, Sotoon dedicated compute
  with `local_disk`, Arvan Premium rates with `دیسک لوکال`.
- Class B — shared/network: Sotoon shared (E1) compute with `mana_2_premium`,
  Arvan Standard rates with `دیسک SSD`, and Liara silver published plans.
- Arvan and Hamravesh publish per-resource monthly rates, so every reference
  size is a verified calculation. Liara matches all four sizes exactly. Sotoon's
  Gen2 price list publishes 1 vCPU + 2 GB compute bundles; larger references
  use the owner-approved stacking rule: unit price × vCPU (RAM scales at 2 GB
  per vCPU) plus the selected disk at its GB-month rate.
- The class assignment is explicit, not inferred: the page must publish the
  premium/dedicated tier and local/network disk. Hamravesh's page publishes
  managed vs unmanaged rates and only says «SSD», so local-disk membership is
  flagged as unverified. Liara's page likewise says only «SSD».
- Tax, traffic, IPv4 and read replicas/standby nodes are outside the base price
  when the page does not include them explicitly. Arvan traffic and backup are
  free, IPv4 is separate; Hamravesh prices assume a 30-day month. Where a
  replica or HA standby is mandatory, the displayed base price is a lower bound
  and the row notes say so.
- No LLM is used. `product_family` records `dbaas_<class>_<basis>`; basis badges
  distinguish published (Liara) from calculated (Arvan, Hamravesh, Sotoon).

## KaaS (managed Kubernetes)

Six node-count scenarios (owner request 2026-11-22): 6×8, 12×16, 8×32, 32×16,
40×24 and 32×64 vCPU, for totals of 48, 192, 256, 512, 960 and 2,048 vCPU.
Every scenario assumes 2 GB RAM and 10 GB local SSD per vCPU and 720 hours per
month. The monthly total is management fee + worker resources + control plane.

- Four offerings, always separate in tables and charts: Hamravesh v1 (legacy
  fee schedule), Hamravesh v2 (current self-service KaaS fee schedule), Kubit
  and Sotoon.
- Both Hamravesh offerings use the same collected worker rates and 25M
  control-plane rule, but different fixed management schedules:
  - v1 (old prices): <200 vCPU 70M, 200–799 140M, 800–1,499 220M, ≥1,500 320M
    Toman.
  - v2 (new self-service prices): <200 30M, 200–799 80M, 800–1,499 150M,
    ≥1,500 240M Toman. The page's top band is «ثبت درخواست»; 240M is the
    owner-approved assumption for that band.
- The KaaS page's collected fee ladder is retained as evidence but the view
  uses these configured schedules so v1 and v2 cannot collapse into one line.
- Kubit's Kubernetes licence uses `P = 2×CPU + RAM(GB)` with the published
  ladder; workers use the generation-4 (Standard) CPU/RAM and disk rates. The
  `P ≥ 8,000` band is «تماس بگیرید» and stays unknown.
- Sotoon uses Neda prices only. Worker compute is the C1 (1 vCPU + 2 GB,
  dedicated) bundle × total vCPU; storage is the local SSD GB-month rate.
  Cluster management is a subscription plus a per-node fee: below 30 nodes,
  17M + 3.1M per node; from 30 nodes, 40M + 3.9M per node (externally
  confirmed). The C1 multiplication is a comparison assumption, not a verified
  native node shape. Local SSD is close to Ultra3 persistent storage, so the
  result is an approximate reference for either option. Extra control-plane
  cores remain optional/support charges and are excluded.
- Control-plane comparison rules: Hamravesh v1/v2 25M Toman, Kubit 10M, Sotoon 0
  (included). These are owner-provided comparison inputs, not scraped tariffs;
  the UI says so.
- Sotoon prints IRR; the dashboard converts to Toman by dividing by 10 and keeps
  the source page, document and validity. Tax, traffic, IPv4, support and
  optional add-ons are excluded.
- No LLM is used. `collectors/kaas_pipeline.py` stores worker rows (and the
  current page fee ladder as evidence) in `resource_rates`; the configured v1/v2
  fee schedules live in `benchmarks.yaml`, and `comparison/kaas_pricing.py` owns
  all arithmetic. The view only shapes the results.

## Presentation and future CDN

Use the VM shared visual standard: one selected scenario, basis colors, provider
labels, cheapest-first bars and provider-row tables, with caveats and freshness.
OS assumptions prevent treating its bars as full equivalent purchase costs.

Every product page uses that standard inside a three-section shell: a centered
product title, then «مقایسه قیمت» (the chart, provider-row table, details and
freshness), «مقایسه قابلیت‌ها» and «مقایسه عملکرد». Capability comparison is
still a «به‌زودی» placeholder everywhere; the Object Storage performance section
is the first implemented one — an offline benchmark table with its own
provenance notes — while VM, PaaS, DBaaS and KaaS keep the placeholder until
their data models exist. The homepage is static:
title/subtitle, a layered IaaS/CaaS/PaaS product map (implemented products are
links; the rest are disabled with «به‌زودی») and a methodology summary. Size-miss
notes that merely restate the reference resources are not shown; genuine
coverage gaps (uncollected tier, foreign-only plans) remain. Mixed Persian/Latin
labels use bidi isolation so `x vCPU + y GB` renders in the intended order.
Manually imported prices are visually distinct from collected ones: a «دستی»
badge plus the document and validity date, and the freshness panel reports the
document's validity instead of a 48-hour collection window.

Object Storage explains its pricing model once, in a «نحوه محاسبه قیمت» box
between the chart and the table: the three cost elements (storage, traffic,
requests), the bundled-plan versus PAYG distinction, the request estimate and
the VAT/partial-total caveats. Provider rows only state which model that
provider uses (including the CDN offload where it applies), so the same caveat
is not repeated in every row.

CDN needs its own schema/scenarios for package fees, traffic geography, requests,
quotas and overages. Agree scenarios before implementation; do not reuse VM tiers.
