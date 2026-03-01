"""Central config: env vars and model names for planner and chat agent."""
import os

# Optional: load .env from project root (system env vars still take precedence)
try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_root, ".env"), override=False)
except ImportError:
    pass

def get_api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("API-KEY") or ""
    # When key is empty, try loading .env again (e.g. process didn't inherit system env)
    if not key:
        try:
            from dotenv import load_dotenv
            _root = os.path.dirname(os.path.abspath(__file__))
            load_dotenv(os.path.join(_root, ".env"), override=False)
            key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("API-KEY") or ""
        except ImportError:
            pass
    return key

def get_planner_model() -> str:
    return os.getenv("PLANNER_MODEL", "claude-haiku-4-5-20251001")

def get_model_candidates() -> list:
    env_model = (os.getenv("CLAUDE_MODEL") or "").strip()
    candidates = []
    if env_model:
        candidates.append(env_model)
    candidates += [
        "claude-3-5-sonnet-20240620",
        "claude-3-7-sonnet-20250219",
        "claude-3-7-sonnet-latest",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-20241022",
        "claude-3-haiku-20240307",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
    ]
    seen = set()
    out = []
    for c in candidates:
        if c and c not in seen:
            out.append(c)
            seen.add(c)
    return out
