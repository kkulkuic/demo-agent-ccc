import json
import re
from typing import Any


def extract_json_object(text: str) -> str:
    """
    Try to pull a JSON object out of raw model text, even if the model wraps it
    in markdown fences or extra explanation.
    """
    if not text:
        return ""

    text = text.strip()

    # Remove ```json ... ``` fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    # Fallback: grab first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1].strip()

    return text


def safe_json_loads(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        extracted = extract_json_object(text)
        try:
            return json.loads(extracted)
        except Exception:
            return {}


def get_response_text(response) -> str:
    parts = []

    if hasattr(response, "content") and response.content:
        for block in response.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)

    return "\n".join(parts).strip()


def optimize_query_with_llm(client, instruction: str) -> dict[str, Any]:
    prompt = f"""
You are a search query optimizer for a web research agent.

Your job:
- Convert the user's instruction into the best short Google search query.
- Remove command words like "scrape", "search", "find", "look up".
- Keep the core topic, year, location, and target concept.
- Prefer wording that would retrieve relevant, authoritative sources.
- Return ONLY valid JSON.

User instruction:
{instruction}

Return JSON in this format:
{{
  "optimized_query": "...",
  "reasoning": "..."
}}
"""

    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=300,
        temperature=0,
        messages=[
            {"role": "user", "content": prompt}
        ],
    )

    text = get_response_text(response)
    parsed = safe_json_loads(text)

    if not parsed.get("optimized_query"):
        return {
            "optimized_query": instruction,
            "reasoning": "LLM query optimization failed, using original instruction.",
            "raw_response": text,
        }

    parsed["raw_response"] = text
    return parsed


def rank_search_results_with_llm(client, instruction: str, results: list[dict], max_select: int = 3) -> dict[str, Any]:
    numbered_results = []
    for i, item in enumerate(results, start=1):
        numbered_results.append(
            {
                "index": i,
                "title": item.get("title", ""),
                "url": item.get("url", ""),
            }
        )

    prompt = f"""
You are ranking search results for a web research agent.

User instruction:
{instruction}

Choose the most relevant results to scrape.
Prefer:
- official sources
- government or authoritative reports
- pages directly about the requested topic
Avoid:
- spammy SEO pages
- weakly related pages
- redundant duplicates

Return ONLY valid JSON.

Search results:
{json.dumps(numbered_results, indent=2)}

Return JSON in this format:
{{
  "selected_indices": [1, 2, 3],
  "reasoning": "..."
}}

Rules:
- Select at most {max_select} results
- Use only indices from the provided list
- Prefer .gov, official reports, and directly relevant sources when possible
"""

    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=400,
        temperature=0,
        messages=[
            {"role": "user", "content": prompt}
        ],
    )

    text = get_response_text(response)
    parsed = safe_json_loads(text)

    selected = parsed.get("selected_indices", [])
    if not isinstance(selected, list):
        selected = []

    selected = [i for i in selected if isinstance(i, int) and 1 <= i <= len(results)]
    selected = selected[:max_select]

    if not selected:
        selected = list(range(1, min(max_select, len(results)) + 1))
        parsed["reasoning"] = "LLM ranking failed, defaulted to top results."
        parsed["raw_response"] = text

    parsed["selected_indices"] = selected
    return parsed