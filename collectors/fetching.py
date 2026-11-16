"""HTTP/browser acquisition dispatch shared across services."""
from config.loader import SourceConfig
from collectors.common import FetchError, FetchResult

def fetch_source(source: SourceConfig) -> FetchResult:
    """Dispatch fetching by collection method (browser for JS/challenge sites,
    plain HTTP for static pages)."""
    if source.collection_method == "playwright":
        from collectors.arvan_fetch import fetch_with_browser

        marker = source.navigation.get("ready_marker", "")
        result = fetch_with_browser(
            source.url,
            ready_marker=marker,
            click_selector=source.navigation.get("click_selector"),
        )
        return FetchResult(html=result.html, http_status=result.http_status, final_url=result.final_url)
    if source.collection_method == "http":
        import httpx

        response = httpx.get(
            source.url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                ),
                "Accept-Language": "fa,en;q=0.8",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        return FetchResult(html=response.text, http_status=response.status_code, final_url=str(response.url))
    raise FetchError(f"collection method {source.collection_method!r} not implemented yet")
