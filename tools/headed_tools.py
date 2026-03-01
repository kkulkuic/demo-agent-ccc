"""Headed browser tools for ReAct agent; optional visualization via set_enable_viz."""
import json
from typing import Dict, Any

from langchain_core.tools import tool
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

from core.browser import (
    get_page,
    start_browser_session,
    stop_browser_session,
    safe_page_snapshot,
    ensure_thread_event_loop,
)
from core.consent import dismiss_cookie_consent, looks_like_bot_challenge
from core.visualization import (
    highlight_locator,
    ensure_overlays_installed,
    highlight_element_for_agent,
)

# Global flag for visualization in chat mode; set via set_enable_viz() from app.
_ENABLE_VIZ = False


def set_enable_viz(value: bool) -> None:
    global _ENABLE_VIZ
    _ENABLE_VIZ = value


def fetch_title_and_description_headed(
    url: str,
    timeout_ms: int = 25000,
    slow_mo_ms: int = 150,
    keep_open_ms: int = 1200,
    wait_until: str = "domcontentloaded",
) -> Dict[str, Any]:
    ensure_thread_event_loop()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
        page = browser.new_page()
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            page.wait_for_timeout(900)
            dismiss_cookie_consent(page)
            title = (page.title() or "").strip() or None
            body_sample = ""
            try:
                body_sample = (page.inner_text("body") or "")[:2000]
            except Exception:
                body_sample = ""
            if looks_like_bot_challenge(title, body_sample):
                if keep_open_ms and keep_open_ms > 0:
                    page.wait_for_timeout(keep_open_ms)
                return {"url": url, "title": None, "description": None, "error": "Bot/verification wall detected."}
            desc = None
            try:
                desc = page.eval_on_selector('meta[name="description"]', "el => el.getAttribute('content')")
            except Exception:
                desc = None
            if not desc:
                for sel in ('meta[property="og:description"]', 'meta[name="twitter:description"]'):
                    try:
                        desc = page.eval_on_selector(sel, "el => el.getAttribute('content')")
                    except Exception:
                        desc = None
                    if desc:
                        break
            if not desc:
                try:
                    desc = page.eval_on_selector("p", "el => el.textContent") or None
                except Exception:
                    desc = None
            if desc:
                desc = " ".join(desc.split())[:300]
            if keep_open_ms and keep_open_ms > 0:
                page.wait_for_timeout(keep_open_ms)
            return {"url": url, "title": title, "description": desc, "error": None}
        except PWTimeoutError:
            return {"url": url, "title": None, "description": None, "error": f"Timeout loading {url}"}
        except Exception as e:
            return {"url": url, "title": None, "description": None, "error": f"{type(e).__name__}: {e}"}
        finally:
            browser.close()


@tool
def scrape_webpage_headed(url: str) -> str:
    """Open a visible browser, dismiss cookie consent if present, then return page title + brief description as JSON text."""
    result = fetch_title_and_description_headed(url)
    return json.dumps(result, indent=2)


@tool
def open_url_headed(session_id: str, url: str) -> str:
    """Open a URL in a persistent headed browser session and try to dismiss cookie banners."""
    try:
        page = get_page(session_id)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(900)
        dismiss_cookie_consent(page)
        snap = safe_page_snapshot(page)
        if looks_like_bot_challenge(snap.get("title"), snap.get("body_sample")):
            return json.dumps({"ok": False, "error": "Bot/verification wall detected. Please complete it manually in the opened browser, then tell me when you're done.", **snap}, indent=2)
        return json.dumps({"ok": True, "note": "Page opened.", **snap}, indent=2)
    except PWTimeoutError:
        return json.dumps({"ok": False, "error": f"Timeout loading {url}"}, indent=2)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, indent=2)


@tool
def read_page_headed(session_id: str, max_chars: int = 6000) -> str:
    """Read the current page (title + visible body text sample) from the persistent headed session."""
    try:
        page = get_page(session_id)
        page.wait_for_timeout(300)
        snap = safe_page_snapshot(page, max_chars=max_chars)
        if looks_like_bot_challenge(snap.get("title"), snap.get("body_sample")):
            return json.dumps({"ok": False, "error": "Bot/verification wall detected. Please complete it manually in the opened browser, then tell me when you're done.", **snap}, indent=2)
        return json.dumps({"ok": True, **snap}, indent=2)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, indent=2)


