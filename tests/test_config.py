"""Tests for YAML configuration loading and validation."""

from pathlib import Path

import pytest
import yaml

from config.loader import (
    BenchmarksFile,
    ProvidersFile,
    TiersFile,
    load_benchmarks,
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
    assert tiers.vm.providers["liara"].default == "standard"
