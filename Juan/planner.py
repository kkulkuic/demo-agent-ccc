def plan_actions(
    instruction: str,
    search_limit: int = 25,
    summary_limit: int = 8,
    crawl_limit: int = 50,
):
    lower = instruction.lower().strip()

    # Use crawl only when the user is clearly asking for broad URL discovery
    # across a domain, not just docs/API identification.
    strong_crawl_terms = [
        "crawl the site",
        "crawl this site",
        "crawl the domain",
        "crawl this domain",
        "site map",
        "sitemap",
        "enumerate urls",
        "enumerate all urls",
        "list all urls",
        "list every url",
        "map the whole site",
        "map entire site",
        "full site structure",
        "full website structure",
        "all pages on the site",
        "all pages on this site",
    ]

    # These should still use search first because search is better at finding
    # the important official docs/API hubs before crawl gets noisy.
    search_first_discovery_terms = [
        "map out the urls",
        "map out urls",
        "identify which ones appear to be documentation",
        "identify which ones are documentation",
        "identify which ones appear to be api pages",
        "identify which ones are api pages",
        "documentation pages",
        "documentation-related urls",
        "developer pages",
        "api-related pages",
        "api pages",
        "related to building apps",
        "what pages on",
        "identify pages on",
        "find pages on",
        "official documentation pages",
        "docs pages",
    ]

    # Freshness / recency-sensitive prompts.
    # These should search, but the executor should preserve the original intent
    # and later rank/filter using freshness and source preferences.
    freshness_terms = [
        "latest",
        "most recent",
        "recent",
        "past month",
        "last month",
        "past week",
        "last week",
        "last 24 hours",
        "today",
        "yesterday",
        "this week",
        "breaking",
        "current",
        "newest",
    ]

    reddit_terms = [
        "reddit",
        "subreddit",
        "discussion",
        "discussions",
        "thread",
        "threads",
        "posts",
    ]

    news_terms = [
        "news",
        "headline",
        "headlines",
        "story",
        "stories",
        "breaking news",
    ]

    search_terms = [
        "summarize",
        "pricing",
        "faq",
        "business model",
        "find pricing-related pages",
        "returns",
        "return policy",
        "login",
        "documentation",
        "docs",
        "api",
        "developer",
    ]

    use_strong_crawl = any(term in lower for term in strong_crawl_terms)
    if use_strong_crawl:
        return [
            {
                "tool": "crawl_site_map",
                "args": {
                    "query": instruction,
                    "limit": crawl_limit,
                },
            },
            {
                "tool": "summarize_crawl_results",
                "args": {
                    "limit": summary_limit,
                },
            },
        ]

    use_search_first_discovery = any(
        term in lower for term in search_first_discovery_terms
    )
    if use_search_first_discovery:
        return [
            {
                "tool": "search_web",
                "args": {
                    "query": instruction,
                    "limit": search_limit,
                    "search_profile": "search_first_discovery",
                },
            },
            {
                "tool": "summarize_search_results",
                "args": {
                    "limit": summary_limit,
                    "summary_profile": "search_first_discovery",
                },
            },
        ]

    use_freshness = any(term in lower for term in freshness_terms)
    use_reddit = any(term in lower for term in reddit_terms)
    use_news = any(term in lower for term in news_terms)

    # Reddit recent discussion search
    if use_reddit and (use_freshness or "shopify returns" in lower):
        return [
            {
                "tool": "search_web",
                "args": {
                    "query": instruction,
                    "limit": search_limit,
                    "search_profile": "reddit_recent",
                },
            },
            {
                "tool": "summarize_search_results",
                "args": {
                    "limit": summary_limit,
                    "summary_profile": "reddit_recent",
                },
            },
        ]

    # News / current events search
    if use_news or (use_freshness and "top 5" in lower):
        return [
            {
                "tool": "search_web",
                "args": {
                    "query": instruction,
                    "limit": search_limit,
                    "search_profile": "news_recent",
                },
            },
            {
                "tool": "summarize_search_results",
                "args": {
                    "limit": min(summary_limit, 5) if "top 5" in lower else summary_limit,
                    "summary_profile": "news_recent",
                },
            },
        ]

    # Generic recent/fresh search
    if use_freshness:
        return [
            {
                "tool": "search_web",
                "args": {
                    "query": instruction,
                    "limit": search_limit,
                    "search_profile": "fresh_search",
                },
            },
            {
                "tool": "summarize_search_results",
                "args": {
                    "limit": summary_limit,
                    "summary_profile": "fresh_search",
                },
            },
        ]

    use_search = any(term in lower for term in search_terms)
    if use_search:
        return [
            {
                "tool": "search_web",
                "args": {
                    "query": instruction,
                    "limit": search_limit,
                    "search_profile": "general_search",
                },
            },
            {
                "tool": "summarize_search_results",
                "args": {
                    "limit": summary_limit,
                    "summary_profile": "general_search",
                },
            },
        ]

    # Default fallback: search flow
    return [
        {
            "tool": "search_web",
            "args": {
                "query": instruction,
                "limit": search_limit,
                "search_profile": "general_search",
            },
        },
        {
            "tool": "summarize_search_results",
            "args": {
                "limit": summary_limit,
                "summary_profile": "general_search",
            },
        },
    ]