# demo-agent-ccc
Agent with browser use
[react_web_assistant_react_headed_v4.py](https://github.com/user-attachments/files/25529418/react_web_assistant_react_headed_v4.py)
"""
ReAct Agent + Headed Playwright Tool (Claude) — v3 (Windows fix for NotImplementedError)

Your traceback shows the real cause now:

  asyncio.base_events._make_subprocess_transport -> NotImplementedError

That happens when Playwright tries to launch its driver subprocess from a thread
running an event loop that DOES NOT support subprocesses on Windows
(e.g., SelectorEventLoop).

LangGraph’s ToolNode runs tools in a worker thread. On Windows/Python 3.12 that
thread may default to a loop policy that can’t spawn subprocesses -> boom.

Fixes in this version:
1) Force Windows Proactor event loop policy at import time.
2) In the tool, ensure the *current thread* has a Proactor-compatible loop set.
3) Keep your model fallback + JSON tool output.

Install / upgrade (recommended):
  pip install -U langgraph langchain langchain-core langchain-anthropic anthropic streamlit playwright
  playwright install

Run (Windows CMD):
  set ANTHROPIC_API_KEY=YOUR_KEY
  set CLAUDE_MODEL=claude-3-5-sonnet-20240620
  streamlit run react_chat_headed_app_claude_fallback_v3.py
"""

import os
import sys
import json
import asyncio
import traceback
from typing import Optional, Dict, Any, List

import streamlit as st

from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, ToolMessage

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

# -----------------------------
# Persistent headed browser sessions (multi-step workflows)
# -----------------------------
# NOTE: We keep browser/page objects in a module-level dict keyed by session_id.
# This works better than relying on Streamlit session_state inside worker threads.
BROWSER_SESSIONS: Dict[str, Dict[str, Any]] = {}

def _get_session(session_id: str) -> Dict[str, Any]:
    if not session_id:
        raise ValueError("session_id is required")
    if session_id not in BROWSER_SESSIONS:
        BROWSER_SESSIONS[session_id] = {"playwright": None, "browser": None, "page": None}
    return BROWSER_SESSIONS[session_id]

def start_browser_session(session_id: str, slow_mo_ms: int = 150) -> None:
    ensure_thread_event_loop()
    s = _get_session(session_id)
    if s["browser"] is not None and s["page"] is not None:
        return
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False, slow_mo=slow_mo_ms)
    page = browser.new_page()
    s["playwright"] = p
    s["browser"] = browser
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
    s["page"] = None

def get_page(session_id: str):
    s = _get_session(session_id)
    if s.get("page") is None:
        start_browser_session(session_id=session_id)
    return s["page"]

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



# -----------------------------
# Windows event loop policy fix
# -----------------------------
if sys.platform.startswith("win"):
    # Ensures new event loops (including in worker threads) are Proactor-based,
    # which supports subprocesses on Windows.
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
    except Exception:
        # If unavailable for any reason, we’ll handle per-thread in ensure_thread_event_loop().
        pass


def ensure_thread_event_loop() -> None:
    """
    LangGraph ToolNode runs tools in a worker thread.
    Playwright sync API internally uses asyncio + a driver subprocess.
    On Windows, worker threads can end up with an event loop that cannot spawn subprocesses.
    This function ensures a compatible loop exists for the current thread.
    """
    if not sys.platform.startswith("win"):
        return

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    # If no loop in this thread, create one that follows the current policy.
    if loop is None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return

    # Some loops on Windows may still be Selector-based. If so, replace it.
    # We detect by method presence (Proactor loops support subprocess transports).
    if "Proactor" not in loop.__class__.__name__:
        try:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
        except Exception:
            pass


# -----------------------------
# Playwright headed tool helpers
# -----------------------------
def looks_like_bot_challenge(title: Optional[str], body_text: Optional[str]) -> bool:
    hay = f"{title or ''} {body_text or ''}".lower()
    keywords = [
        "not a robot",
        "verify you are human",
        "verification",
        "captcha",
        "access denied",
        "unusual traffic",
        "just a moment",
        "checking your browser",
        "cloudflare",
        "enable cookies",
        "are you human",
        "blocked",
        "security check",
    ]
    return any(k in hay for k in keywords)


def highlight_locator(locator) -> None:
    """Visually highlight an element by styling the actual DOM node (works in iframes too)."""
    try:
        locator.evaluate(r"""
        (node) => {
          node.style.outline = '4px solid red';
          node.style.outlineOffset = '2px';
          node.style.backgroundColor = 'yellow';
          node.style.boxShadow = '0 0 0 6px rgba(255,0,0,0.35)';
          node.style.transition = 'all 150ms ease-in-out';
        }
        """)
    except Exception:
        pass


