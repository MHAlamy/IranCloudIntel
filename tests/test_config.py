"""Tests for YAML configuration loading and validation."""

from pathlib import Path

import pytest
import yaml
from decimal import Decimal

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
    assert os_b.scenarios["base"].requests == 100000
    # Sotoon does not bill Object Storage egress for traffic served via its CDN.
    assert os_b.traffic_offloads["sotoon"].cdn_share == Decimal("0.8")
    # PaaS/CNAP: four compute references, Liara silver comparison.
    assert set(benchmarks.paas.selections) == {"s1", "s2", "s3", "s4"}
    assert benchmarks.paas.selections["s4"].disk_gb == 640
    assert benchmarks.paas.liara_tier == "نقره‌ای"
    paas_sources = {
        source.id for provider in providers.providers
        for source in provider.sources if source.service_type == "paas"
    }
    assert paas_sources == {"arvan_paas", "hamravesh_paas", "liara_paas"}
    # DBaaS: two classes share the same four reference sizes.
    assert set(benchmarks.dbaas.sizes) == {"small", "medium", "large", "very_large"}
    assert benchmarks.dbaas.sizes["very_large"].vcpu == 8
    assert benchmarks.dbaas.classes["local"].providers == ["hamravesh", "sotoon", "arvan"]
    assert benchmarks.dbaas.classes["shared"].providers == ["sotoon", "arvan", "liara"]
    # KaaS: six node-count scenarios, 720 hours, owner-provided control plane.
    assert set(benchmarks.kaas.scenarios) == {
        "small", "medium", "large", "x_large", "xx_large", "xxx_large"
    }
    assert benchmarks.kaas.scenarios["small"].total_vcpu == 48
    assert benchmarks.kaas.scenarios["xxx_large"].total_vcpu == 2048
    assert benchmarks.kaas.monthly_hours == 720
    assert benchmarks.kaas.control_plane_toman["kubit"] == Decimal("10000000")
    assert benchmarks.kaas.sotoon_premium_min_nodes == 30
    assert [fee.fee_toman for fee in benchmarks.kaas.management_fees["hamravesh_v1"]] == [
        Decimal("70000000"), Decimal("140000000"),
        Decimal("220000000"), Decimal("320000000"),
    ]
    assert [fee.fee_toman for fee in benchmarks.kaas.management_fees["hamravesh_v2"]] == [
        Decimal("30000000"), Decimal("80000000"),
        Decimal("150000000"), Decimal("240000000"),
    ]
    # Sotoon VM prices come from a transcribed price list, not a fetched page.
    sotoon = next(p for p in providers.providers if p.slug == "sotoon")
    assert [(s.id, s.service_type, s.collection_method) for s in sotoon.sources] == [
        ("sotoon_vm_price_list", "vm", "manual"),
        ("sotoon_object_storage_price_list", "object_storage", "manual"),
        ("sotoon_dbaas_price_list", "dbaas", "manual"),
        ("sotoon_kaas_price_list", "kaas", "manual"),
    ]
    assert sotoon.sources[0].navigation["region"] == "Neda"
    assert sotoon.sources[1].navigation["storage_class"] == "HiCap"
    assert sotoon.sources[2].navigation["network_disk_sku"] == "mana_2_premium"
    assert sotoon.sources[3].navigation["compute_sku"] == "C1"


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
    # Owner decision 2026-11-17: Sotoon dedicated = Premium, shared = Standard.
    assert tiers.vm.providers["sotoon"].aliases == {
        "dedicated": "premium", "shared": "standard"
    }


def test_product_catalog_loads():
    catalog = load_products()
    layers = {layer.id: layer for layer in catalog.layers}
    assert set(layers) == {"iaas", "caas", "paas"}
    assert [p.slug for p in layers["iaas"].products] == ["vm", "object_storage", "cdn", "gpu"]
    assert [p.slug for p in layers["caas"].products] == ["kaas"]
    assert [p.slug for p in layers["paas"].products] == ["cnap", "dbaas", "devops", "aiaas"]
    assert {p.slug for layer in catalog.layers for p in layer.products if p.enabled} == {
        "vm", "object_storage", "cnap", "dbaas", "kaas"
    }
    vm = next(p for p in layers["iaas"].products if p.slug == "vm")
    assert vm.name_fa == "سرور ابری (VM)"
    routes = {p.slug: p.route for layer in catalog.layers for p in layer.products}
    assert routes["vm"] == "/vm"
    assert routes["object_storage"] == "/object-storage"
    assert routes["cnap"] == "/paas"
    assert routes["dbaas"] == "/dbaas"
    assert routes["kaas"] == "/kaas"
    assert routes["cdn"] is None
    cnap = next(p for p in layers["paas"].products if p.slug == "cnap")
    assert cnap.name_fa == "پلتفرم ابری توسعه اپلیکیشن (CNAP)"


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
