import re
import time
from typing import Any

from telemetry import TraceLogger
from tools.firecrawl_tools import search_web, crawl_site_map, extract_search_items


def extract_domain_from_text(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,})\b", text)
    return match.group(1).lower() if match else None


def is_pdf_url(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    return lower.endswith(".pdf") or ".pdf?" in lower


def extract_domain(url: str) -> str:
    match = re.search(r"https?://([^/]+)", (url or "").lower())
    return match.group(1) if match else (url or "").lower()


def domain_matches(url: str, domain: str) -> bool:
    host = extract_domain(url)
    domain = (domain or "").lower().strip()

    if not host or not domain:
        return False

    return host == domain or host.endswith("." + domain)


def classify_search_intent(query: str, search_profile: str | None = None) -> dict:
    q = (query or "").lower()

    time_window = None
    if "last 24 hours" in q or "past 24 hours" in q:
        time_window = "24h"
    elif "past month" in q or "last month" in q:
        time_window = "30d"
    elif "past week" in q or "last week" in q or "this week" in q:
        time_window = "7d"

    is_reddit = (
        search_profile == "reddit_recent"
        or "reddit" in q
        or "subreddit" in q
        or "thread" in q
        or "discussion" in q
        or "discussions" in q
    )

    is_news = (
        search_profile == "news_recent"
        or "news" in q
        or "headline" in q
        or "headlines" in q
        or "story" in q
        or "stories" in q
        or "breaking" in q
    )

    wants_recent = (
        search_profile in {"reddit_recent", "news_recent", "fresh_search"}
        or any(
            phrase in q
            for phrase in [
                "latest",
                "most recent",
                "recent",
                "past month",
                "last month",
                "past week",
                "last week",
                "this week",
                "last 24 hours",
                "past 24 hours",
                "today",
                "yesterday",
                "current",
                "newest",
                "breaking",
            ]
        )
    )

    wants_top_n = None
    top_match = re.search(r"\btop\s+(\d+)\b", q)
    if top_match:
        try:
            wants_top_n = int(top_match.group(1))
        except Exception:
            wants_top_n = None

    return {
        "is_reddit": is_reddit,
        "is_news": is_news,
        "wants_recent": wants_recent,
        "time_window": time_window,
        "search_profile": search_profile or "general_search",
        "wants_top_n": wants_top_n,
    }


def normalize_search_query(query: str, search_profile: str | None = None) -> str:
    if not query:
        return query

    cleaned = query.strip()

    m = re.match(
        r"^\s*what\s+does\s+wikipedia\s+say\s+about\s+(.+)$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if m:
        topic = m.group(1).strip(" .,:;?!")
        cleaned = f"{topic} Wikipedia"
        if "-filetype:pdf" not in cleaned.lower():
            cleaned += " -filetype:pdf"
        return cleaned

    intent = classify_search_intent(cleaned, search_profile=search_profile)

    if intent["is_reddit"]:
        no_quotes = re.sub(r"[\"']", "", cleaned).strip()
        if "site:reddit.com" not in no_quotes.lower():
            return f"site:reddit.com {no_quotes}"
        return no_quotes

    if intent["is_news"]:
        return re.sub(r"[\"']", "", cleaned).strip()

    lower = cleaned.lower()
    domain_match = re.search(r"\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,})\b", cleaned)
    domain = domain_match.group(1) if domain_match else None

    if domain:
        if "pricing" in lower and "faq" in lower:
            return f"site:{domain} pricing faq business model -filetype:pdf"
        if "returns" in lower:
            return f"site:{domain} returns return policy -filetype:pdf"
        if "documentation" in lower or "docs" in lower:
            if "state graph" in lower or "stategraph" in lower:
                return f"site:{domain} state graph documentation code example -filetype:pdf"
            return f"site:{domain} documentation docs -filetype:pdf"
        if "login" in lower:
            return f"site:{domain} login -filetype:pdf"
        if "url" in lower or "urls" in lower:
            return f"site:{domain} documentation urls -filetype:pdf"

    filler_patterns = [
        r"\bcrawl\b",
        r"\bscrape\b",
        r"\bsearch\b",
        r"\bfind\b",
        r"\blook up\b",
        r"\bgo to\b",
        r"\bextract\b",
        r"\bsummarize\b",
        r"\bmap out\b",
        r"\bidentify\b",
        r"\breturn\b",
        r"\bentire\b",
        r"\ball\b",
        r"\bsection\b",
        r"\bsections\b",
        r"\bpage\b",
        r"\bpages\b",
        r"\bsite\b",
        r"\bwebsite\b",
        r"\binto markdown\b",
        r"\binto json\b",
        r"[\"']",
    ]

    working = lower
    for pattern in filler_patterns:
        working = re.sub(pattern, " ", working, flags=re.IGNORECASE)

    stopwords = {
        "the", "and", "of", "for", "from", "on", "a", "an", "to",
        "all", "their", "its", "with", "that", "which", "ones",
        "found", "available", "major",
    }

    tokens = re.findall(r"[a-zA-Z0-9_-]+", working)

    filtered_tokens = []
    for token in tokens:
        if token in stopwords:
            continue
        if domain and token in domain.lower():
            continue
        if len(token) <= 1:
            continue
        filtered_tokens.append(token)

    seen = set()
    keywords = []
    for token in filtered_tokens:
        if token not in seen:
            seen.add(token)
            keywords.append(token)

    if domain:
        priority_terms = []
        for term in [
            "pricing", "faq", "returns", "return", "documentation", "docs",
            "stategraph", "state", "graph", "code", "example", "login",
            "business", "model", "urls",
        ]:
            if term in keywords:
                priority_terms.append(term)

        other_terms = [k for k in keywords if k not in priority_terms]
        final_terms = (priority_terms + other_terms)[:8]
        cleaned = f"site:{domain} " + " ".join(final_terms)
    else:
        cleaned = " ".join(keywords[:10])

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if cleaned and "-filetype:pdf" not in cleaned.lower():
        cleaned += " -filetype:pdf"

    return cleaned or query.strip()


def build_search_queries(query: str, search_profile: str | None = None) -> list[str]:
    normalized = normalize_search_query(query, search_profile=search_profile)
    intent = classify_search_intent(query, search_profile=search_profile)
    expanded = []

    if intent["is_reddit"]:
        base = re.sub(r"[\"']", "", query or "").strip()
        candidates = [
            f"site:reddit.com {base}",
            f"site:reddit.com/r/shopify {base}" if "shopify" in base.lower() else "",
            f"site:reddit.com {base} discussion",
            f"site:reddit.com {base} thread",
        ]
        expanded.extend([re.sub(r"\s+", " ", c).strip() for c in candidates if c])

    elif intent["is_news"]:
        base = re.sub(r"[\"']", "", query or "").strip()
        candidates = [
            base,
            f"{base} breaking news",
            f"{base} latest updates",
        ]
        expanded.extend([re.sub(r"\s+", " ", c).strip() for c in candidates if c])

    elif search_profile == "search_first_discovery":
        expanded.append(normalized)
        lower = (query or "").lower()
        domain = extract_domain_from_text(query or "")
        if domain:
            if "build" in lower or "apps" in lower:
                expanded.append(f"site:{domain} building apps developer docs -filetype:pdf")
            if "documentation" in lower or "api" in lower:
                expanded.append(f"site:{domain} documentation api developer -filetype:pdf")
    else:
        expanded.append(normalized)

    seen = set()
    final_queries = []
    for q in expanded:
        key = q.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        final_queries.append(q)

    return final_queries[:4]


def infer_recency_score(item: dict, intent: dict | None = None) -> int:
    if not intent or not intent.get("wants_recent"):
        return 0

    score = 0
    title = (item.get("title") or "").lower()
    description = (item.get("description") or "").lower()
    published_date = (item.get("published_date") or "").lower()
    combined = f"{title} {description} {published_date}"

    if published_date:
        score += 4

    recent_terms = [
        "today", "yesterday", "hours ago", "hour ago", "minutes ago",
        "minute ago", "just now", "latest", "breaking", "new", "updated",
    ]
    if any(term in combined for term in recent_terms):
        score += 4

    stale_terms = ["2021", "2022", "2023", "2024"]
    if intent.get("time_window") in {"24h", "7d", "30d"} and any(term in combined for term in stale_terms):
        score -= 4

    return score


def score_search_item(item: dict, query: str, intent: dict | None = None) -> int:
    score = 0
    q_words = set(re.findall(r"\w+", (query or "").lower()))

    title = (item.get("title") or "").lower()
    description = (item.get("description") or "").lower()
    url = (item.get("url") or "").lower()
    domain = extract_domain(url)

    for word in q_words:
        if len(word) < 3:
            continue
        if word in title:
            score += 3
        elif word in description:
            score += 2
        elif word in url:
            score += 1

    if title:
        score += 1
    if description:
        score += 1

    if "docs" in url or "documentation" in url:
        score += 3
    if "/api" in url or "developer" in url:
        score += 2

    if is_pdf_url(url):
        score -= 100

    if intent:
        if intent.get("is_reddit"):
            if "reddit.com" in domain:
                score += 10
            if "/r/" in url:
                score += 3
            if "comments" in url:
                score += 3

        if intent.get("is_news"):
            trusted_news_domains = [
                "reuters.com", "apnews.com", "wsj.com", "bloomberg.com",
                "cnbc.com", "retaildive.com", "modernretail.co",
                "chainstoreage.com", "retailwire.com",
            ]
            if any(d in domain for d in trusted_news_domains):
                score += 8

        score += infer_recency_score(item, intent=intent)

    return score


def rank_and_filter_search_results(
    search_items: list[dict],
    original_query: str,
    intent: dict | None = None,
    max_results: int = 8,
) -> list[dict]:
    if not search_items:
        return []

    seen_urls = set()
    unique_items = []

    for item in search_items:
        url = item["url"]
        if is_pdf_url(url):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        unique_items.append(item)

    ranked = sorted(
        unique_items,
        key=lambda x: score_search_item(x, original_query, intent=intent),
        reverse=True,
    )

    final_items = []
    domain_counts = {}

    for item in ranked:
        domain = extract_domain(item["url"])
        domain_counts.setdefault(domain, 0)

        per_domain_cap = 4 if intent and (intent.get("is_reddit") or intent.get("is_news")) else 3

        if domain_counts[domain] >= per_domain_cap:
            continue

        final_items.append(item)
        domain_counts[domain] += 1

        if len(final_items) >= max_results:
            break

    return final_items


def should_use_llm_rerank(intent: dict, items: list[dict]) -> bool:
    if not items or len(items) < 5:
        return False

    if intent.get("is_reddit"):
        return True

    if intent.get("is_news"):
        return True

    if intent.get("search_profile") in {"fresh_search", "search_first_discovery"}:
        return True

    return False


def llm_rerank_results(
    items: list[dict],
    query: str,
    intent: dict,
    llm_client=None,
) -> list[dict]:
    if not llm_client or not items:
        return items

    numbered_blocks = []
    for i, item in enumerate(items, start=1):
        numbered_blocks.append(
            f"[{i}]\n"
            f"Title: {item.get('title', '')}\n"
            f"Description: {item.get('description', '')}\n"
            f"URL: {item.get('url', '')}\n"
            f"Published Date: {item.get('published_date', '')}"
        )

    prompt = (
        "Rank these search results from most useful to least useful for the user's query.\n\n"
        "Prioritize:\n"
        "1. Exact relevance to the query\n"
        "2. Source match\n"
        "3. Recency if the user asked for recent/latest information\n"
        "4. Official or primary sources when appropriate\n\n"
        "Return only a comma-separated list of result numbers in ranked order.\n\n"
        f"User query: {query}\n"
        f"Intent: {intent}\n\n"
        + "\n\n".join(numbered_blocks)
    )

    try:
        response = llm_client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=120,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        nums = re.findall(r"\d+", text)
        ranked_indices = []
        seen = set()

        for n in nums:
            idx = int(n)
            if 1 <= idx <= len(items) and idx not in seen:
                ranked_indices.append(idx)
                seen.add(idx)

        reranked = [items[idx - 1] for idx in ranked_indices]

        for i, item in enumerate(items, start=1):
            if i not in seen:
                reranked.append(item)

        return reranked

    except Exception:
        return items


def summarize_search_results_only(
    ranked_items: list[dict],
    query: str,
    summary_profile: str | None = None,
    llm_client=None,
    max_results: int = 8,
) -> str:
    top_items = ranked_items[:max_results]

    if not top_items:
        return "No useful non-PDF search results were found."

    if llm_client:
        try:
            result_text = "\n\n".join(
                (
                    f"Title: {item['title']}\n"
                    f"Description: {item['description']}\n"
                    f"URL: {item['url']}\n"
                    f"Published Date: {item.get('published_date', '')}"
                )
                for item in top_items
            )

            response = llm_client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=450,
                temperature=0.2,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Summarize these search results into a concise but informative answer. "
                            "Use only the titles, descriptions, URLs, and published dates provided. "
                            "Prioritize official documentation or primary sources when present. "
                            "Do not invent details.\n\n"
                            f"User query: {query}\n\n"
                            f"{result_text}"
                        ),
                    }
                ],
            )

            if response.content and len(response.content) > 0:
                return response.content[0].text.strip()
        except Exception:
            pass

    lines = [f"Summary based on top search results for: {query}\n"]
    for idx, item in enumerate(top_items, start=1):
        title = item["title"] or "Untitled result"
        desc = item["description"] or "No description available."
        url = item["url"]
        lines.append(f"{idx}. {title} — {desc} ({url})")

    return "\n".join(lines)