CONSENT_SELECTORS = [
    "button:has-text('Accept')",
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('Agree')",
    "button:has-text('I agree')",
    "button:has-text('OK')",
    "button:has-text('Okay')",
    "button:has-text('Got it')",
    "button:has-text('Continue')",
    "button:has-text('Reject')",
    "button:has-text('Reject all')",
    "button:has-text('Reject All')",
    "button:has-text('Decline')",
    "button:has-text('No thanks')",
    "button:has-text('Allow all')",
    "button:has-text('Allow All')",
    "button:has-text('Manage preferences')",
    "button:has-text('Manage Preferences')",
    "button:has-text('Confirm choices')",
    "button:has-text('Confirm Choices')",
    "[aria-label*='accept' i]",
    "[aria-label*='agree' i]",
    "[aria-label*='reject' i]",
    "[id*='accept' i]",
    "[id*='agree' i]",
    "[id*='reject' i]",
    "[class*='accept' i]",
    "[class*='agree' i]",
    "[class*='reject' i]",
    "[data-testid*='accept' i]",
    "[data-testid*='agree' i]",
    "[data-testid*='reject' i]",
]


def dismiss_cookie_consent(page) -> bool:
    """Try consent in main doc, then iframes. Returns True if clicked."""
    for sel in CONSENT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=350):
                highlight_locator(loc)
                page.wait_for_timeout(900)
                loc.click(timeout=2000)
                page.wait_for_timeout(350)
                return True
        except Exception:
            pass

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        for sel in CONSENT_SELECTORS:
            try:
                loc = frame.locator(sel).first
                if loc.is_visible(timeout=350):
                    highlight_locator(loc)
                    page.wait_for_timeout(900)
                    loc.click(timeout=2000)
                    page.wait_for_timeout(350)
                    return True
            except Exception:
                pass

    return False


def fetch_title_and_description_headed(
    url: str,
    timeout_ms: int = 25000,
    slow_mo_ms: int = 150,
    keep_open_ms: int = 1200,
    wait_until: str = "domcontentloaded",
) -> Dict[str, Any]:
    # Critical: ensure this thread can spawn subprocesses on Windows.
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
    """
    Open a visible browser, dismiss cookie consent if present,
    then return page title + brief description as JSON text.
    """
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
        # Try selector first
        clicked = False
        try:
            loc = page.locator(target).first
            if loc.is_visible(timeout=1200):
                highlight_locator(loc)
                page.wait_for_timeout(300)
                loc.click(timeout=5000)
                clicked = True
        except Exception:
            clicked = False

        # Fallback: click by text
        if not clicked:
            try:
                loc = page.get_by_text(target, exact=False).first
                if loc.is_visible(timeout=1200):
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

        # Safety: refuse obviously sensitive fields
        lowered = sel.lower()
        if any(k in lowered for k in ["password", "passcode", "otp", "mfa", "2fa"]):
            return json.dumps({"ok": False, "error": "Refusing to type into a likely sensitive field (password/OTP/MFA). Please type it yourself.", "selector": sel}, indent=2)

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


# -----------------------------
# ReAct Agent (Claude) with model fallback
# -----------------------------
def is_model_not_found_error(e: Exception) -> bool:
    txt = str(e).lower()
    return ("not_found" in txt and "model" in txt) or ("not_found_error" in txt)


def build_agent(model_name: str, session_id: str):
    llm = ChatAnthropic(model=model_name, temperature=0.2)

    system_prompt = f"""You are a web navigation assistant that helps the user complete tasks across websites
(e.g., paying bills, setting up accounts, updating profiles). You MUST narrate your work.

You have a persistent headed browser session available via tools. The current session_id is: {session_id}

Output format for each response:
- Goal: one sentence
- Plan: 1–3 bullets (high-level)
- Live Log: short step-by-step updates in plain English (what you did + why)
- Checkpoint: clearly state what you need from the user next (confirm / provide info / take over)
- Result: what you found / current state

Critical rules:
1) Never ask for or store passwords, MFA codes, or full sensitive credentials.
2) Never submit payments, place orders, or finalize account changes without an explicit user confirmation.
3) If an action would submit, pay, delete, sign, or finalize: STOP and ask for confirmation.
4) Prefer pause points. After each major step, include a Checkpoint so the user can read and decide.
5) If a site shows a bot/verification/CAPTCHA wall, explain it and ask the user to complete it manually in the opened browser.

Tool use guidance:
- If the user provides a URL or asks you to check/navigate a site: use open_url_headed(session_id, url) first.
- Use read_page_headed and find_text_on_page to understand where you are.
- Use click_on_page for navigation clicks. Use type_text_on_page for non-sensitive inputs (never passwords/OTP).
- Use close_browser_headed when done.
"""

    tools = [
        open_url_headed,
        read_page_headed,
        find_text_on_page,
        click_on_page,
        type_text_on_page,
        close_browser_headed,
        scrape_webpage_headed,  # keep the simple one-shot scraper too
    ]
    return create_react_agent(model=llm, tools=tools, prompt=system_prompt)


