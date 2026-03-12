"""Tavily evaluation script with four metrics output."""
import csv
import json
import os
import time
from typing import Any, Dict, Iterable, List

from anthropic import Anthropic

import config
from core.json_parser import extract_json_from_markdown
from tools.tavily_tools import tavily_search_raw


def _load_queries(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _anthropic_client() -> Anthropic:
    return Anthropic(api_key=config.get_api_key())


def _judge_extraction_quality(client: Anthropic, query: str, extracted_text: str) -> Dict[str, Any]:
    truncated_text = extracted_text[:4000]
    system_prompt = """
You are evaluating web extraction quality.
Return JSON with:
- "quality": "Good" or "Bad"
- "score": 1 or 0
- "reason": short explanation
"""
    user_content = f"Query:\n{query}\n\nExtracted text:\n{truncated_text}"
    response = client.messages.create(
        model=config.get_planner_model(),
        max_tokens=256,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    text = response.content[0].text if response.content else ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        extracted_json = extract_json_from_markdown(text)
        if extracted_json:
            try:
                parsed = json.loads(extracted_json)
            except json.JSONDecodeError:
                parsed = {"quality": "Bad", "score": 0, "reason": f"Non-JSON judge output: {text[:200]}"}
        else:
            parsed = {"quality": "Bad", "score": 0, "reason": f"Non-JSON judge output: {text[:200]}"}

    usage = getattr(response, "usage", None) or {}
    input_tokens = getattr(usage, "input_tokens", None) or getattr(usage, "input", None) or 0
    output_tokens = getattr(usage, "output_tokens", None) or getattr(usage, "output", None) or 0
    parsed["_usage"] = {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(input_tokens) + int(output_tokens),
    }
    return parsed


def _extract_text_from_tavily_response(resp: Dict[str, Any]) -> str:
    results = resp.get("results") or []
    chunks: List[str] = []
    for r in results:
        content = (r.get("content") or "").strip()
        if content:
            chunks.append(content)
    return "\n\n".join(chunks)


def run_tavily_eval(
    queries_path: str = os.path.join("eval", "tavily_queries.jsonl"),
    output_path: str = os.path.join("eval", "tavily_results.csv"),
) -> None:
    client = _anthropic_client()
    rows: List[Dict[str, Any]] = []

    for q in _load_queries(queries_path):
        query = q["query"]
        qid = q["id"]
        qtype = q["query_type"]

        start = time.perf_counter()
        resp = tavily_search_raw(query)
        latency_ms = (time.perf_counter() - start) * 1000.0

        extracted = _extract_text_from_tavily_response(resp)
        judge = _judge_extraction_quality(client, query=query, extracted_text=extracted)
        usage = judge.get("_usage", {})

        rows.append(
            {
                "Tools": "Tavily",
                "Query ID": qid,
                "Query": query,
                "Query Type": qtype,
                "Latency (ms)": f"{latency_ms:.2f}",
                "Extraction Quality": judge.get("quality", "Bad"),
                "Tokens consumed (LLM total)": usage.get("total_tokens", 0),
                "LLM input tokens": usage.get("input_tokens", 0),
                "LLM output tokens": usage.get("output_tokens", 0),
                "judge_reason": judge.get("reason", ""),
            }
        )

    fieldnames = [
        "Tools",
        "Query ID",
        "Query",
        "Query Type",
        "Latency (ms)",
        "Extraction Quality",
        "Tokens consumed (LLM total)",
        "LLM input tokens",
        "LLM output tokens",
        "judge_reason",
    ]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    run_tavily_eval()
