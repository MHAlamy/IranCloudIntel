"""Typed loading and validation of analyst-maintained YAML configuration.

All configuration is validated on startup (price_gathering_guide.md 9).
Credentials never live in these files.
"""

from __future__ import annotations

from pathlib import Path
from decimal import Decimal
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    service_type: Literal["vm", "object_storage", "cdn", "paas", "dbaas"]
    url: str = Field(min_length=1)
    # "manual" = transcribed offline document; never fetched over the network.
    collection_method: Literal["http", "playwright", "manual"]
    region_scope: str = ""
    enabled: bool = True
    navigation: dict[str, Any] = Field(default_factory=dict)


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1)
    official_url: str = Field(min_length=1)
    sources: list[SourceConfig] = Field(default_factory=list)


class ProvidersFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: list[ProviderConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "ProvidersFile":
        slugs = [p.slug for p in self.providers]
        if len(slugs) != len(set(slugs)):
            raise ValueError("duplicate provider slug in providers.yaml")
        source_ids = [s.id for p in self.providers for s in p.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate source id in providers.yaml")
        return self


class TierProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aliases: dict[str, str] = Field(default_factory=dict)
    default: str | None = None
    unknown_label_policy: Literal["review", "standard"] = "review"


class VMTiers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tiers: list[str] = Field(min_length=1)
    providers: dict[str, TierProvider] = Field(min_length=1)


class TiersFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vm: VMTiers


class BenchmarkSize(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vcpu: int = Field(ge=1)
    ram_gb: int = Field(ge=1)
    disk_gb: int = Field(ge=1)


class IPV4Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_in_cost: bool = False


class RegionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["iran", "all"] = "iran"
    iranian_prefix: str = "ir-"


class VMBenchmarks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_hours: int = Field(ge=1, le=744)
    default_region_scope: str
    default_os: str
    sizes: dict[str, BenchmarkSize] = Field(min_length=1)
    matching: dict[str, bool] = Field(default_factory=dict)
    ipv4: IPV4Config = IPV4Config()
    regions: RegionConfig = RegionConfig()


class PaasSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vcpu: int = Field(ge=1)
    ram_gb: int = Field(ge=1)
    disk_gb: int = Field(ge=1)


class PaasBenchmarks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    liara_tier: str = "نقره‌ای"
    selections: dict[str, PaasSelection] = Field(default_factory=dict)


class DbaasClass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    providers: list[str] = Field(min_length=1)


class DbaasBenchmarks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classes: dict[str, DbaasClass] = Field(default_factory=dict)
    sizes: dict[str, BenchmarkSize] = Field(default_factory=dict)


class BenchmarksFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vm: VMBenchmarks
    object_storage: "ObjectStorageBenchmarks" = Field(
        default_factory=lambda: ObjectStorageBenchmarks()  # type: ignore[call-arg]
    )
    paas: PaasBenchmarks = Field(default_factory=PaasBenchmarks)
    dbaas: DbaasBenchmarks = Field(default_factory=DbaasBenchmarks)


class OSScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    storage_gb: Decimal = Field(ge=0)
    traffic_gb: Decimal = Field(ge=0)
    # Analyst estimate of monthly requests, used only for providers that bill
    # requests separately. Deliberately a low-end figure.
    requests: int = Field(default=0, ge=0)


class OSTrafficOffload(BaseModel):
    """Share of scenario traffic served through a provider's own CDN.

    Traffic served through the CDN is not billed as Object Storage egress, so
    the dashboard can show a second, CDN-assisted price.
    """

    model_config = ConfigDict(extra="forbid")

    cdn_share: Decimal = Field(ge=0, le=1)
    label: str = ""


class ObjectStorageBenchmarks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_to_gb: int = Field(default=1024, ge=1)
    baseline: str = ""
    scenarios: dict[str, OSScenario] = Field(default_factory=dict)
    traffic_offloads: dict[str, OSTrafficOffload] = Field(default_factory=dict)


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a YAML mapping")
    return data


def load_providers(config_dir: Path = CONFIG_DIR) -> ProvidersFile:
    return ProvidersFile(**_load_yaml(config_dir / "providers.yaml"))


def load_tiers(config_dir: Path = CONFIG_DIR) -> TiersFile:
    return TiersFile(**_load_yaml(config_dir / "tiers.yaml"))


def load_benchmarks(config_dir: Path = CONFIG_DIR) -> BenchmarksFile:
    return BenchmarksFile(**_load_yaml(config_dir / "benchmarks.yaml"))


class ProductEntry(BaseModel):
    """One product tile on the homepage layer map."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    name_fa: str = Field(min_length=1)
    route: str | None = None
    enabled: bool = False

    @model_validator(mode="after")
    def _route_matches_enabled(self) -> "ProductEntry":
        if self.enabled and not (self.route or "").startswith("/"):
            raise ValueError(f"enabled product {self.slug!r} needs a route")
        if not self.enabled and self.route:
            raise ValueError(f"disabled product {self.slug!r} must not define a route")
        return self


class ProductLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    acronym: str = Field(min_length=1)
    name_fa: str = Field(min_length=1)
    products: list[ProductEntry] = Field(min_length=1)


class ProductsCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layers: list[ProductLayer] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "ProductsCatalog":
        layer_ids = [layer.id for layer in self.layers]
        if len(layer_ids) != len(set(layer_ids)):
            raise ValueError("duplicate layer id in products.yaml")
        slugs = [product.slug for layer in self.layers for product in layer.products]
        if len(slugs) != len(set(slugs)):
            raise ValueError("duplicate product slug in products.yaml")
        return self


def load_products(config_dir: Path = CONFIG_DIR) -> ProductsCatalog:
    return ProductsCatalog(**_load_yaml(config_dir / "products.yaml"))


class QuoteTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    cpu: int = Field(ge=1)
    ram: int = Field(ge=1)
    disk: int = Field(ge=1)


class AnalystProviderFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ipv4_monthly_toman: Decimal | None = None
    monthly_discount: Decimal = Decimal("1")
    month_days: int = Field(default=30, ge=1)
    quotes: list[QuoteTarget] = Field(default_factory=list)


def load_analyst_facts(config_dir: Path = CONFIG_DIR) -> dict[str, AnalystProviderFacts]:
    path = config_dir / "analyst_facts.yaml"
    if not path.exists():
        return {}
    data = _load_yaml(path)
    return {slug: AnalystProviderFacts(**cfg) for slug, cfg in data.items()}
