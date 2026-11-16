"""Source collection status view."""
from config.loader import load_providers
from storage.repository import Repository
from util.jalali import format_jalali
from app.view_common import _provider_id

def build_status_view(repo: Repository) -> dict:
    # same canonical provider order as the comparison views
    provider_order = {p.slug: i for i, p in enumerate(load_providers().providers)}
    sources = []
    for source in repo.list_sources():
        runs = repo.source_runs(source["id"])
        sources.append({
            "provider_name": source["provider_name"],
            "provider_slug": source["provider_slug"],
            "service_type": source["service_type"],
            "url": source["url"],
            "enabled": bool(source["enabled"]) if "enabled" in source.keys() else True,
            "rates_stored": repo.rate_count(_provider_id(repo, source["provider_slug"]) or 0),
            "runs": [
                {
                    "status": r["status"],
                    "started_jalali": format_jalali(r["started_at"]),
                    "tokens": f"{r['prompt_tokens']}/{r['completion_tokens']}",
                    "error": r["error"],
                }
                for r in runs
            ],
        })
    sources.sort(key=lambda s: provider_order.get(s["provider_slug"], 99))
    return {"sources": sources}
