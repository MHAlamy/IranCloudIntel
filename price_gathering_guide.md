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
  PAYG, Kubit HTTP PAYG, ParsPack browser storage-only quotes. CDN is pending.
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

## Object Storage

Use Hamravesh's configured capacity/traffic scenarios as the baseline; reference
amounts are in `benchmarks.yaml`, not duplicated here. Prefer an exact published
bundle, then documented PAYG calculation, then exact storage-only quote, then
nearest larger quote with actual capacity and an approximation label.
These are subtotals: requests and tax are excluded; unknown extra charges are not
zero. Arvan PAYG period is assumed monthly; FAQ/rate-table contradictions remain
flagged. Kubit uses egress outside location as the explicitly provisional traffic
analog. ParsPack HDD/Iran/one-month quotes omit traffic and are not complete totals.
Only progressive tariffs are implemented: contiguous, nonoverlapping intervals,
known nonnegative rates and coverage of usage are required. Volume tariffs need
an explicit adapter. Preserve free quotas, classes, minimums and geography.

## Presentation and future CDN

Use the VM shared visual standard: one selected scenario, basis colors, provider
labels, cheapest-first bars and provider-row tables, with caveats and freshness.
OS assumptions prevent treating its bars as full equivalent purchase costs.
CDN needs its own schema/scenarios for package fees, traffic geography, requests,
quotas and overages. Agree scenarios before implementation; do not reuse VM tiers.
