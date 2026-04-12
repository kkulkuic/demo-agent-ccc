"""
demo-test — Streamlit app wrapping research+navi.py
Inspired by StackAI enterprise SaaS aesthetic:
  - Clean white/light theme with blue accents
  - Left sidebar navigation
  - Agent cards layout
  - Professional typography & subtle shadows
  - Real-time step pipeline
  - Model: GLM-5V-Turbo (nav) + GLM-5.1 (research)
"""

from __future__ import annotations

import os, sys, json, uuid, logging, traceback, asyncio, threading

# ─────────────────────────────────────────────────────────────────────────────
# PATCHES — must come before any research+navi import
# ─────────────────────────────────────────────────────────────────────────────

# Patch 1: fake pkg_resources (removed from Python 3.14)
sys.path.insert(0, os.path.dirname(__file__))
import pkg_resources_compat as pkg_resources
sys.modules['pkg_resources'] = pkg_resources

# Patch 2: stealth_async — playwright_stealth already has stealth_async
# No additional patch needed, just ensure import works via pkg_resources_compat
import playwright_stealth
_orig_stealth_async = playwright_stealth.stealth_async

# NOTE: ChatAnthropic uses official Anthropic API directly (key is valid)
# No model patch needed — research+navi.py line 1232-1236 handles it
# Tavily version has built-in research step budget (20 hard limit) — no patch needed


# Import research+navi
import importlib.util
if "research_navi" not in sys.modules or not hasattr(sys.modules.get("research_navi"), "app"):
    _spec = importlib.util.spec_from_file_location(
        "research_navi",
        os.path.join(os.path.dirname(__file__), "research+navi.py"))
    rn = importlib.util.module_from_spec(_spec)
    sys.modules["research_navi"] = rn
    _spec.loader.exec_module(rn)
else:
    rn = sys.modules["research_navi"]

# Patch: Add step budget (20 steps) to research_agent_node + lower nav to 20
# Step budgets: Tavily version has built-in budgets
# - research: 20 hard limit, 15 soft warning, loop detection
# - nav: 50 steps
# No patch needed.


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
st.set_page_config(
    page_title="HybridAgent",
    page_icon="🔵",
    layout="wide",
    initial_sidebar_state="expanded",
)
from langgraph.types import Command

# ─────────────────────────────────────────────────────────────────────────────
# Theme: StackAI-inspired CSS (clean enterprise blue/white)
# ─────────────────────────────────────────────────────────────────────────────
BLUE      = "#2563EB"   # StackAI primary blue
BLUE_DARK = "#1D4ED8"
BLUE_LIGHT= "#EFF6FF"
BLUE_BORDER = "#BFDBFE"
GRAY_DARK  = "#1F2937"
GRAY_MED   = "#6B7280"
GRAY_LIGHT = "#F9FAFB"
GRAY_BORDER= "#E5E7EB"
WHITE      = "#FFFFFF"
SUCCESS    = "#10B981"
WARNING    = "#F59E0B"
ERROR      = "#EF4444"
ORANGE     = "#F97316"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }}

.stApp {{ background: {GRAY_LIGHT}; }}

.stTextInput > div > div > input,
.stTextArea > div > div > textarea {{
    border-radius: 8px !important;
    border: 1.5px solid {GRAY_BORDER} !important;
    font-size: 15px !important;
    padding: 10px 14px !important;
    background: {WHITE} !important;
}}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {{
    border-color: {BLUE} !important;
    box-shadow: 0 0 0 3px {BLUE_BORDER} !important;
}}

/* Sidebar */
[data-testid="stSidebar"] {{
    background: {WHITE} !important;
    border-right: 1.5px solid {GRAY_BORDER};
    padding: 0 !important;
}}
[data-testid="stSidebar"] > div {{ padding: 20px 16px !important; }}

/* Buttons */
.stButton > button {{
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em !important;
    transition: all 0.15s ease !important;
    border: none !important;
}}
.stButton.primary > button {{
    background: {BLUE} !important;
    color: {WHITE} !important;
}}
.stButton.primary > button:hover {{
    background: {BLUE_DARK} !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(37,99,235,0.3) !important;
}}
.stButton.secondary > button {{
    background: {WHITE} !important;
    color: {GRAY_DARK} !important;
    border: 1.5px solid {GRAY_BORDER} !important;
}}
.stButton.secondary > button:hover {{
    border-color: {BLUE} !important;
    color: {BLUE} !important;
}}

/* Chat messages */
[data-testid="stChatMessage"] {{
    border-radius: 12px !important;
    padding: 14px 18px !important;
    margin: 6px 0 !important;
    border: 1px solid {GRAY_BORDER} !important;
    background: {WHITE} !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
}}
[data-testid="stChatMessage"][data-testid="stChatMessage-user"] {{
    background: {BLUE_LIGHT} !important;
    border-color: {BLUE_BORDER} !important;
}}

