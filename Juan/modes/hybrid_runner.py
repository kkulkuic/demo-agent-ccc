import os
import re
import time
import asyncio
import traceback
from typing import Any

from dotenv import load_dotenv
from firecrawl import FirecrawlApp

from core.browser_session import BrowserSession
from telemetry import TraceLogger
from tools.headed_tools import (
    open_url_headed,
    read_page_headed,
    close_browser_headed,
    looks_like_bot_challenge,
    capture_screenshot,
)

load_dotenv()


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
    else:
        patterns = [
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

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;?!")
    return cleaned or query.strip()


def extract_domain(url: str) -> str:
    match = re.search(r"https?://([^/]+)", (url or "").lower())
    return match.group(1) if match else (url or "").lower()


def is_pdf_url(url: str) -> bool:
    lower = (url or "").lower()
    return lower.endswith(".pdf") or ".pdf?" in lower


def extract_search_items(search_result) -> list[dict]:
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
        )

    items = []
    for item in raw_items:
        if isinstance(item, dict):
            url = (item.get("url") or item.get("link") or item.get("source_url") or "").strip()
            title = (item.get("title") or "").strip()
            description = (item.get("description") or item.get("snippet") or "").strip()
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


def score_search_item(item: dict, query: str) -> int:
    score = 0
    q_words = set(re.findall(r"\w+", (query or "").lower()))

    title = (item.get("title") or "").lower()
    description = (item.get("description") or "").lower()
    url = (item.get("url") or "").lower()

    official_bonus_domains = [
        ".gov",
        ".edu",
        "docs.",
        "developer.",
        "developers.",
        "playwright.dev",
        "python.org",
        "wikipedia.org",
        "github.com",
    ]

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

    if any(d in url for d in official_bonus_domains):
        score += 3

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

        if domain_counts[domain] >= 2:
            continue

        final_items.append(item)
        domain_counts[domain] += 1

        if len(final_items) >= max_results:
            break

    return final_items


