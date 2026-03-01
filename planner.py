import json
import os
import re
import time
from anthropic import Anthropic

import config

# #region agent log
def _log(hid, loc, msg, data):
    try:
        lp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug-3bc52e.log")
        with open(lp, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId": "3bc52e", "hypothesisId": hid, "location": loc, "message": msg, "data": data, "timestamp": int(time.time() * 1000)}, ensure_ascii=False) + "\n")
    except Exception:
        pass
# #endregion


def _extract_json_from_markdown(text):
    """Extract first JSON object from markdown (e.g. ```json ... ```). Returns stripped text or None."""
    if not text or not text.strip():
        return None
    text = text.strip()
    # Match ```json ... ``` or ``` ... ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Fallback: find first { ... } block
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


_client = None

def _get_client():
    global _client
    if _client is None:
        _client = Anthropic(api_key=config.get_api_key())
    return _client

SYSTEM_PROMPT = """
You are a browser automation planner.
Return ONLY valid JSON.
Format:
{
  "actions": [
    {"action": "click", "target": "..."},
    {"action": "type", "target": "...", "text": "..."},
    {"action": "navigate", "target": "..."}
  ]
}

"""

def plan_actions(user_instruction, page_context=""):
    # #region agent log
    _log("H4", "planner.py:plan_actions:entry", "plan_actions called", {"instruction_len": len(user_instruction or ""), "context_len": len(page_context or "")})
    # #endregion
    client = _get_client()
    response = client.messages.create(
        model=config.get_planner_model(),
        max_tokens=800,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"""
Instruction:
{user_instruction}

Page context:
{page_context}
"""}
        ]
    )
    # #region agent log
    _log("H4", "planner.py:plan_actions:after_api", "response received", {"content_blocks": len(response.content) if response.content else 0})
    # #endregion
    content = response.content[0].text
    # #region agent log
    _log("H1", "planner.py:plan_actions:before_loads", "content before json.loads", {"content_len": len(content), "content_empty": not (content or "").strip(), "preview": (content or "")[:400]})
    # #endregion
    to_parse = _extract_json_from_markdown(content)
    if to_parse is None:
        to_parse = (content or "").strip()
    try:
        out = json.loads(to_parse)
        # #region agent log
        _log("H3", "planner.py:plan_actions:parse_ok", "json.loads success", {"extracted": to_parse != content.strip(), "actions_count": len(out.get("actions") or [])})
        # #endregion
        return out
    except json.JSONDecodeError as e:
        # #region agent log
        _log("H2", "planner.py:plan_actions:json_error", "JSONDecodeError", {"error": str(e), "content_len": len(content), "preview": (content or "")[:500]})
        # #endregion
        raise
