"""Tests for YAML configuration loading and validation."""

from pathlib import Path

import pytest
import yaml

from config.loader import (
    BenchmarksFile,
    ProductsCatalog,
    ProvidersFile,
    TiersFile,
    load_benchmarks,
    load_products,
    load_providers,
    load_tiers,
)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def test_committed_configs_load_and_validate():
    providers = load_providers()
    tiers = load_tiers()
    benchmarks = load_benchmarks()
    arvan = next(p for p in providers.providers if p.slug == "arvan")
    source = arvan.sources[0]
    assert source.service_type == "vm" and source.collection_method == "playwright"
    assert source.navigation["tabs"] == ["basic", "standard", "premium"]
    assert set(tiers.vm.tiers) == {"economy", "standard", "premium"}
    assert set(benchmarks.vm.sizes) == {"small", "medium", "large", "very_large"}
    assert benchmarks.vm.sizes["medium"].vcpu == 4
    assert benchmarks.vm.monthly_hours == 730
    # object-storage benchmarks: Hamravesh plans are the baseline (owner decision)
    os_b = benchmarks.object_storage
    assert os_b.baseline == "hamravesh"
    assert os_b.tb_to_gb == 1024
    assert set(os_b.scenarios) == {"base", "growth", "pro", "dedicated"}
    assert os_b.scenarios["growth"].storage_gb == 500
    assert os_b.scenarios["growth"].traffic_gb == 2048


def test_duplicate_provider_slug_rejected(tmp_path):
    data = {"providers": [
        {"slug": "arvan", "name": "A", "official_url": "https://a.ir", "sources": []},
        {"slug": "arvan", "name": "B", "official_url": "https://b.ir", "sources": []},
    ]}
    path = tmp_path / "providers.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate provider slug"):
        ProvidersFile(**yaml.safe_load(path.read_text(encoding="utf-8")))


def test_invalid_service_type_rejected():
    with pytest.raises(Exception):
        ProvidersFile(**{"providers": [{
            "slug": "x", "name": "X", "official_url": "https://x.ir",
            "sources": [{"id": "s1", "service_type": "quantum", "url": "https://x.ir/p",
                         "collection_method": "http"}],
        }]})


def test_invalid_benchmark_size_rejected():
    with pytest.raises(Exception):
        BenchmarksFile(**{"vm": {
            "monthly_hours": 730, "default_region_scope": "iran", "default_os": "linux",
            "sizes": {"bad": {"vcpu": 0, "ram_gb": 2, "disk_gb": 20}},
            "matching": {},
        }})


def test_tiers_file_shape():
    tiers = TiersFile(**yaml.safe_load((CONFIG_DIR / "tiers.yaml").read_text(encoding="utf-8")))
    arvan = tiers.vm.providers["arvan"]
    assert arvan.aliases["basic"] == "economy"
    assert arvan.unknown_label_policy == "review"
    # Owner decision 2026-11-15: Liara and ParsPack compare under Economy.
    assert tiers.vm.providers["liara"].default == "economy"
    assert tiers.vm.providers["parspack"].default == "economy"


def test_product_catalog_loads():
    catalog = load_products()
    layers = {layer.id: layer for layer in catalog.layers}
    assert set(layers) == {"iaas", "caas", "paas"}
    assert [p.slug for p in layers["iaas"].products] == ["vm", "object_storage", "cdn", "gpu"]
    assert [p.slug for p in layers["caas"].products] == ["kaas"]
    assert [p.slug for p in layers["paas"].products] == ["cnap", "dbaas", "devops", "aiaas"]
    assert {p.slug for layer in catalog.layers for p in layer.products if p.enabled} == {
        "vm", "object_storage"
    }
    routes = {p.slug: p.route for layer in catalog.layers for p in layer.products}
    assert routes["vm"] == "/vm"
    assert routes["object_storage"] == "/object-storage"
    assert routes["cdn"] is None
    cnap = next(p for p in layers["paas"].products if p.slug == "cnap")
    assert cnap.name_fa == "(CNAP) پلتفرم ابری توسعه اپلیکیشن"


def test_product_catalog_rejects_duplicate_slugs():
    data = {"layers": [
        {"id": "a", "acronym": "A", "name_fa": "الف",
         "products": [{"slug": "x", "name_fa": "X"}]},
        {"id": "b", "acronym": "B", "name_fa": "ب",
         "products": [{"slug": "x", "name_fa": "X"}]},
    ]}
    with pytest.raises(ValueError, match="duplicate product slug"):
        ProductsCatalog(**data)


def test_product_catalog_route_must_match_enabled():
    enabled_without_route = {"layers": [{
        "id": "a", "acronym": "A", "name_fa": "الف",
        "products": [{"slug": "x", "name_fa": "X", "enabled": True}],
    }]}
    with pytest.raises(ValueError, match="needs a route"):
        ProductsCatalog(**enabled_without_route)

    disabled_with_route = {"layers": [{
        "id": "a", "acronym": "A", "name_fa": "الف",
        "products": [{"slug": "x", "name_fa": "X", "route": "/x"}],
    }]}
    with pytest.raises(ValueError, match="must not define a route"):
        ProductsCatalog(**disabled_with_route)
