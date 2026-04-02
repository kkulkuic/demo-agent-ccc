def plan_actions(
    instruction: str,
    search_limit: int = 25,
    summary_limit: int = 8,
    crawl_limit: int = 50,
):
    lower = instruction.lower().strip()

    def has_any(terms: list[str]) -> bool:
        return any(term in lower for term in terms)

    def extract_after_phrase(phrases: list[str]) -> str | None:
        for phrase in phrases:
            idx = lower.find(phrase)
            if idx != -1:
                value = instruction[idx + len(phrase):].strip(" :,-")
                if value:
                    return value
        return None

    # ------------------------------------------------------------------
    # Existing crawl / discovery logic
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # NEW: direct browser / interaction logic
    # ------------------------------------------------------------------
    open_direct_terms = [
        "open ",
        "go to ",
        "visit ",
        "navigate to ",
    ]

    read_page_terms = [
        "read this page",
        "read the page",
        "open and read",
        "open the page",
        "open website",
        "open the site",
        "visit the site",
    ]

    click_terms = [
        "click ",
        "press ",
        "select ",
        "tap ",
    ]

    type_terms = [
        "type ",
        "enter ",
        "search for ",
        "fill in ",
        "put ",
    ]

    screenshot_terms = [
        "screenshot",
        "capture screenshot",
        "take a screenshot",
        "save screenshot",
    ]

    current_url_terms = [
        "current url",
        "what url am i on",
        "where am i",
        "get current url",
    ]

    # ------------------------------------------------------------------
    # 1. Strong crawl mode
    # ------------------------------------------------------------------
    if has_any(strong_crawl_terms):
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

    # ------------------------------------------------------------------
    # 2. Search-first discovery mode
    # ------------------------------------------------------------------
    if has_any(search_first_discovery_terms):
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

    # ------------------------------------------------------------------
    # 3. Click action after open
    # Example: "search for OpenAI and click pricing"
    # ------------------------------------------------------------------
    if has_any(click_terms) and ("search" in lower or "find" in lower or "look up" in lower):
        click_target = extract_after_phrase(["click ", "press ", "select ", "tap "]) or ""
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
                "tool": "open_best_search_result",
                "args": {},
            },
            {
                "tool": "read_opened_page",
                "args": {
                    "max_chars": 4000,
                },
            },
            {
                "tool": "click_on_page",
                "args": {
                    "target": click_target,
                    "show_viz": True,
                },
            },
            {
                "tool": "read_opened_page",
                "args": {
                    "max_chars": 4000,
                },
            },
            {
                "tool": "summarize_opened_page",
                "args": {
                    "max_results": summary_limit,
                    "max_page_chars": 3500,
                },
            },
        ]

    # ------------------------------------------------------------------
    # 4. Type/search-box action after open
    # Example: "open google and type Playwright"
    # ------------------------------------------------------------------
    if has_any(type_terms) and has_any(open_direct_terms + read_page_terms):
        typed_text = extract_after_phrase(["type ", "enter ", "search for ", "fill in ", "put "]) or ""
        url = extract_after_phrase(["open ", "go to ", "visit ", "navigate to "]) or ""

        if not url.startswith("http") and "." in url:
            url = f"https://{url}"
        elif not url:
            url = "https://www.google.com"

        return [
            {
                "tool": "open_url_direct",
                "args": {
                    "url": url,
                },
            },
            {
                "tool": "read_opened_page",
                "args": {
                    "max_chars": 3000,
                },
            },
            {
                "tool": "type_text_on_page",
                "args": {
                    "selector": "textarea[name='q'], input[name='q']",
                    "text": typed_text,
                    "delay_ms": 25,
                    "press_enter": True,
                    "show_viz": True,
                },
            },
            {
                "tool": "read_opened_page",
                "args": {
                    "max_chars": 4000,
                },
            },
            {
                "tool": "summarize_opened_page",
                "args": {
                    "max_results": summary_limit,
                    "max_page_chars": 3500,
                },
            },
        ]

    # ------------------------------------------------------------------
    # 5. Direct open + click
    # Example: "open wikipedia.org and click English"
    # ------------------------------------------------------------------
    if has_any(click_terms) and has_any(open_direct_terms):
        click_target = extract_after_phrase(["click ", "press ", "select ", "tap "]) or ""
        url = extract_after_phrase(["open ", "go to ", "visit ", "navigate to "]) or ""

        if url and not url.startswith("http") and "." in url:
            url = f"https://{url}"

        return [
            {
                "tool": "open_url_direct",
                "args": {
                    "url": url,
                },
            },
            {
                "tool": "read_opened_page",
                "args": {
                    "max_chars": 3000,
                },
            },
            {
                "tool": "click_on_page",
                "args": {
                    "target": click_target,
                    "show_viz": True,
                },
            },
            {
                "tool": "read_opened_page",
                "args": {
                    "max_chars": 4000,
                },
            },
            {
                "tool": "summarize_opened_page",
                "args": {
                    "max_results": summary_limit,
                    "max_page_chars": 3500,
                },
            },
        ]

    # ------------------------------------------------------------------
    # 6. Direct open + read
    # ------------------------------------------------------------------
    if has_any(open_direct_terms) or has_any(read_page_terms):
        url = extract_after_phrase(["open ", "go to ", "visit ", "navigate to "]) or ""

        if url and not url.startswith("http") and "." in url:
            url = f"https://{url}"

        if url:
            return [
                {
                    "tool": "open_url_direct",
                    "args": {
                        "url": url,
                    },
                },
                {
                    "tool": "read_opened_page",
                    "args": {
                        "max_chars": 5000,
                    },
                },
                {
                    "tool": "summarize_opened_page",
                    "args": {
                        "max_results": summary_limit,
                        "max_page_chars": 3500,
                    },
                },
            ]

    # ------------------------------------------------------------------
    # 7. Screenshot current page
    # ------------------------------------------------------------------
    if has_any(screenshot_terms):
        return [
            {
                "tool": "capture_screenshot",
                "args": {
                    "path": "headed_step.png",
                },
            },
            {
                "tool": "get_current_url",
                "args": {},
            },
        ]

    # ------------------------------------------------------------------
    # 8. Current URL only
    # ------------------------------------------------------------------
    if has_any(current_url_terms):
        return [
            {
                "tool": "get_current_url",
                "args": {},
            }
        ]

    # ------------------------------------------------------------------
    # 9. Reddit recent discussion search
    # ------------------------------------------------------------------
    use_freshness = has_any(freshness_terms)
    use_reddit = has_any(reddit_terms)
    use_news = has_any(news_terms)

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

    # ------------------------------------------------------------------
    # 10. News / current events
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 11. Generic recent/fresh search
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 12. General search + open best result
    # Better than only search/summarize if user likely wants browsing
    # ------------------------------------------------------------------
    use_search = has_any(search_terms)
    browse_like_terms = [
        "open",
        "visit",
        "website",
        "site",
        "page",
        "show me",
        "go to",
    ]

    if use_search or has_any(browse_like_terms):
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
                "tool": "open_best_search_result",
                "args": {},
            },
            {
                "tool": "read_opened_page",
                "args": {
                    "max_chars": 5000,
                },
            },
            {
                "tool": "summarize_opened_page",
                "args": {
                    "max_results": summary_limit,
                    "max_page_chars": 3500,
                },
            },
        ]

    # ------------------------------------------------------------------
    # 13. Default fallback
    # ------------------------------------------------------------------
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
            "tool": "open_best_search_result",
            "args": {},
        },
        {
            "tool": "read_opened_page",
            "args": {
                "max_chars": 5000,
            },
        },
        {
            "tool": "summarize_opened_page",
            "args": {
                "max_results": summary_limit,
                "max_page_chars": 3500,
            },
        },
    ]
