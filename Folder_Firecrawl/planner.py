def plan_actions(instruction: str):
    lower = instruction.lower()

    multi_site_triggers = [
        "all results",
        "all info",
        "all information",
        "multiple websites",
        "multiple sources",
        "scrape information on",
        "scrape all info",
        "scrape all information",
        "find information on",
        "search for",
        "search all",
        "compare sources",
    ]

    if any(trigger in lower for trigger in multi_site_triggers):
        return [
            {
                "tool": "search_web",
                "args": {
                    "query": instruction,
                    "limit": 10,
                },
            },
            {
                "tool": "scrape_top_search_results",
                "args": {
                    "limit": 3,
                },
            },
            {
                "tool": "summarize_last_scrape",
                "args": {},
            },
        ]

    return [
        {
            "tool": "search_web",
            "args": {
                "query": instruction,
                "limit": 10,
            },
        },
        {
            "tool": "scrape_first_search_result",
            "args": {},
        },
        {
            "tool": "summarize_last_scrape",
            "args": {},
        },
    ]