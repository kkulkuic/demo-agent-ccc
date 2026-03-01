"""Single entry: Streamlit app with Auto and Chat modes, shared browser session, optional visualization."""
import os
import sys
import uuid
import traceback
from typing import List

import streamlit as st
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

from core.browser import get_page, stop_browser_session
from agent.auto import run_auto_agent
from agent.chat import build_chat_agent, get_model_candidates, is_model_not_found_error
import tools.headed_tools as headed_tools

st.set_page_config(page_title="Agent-Browser", page_icon="🧭", layout="wide")
st.title("Agent-Browser: Auto + Chat")
st.caption("One entry: Auto (plan + execute) or Chat (ReAct + headed browser). Toggle behavior visualization in the sidebar.")

# Session state
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "model_in_use" not in st.session_state:
    st.session_state.model_in_use = None
if "model_candidates" not in st.session_state:
    st.session_state.model_candidates = get_model_candidates()
if "model_index" not in st.session_state:
    st.session_state.model_index = 0
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

    st.subheader("Claude Model")
    try:
        _api_key_set = bool(__import__("config").get_api_key())
    except Exception:
        _api_key_set = False
    if not _api_key_set:
        st.error("API key missing. Set ANTHROPIC_API_KEY in system env, or create a .env file in the project root with: ANTHROPIC_API_KEY=sk-ant-...")
        st.caption("If you set system env, restart the terminal/IDE before running streamlit.")
    st.write("Using:", st.session_state.get("model_in_use") or "(not set yet)")
    st.caption("Auto mode uses planner model from config; Chat uses first available from list.")
    st.code("\n".join(st.session_state.model_candidates[:5]))

    st.subheader("Debug")
    with st.expander("Last traceback"):
        st.code(st.session_state.get("last_traceback") or "(none)")

    if sys.platform.startswith("win"):
        st.caption("Windows: Proactor event loop is set for Playwright in tool threads.")

    st.subheader("Browser 窗口")
    st.info("运行 Auto 或发送 Chat 消息时会打开**可见的浏览器窗口**。请在该窗口中查看 agent 的操作；如遇验证码或人机验证，请在该窗口中手动完成。")
    st.caption("Same browser session for both modes.")
    st.code(st.session_state.session_id)
    if st.button("Close browser session"):
        try:
            stop_browser_session(st.session_state.session_id)
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


def invoke_chat_with_fallback(lc_messages: List[BaseMessage]):
    candidates = st.session_state.model_candidates
    idx = st.session_state.model_index
    for _ in range(len(candidates)):
        model = candidates[idx]
        try:
            st.session_state.model_in_use = model
            agent = build_chat_agent(model, session_id=st.session_state.session_id)
            return agent.invoke({"messages": lc_messages})
        except Exception as e:
            if is_model_not_found_error(e) and (idx + 1) < len(candidates):
                idx += 1
                st.session_state.model_index = idx
                continue
            raise


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
                result = invoke_chat_with_fallback(lc_messages)
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
