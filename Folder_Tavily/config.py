"""Local config for search tool benchmark."""
import os

try:
    from dotenv import load_dotenv

    _root = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_root, ".env"), override=False)
except ImportError:
    pass


def _load_env_if_needed() -> None:
    try:
        from dotenv import load_dotenv as _load

        _root = os.path.dirname(os.path.abspath(__file__))
        _load(os.path.join(_root, ".env"), override=False)
    except ImportError:
        pass


def get_api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("API-KEY") or ""
    if not key:
        _load_env_if_needed()
        key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("API-KEY") or ""
    return key


def get_tavily_api_key() -> str:
    key = os.getenv("TAVILY_API_KEY") or ""
    if not key:
        _load_env_if_needed()
        key = os.getenv("TAVILY_API_KEY") or ""
    return key


def get_planner_model() -> str:
    return os.getenv("PLANNER_MODEL", "claude-haiku-4-5-20251001")