/* Status / expander */
[data-testid="stExpander"] {{
    border-radius: 10px !important;
    border: 1px solid {GRAY_BORDER} !important;
    background: {WHITE} !important;
}}
.stStatusWidget {{ border-radius: 10px !important; }}

/* Tabs */
.stTabs [data-testid="stTab"] {{
    border-radius: 8px 8px 0 0 !important;
    font-weight: 600 !important;
    padding: 8px 20px !important;
}}

/* Cards */
.agent-card {{
    background: {WHITE};
    border: 1.5px solid {GRAY_BORDER};
    border-radius: 14px;
    padding: 20px 24px;
    margin: 10px 0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    transition: all 0.2s ease;
}}
.agent-card:hover {{
    box-shadow: 0 4px 16px rgba(37,99,235,0.1);
    border-color: {BLUE_BORDER};
}}

/* Pipeline step */
.pipeline-step {{
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 8px 12px;
    border-radius: 8px;
    margin: 5px 0;
    background: {GRAY_LIGHT};
    border-left: 3px solid {BLUE};
    font-size: 13px;
}}
.pipeline-step .step-num {{
    font-weight: 700;
    color: {BLUE};
    min-width: 50px;
}}
.pipeline-step .step-icon {{ font-size: 14px; }}
.pipeline-step .step-text {{ color: {GRAY_DARK}; line-height: 1.5; }}
.pipeline-step .tool-name {{
    font-weight: 600;
    color: {BLUE_DARK};
    background: {BLUE_LIGHT};
    padding: 1px 7px;
    border-radius: 5px;
    font-size: 12px;
}}

