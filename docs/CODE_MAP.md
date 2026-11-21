# Task map

| Task | Implementation | Targeted tests |
|---|---|---|
| HTTP/browser dispatch | `collectors/fetching.py`, `arvan_fetch.py`, `browser.py` | `test_browser.py`, `test_waits.py` |
| VM extraction/publication | `collectors/vm_pipeline.py`, `extractors/schema.py`, `normalization/validate.py` | `test_pipeline.py`, `test_collection_regressions.py` |
| OS extraction/publication | `collectors/os_pipeline.py`, `extractors/os_schema.py` | `test_os_pipeline.py`, `test_os_parsers.py` |
| PaaS extraction/publication | `collectors/paas_pipeline.py`, `hamravesh_paas.py`, `arvan_paas.py`, `liara_paas.py` | `test_paas_pipeline.py`, `test_paas_parsers.py` |
| PaaS comparison/rendering | `app/paas_view.py`, `app/templates/paas.html` | `test_paas_dashboard.py` |
| Schema v5 PaaS service type | `storage/migrations/v5__paas.sql` | `test_paas_pipeline.py` |
| Manual (offline) import | `collectors/offline_pipeline.py`, `sotoon_offline.py`, `storage/migrations/v6__manual_sources.sql` | `test_sotoon_offline.py`, `test_sotoon_os.py` |
| Offline dataset packages | `datasets/offline/<source_id>/` (manifest + CSV) | `test_sotoon_offline.py`, `test_sotoon_os.py`, `test_benchmark_pivot.py` |
| Benchmark pivot (display) | `comparison/benchmarks.py` (long CSV is the only stored source) | `test_benchmark_pivot.py` |
| OS performance table | `app/benchmark_view.py`, `app/templates/os_benchmark.html` | `test_benchmark_view.py`, `test_os_dashboard.py` |
| ParsPack interaction | `collectors/parspack_quotes.py`, `parspack_os.py`, `waits.py` | `test_waits.py` (browser cases are opt-in) |
| Provider parsers | `collectors/{provider}*.py` | `test_liara.py`, `test_kubit.py`, `test_rates.py`, `test_os_parsers.py` |
| Accepted history/freshness | `storage/repository.py`, `collectors/common.py` | `test_publication.py`, `test_storage.py` |
| Tariff/monthly semantics | `comparison/tariffs.py`, `normalization/validate.py` | `test_price_semantics.py` |
| Homepage/product catalogue | `config/products.yaml`, `app/templates/home.html`, `app/main.py` | `test_home.py`, `test_config.py` |
| Product page shell | `app/templates/vm.html`, `os.html`, `paas.html`, `macros.html` | dashboard tests |
| VM comparison/rendering | `app/vm_view.py`, `comparison/matching.py`, `app/templates/vm.html` | `test_matching.py`, `test_dashboard.py` |
| OS comparison/rendering | `app/os_view.py`, `app/templates/os_comparison.html` | `test_os_dashboard.py` |
| Shared chart design | `app/templates/price_chart.html`, `app/static/style.css` | dashboard tests |
| Read-only inspection | `scripts/inspect_data.py` | `test_inspect_data.py` |
| Bounded file/log output | `scripts/peek.py` | `test_peek.py` |

`app/data.py` and `collectors/pipeline.py` preserve old imports; edit the actual
service modules. Prices, prompts and rules live in code/YAML, not historical docs.

Explore with file lists, function searches and bounded excerpts. Exclude `.venv/`,
`data/`, `evidence/`, `.pytest*/`, `tests/fixtures/`, `scripts/archive/`, and
`docs/archive/` from broad content searches; read a specific fixture when needed.