def normalize_crawl_query(query: str) -> dict:
    original = (query or "").strip()
    lower = original.lower()
    domain = extract_domain_from_text(original)

    if not domain:
        raise ValueError("Could not detect a domain for crawl mode.")

    include_patterns = []
    if any(term in lower for term in ["doc", "documentation", "api", "developer"]):
        include_patterns.extend(["docs", "documentation", "api", "developer"])
    if "pricing" in lower:
        include_patterns.extend(["pricing", "plans"])
    if "faq" in lower or "help" in lower:
        include_patterns.extend(["faq", "help"])
    if "build" in lower or "apps" in lower:
        include_patterns.extend(["apps", "build", "developer"])

    return {
        "domain": domain,
        "seed_url": f"https://{domain}",
        "include_patterns": list(dict.fromkeys(include_patterns)),
    }


def flatten_crawl_urls(crawl_result) -> list[str]:
    if not crawl_result:
        return []

    if isinstance(crawl_result, dict):
        raw_urls = (
            crawl_result.get("urls")
            or crawl_result.get("links")
            or crawl_result.get("results")
            or []
        )
    else:
        raw_urls = getattr(crawl_result, "urls", None) or getattr(crawl_result, "links", None) or []

    urls = []
    for item in raw_urls:
        if isinstance(item, str):
            url = item.strip()
        elif isinstance(item, dict):
            url = (item.get("url") or item.get("link") or "").strip()
        else:
            url = (getattr(item, "url", "") or getattr(item, "link", "") or "").strip()

        if url:
            urls.append(url)

    seen = set()
    deduped = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)

    return deduped


