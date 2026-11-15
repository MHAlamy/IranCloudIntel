"""Typed loading and validation of analyst-maintained YAML configuration.

All configuration is validated on startup (price_gathering_guide.md 9).
Credentials never live in these files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    service_type: Literal["vm", "object_storage", "cdn"]
    url: str = Field(min_length=1)
    collection_method: Literal["http", "playwright"]
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


class BenchmarksFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vm: VMBenchmarks


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
