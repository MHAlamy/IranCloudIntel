"""One-shot collector CLI.

Usage (from the repository root):
    .\\.venv\\Scripts\\python.exe -m collectors.cli [--source arvan_vm_cloud_server] [--force]

- Loads and validates YAML configuration on startup.
- Holds an exclusive lock so scheduled and manual runs never overlap.
- Default database: data/cloud_intel.db (gitignored).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from config.loader import load_analyst_facts, load_benchmarks, load_providers  # noqa: E402
from collectors.arvan_clean import clean_page  # noqa: E402
from collectors.arvan_os_clean import build_os_cleaned_markdown  # noqa: E402
from collectors.arvan_os_rates import (  # noqa: E402
    crosscheck_arvan_os_plans,
    parse_faq_overage,
    parse_os_rates,
)
from collectors.arvan_rates import parse_rates  # noqa: E402
from collectors.hamravesh_os import build_hamravesh_os_markdown, parse_hamravesh_os_plans  # noqa: E402
from collectors.kubit_clean import clean_kubit  # noqa: E402
from collectors.kubit_os import clean_kubit_os, parse_kubit_os_plans, parse_kubit_os_rates  # noqa: E402
from collectors.kubit_rates import parse_kubit_rates  # noqa: E402
from collectors.liara_clean import clean_liara  # noqa: E402
from collectors.liara_plans import parse_liara_plans  # noqa: E402
from collectors.parspack_os import run_parspack_os  # noqa: E402
from collectors.parspack_quotes import run_parspack_quotes  # noqa: E402
from collectors.pipeline import fetch_source, run_collection, run_os_collection  # noqa: E402
from comparison.rate_check import load_rate_mappings  # noqa: E402
from extractors.llm import LLMClient  # noqa: E402
from storage.repository import Repository  # noqa: E402
from util.runlock import RunLock  # noqa: E402

DATA_DIR = ROOT / "data"

PROVIDER_COLLECTION = {
    "arvan": {"cleaner": clean_page, "rates_parser": parse_rates, "plans_parser": None},
    "kubit": {"cleaner": clean_kubit, "rates_parser": parse_kubit_rates, "plans_parser": None},
    "liara": {"cleaner": clean_liara, "rates_parser": None, "plans_parser": parse_liara_plans},
}

OS_COLLECTION = {
    "arvan": {
        "cleaner": build_os_cleaned_markdown,
        "os_plans_parser": None,        # plan cards via LLM
        "os_rates_parser": lambda html: parse_os_rates(html) + parse_faq_overage(html),
        "os_crosscheck": lambda html, pairs: crosscheck_arvan_os_plans(
            html, [(raw, norm) for raw, norm in pairs]
        ),
        "llm": True,
    },
    "hamravesh": {
        "cleaner": build_hamravesh_os_markdown,
        "os_plans_parser": parse_hamravesh_os_plans,
        "os_rates_parser": None,
        "os_crosscheck": None,
        "llm": False,
    },
    "kubit": {
        "cleaner": clean_kubit_os,
        "os_plans_parser": parse_kubit_os_plans,
        "os_rates_parser": parse_kubit_os_rates,
        "os_crosscheck": None,
        "llm": False,
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="One-shot price collection")
    parser.add_argument("--db", default=str(DATA_DIR / "cloud_intel.db"))
    parser.add_argument("--source", default=None, help="collect only this source id")
    parser.add_argument("--force", action="store_true", help="extract even when content is unchanged")
    args = parser.parse_args()

    providers_file = load_providers()
    rate_mappings = load_rate_mappings()
    os_benchmarks = load_benchmarks().object_storage
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with RunLock(DATA_DIR / ".collection.lock"):
        repository = Repository(args.db)
        try:
            exit_code = 0
            for provider in providers_file.providers:
                for source in provider.sources:
                    if not source.enabled or (args.source and source.id != args.source):
                        continue
                    print(f"--- collecting {source.id} ---")
                    if provider.slug == "parspack" and source.service_type == "vm":
                        # configurable-quote provider: drive the calculator
                        outcome = run_parspack_quotes(
                            provider=provider,
                            source=source,
                            repo=repository,
                            facts=load_analyst_facts()["parspack"],
                            evidence_root=ROOT / "evidence",
                            force=args.force,
                        )
                    elif provider.slug == "parspack" and source.service_type == "object_storage":
                        # configurable-quote provider: drive the storage calculator
                        outcome = run_parspack_os(
                            provider=provider,
                            source=source,
                            repo=repository,
                            evidence_root=ROOT / "evidence",
                            force=args.force,
                        )
                    elif source.service_type == "object_storage":
                        config = OS_COLLECTION.get(
                            provider.slug,
                            {"cleaner": build_os_cleaned_markdown, "os_plans_parser": None,
                             "os_rates_parser": None, "os_crosscheck": None, "llm": False},
                        )
                        outcome = run_os_collection(
                            provider=provider,
                            source=source,
                            repo=repository,
                            fetcher=fetch_source,
                            cleaner=config["cleaner"],
                            llm_factory=LLMClient if config["llm"] else None,
                            os_plans_parser=config["os_plans_parser"],
                            os_rates_parser=config["os_rates_parser"],
                            os_crosscheck=config["os_crosscheck"],
                            tb_to_gb=os_benchmarks.tb_to_gb,
                            evidence_root=ROOT / "evidence",
                            force=args.force,
                        )
                    else:
                        collection = PROVIDER_COLLECTION.get(
                            provider.slug,
                            {"cleaner": clean_page, "rates_parser": None, "plans_parser": None},
                        )
                        outcome = run_collection(
                            provider=provider,
                            source=source,
                            repo=repository,
                            llm_factory=LLMClient,
                            fetcher=fetch_source,
                            cleaner=collection["cleaner"],
                            force=args.force,
                            rates_parser=collection["rates_parser"],
                            rate_mappings=rate_mappings,
                            bundle_extraction=source.navigation.get("bundle_extraction", True),
                            plans_parser=collection["plans_parser"],
                        )
                    print(
                        f"    status={outcome.status} skipped={outcome.skipped} "
                        f"observations={outcome.observations} suspect={outcome.suspect_rows} "
                        f"tokens(prompt/completion)={outcome.prompt_tokens}/{outcome.completion_tokens}"
                    )
                    if outcome.error:
                        print(f"    ERROR: {outcome.error}")
                        exit_code = 1
            return exit_code
        finally:
            repository.close()


if __name__ == "__main__":
    sys.exit(main())
