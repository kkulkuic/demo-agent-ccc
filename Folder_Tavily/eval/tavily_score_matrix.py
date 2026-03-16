"""Tavily score-matrix evaluation: 10 prompts x include_answer x search_depth, with Anthropic goal_met judge.

Run from project root: python -m eval.tavily_score_matrix
Output: eval/tavily_score_matrix_results.csv
"""
import csv
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from anthropic import Anthropic

import config
from core.json_parser import extract_json_from_markdown
from tools.tavily_tools import tavily_search_raw


PROMPTS: List[Tuple[str, str]] = [
    ("prompt_1", "Find the top-rated shoe repair shops in Chicago with their phone numbers and opening hours."),
    ("prompt_2", "What are the 'People Also Ask' questions for 'reverse logistics startup ideas'?"),
    ("prompt_3", "List the top 5 organic search results for 'sustainable clothing brands' in the UK vs. the US."),
    ("prompt_4", "Find the current price and availability of the 'Sony WH-1000XM5' from the Google Shopping tab."),
    ("prompt_5", "Get the latest news snippets from Google News about 'retail returns crisis 2026'."),
    ("prompt_6", "Give me a detailed comparison of the top 3 reverse logistics software providers in 2026."),
    ("prompt_7", "What are the latest tax regulations for small e-commerce businesses in Illinois?"),
    ("prompt_8", "Explain the current state of the global supply chain for recycled textiles."),
    ("prompt_9", "Find the 5 most cited research papers on 'AI-driven route optimization' from the last 12 months."),
    ("prompt_10", "Summarize the key takeaways from the most recent National Retail Federation conference."),
]

INCLUDE_ANSWER_VALUES: List[Any] = [False, "advanced"]
SEARCH_DEPTH_VALUES: List[str] = ["advanced", "ultra-fast", "basic"]
MAX_RESULTS = 6
TOP_N = 4
SCORE_THRESHOLD = 0.8
CONTENT_SNIPPET_CHARS = 400


def _build_search_summary(results: List[Dict[str, Any]], answer: Optional[str] = None) -> str:
    lines: List[str] = []
    for i, r in enumerate(results[:TOP_N], start=1):
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        score = r.get("score")
        content = (r.get("content") or "").strip()
        if len(content) > CONTENT_SNIPPET_CHARS:
            content = content[:CONTENT_SNIPPET_CHARS] + "..."
        lines.append(f"[{i}] title: {title}\nurl: {url}\nscore: {score}\ncontent: {content}")
    summary = "\n\n".join(lines)
    if answer:
        summary += "\n\n--- Generated answer ---\n" + (answer[:2000] + "..." if len(answer) > 2000 else answer)
    return summary


def _run_judge(client: Anthropic, query: str, search_summary: str) -> Tuple[Any, Any, int, int]:
    system = """You evaluate whether a search outcome is good enough for the user's query.
Given the user's query and a summary of the search results (and optional generated answer), decide ONLY based on that information.

Set \"goal_met\" to true if AT LEAST ONE of the returned results (or the generated answer, if present) would allow a careful reader to correctly answer the query with reasonable effort, even if the overall set is imperfect or noisy.
Set \"goal_met\" to false only if NONE of the results (and no generated answer) provide enough information to answer the query in a useful way.

Return a JSON object with:
- \"goal_met\": true or false
- \"judge_reason\": a short justification (1-2 sentences)
Output only valid JSON, no markdown."""
    user = f"Query:\n{query}\n\nSearch outcome summary:\n{search_summary}"
    response = client.messages.create(
        model=config.get_planner_model(),
        max_tokens=256,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = response.content[0].text if response.content else ""
    usage = getattr(response, "usage", None) or {}
    in_tok = getattr(usage, "input_tokens", None) or getattr(usage, "input", None) or 0
    out_tok = getattr(usage, "output_tokens", None) or getattr(usage, "output", None) or 0
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        extracted = extract_json_from_markdown(text)
        if extracted:
            try:
                parsed = json.loads(extracted)
            except json.JSONDecodeError:
                parsed = {"goal_met": False, "judge_reason": f"Parse failed: {text[:150]}"}
        else:
            parsed = {"goal_met": False, "judge_reason": f"No JSON: {text[:150]}"}
    return parsed.get("goal_met"), parsed.get("judge_reason", ""), int(in_tok), int(out_tok)


def run() -> None:
    client = Anthropic(api_key=config.get_api_key())
    rows: List[Dict[str, Any]] = []
    out_path = os.path.join(os.path.dirname(__file__), "tavily_score_matrix_results.csv")

    for prompt_id, query in PROMPTS:
        for include_answer in INCLUDE_ANSWER_VALUES:
            for search_depth in SEARCH_DEPTH_VALUES:
                resp = tavily_search_raw(
                    query=query,
                    search_depth=search_depth,
                    max_results=MAX_RESULTS,
                    include_answer=include_answer,
                )
                response_time = resp.get("response_time")
                if response_time is None:
                    response_time = ""
                results = resp.get("results") or []
                answer = resp.get("answer") if include_answer else None

                scores = [float(r.get("score") or 0) for r in results]
                sorted_results = sorted(results, key=lambda r: float(r.get("score") or 0), reverse=True)
                top4 = sorted_results[:TOP_N]
                top4_scores = [float(r.get("score") or 0) for r in top4]
                avg_top4 = sum(top4_scores) / len(top4_scores) if top4_scores else 0.0
                count_above_08 = sum(1 for s in scores if s > SCORE_THRESHOLD)
                best_score = max(scores) if scores else 0.0

                search_summary = _build_search_summary(sorted_results, answer)
                goal_met, judge_reason, judge_in, judge_out = _run_judge(client, query, search_summary)

                rows.append({
                    "prompt_id": prompt_id,
                    "prompt": query,
                    "include_answer": str(include_answer).lower() if include_answer is False else include_answer,
                    "search_depth": search_depth,
                    "response_time": response_time,
                    "avg_top4_score": round(avg_top4, 4),
                    "num_results": len(results),
                    "count_score_above_08": count_above_08,
                    "best_score": round(best_score, 4),
                    "goal_met": str(goal_met).lower() if isinstance(goal_met, bool) else goal_met,
                    "judge_reason": (judge_reason or "")[:500],
                    "judge_input_tokens": judge_in,
                    "judge_output_tokens": judge_out,
                })

    fieldnames = [
        "prompt_id", "prompt", "include_answer", "search_depth", "response_time",
        "avg_top4_score", "num_results", "count_score_above_08", "best_score",
        "goal_met", "judge_reason", "judge_input_tokens", "judge_output_tokens",
    ]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    run()

