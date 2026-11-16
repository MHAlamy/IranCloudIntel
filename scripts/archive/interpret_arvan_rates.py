"""One bounded LLM call: interpret Arvan's PAYG rate table from page text.

The LLM's role (owner decision 2026-11-15): interpret labels/semantics and
surface documented discounts. The arithmetic verification itself stays
deterministic. Output saved as evidence for the analyst; never auto-applied.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from bs4 import BeautifulSoup  # noqa: E402
from extractors.llm import LLMClient, parse_json_loose  # noqa: E402
from extractors.prompts import SYSTEM_PROMPT  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "arvan_cloud_server" / "rates_section.html"
EVIDENCE = ROOT / "evidence" / "arvan" / "vm"

PROMPT = """Below is the pay-as-you-go rate section of ArvanCloud's cloud-server
pricing page (Persian). Region panes are toggled by Alpine.js (x-show region ===
'iran' / 'europe'); both panes' text is present.

Answer these questions precisely, citing the exact Persian labels you rely on:
1. For each category (پردازنده، حافظه (RAM)، فضای ذخیره‌سازی، نشانی آی‌پی، ترافیک),
   which unit labels appear (e.g. هر vCore, هر vCPU, هر گیگابایت, هر آدرس) and
   does any category's meaning differ between the Iran and Europe panes?
2. List the storage classes and their Iran per-GB monthly prices.
3. Is there any documented discount, promotion or footnote that would explain a
   bundle price lower than the sum of its components (e.g. 30% off for specific
   package families)? Quote the relevant Persian text if present.
4. Does the page state whether the PAYG table prices are monthly or hourly?

Return strict JSON:
{
  "categories": [{"category": "...", "iran_units": [...], "europe_units": [...], "notes": "..."}],
  "storage_classes_iran": [{"label": "...", "toman_per_gb_month": "..."}],
  "documented_discounts": [{"text": "...", "applies_to": "..."}],
  "price_period": "...",
  "analyst_notes": "..."
}
"""

if __name__ == "__main__":
    soup = BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")
    for tag in soup(["script", "style", "svg"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    print(f"Rate-section text: {len(text)} chars")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": PROMPT + "\n\n--- BEGIN PAGE CONTENT ---\n" + text + "\n--- END PAGE CONTENT ---"},
    ]
    with LLMClient() as client:
        response = client.chat(messages, max_tokens=3000)
    print(f"tokens: {response.prompt_tokens}/{response.completion_tokens} finish={response.finish_reason}")
    data = parse_json_loose(response.content)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = EVIDENCE / f"{stamp}_rate_interpretation.json"
    out.write_text(
        json.dumps({"observed_at": stamp, "usage": {
            "prompt_tokens": response.prompt_tokens, "completion_tokens": response.completion_tokens},
            "interpretation": data}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
    print(f"\nSaved: {out.name}")
