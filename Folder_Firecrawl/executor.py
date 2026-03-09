import re
import time
from typing import Any, Optional

from telemetry import TraceLogger
from tools.firecrawl_tools import (
    search_web,
    scrape_url,
    map_site,
    crawl_site,
    extract_structured,
)


def get_markdown_from_result(result) -> str:
    if hasattr(result, "markdown"):
        return result.markdown or ""
    if isinstance(result, dict):
        return result.get("markdown", "") or ""
    return ""


def extract_first_url_from_search_result(search_result) -> Optional[str]:
    if not search_result:
        return None

    if hasattr(search_result, "web") and getattr(search_result, "web", None):
        first_item = search_result.web[0]
        if isinstance(first_item, dict):
            return first_item.get("url")
        return getattr(first_item, "url", None)

    if isinstance(search_result, dict):
        web_results = search_result.get("web", [])
        if web_results:
            first_item = web_results[0]
            if isinstance(first_item, dict):
                return first_item.get("url")
            return getattr(first_item, "url", None)

    return None


def extract_urls_from_search_result(search_result, limit: int = 3) -> list[str]:
    urls = []

    if not search_result:
        return urls

    items = []
    if hasattr(search_result, "web") and getattr(search_result, "web", None):
        items = search_result.web
    elif isinstance(search_result, dict):
        items = search_result.get("web", [])

    for item in items:
        if isinstance(item, dict):
            url = item.get("url")
        else:
            url = getattr(item, "url", None)

        if url and url not in urls:
            urls.append(url)

        if len(urls) >= limit:
            break

    return urls


def is_supported_scrape_url(url: str) -> bool:
    if not url:
        return False

    blocked_domains = [
        "facebook.com",
        "m.facebook.com",
        "instagram.com",
        "tiktok.com",
        "x.com",
        "twitter.com",
        "linkedin.com",
        "pinterest.com",
    ]

    lower = url.lower()
    return not any(domain in lower for domain in blocked_domains)


def normalize_search_query(query: str) -> str:
    if not query:
        return query

    cleaned = query.strip()

    patterns = [
        r"^\s*scrape\s+top\s+result\s+of\s+",
        r"^\s*scrape\s+all\s+info\s+on\s+",
        r"^\s*scrape\s+all\s+information\s+on\s+",
        r"^\s*scrape\s+information\s+on\s+",
        r"^\s*scrape\s+info\s+on\s+",
        r"^\s*scrape\s+",
        r"^\s*search\s+all\s+results\s+of\s+",
        r"^\s*search\s+for\s+",
        r"^\s*search\s+",
        r"^\s*find\s+information\s+on\s+",
        r"^\s*find\s+info\s+on\s+",
        r"^\s*find\s+",
        r"^\s*look\s+up\s+",
        r"^\s*gather\s+information\s+on\s+",
        r"^\s*get\s+information\s+on\s+",
    ]

    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;")
    return cleaned or query.strip()


def strip_markdown_noise(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"#+", "", text)
    text = text.replace("\r", "")
    return text


def extract_main_content(text: str) -> str:
    if not text:
        return ""

    cleaned = strip_markdown_noise(text)

    generic_markers = [
        "Main content",
        "Overview",
        "Introduction",
        "Crash Facts",
        "Crash Data",
        "Safety",
        "Reports",
        "Statistics",
        "Travel",
        "Maps",
    ]

    for marker in generic_markers:
        idx = cleaned.find(marker)
        if idx != -1:
            return cleaned[idx:]

    return cleaned


def clean_summary_lines(lines: list[str]) -> list[str]:
    junk_prefixes = (
        "skip to main content",
        "search...",
        "ctrl k",
        "navigation",
        "get started",
        "playground",
        "blog",
        "community",
        "changelog",
        "on this page",
        "ready to build?",
        "start for free",
        "see our plans",
    )

    junk_phrases = (
        "what can",
        "why ",
        "use firecrawl with",
        "scrape your first",
        "quickstart",
        "documentation",
        "sdk",
        "integrations",
        "api reference",
        "toggle search",
        "agency header search",
    )

    junk_exact = {
        "v2",
        "english",
        "new features",
        "standard features",
        "developer guides",
        "webhooks",
        "use cases",
        "contributing",
        "resources",
        "search",
        "menu",
        "navigation",
        "home",
    }

    cleaned = []
    seen = set()

    for line in lines:
        line = re.sub(r"^[-•\s]+", "", line.strip()).strip()

        if not line or len(line) < 3:
            continue

        lower = line.lower()

        if lower in junk_exact:
            continue

        if any(lower.startswith(prefix) for prefix in junk_prefixes):
            continue

        if any(phrase in lower for phrase in junk_phrases):
            continue

        if lower in seen:
            continue

        seen.add(lower)
        cleaned.append(line)

    return cleaned


def summarize_single_page(text: str, max_chars: int = 4000) -> str:
    if not text:
        return "No meaningful content found."

    main_content = extract_main_content(text)[:max_chars]
    raw_lines = [line.strip() for line in main_content.splitlines() if line.strip()]
    filtered_lines = clean_summary_lines(raw_lines)

    if not filtered_lines:
        return "No meaningful content found."

    title_line = filtered_lines[0]
    useful_lines = []

    for line in filtered_lines[1:]:
        lower = line.lower()

        if len(line) < 20:
            continue
        if line.endswith(":") and len(line) < 40:
            continue
        if lower in {"search", "menu", "navigation", "home", "english"}:
            continue

        useful_lines.append(line)

    bullets = []
    seen = set()

    for line in useful_lines:
        norm = line.lower().strip()
        if norm in seen:
            continue
        seen.add(norm)

        if 30 <= len(line) <= 220:
            bullets.append(line)

        if len(bullets) == 3:
            break

    summary = f"Topic: {title_line}\n"
    if bullets:
        summary += "Highlights:\n"
        for bullet in bullets:
            summary += f"- {bullet}\n"

    return summary.strip()


