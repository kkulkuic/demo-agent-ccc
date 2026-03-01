"""Unified browser session: get_page(session_id), start/stop_session, safe_page_snapshot."""
import sys
import asyncio
from typing import Dict, Any

from playwright.sync_api import sync_playwright

BROWSER_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _get_session(session_id: str) -> Dict[str, Any]:
    if not session_id:
        raise ValueError("session_id is required")
    if session_id not in BROWSER_SESSIONS:
        BROWSER_SESSIONS[session_id] = {"playwright": None, "browser": None, "context": None, "page": None}
    return BROWSER_SESSIONS[session_id]


def ensure_thread_event_loop() -> None:
    """On Windows, ensure worker threads have a Proactor event loop for Playwright subprocesses."""
    if not sys.platform.startswith("win"):
        return
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return
    if "Proactor" not in loop.__class__.__name__:
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
        except Exception:
            pass


if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
    except Exception:
        pass


def start_browser_session(session_id: str, slow_mo_ms: int = 150) -> None:
    ensure_thread_event_loop()
    s = _get_session(session_id)
    if s["browser"] is not None and s["page"] is not None:
        return
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    s["playwright"] = p
    s["browser"] = browser
    s["context"] = context
    s["page"] = page


def stop_browser_session(session_id: str) -> None:
    s = _get_session(session_id)
    try:
        if s.get("browser"):
            s["browser"].close()
    except Exception:
        pass
    try:
        if s.get("playwright"):
            s["playwright"].stop()
    except Exception:
        pass
    s["playwright"] = None
    s["browser"] = None
    s["context"] = None
    s["page"] = None


def get_page(session_id: str):
    s = _get_session(session_id)
    if s.get("page") is None:
        start_browser_session(session_id=session_id)
    page = s["page"]
    try:
        page.bring_to_front()
    except Exception:
        pass
    return page


def safe_page_snapshot(page, max_chars: int = 6000) -> Dict[str, Any]:
    title = None
    url = None
    body = ""
    try:
        title = (page.title() or "").strip() or None
    except Exception:
        title = None
    try:
        url = page.url
    except Exception:
        url = None
    try:
        body = (page.inner_text("body") or "")[:max_chars]
    except Exception:
        body = ""
    return {"url": url, "title": title, "body_sample": body}
