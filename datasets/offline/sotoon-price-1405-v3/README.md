# Sotoon price catalogue, Spring 1405 (v3)

Manually transcribed commercial tariffs from the Sotoon price list. The source
document is a 13-page PDF whose price tables are images; the transcription was
read from the rendered pages, not OCR.

- **`source_id`**: `sotoon-price-1405-v3`
- **Currency**: IRR (Rial). Toman = IRR / 10.
- **Validity**: the cover states valid until the end of Esfand 1405, despite the
  "Spring 1405" filename. Do not assume it is current; confirm any superseding
  document independently.
- **Review status**: `draft_for_user_verification` in `manifest.json`.

## Files

| File | Page | Contents |
|---|---|---|
| `prices/vm_gen2.csv` | 4 | Gen2 compute bundles by datacenter, disk classes, backup, extra RAM, IPv4, traffic, load balancers |
| `prices/k8s_gen2.csv` | 5 | Gen2 KaaS cluster subscription, per-node maintenance, extra control-plane core |
| `prices/object_storage.csv` | 6–7 | Archive/HiCap/Hiops capacity by datacenter, request charges, nine egress bands |
| `prices/dbaas_gen2.csv` | 9 | Gen2 database compute bundles and disk classes |
| `prices/cdn.csv` | 8 | Iran/outside-Iran traffic bands, requests, image processing, logs, IP, TLS, DNS, video, smart routing |

All files are UTF-8 with BOM (so Excel opens the Persian labels), one header row,
and a `source_pdf_page` column on every row.

## Read before using

- **Compute is one vCPU.** C1, G1, M1 and E1 are all 1 vCPU bundles with
  different RAM and shared/dedicated allocation. The dashboard's 4/8, 16/32 and
  32/64 VM references cannot be matched without an explicit stacking assumption.
- **Disk is separate.** Unlike Arvan or Liara bundles, Sotoon bills compute,
  disk and IPv4 separately, so a comparable monthly total must be calculated.
- **Datacenter pricing.** Bourse, Neda and Sabalan differ by roughly 10%; a
  region policy is required before any single price is displayed.
- **Egress bands are textual.** Object Storage rows keep labels such as
  `first_50_GB` in `notes` and leave the numeric bounds empty, while CDN rows do
  carry GB bounds. Scenario maths needs numeric bounds for both.
- **Outliers to verify.** CDN `each_ip` (25,000,000 Toman per IP-month), CDN log
  pricing, K8s cluster subscriptions, and the Archive-above-HiCap egress
  ordering all look unusual enough to re-check against the source pages.
- See `open_review_items` in `manifest.json` for the full list.

The original PDF is not committed. Its path and SHA-256 are recorded in
`manifest.json` under `original_document`.
