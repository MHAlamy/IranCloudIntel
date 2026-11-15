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

from config.loader import load_providers  # noqa: E402
from collectors.arvan_clean import clean_page  # noqa: E402
from collectors.arvan_rates import parse_rates  # noqa: E402
from collectors.pipeline import fetch_source, run_collection  # noqa: E402
from comparison.rate_check import load_rate_mappings  # noqa: E402
from extractors.llm import LLMClient  # noqa: E402
from storage.repository import Repository  # noqa: E402
from util.runlock import RunLock  # noqa: E402

DATA_DIR = ROOT / "data"


def main() -> int:
    parser = argparse.ArgumentParser(description="One-shot price collection")
    parser.add_argument("--db", default=str(DATA_DIR / "cloud_intel.db"))
    parser.add_argument("--source", default=None, help="collect only this source id")
    parser.add_argument("--force", action="store_true", help="extract even when content is unchanged")
    args = parser.parse_args()

    providers_file = load_providers()
    rate_mappings = load_rate_mappings()
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
                    outcome = run_collection(
                        provider=provider,
                        source=source,
                        repo=repository,
                        llm_factory=LLMClient,
                        fetcher=fetch_source,
                        cleaner=clean_page,
                        force=args.force,
                        rates_parser=parse_rates if provider.slug == "arvan" else None,
                        rate_mappings=rate_mappings,
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