def classify_url(url: str) -> str:
    u = (url or "").lower()
    host = extract_domain(url)

    if host.startswith("docs.") or "/docs" in u or "/documentation" in u:
        return "documentation"
    if host.startswith("api.") or "/api" in u or "developer" in u:
        return "api/developer"
    if "/apps" in u or "/build" in u:
        return "apps/build"
    if "/pricing" in u or "/plans" in u:
        return "pricing"
    if "/faq" in u or "/help" in u or "/support" in u:
        return "faq/help"
    if "/blog" in u:
        return "blog"
    if "/login" in u or "/signin" in u or "/account" in u:
        return "account"
    if "forum." in host or "/forum" in u or "/community" in u:
        return "community/forum"
    return "other"


def filter_crawl_urls(urls: list[str], domain: str, limit: int = 50) -> list[dict]:
    filtered = []
    for url in urls:
        if not domain_matches(url, domain):
            continue
        if is_pdf_url(url):
            continue
        filtered.append(
            {
                "url": url,
                "category": classify_url(url),
            }
        )

    preferred_order = {
        "documentation": 0,
        "api/developer": 1,
        "apps/build": 2,
        "pricing": 3,
        "faq/help": 4,
        "other": 5,
        "blog": 6,
        "community/forum": 7,
        "account": 8,
    }

    filtered = sorted(
        filtered,
        key=lambda x: (preferred_order.get(x["category"], 99), x["url"]),
    )

    seen = set()
    deduped = []
    for item in filtered:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        deduped.append(item)
        if len(deduped) >= limit:
            break

    return deduped


