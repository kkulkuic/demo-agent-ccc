import re
import time
from typing import Any

from telemetry import TraceLogger
from tools.firecrawl_tools import search_web, crawl_site_map


def normalize_search_query(query: str) -> str:
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
        "the",
        "and",
        "of",
        "for",
        "from",
        "on",
        "a",
        "an",
        "to",
        "all",
        "their",
        "its",
        "with",
        "that",
        "which",
        "ones",
        "found",
        "available",
        "major",
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
            "pricing",
            "faq",
            "returns",
            "return",
            "documentation",
            "docs",
            "stategraph",
            "state",
            "graph",
            "code",
            "example",
            "login",
            "business",
            "model",
            "urls",
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


def extract_domain_from_text(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,})\b", text)
    return match.group(1).lower() if match else None


def extract_search_items(search_result) -> list[dict]:
    if not search_result:
        return []

    items = []
    raw_items = []

    if hasattr(search_result, "web") and getattr(search_result, "web", None):
        raw_items = search_result.web
    elif isinstance(search_result, dict):
        raw_items = search_result.get("web", [])

    for item in raw_items:
        if isinstance(item, dict):
            url = (item.get("url") or "").strip()
            title = (item.get("title") or "").strip()
            description = (item.get("description") or "").strip()
        else:
            url = (getattr(item, "url", "") or "").strip()
            title = (getattr(item, "title", "") or "").strip()
            description = (getattr(item, "description", "") or "").strip()

        if not url:
            continue

        items.append(
            {
                "url": url,
                "title": title,
                "description": description,
            }
        )

    return items


def is_pdf_url(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    return lower.endswith(".pdf") or ".pdf?" in lower


def extract_domain(url: str) -> str:
    match = re.search(r"https?://([^/]+)", (url or "").lower())
    return match.group(1) if match else (url or "").lower()


def domain_matches(url: str, domain: str) -> bool:
    """
    Allow the exact domain and any subdomain.
    Example:
      domain=langchain.com
      matches langchain.com, docs.langchain.com, python.langchain.com
    """
    host = extract_domain(url)
    domain = (domain or "").lower().strip()

    if not host or not domain:
        return False

    return host == domain or host.endswith("." + domain)


def score_search_item(item: dict, query: str) -> int:
    score = 0
    q_words = set(re.findall(r"\w+", (query or "").lower()))

    title = (item.get("title") or "").lower()
    description = (item.get("description") or "").lower()
    url = (item.get("url") or "").lower()

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

    return score


def rank_and_filter_search_results(
    search_result,
    original_query: str,
    max_results: int = 8,
) -> list[dict]:
    items = extract_search_items(search_result)

    if not items:
        return []

    seen_urls = set()
    unique_items = []

    for item in items:
        url = item["url"]
        if is_pdf_url(url):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        unique_items.append(item)

    ranked = sorted(
        unique_items,
        key=lambda x: score_search_item(x, original_query),
        reverse=True,
    )

    final_items = []
    domain_counts = {}

    for item in ranked:
        domain = extract_domain(item["url"])
        domain_counts.setdefault(domain, 0)

        if domain_counts[domain] >= 3:
            continue

        final_items.append(item)
        domain_counts[domain] += 1

        if len(final_items) >= max_results:
            break

    return final_items


def summarize_search_results_only(
    search_result,
    query: str,
    llm_client=None,
    max_results: int = 8,
) -> str:
    ranked_items = rank_and_filter_search_results(
        search_result=search_result,
        original_query=query,
        max_results=max_results,
    )

    if not ranked_items:
        return "No useful non-PDF search results were found."

    if llm_client:
        try:
            result_text = "\n\n".join(
                f"Title: {item['title']}\nDescription: {item['description']}\nURL: {item['url']}"
                for item in ranked_items
            )

            response = llm_client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=350,
                temperature=0.2,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Summarize these search results into a concise but informative answer. "
                            "Use only the titles and descriptions provided. "
                            "Prioritize official documentation or primary sources when present. "
                            "List the most relevant URLs first if appropriate. "
                            "Do not say you scraped or opened the websites. "
                            "Do not invent details not present in the search results.\n\n"
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
    for idx, item in enumerate(ranked_items, start=1):
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
            cleaned_query = normalize_search_query(args.get("query", ""))
            cleaned_args["query"] = cleaned_query

            print(f"[DEBUG] Firecrawl query: {cleaned_query}")

            tool_start = time.perf_counter()
            result = search_web(**cleaned_args)
            tool_elapsed = round(time.perf_counter() - tool_start, 4)

            raw_items = extract_search_items(result)
            ranked_items = rank_and_filter_search_results(
                search_result=result,
                original_query=cleaned_query,
                max_results=args.get("limit", 25),
            )

            self.context["last_search_result"] = result
            self.context["last_search_query"] = cleaned_query
            self.context["search_response_time_seconds"] = tool_elapsed
            self.context["raw_result_count"] = len(raw_items)
            self.context["filtered_result_count"] = len(ranked_items)
            self.context["returned_urls"] = [item["url"] for item in ranked_items]
            self.context["returned_domains"] = sorted(
                list({extract_domain(item["url"]) for item in ranked_items})
            )
            self.context["results_preview"] = ranked_items[:5]

            return result

        if tool_name == "summarize_search_results":
            search_result = self.context.get("last_search_result")
            query = self.context.get("last_search_query", "")

            tool_start = time.perf_counter()
            result = summarize_search_results_only(
                search_result=search_result,
                query=query,
                llm_client=self.llm_client,
                max_results=args.get("limit", 8),
            )
            tool_elapsed = round(time.perf_counter() - tool_start, 4)

            self.context["last_summary"] = result
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
