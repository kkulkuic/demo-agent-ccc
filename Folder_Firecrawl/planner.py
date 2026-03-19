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
                },
            },
            {
                "tool": "summarize_search_results",
                "args": {
                    "limit": summary_limit,
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
                },
            },
            {
                "tool": "summarize_search_results",
                "args": {
                    "limit": summary_limit,
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
            },
        },
        {
            "tool": "summarize_search_results",
            "args": {
                "limit": summary_limit,
            },
        },
    ]
