"""Unified browser session: get_page(session_id), start/stop_session, safe_page_snapshot.
All session and page operations run on a dedicated browser thread to avoid "cannot switch to a different thread" when tools are invoked from LangGraph worker threads."""
import sys
import asyncio
import json
import os
import queue
import threading
import time
from typing import Dict, Any, Callable, TypeVar

from playwright.sync_api import sync_playwright

BROWSER_SESSIONS: Dict[str, Dict[str, Any]] = {}

_T = TypeVar("_T")
_browser_task_queue: queue.Queue = queue.Queue()
_browser_thread: threading.Thread | None = None
_browser_thread_started = threading.Lock()

# #region agent log
def _log(hid: str, loc: str, msg: str, data: dict) -> None:
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lp = os.path.join(root, "debug-3c73a9.log")
        payload = {"sessionId": "3c73a9", "hypothesisId": hid, "location": loc, "message": msg, "data": {**data, "thread_id": threading.get_ident()}, "timestamp": int(time.time() * 1000)}
        with open(lp, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
# #endregion


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


def _browser_thread_loop() -> None:
    while True:
        item = _browser_task_queue.get()
        if item is None:
            break
        session_id, fn, result_queue = item
        try:
            if fn is None:
                stop_browser_session(session_id)
                result_queue.put(("ok", None))
            else:
                page = get_page(session_id)
                result = fn(page)
                result_queue.put(("ok", result))
        except Exception as e:
            result_queue.put(("err", e))


def _ensure_browser_thread() -> None:
    global _browser_thread
    with _browser_thread_started:
        if _browser_thread is not None and _browser_thread.is_alive():
            return
        _browser_thread = threading.Thread(target=_browser_thread_loop, daemon=True)
        _browser_thread.start()


def run_in_browser_thread(session_id: str, fn: Callable[..., _T] | None) -> _T:
    """Run fn(page) on the dedicated browser thread so Playwright is never used from another thread. If fn is None, stops the session."""
    _ensure_browser_thread()
    result_queue: queue.Queue = queue.Queue()
    _browser_task_queue.put((session_id, fn, result_queue))
    status, value = result_queue.get()
    if status == "err":
        raise value
    return value


def get_page(session_id: str):
    s = _get_session(session_id)
    had_page = s.get("page") is not None
    if s.get("page") is None:
        start_browser_session(session_id=session_id)
    page = s["page"]
    _log("H1", "core/browser:get_page:return", "get_page returning", {"had_existing_page": had_page})
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
