"""Single entry: Streamlit app with Auto and Chat modes, shared browser session, optional visualization."""
import os
import sys
import uuid
import traceback
from typing import List

import streamlit as st
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

import config
from core.browser import run_in_browser_thread
from agent.auto import run_auto_agent
from agent.chat import build_chat_agent
import tools.headed_tools as headed_tools

st.set_page_config(page_title="Agent-Browser", page_icon="🧭", layout="wide")
st.title("Agent-Browser: Auto + Chat")
st.caption("One entry: Auto (plan + execute) or Chat (ReAct + headed browser). Toggle behavior visualization in the sidebar.")

# Session state
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_traceback" not in st.session_state:
    st.session_state.last_traceback = ""
if "mode" not in st.session_state:
    st.session_state.mode = "Chat"
if "enable_viz" not in st.session_state:
    st.session_state.enable_viz = False

# Sidebar
with st.sidebar:
    st.subheader("Mode")
    mode = st.radio("Run", ["Chat", "Auto"], index=0 if st.session_state.mode == "Chat" else 1, key="mode_radio")
    st.session_state.mode = mode

    st.subheader("Behavior visualization")
    enable_viz = st.checkbox("Show dot + element highlight during actions", value=st.session_state.enable_viz, key="enable_viz_cb")
    st.session_state.enable_viz = enable_viz

    try:
        _api_key_set = bool(config.get_api_key())
    except Exception:
        _api_key_set = False
    if not _api_key_set:
        st.error("API key missing. Set ANTHROPIC_API_KEY in system env, or create a .env file in the project root with: ANTHROPIC_API_KEY=sk-ant-...")
        st.caption("If you set system env, restart the terminal/IDE before running streamlit.")

    st.subheader("Debug")
    with st.expander("Last traceback"):
        st.code(st.session_state.get("last_traceback") or "(none)")

    if sys.platform.startswith("win"):
        st.caption("Windows: Proactor event loop is set for Playwright in tool threads.")

    st.subheader("Browser window")
    st.info("Running Auto or sending a Chat message opens a visible browser window. Use it to observe agent actions; complete CAPTCHA or human verification manually if prompted.")
    st.caption("Same browser session for both modes.")
    st.code(st.session_state.session_id)
    if st.button("Close browser session"):
        try:
            run_in_browser_thread(st.session_state.session_id, None)
            st.success("Browser session closed.")
        except Exception as e:
            st.error(str(e))


def render_trace(messages: List[BaseMessage]) -> str:
    """Render agent trace and return final assistant text."""
    final = ""
    for m in messages:
        if isinstance(m, ToolMessage):
            with st.expander(f"Tool: {getattr(m, 'name', 'tool')}", expanded=False):
                st.code(m.content)
        else:
            role = "user" if getattr(m, "type", None) == "human" else "assistant"
            with st.chat_message(role):
                content = getattr(m, "content", str(m))
                st.markdown(content)
                if role == "assistant":
                    final = content
    return final


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


# Main area
if st.session_state.mode == "Auto":
    st.subheader("Auto: plan + execute")
    instruction = st.text_input("Instruction", placeholder="e.g. Search for a product and add it to cart.")
    start_url = st.text_input("Start URL", value="https://www.saucedemo.com/")
    if st.button("Run auto agent"):
        if not instruction or not start_url:
            st.warning("Provide instruction and start URL.")
        else:
            headed_tools.set_enable_viz(st.session_state.enable_viz)
            with st.spinner("Planning and executing…"):
                try:
                    result = run_auto_agent(
                        instruction=instruction,
                        start_url=start_url,
                        session_id=st.session_state.session_id,
                        enable_viz=st.session_state.enable_viz,
                        snapshot_dir="screenshots",
                    )
                    st.success(f"Completed {result['steps']} steps.")
                    with st.expander("Plan"):
                        st.json(result.get("plan", {}))
                    if os.path.isdir("screenshots"):
                        shots = sorted([f for f in os.listdir("screenshots") if f.endswith(".png")])
                        if shots:
                            with st.expander("Screenshots"):
                                for f in shots[-10:]:
                                    st.image(os.path.join("screenshots", f), caption=f)
                except Exception as e:
                    st.session_state.last_traceback = traceback.format_exc()
                    st.error(f"{type(e).__name__}: {e}")

else:
    st.subheader("Chat: ReAct + headed browser")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_text = st.chat_input("Ask to open a URL, click, or type…")
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.markdown(user_text)

        headed_tools.set_enable_viz(st.session_state.enable_viz)
        lc_messages = to_lc_messages(st.session_state.messages)
        with st.spinner("Thinking…"):
            try:
                agent = build_chat_agent(config.get_planner_model(), session_id=st.session_state.session_id)
                result = agent.invoke({"messages": lc_messages})
                trace = result.get("messages", []) if isinstance(result, dict) else []
                if trace:
                    final_text = render_trace(trace) or getattr(trace[-1], "content", str(trace[-1]))
                else:
                    final_text = str(result)
                    with st.chat_message("assistant"):
                        st.markdown(final_text)
            except Exception as e:
                st.session_state.last_traceback = traceback.format_exc()
                final_text = f"Error: {type(e).__name__}: {e}"
                with st.chat_message("assistant"):
                    st.markdown(final_text)
        st.session_state.messages.append({"role": "assistant", "content": final_text})
