from core.browser import (
    get_page,
    start_browser_session,
    stop_browser_session,
    safe_page_snapshot,
)
from core.consent import dismiss_cookie_consent, looks_like_bot_challenge
from core.visualization import (
    install_dot,
    install_highlighter,
    ensure_overlays_installed,
    highlight_element_for_agent,
    highlight_locator,
)

__all__ = [
    "get_page",
    "start_browser_session",
    "stop_browser_session",
    "safe_page_snapshot",
    "dismiss_cookie_consent",
    "looks_like_bot_challenge",
    "install_dot",
    "install_highlighter",
    "ensure_overlays_installed",
    "highlight_element_for_agent",
    "highlight_locator",
]
