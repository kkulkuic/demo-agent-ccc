from firecrawl import Firecrawl
from config import FIRECRAWL_API_KEY, DEFAULT_SEARCH_LIMIT, DEFAULT_CRAWL_LIMIT


class FirecrawlClient:
    """
    Thin wrapper around the Firecrawl SDK.

    Keeps one consistent interface for:
    - search
    - scrape
    - site map
    - crawl
    - extract

    This makes the rest of the app easier to update if Firecrawl's SDK
    response format or method signatures change later.
    """

    def __init__(self, api_key: str | None = None):
        key = api_key or FIRECRAWL_API_KEY
        if not key:
            raise ValueError("Missing FIRECRAWL_API_KEY in environment.")
        self.client = Firecrawl(api_key=key)

    def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT):
        """
        Run Firecrawl search.
        """
        if not query or not str(query).strip():
            raise ValueError("search() requires a non-empty query.")

        limit = max(1, int(limit))
        return self.client.search(query=query.strip(), limit=limit)

    def scrape(self, url: str, formats: list[str] | None = None):
        """
        Scrape a single URL with Firecrawl.
        Defaults to markdown + html for flexibility.
        """
        if not url or not str(url).strip():
            raise ValueError("scrape() requires a non-empty URL.")

        cleaned_url = url.strip()
        cleaned_formats = formats or ["markdown", "html"]

        return self.client.scrape(
            cleaned_url,
            formats=cleaned_formats,
        )

    def map_site(self, url: str, limit: int = 20):
        """
        Discover site URLs without crawling full content.
        """
        if not url or not str(url).strip():
            raise ValueError("map_site() requires a non-empty URL.")

        limit = max(1, int(limit))
        return self.client.map(url=url.strip(), limit=limit)

    def crawl_site(self, url: str, limit: int = DEFAULT_CRAWL_LIMIT):
        """
        Crawl a site and retrieve page content/results.
        """
        if not url or not str(url).strip():
            raise ValueError("crawl_site() requires a non-empty URL.")

        limit = max(1, int(limit))
        return self.client.crawl(url=url.strip(), limit=limit)

    def extract(self, prompt: str, urls: list[str] | None = None):
        """
        Firecrawl structured extraction.
        """
        if not prompt or not str(prompt).strip():
            raise ValueError("extract() requires a non-empty prompt.")

        cleaned_prompt = prompt.strip()

        if urls:
            cleaned_urls = [u.strip() for u in urls if u and str(u).strip()]
            if cleaned_urls:
                return self.client.extract(prompt=cleaned_prompt, urls=cleaned_urls)

        return self.client.extract(prompt=cleaned_prompt)