"""Tavily search helpers for benchmark use."""
from typing import Any, Dict, Optional, Union

from langchain_core.tools import tool
from tavily import TavilyClient

import config


def _get_tavily_client() -> TavilyClient:
    api_key = config.get_tavily_api_key()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set.")
    return TavilyClient(api_key=api_key)


def tavily_search_raw(
    query: str,
    search_depth: str = "basic",
    topic: Optional[str] = None,
    max_results: int = 5,
    include_answer: Optional[Union[bool, str]] = None,
) -> Dict[str, Any]:
    client = _get_tavily_client()
    params: Dict[str, Any] = {
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
    }
    if topic:
        params["topic"] = topic
    if include_answer is not None:
        params["include_answer"] = include_answer
    return client.search(**params)  # type: ignore[arg-type]


@tool
def tavily_search(query: str) -> str:
    """Return concise Tavily result snippets for agent usage."""
    response = tavily_search_raw(query)
    results = response.get("results") or []
    lines = []
    for i, item in enumerate(results, start=1):
        title = item.get("title") or ""
        url = item.get("url") or ""
        content = (item.get("content") or "").strip()
        if len(content) > 300:
            content = content[:297] + "..."
        lines.append(f"{i}. {title}\nURL: {url}\nSnippet: {content}")
    return "\n\n".join(lines) if lines else "No results."
