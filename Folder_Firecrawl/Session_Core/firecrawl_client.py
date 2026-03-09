from firecrawl import Firecrawl
from config import FIRECRAWL_API_KEY, DEFAULT_SEARCH_LIMIT, DEFAULT_CRAWL_LIMIT


class FirecrawlClient:
    def __init__(self, api_key: str | None = None):
        key = api_key or FIRECRAWL_API_KEY
        if not key:
            raise ValueError("Missing FIRECRAWL_API_KEY in environment.")
        self.client = Firecrawl(api_key=key)

    def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT):
        return self.client.search(query=query, limit=limit)

    def scrape(self, url: str, formats: list[str] | None = None):
        return self.client.scrape(
            url,
            formats=formats or ["markdown", "html"]
        )

    def map_site(self, url: str, limit: int = 20):
        return self.client.map(url=url, limit=limit)

    def crawl_site(self, url: str, limit: int = DEFAULT_CRAWL_LIMIT):
        return self.client.crawl(url=url, limit=limit)

    def extract(self, prompt: str, urls: list[str] | None = None):
        if urls:
            return self.client.extract(prompt=prompt, urls=urls)
        return self.client.extract(prompt=prompt)