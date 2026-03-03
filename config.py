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


def get_industrial_model() -> str:
    """Model for industrial/ReAct agent (defaults to planner model)."""
    return os.getenv("INDUSTRIAL_MODEL") or get_planner_model()

def get_max_steps() -> int:
    """Max steps for industrial/ReAct agent loop (from env or default)."""
    try:
        return int(os.getenv("MAX_STEPS", "20"))
    except ValueError:
        return 20


def get_max_retries() -> int:
    """Max retries per step on failure (from env or default)."""
    try:
        return int(os.getenv("MAX_RETRIES", "3"))
    except ValueError:
        return 3


def get_default_headless() -> bool:
    """Default headless mode for browser (from env or default)."""
    v = os.getenv("DEFAULT_HEADLESS", "false").strip().lower()
    return v in ("1", "true", "yes")


def get_viz_mode() -> str:
    """Visualization mode: 'dot_hilite' (default), 'bounding_box', or 'both'."""
    v = (os.getenv("VIZ_MODE") or "dot_hilite").strip().lower()
    if v in ("dot_hilite", "bounding_box", "both"):
        return v
    return "dot_hilite"


def get_model_candidates() -> list:
    """Single default model (for compatibility where a list is expected)."""
    return [get_planner_model()]