def get_model_candidates() -> List[str]:
    env_model = os.getenv("CLAUDE_MODEL", "").strip()
    candidates: List[str] = []
    if env_model:
        candidates.append(env_model)

    candidates += [
        # Strong default for tool calling:
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
    out: List[str] = []
    for c in candidates:
        if c and c not in seen:
            out.append(c)
            seen.add(c)
    return out


def to_lc_messages(history: List[dict]) -> List[BaseMessage]:
    out: List[BaseMessage] = []
    for m in history:
        role = m.get("role")
        content = m.get("content", "")
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        else:
            out.append(AIMessage(content=str(content)))
    return out

def render_trace(messages: List[BaseMessage]) -> None:
    """Render the full agent trace, including tool outputs."""
    for m in messages:
        if isinstance(m, ToolMessage):
            with st.expander(f"🔧 Tool result: {m.name}", expanded=False):
                st.code(m.content)
        else:
            role = "assistant"
            if getattr(m, "type", None) == "human":
                role = "user"
            with st.chat_message(role):
                st.markdown(getattr(m, "content", str(m)))



# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Chatbox Scraper (ReAct + Claude)", page_icon="🧠", layout="wide")
st.title("🧭 Web Assistant (ReAct + Claude + Headed Browser)")
st.caption("Ask it to navigate websites and narrate actions. It can open a persistent headed browser session, read pages, find text, click, and type into non-sensitive fields.")

if "session_id" not in st.session_state:
    # Stable per-browser-tab identifier used to keep a persistent Playwright session across tool calls
    import uuid
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "model_in_use" not in st.session_state:
    st.session_state.model_in_use = None

if "model_candidates" not in st.session_state:
    st.session_state.model_candidates = get_model_candidates()

if "model_index" not in st.session_state:
    st.session_state.model_index = 0

# Avoid stale compiled graph after edits:
st.session_state.agent = None

if "last_traceback" not in st.session_state:
    st.session_state.last_traceback = ""


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_text = st.chat_input("Try: 'Scrape https:// website' or ask a question…")


def invoke_with_fallback(lc_messages: List[BaseMessage]):
    candidates = st.session_state.model_candidates
    idx = st.session_state.model_index

    for _ in range(len(candidates)):
        model = candidates[idx]
        try:
            st.session_state.model_in_use = model
            st.session_state.agent = build_agent(model, session_id=st.session_state.session_id)
            return st.session_state.agent.invoke({"messages": lc_messages})
        except Exception as e:
            if is_model_not_found_error(e) and (idx + 1) < len(candidates):
                idx += 1
                st.session_state.model_index = idx
                continue
            raise


if user_text:
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    lc_messages = to_lc_messages(st.session_state.messages)

    with st.chat_message("assistant"):
        with st.spinner("Thinking (and maybe opening the browser)…"):
            try:
                result = invoke_with_fallback(lc_messages)
                trace = result.get("messages", []) if isinstance(result, dict) else []
                if trace:
                    render_trace(trace)
                    final_text = getattr(trace[-1], "content", str(trace[-1]))
                else:
                    final_text = str(result)
                    st.markdown(final_text)

            except Exception as e:
                st.session_state.last_traceback = traceback.format_exc()
                final_text = f"Error: {type(e).__name__}: {e}"
                st.markdown(final_text)

        st.session_state.messages.append({"role": "assistant", "content": final_text})

with st.sidebar:
    st.subheader("Claude Model")
    st.write("Using:", st.session_state.get("model_in_use", "(not set yet)"))
    st.caption("If a model returns NotFound, the app automatically tries the next model ID.")
    st.write("Candidates (in order):")
    st.code("\n".join(st.session_state.model_candidates))

    st.subheader("Debug")
    st.caption("This shows where any exception is coming from.")
    with st.expander("Show last traceback"):
        st.code(st.session_state.get("last_traceback", "") or "(no traceback captured yet)")

    if sys.platform.startswith("win"):
        st.subheader("Windows note")
        st.write("This build forces a Proactor event loop policy so Playwright can spawn subprocesses inside tool threads.")


    st.subheader("Session")
    st.caption("This session_id keeps the headed browser persistent across tool calls.")
    st.code(st.session_state.get("session_id", ""))
    if st.button("Close browser session"):
        try:
            stop_browser_session(st.session_state.session_id)
            st.success("Closed browser session.")
        except Exception as e:
            st.error(f"Failed to close session: {e}")

    st.subheader("Tip")
    st.write("If the headed browser opens & closes too fast, increase keep_open_ms in fetch_title_and_description_headed().")