def summarize_multi_page_results(scraped_pages: list[dict]) -> str:
    if not scraped_pages:
        return "No scraped pages available to summarize."

    source_summaries = []

    for idx, page in enumerate(scraped_pages, start=1):
        url = page.get("url", "Unknown URL")

        if page.get("error"):
            source_summaries.append(
                {
                    "source_number": idx,
                    "url": url,
                    "summary": f"Source {idx} could not be summarized because scraping failed: {page['error']}",
                }
            )
            continue

        markdown = page.get("markdown", "")
        mini_summary = summarize_single_page(markdown)

        source_summaries.append(
            {
                "source_number": idx,
                "url": url,
                "summary": mini_summary,
            }
        )

    lines = []
    lines.append("Multi-source summary:\n")

    for item in source_summaries:
        lines.append(f"Source {item['source_number']}: {item['url']}")
        lines.append(item["summary"])
        lines.append("")

    return "\n".join(lines).strip()


def summarize_text(text: str, max_chars: int = 6000) -> str:
    if not text:
        return "No content available to summarize."

    return summarize_single_page(text, max_chars=max_chars)


class AgentExecutor:
    def __init__(self, instruction: str, mode: str = "firecrawl_headless"):
        self.trace_logger = TraceLogger(instruction=instruction, mode=mode)
        self.context = {}

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
            cleaned_args["query"] = normalize_search_query(args.get("query", ""))
            result = search_web(**cleaned_args)
            self.context["last_search_result"] = result
            self.context["last_search_query"] = cleaned_args["query"]
            return result

        if tool_name == "scrape_url":
            result = scrape_url(**args)
            markdown_text = get_markdown_from_result(result)
            self.context["last_scrape_markdown"] = markdown_text
            self.context["last_scraped_url"] = args.get("url")
            return result

        if tool_name == "map_site":
            return map_site(**args)

        if tool_name == "crawl_site":
            return crawl_site(**args)

        if tool_name == "extract_structured":
            return extract_structured(**args)

        if tool_name == "scrape_first_search_result":
            search_result = self.context.get("last_search_result")
            if not search_result:
                raise ValueError("No previous search result found in context.")

            urls = extract_urls_from_search_result(search_result, limit=10)
            if not urls:
                raise ValueError("Could not find usable URLs from search results.")

            chosen_url = None
            for url in urls:
                if is_supported_scrape_url(url):
                    chosen_url = url
                    break

            if not chosen_url:
                raise ValueError("No supported URLs found in search results.")

            result = scrape_url(url=chosen_url)
            markdown_text = get_markdown_from_result(result)

            self.context["last_scraped_url"] = chosen_url
            self.context["last_scrape_markdown"] = markdown_text
            return result

        if tool_name == "scrape_top_search_results":
            search_result = self.context.get("last_search_result")
            if not search_result:
                raise ValueError("No previous search result found in context.")

            urls = extract_urls_from_search_result(
                search_result,
                limit=args.get("limit", 3),
            )
            if not urls:
                raise ValueError("Could not find usable URLs from search results.")

            scraped_pages = []
            combined_markdown_parts = []

            for url in urls:
                if not is_supported_scrape_url(url):
                    scraped_pages.append(
                        {
                            "url": url,
                            "error": "Unsupported or blocked domain for scraping.",
                        }
                    )
                    continue

                try:
                    result = scrape_url(url=url)
                    markdown_text = get_markdown_from_result(result)

                    scraped_pages.append(
                        {
                            "url": url,
                            "markdown": markdown_text[:4000],
                        }
                    )

                    if markdown_text:
                        combined_markdown_parts.append(f"URL: {url}\n{markdown_text}")

                except Exception as e:
                    scraped_pages.append(
                        {
                            "url": url,
                            "error": str(e),
                        }
                    )

            combined_markdown = "\n\n---\n\n".join(combined_markdown_parts)

            self.context["scraped_pages"] = scraped_pages
            self.context["last_scraped_urls"] = [
                p.get("url") for p in scraped_pages if p.get("markdown")
            ]
            self.context["last_scraped_url"] = (
                self.context["last_scraped_urls"][0]
                if self.context["last_scraped_urls"]
                else None
            )
            self.context["last_scrape_markdown"] = combined_markdown

            return {
                "scraped_count": len([p for p in scraped_pages if "markdown" in p]),
                "pages": scraped_pages,
            }

        if tool_name == "summarize_last_scrape":
            scraped_pages = self.context.get("scraped_pages")

            if scraped_pages:
                result = summarize_multi_page_results(scraped_pages)
                self.context["page_summaries"] = [
                    {
                        "url": page.get("url"),
                        "mini_summary": summarize_single_page(page.get("markdown", ""))
                        if page.get("markdown")
                        else page.get("error", "No content available."),
                    }
                    for page in scraped_pages
                ]
            else:
                scraped_text = self.context.get("last_scrape_markdown", "")
                result = summarize_text(scraped_text)

            self.context["last_summary"] = result
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