"""Shared JSON extraction from markdown/raw text for planner and industrial agent."""
import json
import re
from typing import Any, Optional


def extract_json_from_markdown(text: str) -> Optional[str]:
    """
    Extract first JSON object from markdown (e.g. ```json ... ```).
    Returns stripped text or None if no JSON block found.
    """
    if not text or not text.strip():
        return None
    text = text.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str) -> str:
    """Extract JSON substring from text (markdown code block or first {...} block). Returns raw text if none found."""
    extracted = extract_json_from_markdown(text)
    if extracted is not None:
        return extracted
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


def safe_json_parse(raw: str) -> Optional[Any]:
    """Parse JSON from raw string (after extraction). Returns None on failure."""
    cleaned = extract_json(raw)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None