class HybridRunner:
    """
    Firecrawl-first hybrid runner.

    Flow:
    1. Firecrawl search
    2. Rank/filter results
    3. Open best URL in headed browser
    4. Read page visibly
    5. Summarize from result metadata + opened page content
    """

    def __init__(self, instruction: str, slow_mo: int = 150, llm_client=None):
        self.instruction = instruction
        self.trace_logger = TraceLogger(instruction=instruction, mode="hybrid")
        self.context = {}
        self.llm_client = llm_client

        firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        if not firecrawl_key:
            raise RuntimeError("FIRECRAWL_API_KEY not found in environment.")

        self.firecrawl = FirecrawlApp(api_key=firecrawl_key)

        try:
            self.session = BrowserSession(headless=False, slow_mo=slow_mo)
            self.context["session_initialized"] = True
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize BrowserSession: {type(e).__name__}: {repr(e)}"
            ) from e

    def _run_step(self, step_number, tool_name, args, func, *func_args, **func_kwargs):
        start_perf = time.perf_counter()
        start_time_iso = self.trace_logger.now_iso()

        try:
            result = func(*func_args, **func_kwargs)

            self.trace_logger.log_step(
                step_number=step_number,
                tool=tool_name,
                args=args,
                start_perf=start_perf,
                start_time_iso=start_time_iso,
                status="success",
                result=result,
            )

            return {
                "step": step_number,
                "tool": tool_name,
                "args": args,
                "result": result,
            }

        except Exception as e:
            error_text = f"{type(e).__name__}: {repr(e)}"
            tb = traceback.format_exc()

            self.trace_logger.log_step(
                step_number=step_number,
                tool=tool_name,
                args=args,
                start_perf=start_perf,
                start_time_iso=start_time_iso,
                status="error",
                error=f"{error_text}\n{tb}",
            )

            return {
                "step": step_number,
                "tool": tool_name,
                "args": args,
                "error": f"{error_text}\n{tb}",
            }

    def _hitl_pause_for_bot_verification(self):
        self.context["hitl_triggered"] = True
        self.context["hitl_reason"] = "bot_verification"

        print("\n" + "=" * 80)
        print("HITL REQUIRED")
        print("Bot verification detected in the browser.")
        print("Please solve it manually in the opened browser window.")
        print("After you finish, come back here and press Enter to continue.")
        print("=" * 80 + "\n")

        hitl_start = time.perf_counter()
        input("Press Enter after completing the verification... ")
        hitl_end = time.perf_counter()

        self.context["hitl_resume_time_seconds"] = round(hitl_end - hitl_start, 4)

    def _page(self):
        return self.session.get_page()

    async def _search_firecrawl_async(self, query: str, limit: int = 10):
        return await asyncio.to_thread(
            self.firecrawl.search,
            query=query,
            limit=limit,
        )

    def _search_web_firecrawl(self, query: str, limit: int = 10) -> dict:
        normalized_query = normalize_search_query(query)

        if self.llm_client:
            try:
                from reasoning_layer import optimize_query_with_llm

                llm_query = optimize_query_with_llm(self.llm_client, query)
                if llm_query.get("optimized_query"):
                    normalized_query = llm_query["optimized_query"]
                    self.context["query_optimizer_reasoning"] = llm_query.get(
                        "reasoning", ""
                    )
            except Exception as e:
                self.context["query_optimizer_error"] = (
                    f"{type(e).__name__}: {repr(e)}"
                )

        search_result = asyncio.run(
            self._search_firecrawl_async(normalized_query, limit=limit)
        )

        ranked_items = rank_and_filter_search_results(
            search_result=search_result,
            original_query=normalized_query,
            max_results=min(limit, 8),
        )

        if self.llm_client and ranked_items:
            try:
                from reasoning_layer import rank_search_results_with_llm

                ranking = rank_search_results_with_llm(
                    self.llm_client,
                    instruction=query,
                    results=ranked_items,
                    max_select=min(5, len(ranked_items)),
                )

                self.context["result_ranking_reasoning"] = ranking.get("reasoning", "")
                self.context["selected_result_indices"] = ranking.get(
                    "selected_indices", []
                )

                selected_items = []
                for idx in ranking.get("selected_indices", []):
                    if 1 <= idx <= len(ranked_items):
                        selected_items.append(ranked_items[idx - 1])

                if selected_items:
                    ranked_items = selected_items

            except Exception as e:
                self.context["result_ranking_error"] = (
                    f"{type(e).__name__}: {repr(e)}"
                )

        results = {"web": ranked_items}

        self.context["last_search_result"] = results
        self.context["last_search_query"] = normalized_query
        self.context["original_instruction"] = query
        self.context["results_preview"] = ranked_items[:5]
        self.context["raw_result_count"] = len(extract_search_items(search_result))
        self.context["filtered_result_count"] = len(ranked_items)

        return results

    def _open_best_search_result(self) -> dict:
        search_result = self.context.get("last_search_result") or {}
        items = extract_search_items(search_result)

        if not items:
            raise RuntimeError("No search results available to open.")

        best = items[0]
        url = best["url"]

        step_output = self._run_step(
            0,
            "open_url_headed",
            {"url": url},
            open_url_headed,
            self.session,
            url,
        )
        if "error" in step_output:
            raise RuntimeError(step_output["error"])

        self._page().wait_for_timeout(2000)

        bot_check = self._run_step(
            0,
            "looks_like_bot_challenge",
            {},
            looks_like_bot_challenge,
            self.session,
        )
        if "error" in bot_check:
            raise RuntimeError(bot_check["error"])

        bot_result = bot_check.get("result") or {}
        if bot_result.get("is_bot_challenge"):
            shot = self._run_step(
                0,
                "capture_screenshot",
                {"path": "bot_challenge.png"},
                capture_screenshot,
                self.session,
                "bot_challenge.png",
            )
            if "error" not in shot:
                self.context["bot_challenge_screenshot"] = "bot_challenge.png"

            self._hitl_pause_for_bot_verification()
            self._page().wait_for_timeout(1500)

        try:
            page_title = self._page().title()
        except Exception:
            page_title = ""

        self.context["selected_url"] = url
        self.context["selected_result"] = best
        self.context["opened_in_browser"] = True
        self.context["page_title"] = page_title

        return {
            "opened_url": url,
            "page_title": page_title,
            "selected_result": best,
        }

    def _read_opened_page(self, max_chars: int = 5000) -> str:
        if not self.context.get("opened_in_browser"):
            raise RuntimeError("No page has been opened in the browser yet.")

        step_output = self._run_step(
            0,
            "read_page_headed",
            {"max_chars": max_chars},
            read_page_headed,
            self.session,
            max_chars,
        )
        if "error" in step_output:
            raise RuntimeError(step_output["error"])

        page_text = step_output.get("result") or ""
        self.context["opened_page_text"] = page_text[:max_chars]
        return self.context["opened_page_text"]

    def _summarize_opened_page(
        self,
        max_results: int = 8,
        max_page_chars: int = 3500,
    ) -> str:
        search_result = self.context.get("last_search_result") or {}
        ranked_items = rank_and_filter_search_results(
            search_result=search_result,
            original_query=self.context.get("last_search_query", self.instruction),
            max_results=max_results,
        )

        page_text = (self.context.get("opened_page_text") or "")[:max_page_chars]
        selected = self.context.get("selected_result") or {}
        selected_title = selected.get("title", "")
        selected_url = selected.get("url", "")

        if self.llm_client:
            try:
                results_text = "\n\n".join(
                    f"Title: {item['title']}\nDescription: {item['description']}\nURL: {item['url']}"
                    for item in ranked_items
                )

                response = self.llm_client.messages.create(
                    model="claude-3-5-sonnet-latest",
                    max_tokens=550,
                    temperature=0.2,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                "Answer the user's request using the Firecrawl search results and the text "
                                "read from the opened webpage. Be concise but informative. "
                                "Do not invent facts not present in the inputs. "
                                "If something is uncertain, say so clearly.\n\n"
                                f"User instruction: {self.instruction}\n\n"
                                f"Top search results:\n{results_text}\n\n"
                                f"Selected result title: {selected_title}\n"
                                f"Selected result URL: {selected_url}\n\n"
                                f"Opened page text:\n{page_text}"
                            ),
                        }
                    ],
                )

                if response.content and len(response.content) > 0:
                    summary = response.content[0].text.strip()
                    self.context["last_summary"] = summary
                    return summary
            except Exception as e:
                self.context["summary_error"] = f"{type(e).__name__}: {repr(e)}"

        lines = []

        if selected_title or selected_url:
            lines.append("Opened best Firecrawl result:")
            if selected_title:
                lines.append(f"Title: {selected_title}")
            if selected_url:
                lines.append(f"URL: {selected_url}")
            lines.append("")

        if page_text:
            lines.append("Visible page text preview:")
            lines.append(page_text[:1200])
        else:
            lines.append("The page opened, but no readable page text was captured.")

        summary = "\n".join(lines).strip()
        self.context["last_summary"] = summary
        return summary

    def _execute_tool(self, tool_name: str, args: dict) -> Any:
        if tool_name == "search_web":
            return self._search_web_firecrawl(
                query=args["query"],
                limit=args.get("limit", 10),
            )

        if tool_name == "open_best_search_result":
            return self._open_best_search_result()

        if tool_name == "read_opened_page":
            return self._read_opened_page(
                max_chars=args.get("max_chars", 5000),
            )

        if tool_name == "summarize_opened_page":
            return self._summarize_opened_page(
                max_results=args.get("max_results", 8),
                max_page_chars=args.get("max_page_chars", 3500),
            )

        raise ValueError(f"Unknown tool: {tool_name}")

    def run_plan(self, plan: list[dict]) -> dict[str, Any]:
        outputs = []

        try:
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

                    self.trace_logger.log_step(
                        step_number=i,
                        tool=tool_name,
                        args=args,
                        start_perf=start_perf,
                        start_time_iso=start_time_iso,
                        status="success",
                        result=result,
                    )

                except Exception as e:
                    error_text = f"{type(e).__name__}: {repr(e)}"
                    tb = traceback.format_exc()

                    self.trace_logger.log_step(
                        step_number=i,
                        tool=tool_name,
                        args=args,
                        start_perf=start_perf,
                        start_time_iso=start_time_iso,
                        status="error",
                        error=f"{error_text}\n{tb}",
                    )

                    outputs.append(
                        {
                            "step": i,
                            "tool": tool_name,
                            "args": args,
                            "error": f"{error_text}\n{tb}",
                        }
                    )
                    break

        finally:
            try:
                close_browser_headed(self.session)
            except Exception:
                pass

        return {
            "outputs": outputs,
            "trace": self.trace_logger.to_dict(),
            "context": self.context,
        }

    def run_firecrawl_open_flow(self):
        plan = [
            {
                "tool": "search_web",
                "args": {
                    "query": self.instruction,
                    "limit": 10,
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
                    "max_results": 8,
                    "max_page_chars": 3500,
                },
            },
        ]
        return self.run_plan(plan)