/* Badges */
.badge {{
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 10px; border-radius: 20px;
    font-size: 12px; font-weight: 600;
}}
.badge-blue {{ background: {BLUE_LIGHT}; color: {BLUE_DARK}; border: 1px solid {BLUE_BORDER}; }}
.badge-green {{ background: #D1FAE5; color: #065F46; border: 1px solid #A7F3D0; }}
.badge-red {{ background: #FEE2E2; color: #991B1B; border: 1px solid #FECACA; }}
.badge-gray {{ background: #F3F4F6; color: {GRAY_DARK}; border: 1px solid {GRAY_BORDER}; }}

/* Header */
.main-header {{
    background: {WHITE};
    border-bottom: 1.5px solid {GRAY_BORDER};
    padding: 16px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
}}
.logo {{
    font-size: 20px; font-weight: 700; color: {GRAY_DARK};
    display: flex; align-items: center; gap: 8px;
}}
.logo span {{ color: {BLUE}; }}

/* Metric tile */
.metric {{
    background: {WHITE};
    border: 1.5px solid {GRAY_BORDER};
    border-radius: 12px;
    padding: 16px 20px;
    text-align: center;
}}
.metric .value {{ font-size: 26px; font-weight: 700; color: {BLUE_DARK}; }}
.metric .label {{ font-size: 12px; color: {GRAY_MED}; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.05em; }}

/* Divider */
.section-divider {{ height: 1px; background: {GRAY_BORDER}; margin: 20px 0; }}

/* Answer box */
.answer-box {{
    background: {WHITE};
    border: 1.5px solid {GRAY_BORDER};
    border-left: 4px solid {BLUE};
    border-radius: 12px;
    padding: 20px 24px;
    line-height: 1.7;
    color: {GRAY_DARK};
    font-size: 15px;
    margin: 8px 0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}}

/* Reasoning bubble */
.reasoning {{
    background: {GRAY_LIGHT};
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px;
    color: {GRAY_MED};
    font-style: italic;
    margin: 4px 0;
    border-left: 3px solid {ORANGE};
}}

/* Spinner */
.stSpinner > div {{ border-color: {BLUE} !important; }}

/* Smooth animations */
@keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
@keyframes slideIn {{ from {{ opacity: 0; transform: translateX(-10px); }} to {{ opacity: 1; transform: translateX(0); }} }}
.fade-in {{ animation: fadeIn 0.3s ease-out forwards; }}
.slide-in {{ animation: slideIn 0.3s ease-out forwards; }}

/* Pipeline step animations */
.pipeline-step {{ animation: slideIn 0.2s ease-out forwards; }}

/* Expander smooth open/close */
.streamlit-expanderHeader {{ transition: background 0.15s ease !important; }}
.streamlit-expanderHeader:hover {{ background: {BLUE_LIGHT} !important; }}

/* Chat message animations */
[data-testid="stChatMessage"] {{ animation: fadeIn 0.25s ease-out; }}

/* Tab hover effect */
.stTabs [data-testid="stTab"]:hover {{ background: {BLUE_LIGHT} !important; color: {BLUE} !important; }}

/* Scrollbar */
::-webkit-scrollbar {{ width: 6px; }}
::-webkit-scrollbar-track {{ background: {GRAY_LIGHT}; }}
::-webkit-scrollbar-thumb {{ background: {GRAY_BORDER}; border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: {GRAY_MED}; }}

/* Remove top padding */
.stMainBlockContainer {{ padding-top: 0 !important; }}
.block-container {{ padding-top: 0 !important; padding-bottom: 80px !important; }}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
_log_file = os.path.join(LOG_DIR, "app.log")
_logger = logging.getLogger("app_st")
_logger.setLevel(logging.DEBUG)
if not _logger.handlers:
    _fh = logging.FileHandler(_log_file, mode="a", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    _logger.addHandler(_fh)
    _fh.flush()

# Write raw startup marker (no buffering)
with open(_log_file, "a", encoding="utf-8") as _startup_f:
    import datetime as _dt
    _startup_f.write(f"=== app.py started at {_dt.datetime.now().isoformat()} ===\n")
    _startup_f.flush()
    import os as _os
    _os.fsync(_startup_f.fileno())

def tail_log(n=80):
    try:
        with open(_log_file, encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except Exception:
        return "(no log yet)"

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────
def init_state():
    st.session_state.setdefault("session_id", str(uuid.uuid4())[:8])
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("last_traceback", "")
    st.session_state.setdefault("agent_stopped", False)
    st.session_state.setdefault("stop_requested", False)
    st.session_state.setdefault("graph_initialized", False)
    st.session_state.setdefault("config", None)
    st.session_state.setdefault("active_tab", "💬 Chat")
    st.session_state.setdefault("stats", {"steps": 0, "tokens": 0, "runtime": ""})
    st.session_state.setdefault("phase", "idle")
    st.session_state.setdefault("interrupt_prompt", None)
    st.session_state.setdefault("screenshots", [])  # [(step, screenshot_path), ...]
    if st.session_state.config is None:
        st.session_state.config = {
            "configurable": {"thread_id": f"nav-{st.session_state.session_id}"}}

init_state()

# Global async state (shared across threads)
_g_answer = ""
_g_error  = ""
_g_step   = 0
_g_lock   = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
# Helper: compact tool summary
# ─────────────────────────────────────────────────────────────────────────────
def _tool_summary(tool_calls):
    if not tool_calls: return ""
    parts = []
    icons = {
        "browser_navigate": "🔗", "open_url_headed": "🌐", "browser_click": "🖱",
        "click_on_page": "🖱", "browser_fill": "⌨️", "type_text_on_page": "⌨️",
        "browser_type": "⌨️", "browser_key_press": "⌨️",
        "maps_reviews": "⭐", "places_search": "📍", "place_details": "📋",
        "web_search": "🔍", "deep_scrape": "📄", "compare_prices": "💰",
        "stop": "⏹",
    }
    for tc in tool_calls:
        name = tc.get("name", "?")
        args = tc.get("args", {})
        icon = icons.get(name, "⚙️")
        if name == "places_search":
            parts.append(f'{icon} places_search: "{args.get("query","")[:50]}"')
        elif name in ("open_url_headed", "browser_navigate"):
            parts.append(f'{icon} {args.get("url","")[:60]}')
        elif name == "maps_reviews":
            kw = args.get("keyword", "")
            parts.append(f'{icon} reviews(kw="{kw}")')
        elif name == "stop":
            parts.append(f'{icon} stop')
        else:
            parts.append(f'{icon} {name}')
    return " | ".join(parts)

# ─────────────────────────────────────────────────────────────────────────────
# Async graph runner
# ─────────────────────────────────────────────────────────────────────────────
# Semantic intent classifier — uses Claude Haiku (fast + cheap)
async def _classify_intent(user_input: str, history: list | None = None) -> str:
    """Classify user intent as 'navigate' or 'research' using LLM.
    Accepts optional chat history for context-aware classification.
    """
    try:
        import anthropic
        if not hasattr(_classify_intent, '_client'):
            _classify_intent._client = anthropic.AsyncAnthropic()
        client = _classify_intent._client
        
        # Build context from recent history
        context_lines = ""
        if history:
            recent = history[-6:]  # last 3 exchanges
            for msg in recent:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    context_lines += f"{role}: {content[:150]}\n"
        
        context_block = f"""Previous conversation:
{context_lines}
""" if context_lines else ""
        
        prompt = f"""{context_block}Classify this user request. Reply ONLY with one word: "navigate" or "research".

navigate = needs a live browser to click, scroll, fill forms, visually interact with pages, get directions on a map
research = needs web search, data extraction, price comparison, information lookup

User request: {user_input}

Consider the conversation context if provided. If the user is following up on a previous navigate/directions request, classify as navigate.
Classification:"""
        
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        answer = resp.content[0].text.strip().lower()
        if "nav" in answer:
            return "navigate"
        return "research"
    except Exception as e:
        _logger.warning("Intent classification failed (%s), defaulting to research", e)
        return "research"


# HITL classifier — decide if agent really needs human help
async def _classify_hitl(interrupt_prompt: str, last_agent_msg: str, partial_answer: str) -> str:
    """Use LLM to decide if human help is needed.
    Returns empty string if agent completed task (just waiting for next task).
    Returns a user-facing prompt if human intervention is actually needed.
    """
    try:
        import anthropic
        if not hasattr(_classify_hitl, '_client'):
            _classify_hitl._client = anthropic.AsyncAnthropic()
        client = _classify_hitl._client
        
        prompt = f"""Decide if this agent needs human help RIGHT NOW.

Interrupt: {interrupt_prompt}
Agent said: {last_agent_msg[:200]}
Answer so far: {partial_answer[:150] if partial_answer else 'none'}

If the agent COMPLETED its task and is just asking for the next task (like 'What would you like to do?') → reply: NONE
If the agent needs CAPTCHA solved, login, user choice, or is stuck → reply with a short user-facing prompt

Reply ONLY with:
- NONE (task done, no help needed)
- Or a short prompt (max 80 chars) for the user

Reply:"""
        
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        reason = resp.content[0].text.strip()
        if reason.upper().startswith('NONE') or not reason:
            return ""  # No human help needed
        return reason
    except Exception as e:
        _logger.warning("HITL classification failed (%s), defaulting to show interrupt", e)
        return interrupt_prompt  # fallback: show raw interrupt

def _run_async(user_input, config, on_step, on_tool_result, tracker, chat_history=None):
    global _g_answer, _g_error, _g_step

    async def _runner():
        global _g_answer, _g_error, _g_step
        step = 0
        current_step = 0  # tracks step for screenshot association
        try:
            st.session_state.graph_initialized = True
            from langchain_core.messages import HumanMessage
            from langgraph.types import Command
            _logger.info("USER INPUT: %s", user_input[:200])

            # Check if we're resuming from an interrupt (HITL)
            snapshot = rn.app.get_state(config)
            has_interrupt = snapshot.tasks and snapshot.tasks[0].interrupts
            _logger.info("INTERRUPT CHECK: tasks=%s has_interrupt=%s", len(snapshot.tasks) if snapshot.tasks else 0, has_interrupt)

            if has_interrupt:
                # Resume graph with user's response
                _logger.info("RESUMING from interrupt with: %s", user_input[:200])
                run_input = Command(resume=user_input)
            else:
                # Semantic intent classification via LLM (with chat history)
                _mode = await _classify_intent(user_input, chat_history)
                _logger.info("MODE (LLM): %s", _mode)
                _logger.info("MODE: %s", _mode)
                run_input = {"messages": [HumanMessage(content=user_input)], "mode": _mode}

            async for event in rn.app.astream(
                run_input, config, stream_mode="updates"
            ):
                for node, data in event.items():
                    msgs = data.get("messages", []) if isinstance(data, dict) else []

                    if node in ("nav_agent", "research_agent"):
                        for m in msgs:
                            tc = getattr(m, 'tool_calls', []) or []
                            content = getattr(m, 'content', '') or ''
                            if tc:
                                step += 1
                                _g_step = step
                                tool_names = [t.get('name','') for t in tc]
                                _logger.info("STEP %d | %s | tools: %s", step, node, ', '.join(tool_names))
                                for t in tc:
                                    _logger.debug("  tool_call: %s(%s)", t.get('name',''), str(t.get('args',{}))[:300])
                                reasoning = (content[:200] + "...") if isinstance(content, str) and content else ""
                                current_step = step
                                on_step(step, _tool_summary(tc), reasoning)
                            elif isinstance(content, str) and content.strip() and len(content) > 80:
                                if not tc:
                                    _logger.info("STEP %d | %s | ANSWER (%d chars)", step, node, len(content))
                                    with _g_lock:
                                        _g_answer = content

                    elif node in ("nav_tools", "research_tools"):
                        for m in msgs:
                            name = getattr(m, 'name', 'tool')
                            content = getattr(m, 'content', '') or ''
                            short = (content[:150] + "...") if isinstance(content, str) and len(content) > 150 else content
                            _logger.info("TOOL_RESULT | %s | %s | %s", node, name, short[:200])
                            on_tool_result(node, name, short)
                            # Detect and store screenshot paths
                            if isinstance(content, str):
                                # browser_inspect returns {"screenshot_path": "logs/inspect_XXX.png"}
                                # browser_navigate(visual=True) may also return screenshot path
                                import re
                                # Check for screenshot_path field
                                sp_match = re.search(r'"screenshot_path"\s*:\s*"([^"]+)"', content)
                                if sp_match:
                                    screenshot_path = sp_match.group(1)
                                else:
                                    # Check for direct path reference in content
                                    sp_match = re.search(r'(logs[/\\][\w]+\.(?:png|jpg|jpeg))', content)
                                    screenshot_path = sp_match.group(1) if sp_match else None
                                if screenshot_path:
                                    _logger.info("SCREENSHOT DETECTED | step %d | %s", current_step, screenshot_path)
                                    # Make path absolute if relative
                                    if not os.path.isabs(screenshot_path):
                                        screenshot_path = os.path.join(os.path.dirname(__file__), screenshot_path)
                                    on_tool_result(node, name, short, screenshot_path, current_step)
                            # Capture stop tool answer
                            if name == "stop" and isinstance(content, str):
                                try:
                                    d = json.loads(content)
                                    stop_ans = d.get("answer", "")
                                except (json.JSONDecodeError, TypeError):
                                    stop_ans = content
                                if stop_ans and len(stop_ans) > 30:
                                    _logger.info("STOP ANSWER captured (%d chars)", len(stop_ans))
                                    with _g_lock:
                                        _g_answer = stop_ans

            # After stream ends, check if graph hit an interrupt (needs human)
            snapshot = rn.app.get_state(config)
            if snapshot.tasks and snapshot.tasks[0].interrupts:
                interrupt_value = snapshot.tasks[0].interrupts[0].value
                
                # Get agent's last message to understand WHY it needs help
                last_agent_msg = ""
                state_messages = snapshot.values.get("messages", [])
                for msg in reversed(state_messages):
                    content = getattr(msg, 'content', '') or ''
                    if isinstance(content, str) and content.strip():
                        last_agent_msg = content[:500]
                        break
                
                # Use LLM to decide if human help is actually needed
                hitl_reason = await _classify_hitl(interrupt_value, last_agent_msg, _g_answer)
                _logger.info("HITL INTERRUPT: %s | reason: %s", str(interrupt_value)[:100], hitl_reason[:100])
                
                if hitl_reason:
                    with _g_lock:
                        _g_error = ""
                        tracker['interrupt_prompt'] = hitl_reason
                        tracker['needs_human'] = True
                # If hitl_reason is empty, agent completed task and is just waiting for next task
                # — treat as done, not HITL

        except Exception as e:
            _g_error = f"{type(e).__name__}: {e}"
            _logger.error("Graph error: %s", e, exc_info=True)
        finally:
            _logger.info("RUN COMPLETE | steps=%d | answer=%d chars | error=%s | hitl=%s", _g_step, len(_g_answer), bool(_g_error), tracker.get('needs_human', False))
            with _g_lock:
                tracker['done'].set()

    asyncio.run(_runner())

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    # Logo / Brand
    st.markdown(f"""
    <div style="padding: 4px 4px 20px;">
        <div class="logo">🤖 <span>Hybrid</span>Agent</div>
        <div style="font-size:11px; color:{GRAY_MED}; margin-top:2px;">Agent Platform</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"<div class='section-divider' style='margin: 0 0 16px;'></div>", unsafe_allow_html=True)

    # Stats
    st.markdown(f"<div class='section-divider' style='margin: 16px 0;'></div>", unsafe_allow_html=True)
    st.markdown("**📊 This Session**")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"<div class='metric'><div class='value' id='stat-steps'>0</div><div class='label'>Steps</div></div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='metric'><div class='value'>—</div><div class='label'>Msgs</div></div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div class='metric'><div class='value' style='font-size:16px;'>—</div><div class='label'>Time</div></div>", unsafe_allow_html=True)

    st.markdown(f"<div class='section-divider' style='margin: 16px 0;'></div>", unsafe_allow_html=True)

    # API key
    _key = os.getenv("ANTHROPIC_API_KEY", "")
    if _key:
        st.markdown(f"<span class='badge badge-green'>✅ API Key Set</span>", unsafe_allow_html=True)
    else:
        st.markdown(f"<span class='badge badge-red'>⚠️ API Key Missing</span>", unsafe_allow_html=True)

    st.divider()

    # Stop / Restart
    if st.button("🛑 Stop Agent", use_container_width=True, type="primary"):
        st.session_state.stop_requested = True
        st.session_state.agent_stopped = True
        st.rerun()

    if st.button("🔄 New Session", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    st.divider()

    # Live log
    with st.expander("📋 Agent Log"):
        log_expander = st.empty()
        log_expander.code(tail_log(60), language=None)

    st.divider()

    # Debug
    with st.expander("🐛 Debug / Traceback"):
        tb = st.session_state.get("last_traceback") or "(none)"
        st.code(tb, language=None)

# ─────────────────────────────────────────────────────────────────────────────
# Main header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="main-header">
    <div class="logo">🤖 <span>Hybrid</span>Agent</div>
    <div style="display:flex; align-items:center; gap:12px;">
        <span class="badge badge-green">Claude Haiku</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Alert if stopped
if st.session_state.get("agent_stopped"):
    st.warning("⛔ Agent stopped. Click **🔄 New Session** to start fresh.")

# ─────────────────────────────────────────────────────────────────────────────
# Tabs: Chat | Pipeline | Docs
# ─────────────────────────────────────────────────────────────────────────────
tab_chat, tab_pipeline, tab_docs = st.tabs(["💬 Chat", "📊 Pipeline", "📚 Tools Docs"])

# ─── CHAT TAB ───────────────────────────────────────────────────────────────
with tab_chat:
    # Welcome state when no messages
    if not st.session_state.messages:
        st.markdown(f"""
        <div style="text-align:center; padding: 40px 20px; margin-bottom: 30px;">
            <div style="font-size:48px; margin-bottom: 16px;">🤖</div>
            <h2 style="color:{GRAY_DARK}; margin-bottom: 8px;">Welcome to HybridAgent</h2>
            <p style="color:{GRAY_MED}; font-size: 15px; max-width: 500px; margin: 0 auto 28px;">
                A research agent that can search the web, navigate pages, find local businesses, and more.
            </p>
            <div style="display:flex; flex-wrap:wrap; gap:10px; justify-content:center;">
                <span class="badge badge-blue" style="font-size:13px;padding:6px 14px;">🌐 Web Search</span>
                <span class="badge badge-blue" style="font-size:13px;padding:6px 14px;">🗺️ Local Search</span>
                <span class="badge badge-blue" style="font-size:13px;padding:6px 14px;">💰 Price Compare</span>
                <span class="badge badge-blue" style="font-size:13px;padding:6px 14px;">📄 Deep Scrape</span>
            </div>
        </div>
        <div style="margin: 20px 0;">
            <p style="font-size:13px; color:{GRAY_MED}; margin-bottom: 10px;">Try asking:</p>
            <div style="display:flex; flex-wrap:wrap; gap:8px;">
                <span class="badge badge-gray" style="cursor:pointer;" onclick="document.querySelector('.stTextInput input').value='Compare prices for wireless earbuds'">"Compare prices for wireless earbuds"</span>
                <span class="badge badge-gray" style="cursor:pointer;" onclick="document.querySelector('.stTextInput input').value='Find the best restaurants near Central Park'">"Find restaurants near Central Park"</span>
                <span class="badge badge-gray" style="cursor:pointer;" onclick="document.querySelector('.stTextInput input').value='Search for the latest news about AI agents'">"Search latest AI agent news"</span>
            </div>
        </div>
        <div class="section-divider"></div>
        """, unsafe_allow_html=True)

    # HITL prompt is displayed after runner completes (below)
    # Not here — avoids duplicate rendering

    # Chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input — placeholder changes based on phase
    _placeholder = "Respond to agent..." if st.session_state.get("phase") == "waiting_human" else "Ask anything — search, navigate, find local info..."
    user_text = st.chat_input(_placeholder)

    if user_text and not st.session_state.get("agent_stopped"):
        config = st.session_state.config

        # Reset globals before run
        _g_answer = ""; _g_error = ""; _g_step = 0

        # If waiting for human input (HITL), this is a resume, not a new message
        if st.session_state.get("phase") != "waiting_human":
            # Add user message for new requests
            st.session_state.messages.append({"role": "user", "content": user_text})
            with st.chat_message("user"):
                st.markdown(user_text)
            st.session_state.phase = "running"
        else:
            # HITL resume — show as system response indicator
            with st.chat_message("user"):
                st.markdown(f"_Your response: {user_text}_")


        # Pipeline + answer area
        assistant_slot = st.chat_message("assistant")
        pipeline_placeholder = assistant_slot.empty()

        # Thread-safe: callbacks only append data, rendering happens in main thread poll
        import threading
        _ui_lock = threading.Lock()
        _ui_steps = []  # list of (type, data) tuples
        _ui_new = threading.Event()  # signal that new data arrived

        def on_step(s, summary, reasoning):
            with _ui_lock:
                _ui_steps.append(("step", s, summary, reasoning))
                _ui_new.set()

        def on_tool_result(node, name, short, screenshot_path=None, step=None):
            with _ui_lock:
                _ui_steps.append(("tool", node, name, short))
                if screenshot_path and step:
                    _ui_steps.append(("screenshot", step, screenshot_path))
                    # Store screenshot in _ui_steps; main thread will move to session_state
                _ui_new.set()

        def _render_pipeline():
            lines = []
            with _ui_lock:
                snapshot = list(_ui_steps)
            for entry in snapshot:
                if entry[0] == "step":
                    _, s, summary, reasoning = entry
                    badge = f"<span class='badge badge-blue' style='font-size:11px;padding:2px 8px;'>Step {s}</span>"
                    reasoning_html = f"<div class='reasoning'>💭 {reasoning}</div>" if reasoning else ""
                    lines.append(
                        f"<div class='pipeline-step'>"
                        f"{badge}"
                        f"<div>"
                        f"<span class='tool-name'>{summary or 'reasoning...'}</span>"
                        f"{reasoning_html}"
                        f"</div>"
                        f"</div>"
                    )
                elif entry[0] == "tool":
                    _, node, name, short = entry
                    icon = "\U0001f527" if node == "nav_tools" else "\U0001f4e1"
                    lines.append(
                        f"<div class='pipeline-step' style='border-left-color:{GRAY_MED}; background:#FAFAFA;'>"
                        f"<span style='color:{GRAY_MED}; font-size:12px;'>{icon}</span>"
                        f"<div>"
                        f"<span class='tool-name' style='background:#F3F4F6;color:{GRAY_DARK};border-color:{GRAY_BORDER};'>{name}</span>"
                        f"<div style='font-size:12px;color:{GRAY_MED};margin-top:3px;'>{short[:120]}</div>"
                        f"</div>"
                        f"</div>"
                    )
                elif entry[0] == "screenshot":
                    _, step_num, ss_path = entry
                    # Sync to session_state (main thread only)
                    if (step_num, ss_path) not in st.session_state.screenshots:
                        st.session_state.screenshots.append((step_num, ss_path))
                    if os.path.exists(ss_path):
                        lines.append(
                            f"<div class='pipeline-step' style='border-left-color:#3B82F6;'>"
                            f"<span style='font-size:12px;'>\U0001f5bc\ufe0f</span>"
                            f"<div><span class='tool-name' style='background:#EFF6FF;color:#1D4ED8;border-color:#93C5FD;'>Screenshot Step {step_num}</span></div>"
                            f"</div>"
                        )
            if lines:
                pipeline_placeholder.markdown("\n".join(lines), unsafe_allow_html=True)

        done_event = threading.Event()

        # Run in background
        # Thread-safe event tracker (threading.Lock can't take attributes)
        _tracker = {'done': done_event}
        runner = threading.Thread(target=_run_async, args=(user_text, config, on_step, on_tool_result, _tracker, list(st.session_state.messages)), daemon=True)
        runner.start()

        # Poll until done — main thread renders UI
        status_ph = st.empty()
        with status_ph.status("⚙️ Running agent...", expanded=True) as s:
            while not done_event.is_set():
                import time; time.sleep(0.3)
                if _ui_new.is_set():
                    _ui_new.clear()
                    _render_pipeline()
                if st.session_state.get("stop_requested"):
                    done_event.set()
                    break
            # Final render
            _render_pipeline()
            # Thread-safe read of globals
            with _g_lock:
                final_step = _g_step
                final_answer = _g_answer
                final_error  = _g_error

            # Check HITL interrupt
            interrupt_prompt = _tracker.get('interrupt_prompt')
            needs_human = _tracker.get('needs_human', False)

            if needs_human and interrupt_prompt:
                s.update(label="⚠️ Agent needs your input", state="complete", expanded=False)
            elif final_error:
                s.update(label="❌ Error", state="complete", expanded=False)
            else:
                s.update(label=f"✅ Done — {final_step} steps", state="complete", expanded=False)

        runner.join(timeout=3)

        # Handle HITL — agent paused, waiting for human input
        if needs_human and interrupt_prompt:
            st.session_state.phase = "waiting_human"
            st.session_state.interrupt_prompt = interrupt_prompt
            st.markdown(f"""
            <div style="padding:16px; border-radius:10px; border:2px solid #F59E0B; background:#FFFBEB; margin:10px 0;">
                <div style="font-weight:600; color:#92400E; margin-bottom:8px;">⚠️ Agent Needs Your Help</div>
                <div style="color:#78350F; font-size:14px;">{interrupt_prompt}</div>
            </div>
            """, unsafe_allow_html=True)
            if final_answer:
                st.markdown(f"<div class='answer-box' style='border-left-color:#F59E0B;'>🔄 Partial: {final_answer[:200]}...</div>", unsafe_allow_html=True)
        elif final_error:
            st.markdown(f"<div class='answer-box' style='border-left-color:{ERROR};'>❌ {final_error}</div>", unsafe_allow_html=True)
            st.session_state.last_traceback = traceback.format_exc()
            final_text = f"Error: {final_error}"
            st.session_state.phase = "done"
            st.session_state.messages.append({"role": "assistant", "content": final_text})
        elif final_answer:
            st.markdown(f"<div class='answer-box'>{final_answer}</div>", unsafe_allow_html=True)
            st.session_state.phase = "done"
            st.session_state.messages.append({"role": "assistant", "content": final_answer})

        # Show screenshots from this run in a collapsible section
        run_screenshots = [s for s in st.session_state.get("screenshots", [])]
        if run_screenshots:
            with st.expander(f"🖼️ View {len(run_screenshots)} Screenshot(s)", expanded=False):
                for step_num, screenshot_path in run_screenshots:
                    filename = os.path.basename(screenshot_path)
                    if os.path.exists(screenshot_path):
                        st.image(screenshot_path, caption=f"Step {step_num}: {filename}", use_container_width=True)
                        st.divider()
                    else:
                        st.warning(f"Screenshot not found: {screenshot_path}")
        else:
            st.markdown("<div class='answer-box'>_(no answer returned)_</div>", unsafe_allow_html=True)
            st.session_state.phase = "done"
            st.session_state.messages.append({"role": "assistant", "content": "(no answer)"})

        # Reset globals
        with _g_lock:
            _g_answer = ""; _g_error = ""; _g_step = 0
        st.session_state.stop_requested = False

# ─── PIPELINE TAB ────────────────────────────────────────────────────────────
with tab_pipeline:
    st.markdown("### 📊 Execution Pipeline")
    st.caption("Real-time view of agent steps, tool calls, and intermediate results.")
    st.divider()

    if not st.session_state.messages:
        st.markdown(f"""
        <div style="text-align:center; padding: 50px 20px;">
            <div style="font-size:56px; margin-bottom: 20px;">📊</div>
            <h3 style="color:{GRAY_DARK}; margin-bottom: 10px;">Pipeline Preview</h3>
            <p style="color:{GRAY_MED}; font-size: 14px; max-width: 400px; margin: 0 auto 24px;">
                Your agent's execution steps will appear here as it processes your request.
            </p>
            <div style="display:flex; flex-direction:column; gap:12px; max-width:320px; margin:0 auto;">
                <div class="pipeline-step" style="opacity:0.5;">
                    <span class="step-num">1</span>
                    <span class="step-icon">🔍</span>
                    <span class="step-text">Web Search</span>
                </div>
                <div style="display:flex; justify-content:center; color:{GRAY_BORDER};">↓</div>
                <div class="pipeline-step" style="opacity:0.5;">
                    <span class="step-num">2</span>
                    <span class="step-icon">🌐</span>
                    <span class="step-text">Navigate & Read</span>
                </div>
                <div style="display:flex; justify-content:center; color:{GRAY_BORDER};">↓</div>
                <div class="pipeline-step" style="opacity:0.5;">
                    <span class="step-num">3</span>
                    <span class="step-icon">📝</span>
                    <span class="step-text">Compile Answer</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Rebuild pipeline view from history
        step_n = 0
        for msg in st.session_state.messages:
            if isinstance(msg, dict):
                content = msg.get("content", "")
                role    = msg.get("role", "")
            else:
                content = str(msg)
                role    = ""
            if role == "assistant" and len(content) > 100:
                st.markdown(
                    f"<div class='answer-box'>"
                    f"<span class='badge badge-green'>✅ Final</span>  "
                    f"<span style='color:{GRAY_MED};font-size:13px;'>{content[:300]}...</span>"
                    f"</div>", unsafe_allow_html=True)
        st.divider()

        # Display screenshots from session_state
        screenshots = st.session_state.get("screenshots", [])
        if screenshots:
            st.markdown("### 🖼️ Screenshots")
            st.caption(f"{len(screenshots)} screenshot(s) captured during this session")
            for step_num, screenshot_path in screenshots:
                filename = os.path.basename(screenshot_path)
                with st.expander(f"📸 Step {step_num}: {filename}", expanded=False):
                    if os.path.exists(screenshot_path):
                        st.image(screenshot_path, caption=f"Step {step_num}: {filename}", use_container_width=True)
                    else:
                        st.warning(f"Screenshot not found: {screenshot_path}")
            st.divider()

        st.caption(f"Messages: {len(st.session_state.messages)}")

# ─── TOOLS DOCS TAB ─────────────────────────────────────────────────────────
with tab_docs:
    st.markdown("### 📚 Available Tools")
    st.caption("Agent capabilities and available actions.")
    st.divider()

    with st.expander("#### 🌐 Browser (Navigate)", expanded=True):
        nav_tools = [
            ("browser_navigate", "Navigate to URL, returns DOM snapshot"),
            ("browser_click", "Click element by CSS selector"),
            ("browser_fill", "Fill input, press Enter optionally"),
            ("browser_type", "Type with keyboard delay (autocomplete)"),
            ("browser_key_press", "Press key: Enter, Escape, Tab..."),
            ("browser_click_coords", "Click at (x, y) pixel coords"),
            ("browser_scroll_element", "Scroll element (maps, sidebars)"),
            ("browser_select", "Select option from <select>"),
            ("browser_hover", "Hover to reveal dropdowns/tooltips"),
            ("browser_go_back", "Browser back button"),
            ("browser_wait", "Wait for JS/network to settle"),
            ("browser_read_page", "Read page text (full_page=True for 50k chars)"),
            ("browser_evaluate", "Run JS expression in browser"),
            ("get_accessibility_tree", "Fallback for React/Angular/SVG maps"),
            ("browser_inspect", "Screenshot + DOM snapshot (for CAPTCHAs/maps)"),
        ]
        for name, desc in nav_tools:
            st.markdown(f"- **`{name}`** — {desc}")

    with st.expander("#### 🔍 Research", expanded=True):
        res_tools = [
            ("web_search", "Search the web (Firecrawl)"),
            ("deep_scrape", "Extract full page as markdown"),
            ("compare_prices", "Price comparison across sites"),
            ("extract_structured", "LLM extraction to JSON schema"),
            ("places_search", "Google Places API — local businesses"),
            ("place_details", "Place reviews, phone, website, hours"),
            ("maps_reviews", "Scrape Google Maps reviews with keyword filter"),
        ]
        for name, desc in res_tools:
            st.markdown(f"- **`{name}`** — {desc}")

    with st.expander("#### ⏹ Controls", expanded=False):
        st.markdown("- **`stop`** — End the agent session and return answer")