def summarize_crawl_results_only(
    crawl_items: list[dict],
    domain: str,
    query: str,
    llm_client=None,
    max_results: int = 20,
) -> str:
    if not crawl_items:
        return f"No useful URLs were discovered for {domain}."

    top_items = crawl_items[:max_results]

    if llm_client:
        try:
            crawl_text = "\n".join(
                f"- [{item['category']}] {item['url']}"
                for item in top_items
            )

            response = llm_client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=400,
                temperature=0.2,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Summarize these discovered site URLs. "
                            "Group them by likely category such as documentation, api/developer, apps/build, pricing, or faq/help. "
                            "Use only the URLs provided. "
                            "Do not claim you extracted page content. "
                            "Keep the answer concise and structured.\n\n"
                            f"User query: {query}\n"
                            f"Domain: {domain}\n\n"
                            f"{crawl_text}"
                        ),
                    }
                ],
            )

            if response.content and len(response.content) > 0:
                return response.content[0].text.strip()
        except Exception:
            pass

    grouped = {}
    for item in top_items:
        grouped.setdefault(item["category"], []).append(item["url"])

    lines = [f"Discovered URLs for {domain}:"]
    for category, urls in grouped.items():
        lines.append(f"\n{category.upper()}:")
        for url in urls[:8]:
            lines.append(f"- {url}")

    return "\n".join(lines)


