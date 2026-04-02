from core.firecrawl_client import FirecrawlClient

_fc = FirecrawlClient()


def search_web(query: str, limit: int = 25):
    """
    Firecrawl web search wrapper.
    Returns Firecrawl search results as-is.
    """
    return _fc.search(query=query, limit=limit)


def scrape_url(url: str, formats: list[str] | None = None):
    """
    Firecrawl scrape wrapper.
    """
    if formats is None:
        formats = ["markdown"]
    return _fc.scrape(url=url, formats=formats)


def map_site(url: str, limit: int = 20):
    """
    Firecrawl site map wrapper.
    """
    return _fc.map_site(url=url, limit=limit)


def crawl_site(url: str, limit: int = 10):
    """
    Firecrawl crawl wrapper.
    """
    return _fc.crawl_site(url=url, limit=limit)


def crawl_site_map(url: str, limit: int = 50):
    """
    Sponsor-safe crawl helper:
    returns discovered URLs from Firecrawl's site mapping capability
    without extracting page content.
    """
    return _fc.map_site(url=url, limit=limit)


def extract_structured(prompt: str, urls: list[str] | None = None):
    """
    Firecrawl structured extraction wrapper.
    """
    return _fc.extract(prompt=prompt, urls=urls)


def extract_search_items(search_result) -> list[dict]:
    """
    Normalize Firecrawl search response into a simple list of dicts.
    """
    if not search_result:
        return []

    raw_items = []
    if hasattr(search_result, "web") and getattr(search_result, "web", None):
        raw_items = search_result.web
    elif isinstance(search_result, dict):
        raw_items = (
            search_result.get("web", [])
            or search_result.get("data", [])
            or search_result.get("results", [])
            or []
        )

    items = []
    for item in raw_items:
        if isinstance(item, dict):
            url = (item.get("url") or item.get("link") or item.get("source_url") or "").strip()
            title = (item.get("title") or "").strip()
            description = (item.get("description") or item.get("snippet") or "").strip()
            published_date = (
                item.get("publishedDate")
                or item.get("published_date")
                or item.get("date")
                or item.get("timestamp")
                or ""
            )
        else:
            url = (getattr(item, "url", "") or "").strip()
            title = (getattr(item, "title", "") or "").strip()
            description = (getattr(item, "description", "") or "").strip()
            published_date = (
                getattr(item, "publishedDate", "")
                or getattr(item, "published_date", "")
                or getattr(item, "date", "")
                or getattr(item, "timestamp", "")
                or ""
            )

        if not url:
            continue

        items.append(
            {
                "url": url,
                "title": title,
                "description": description,
                "published_date": str(published_date).strip(),
            }
        )

    return items