@tool
def find_text_on_page(session_id: str, query: str) -> str:
    """Find occurrences of a text snippet on the current page. Returns counts + a few surrounding excerpts."""
    try:
        page = get_page(session_id)
        text = ""
        try:
            text = page.inner_text("body") or ""
        except Exception:
            text = ""
        low = text.lower()
        q = (query or "").lower().strip()
        if not q:
            return json.dumps({"ok": False, "error": "query is empty"}, indent=2)
        idxs = []
        start = 0
        while True:
            i = low.find(q, start)
            if i == -1:
                break
            idxs.append(i)
            start = i + len(q)
            if len(idxs) >= 25:
                break
        excerpts = []
        for i in idxs[:5]:
            a = max(0, i - 80)
            b = min(len(text), i + len(q) + 120)
            excerpts.append(text[a:b].replace("\n", " ").strip())
        return json.dumps({"ok": True, "query": query, "count": len(idxs), "excerpts": excerpts, "url": getattr(page, "url", None), "title": (page.title() or "").strip() or None}, indent=2)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, indent=2)


@tool
def click_on_page(session_id: str, selector_or_text: str) -> str:
    """Click an element by CSS selector or by visible text (best-effort). Use for non-destructive navigation."""
    try:
        page = get_page(session_id)
        target = selector_or_text.strip()
        clicked = False
        if _ENABLE_VIZ:
            ensure_overlays_installed(page, show_label=True)
        try:
            loc = page.locator(target).first
            if loc.is_visible(timeout=1200):
                if _ENABLE_VIZ:
                    highlight_element_for_agent(page, loc, target)
                else:
                    highlight_locator(loc)
                page.wait_for_timeout(300)
                loc.click(timeout=5000)
                clicked = True
        except Exception:
            clicked = False
        if not clicked:
            try:
                loc = page.get_by_text(target, exact=False).first
                if loc.is_visible(timeout=1200):
                    if _ENABLE_VIZ:
                        highlight_element_for_agent(page, loc, target)
                    else:
                        highlight_locator(loc)
                    page.wait_for_timeout(300)
                    loc.click(timeout=5000)
                    clicked = True
            except Exception:
                clicked = False
        page.wait_for_timeout(800)
        dismiss_cookie_consent(page)
        snap = safe_page_snapshot(page)
        if looks_like_bot_challenge(snap.get("title"), snap.get("body_sample")):
            return json.dumps({"ok": False, "error": "Bot/verification wall detected. Please complete it manually in the opened browser, then tell me when you're done.", "clicked": clicked, **snap}, indent=2)
        return json.dumps({"ok": clicked, "clicked": clicked, "note": "Clicked (best-effort).", **snap}, indent=2)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, indent=2)


@tool
def type_text_on_page(session_id: str, selector: str, text: str) -> str:
    """Type into an input by CSS selector. Never use this to enter passwords or MFA codes."""
    try:
        page = get_page(session_id)
        sel = selector.strip()
        loc = page.locator(sel).first
        if not loc.is_visible(timeout=2000):
            return json.dumps({"ok": False, "error": f"Input not visible for selector: {sel}"}, indent=2)
        lowered = sel.lower()
        if any(k in lowered for k in ["password", "passcode", "otp", "mfa", "2fa"]):
            return json.dumps({"ok": False, "error": "Refusing to type into a likely sensitive field (password/OTP/MFA). Please type it yourself.", "selector": sel}, indent=2)
        if _ENABLE_VIZ:
            ensure_overlays_installed(page, show_label=True)
            highlight_element_for_agent(page, loc, sel)
            page.wait_for_timeout(300)
        else:
            highlight_locator(loc)
            page.wait_for_timeout(300)
        loc.fill("")
        loc.type(text, delay=25)
        page.wait_for_timeout(500)
        snap = safe_page_snapshot(page)
        return json.dumps({"ok": True, "note": "Typed text.", "selector": sel, **snap}, indent=2)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, indent=2)


@tool
def close_browser_headed(session_id: str) -> str:
    """Close the persistent headed browser session."""
    try:
        stop_browser_session(session_id)
        return json.dumps({"ok": True, "note": "Browser session closed."}, indent=2)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, indent=2)