class AgentExecutor:
    def __init__(
        self,
        instruction: str,
        mode: str = "firecrawl_headless",
        llm_client=None,
    ):
        self.trace_logger = TraceLogger(instruction=instruction, mode=mode)
        self.context = {
            "original_instruction": instruction,
            "mode": mode,
        }
        self.llm_client = llm_client

    def _log_success(
        self,
        step_number: int,
        tool_name: str,
        args: dict,
        start_perf: float,
        start_time_iso: str,
        result: Any,
    ):
        self.trace_logger.log_step(
            step_number=step_number,
            tool=tool_name,
            args=args,
            start_perf=start_perf,
            start_time_iso=start_time_iso,
            status="success",
            result=result,
        )

    def _log_error(
        self,
        step_number: int,
        tool_name: str,
        args: dict,
        start_perf: float,
        start_time_iso: str,
        error: str,
    ):
        self.trace_logger.log_step(
            step_number=step_number,
            tool=tool_name,
            args=args,
            start_perf=start_perf,
            start_time_iso=start_time_iso,
            status="error",
            error=error,
        )

    def _execute_tool(self, tool_name: str, args: dict) -> Any:
        if tool_name == "search_web":
            cleaned_args = dict(args)
            original_query = args.get("query", "")
            search_profile = args.get("search_profile", "general_search")
            intent = classify_search_intent(original_query, search_profile=search_profile)
            expanded_queries = build_search_queries(original_query, search_profile=search_profile)

            cleaned_args.pop("search_profile", None)

            print(f"[DEBUG] Search profile: {search_profile}")
            print(f"[DEBUG] Expanded Firecrawl queries: {expanded_queries}")

            tool_start = time.perf_counter()
            aggregated_items = []
            raw_results = []

            requested_limit = int(args.get("limit", 25))
            per_query_limit = max(8, requested_limit // max(1, len(expanded_queries)))

            for q in expanded_queries:
                query_args = dict(cleaned_args)
                query_args["query"] = q
                query_args["limit"] = per_query_limit

                result = search_web(**query_args)
                raw_results.append(
                    {
                        "query": q,
                        "result": result,
                    }
                )
                aggregated_items.extend(extract_search_items(result))

            tool_elapsed = round(time.perf_counter() - tool_start, 4)

            ranked_items = rank_and_filter_search_results(
                search_items=aggregated_items,
                original_query=original_query,
                intent=intent,
                max_results=requested_limit,
            )

            final_ranked_items = ranked_items
            if self.llm_client and should_use_llm_rerank(intent, ranked_items):
                final_ranked_items = llm_rerank_results(
                    items=ranked_items[:8],
                    query=original_query,
                    intent=intent,
                    llm_client=self.llm_client,
                )

            aggregated_result = {
                "web": final_ranked_items,
                "raw_queries": expanded_queries,
                "raw_results": raw_results,
            }

            self.context["last_search_result"] = aggregated_result
            self.context["last_search_query"] = original_query
            self.context["last_search_queries"] = expanded_queries
            self.context["last_search_profile"] = search_profile
            self.context["search_intent"] = intent
            self.context["search_response_time_seconds"] = tool_elapsed
            self.context["raw_result_count"] = len(aggregated_items)
            self.context["filtered_result_count"] = len(final_ranked_items)
            self.context["returned_urls"] = [item["url"] for item in final_ranked_items]
            self.context["returned_domains"] = sorted(
                list({extract_domain(item["url"]) for item in final_ranked_items})
            )
            self.context["results_preview"] = final_ranked_items[:5]
            self.context["selected_url"] = final_ranked_items[0]["url"] if final_ranked_items else None
            self.context["selected_result"] = final_ranked_items[0] if final_ranked_items else None

            return aggregated_result

        if tool_name == "summarize_search_results":
            search_result = self.context.get("last_search_result")
            query = self.context.get("last_search_query", "")
            summary_profile = args.get(
                "summary_profile",
                self.context.get("last_search_profile", "general_search"),
            )

            ranked_items = []
            if isinstance(search_result, dict):
                ranked_items = search_result.get("web", [])

            tool_start = time.perf_counter()
            result = summarize_search_results_only(
                ranked_items=ranked_items,
                query=query,
                summary_profile=summary_profile,
                llm_client=self.llm_client,
                max_results=args.get("limit", 8),
            )
            tool_elapsed = round(time.perf_counter() - tool_start, 4)

            self.context["last_summary"] = result
            self.context["summary_profile"] = summary_profile
            self.context["summary_response_time_seconds"] = tool_elapsed
            self.context["summary_length_chars"] = len(result or "")

            return result

        if tool_name == "crawl_site_map":
            crawl_config = normalize_crawl_query(args.get("query", ""))
            domain = crawl_config["domain"]

            print(f"[DEBUG] Firecrawl crawl domain: {domain}")
            print(f"[DEBUG] Firecrawl crawl include patterns: {crawl_config['include_patterns']}")

            tool_start = time.perf_counter()
            result = crawl_site_map(
                url=crawl_config["seed_url"],
                limit=args.get("limit", 50),
            )
            tool_elapsed = round(time.perf_counter() - tool_start, 4)

            raw_urls = flatten_crawl_urls(result)
            filtered_urls = filter_crawl_urls(
                urls=raw_urls,
                domain=domain,
                limit=args.get("limit", 50),
            )

            include_patterns = crawl_config["include_patterns"]
            if include_patterns:
                preferred = []
                others = []
                for item in filtered_urls:
                    u = item["url"].lower()
                    if any(p in u for p in include_patterns):
                        preferred.append(item)
                    else:
                        others.append(item)
                filtered_urls = preferred + others

            categories = {}
            for item in filtered_urls:
                categories[item["category"]] = categories.get(item["category"], 0) + 1

            self.context["last_crawl_result"] = result
            self.context["last_crawl_query"] = args.get("query", "")
            self.context["crawl_domain"] = domain
            self.context["crawl_seed_url"] = crawl_config["seed_url"]
            self.context["crawl_response_time_seconds"] = tool_elapsed
            self.context["crawl_raw_url_count"] = len(raw_urls)
            self.context["crawl_filtered_url_count"] = len(filtered_urls)
            self.context["crawl_urls"] = [item["url"] for item in filtered_urls]
            self.context["crawl_items"] = filtered_urls
            self.context["crawl_category_counts"] = categories

            return result

        if tool_name == "summarize_crawl_results":
            crawl_items = self.context.get("crawl_items", [])
            domain = self.context.get("crawl_domain", "")
            query = self.context.get("last_crawl_query", "")

            tool_start = time.perf_counter()
            result = summarize_crawl_results_only(
                crawl_items=crawl_items,
                domain=domain,
                query=query,
                llm_client=self.llm_client,
                max_results=args.get("limit", 20),
            )
            tool_elapsed = round(time.perf_counter() - tool_start, 4)

            self.context["last_summary"] = result
            self.context["crawl_summary_response_time_seconds"] = tool_elapsed
            self.context["summary_length_chars"] = len(result or "")

            return result

        raise ValueError(f"Unknown tool: {tool_name}")

    def run_plan(self, plan: list[dict]) -> dict[str, Any]:
        outputs = []

        for i, step in enumerate(plan, start=1):
            tool_name = step["tool"]
            args = step.get("args", {})

            start_perf = time.perf_counter()
            start_time_iso = self.trace_logger.now_iso()

            try:
                result = self._execute_tool(tool_name, args)

                outputs.append(
                    {
                        "step": i,
                        "tool": tool_name,
                        "args": args,
                        "result": result,
                    }
                )

                self._log_success(i, tool_name, args, start_perf, start_time_iso, result)

            except Exception as e:
                self._log_error(i, tool_name, args, start_perf, start_time_iso, str(e))
                outputs.append(
                    {
                        "step": i,
                        "tool": tool_name,
                        "args": args,
                        "error": str(e),
                    }
                )
                break

        return {
            "outputs": outputs,
            "trace": self.trace_logger.to_dict(),
            "context": self.context,
        }