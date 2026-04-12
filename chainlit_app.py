"""
Chainlit app wrapping research+navi.py (Folder/research+navi.py)

Simple UI using Chainlit's native features:
  - @on_message for chat
  - cl.Step for tool call steps
  - cl.AskUserMessage for HITL
  - cl.Image for screenshots
"""

import os
import sys
import asyncio
import json
import uuid
import re

from dotenv import load_dotenv
load_dotenv(override=True)

# Patches (same as app.py)
sys.path.insert(0, os.path.dirname(__file__))
import pkg_resources_compat as pkg_resources
sys.modules["pkg_resources"] = pkg_resources
import playwright_stealth

# Cache rn module so InMemorySaver isn't recreated on re-import
_rn_module = None

def get_rn_module():
    global _rn_module
    if _rn_module is None:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "research_navi",
            os.path.join(os.path.dirname(__file__), "research+navi.py"))
        _rn_module = importlib.util.module_from_spec(_spec)
        sys.modules["research_navi"] = _rn_module
        _spec.loader.exec_module(_rn_module)
    return _rn_module


import chainlit as cl
from langchain_core.messages import HumanMessage
from langgraph.types import Command


# ─────────────────────────────────────────────────────────────────
# Intent classifier (Claude Haiku)
# ─────────────────────────────────────────────────────────────────

_intent_client = None

async def get_anthropic_client():
    global _intent_client
    if _intent_client is None:
        import anthropic
        _intent_client = anthropic.AsyncAnthropic()
    return _intent_client


async def classify_intent(user_input: str, history: list | None = None) -> str:
    """Classify user intent as 'navigate' or 'research' using Claude Haiku."""
    try:
        client = await get_anthropic_client()

        context_lines = ""
        if history:
            recent = history[-6:]
            for msg in recent:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    context_lines += f"{role}: {content[:150]}\n"

        context_block = f"Previous conversation:\n{context_lines}\n" if context_lines else ""

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
    except Exception:
        return "research"


async def classify_hitl(interrupt_prompt: str, last_agent_msg: str, partial_answer: str) -> str:
    """Use LLM to decide if human help is actually needed vs agent just waiting for next task."""
    try:
        client = await get_anthropic_client()

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
        if reason.upper().startswith("NONE") or not reason:
            return ""
        return reason
    except Exception:
        return interrupt_prompt


# ─────────────────────────────────────────────────────────────────
# Session setup
# ─────────────────────────────────────────────────────────────────

@cl.on_chat_start
async def on_chat_start():
    session_id = str(uuid.uuid4())[:8]
    thread_id = f"chainlit-{session_id}"
    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("messages", [])
    await cl.Message(
        content=(
            "🤖 **HybridAgent ready!**\n\n"
            "I can research (web search, scrape, price compare) or navigate (live browser interaction).\n\n"
            "What would you like me to do?"
        ),
        author="Agent",
    ).send()


# ─────────────────────────────────────────────────────────────────
# Tool icons
# ─────────────────────────────────────────────────────────────────

TOOL_ICONS = {
    "browser_navigate": "🔗",
    "open_url_headed": "🌐",
    "browser_click": "🖱",
    "click_on_page": "🖱",
    "browser_fill": "⌨️",
    "type_text_on_page": "⌨️",
    "browser_type": "⌨️",
    "browser_key_press": "⌨️",
    "maps_reviews": "⭐",
    "places_search": "📍",
    "place_details": "📋",
    "web_search": "🔍",
    "deep_scrape": "📄",
    "compare_prices": "💰",
    "browser_inspect": "📸",
    "stop": "⏹",
}


def make_tool_summary(tool_calls) -> str:
    if not tool_calls:
        return ""
    parts = []
    for tc in tool_calls:
        name = tc.get("name", "?")
        args = tc.get("args", {})
        icon = TOOL_ICONS.get(name, "⚙️")
        if name == "places_search":
            parts.append(f'{icon} places_search: "{args.get("query", "")[:50]}"')
        elif name in ("open_url_headed", "browser_navigate"):
            parts.append(f"{icon} {args.get('url', '')[:60]}")
        elif name == "maps_reviews":
            kw = args.get("keyword", "")
            parts.append(f'{icon} reviews(kw="{kw}")')
        elif name == "stop":
            parts.append(f"{icon} stop")
        else:
            parts.append(f"{icon} {name}")
    return " | ".join(parts)


# ─────────────────────────────────────────────────────────────────
# Main message handler
# ─────────────────────────────────────────────────────────────────

@cl.on_message
async def on_message(message: cl.Message):
    rn = get_rn_module()
    user_input = message.content
    history = cl.user_session.get("messages", [])
    thread_id = cl.user_session.get("thread_id")
    config = {"configurable": {"thread_id": thread_id}}

    # Add user message to history
    history.append({"role": "user", "content": user_input})

    # Check if resuming from HITL interrupt
    snapshot = rn.app.get_state(config)
    has_interrupt = snapshot.tasks and snapshot.tasks[0].interrupts

    if has_interrupt:
        run_input = Command(resume=user_input)
    else:
        mode = await classify_intent(user_input, history)
        run_input = {"messages": [HumanMessage(content=user_input)], "mode": mode}

    # State tracking for this run
    step_count = 0
    answer_text = ""
    screenshots = []

    # Track active steps per node
    active_steps: dict[str, cl.Step] = {}

    async for event in rn.app.astream(run_input, config, stream_mode="updates"):
        for node, data in event.items():
            msgs = data.get("messages", []) if isinstance(data, dict) else []

            if node in ("nav_agent", "research_agent"):
                for m in msgs:
                    tc = getattr(m, "tool_calls", []) or []
                    content = getattr(m, "content", "") or ""

                    if tc:
                        step_count += 1

                        # End any existing step
                        for step in active_steps.values():
                            await step.update()

                        # Start new step
                        summary = make_tool_summary(tc)
                        step = cl.Step(
                            name=f"Step {step_count}",
                            type="tool",
                            output=summary,
                        )
                        await step.send()
                        active_steps[node] = step

                    elif (
                        isinstance(content, str)
                        and content.strip()
                        and len(content) > 80
                        and not tc
                    ):
                        answer_text = content

            elif node in ("nav_tools", "research_tools"):
                for m in msgs:
                    name = getattr(m, "name", "tool")
                    content = getattr(m, "content", "") or ""
                    short = content[:150] + "..." if isinstance(content, str) and len(content) > 150 else content

                    # End any existing step for this node
                    if node in active_steps:
                        await active_steps[node].update()
                        del active_steps[node]

                    # Check for screenshot in content
                    screenshot_path = None
                    if isinstance(content, str):
                        sp_match = re.search(r'"screenshot_path"\s*:\s*"([^"]+)"', content)
                        if sp_match:
                            screenshot_path = sp_match.group(1)
                        else:
                            sp_match = re.search(r"(logs[/\\][\w]+\.(?:png|jpg|jpeg))", content)
                            if sp_match:
                                screenshot_path = sp_match.group(1)

                    if screenshot_path:
                        if not os.path.isabs(screenshot_path):
                            screenshot_path = os.path.join(os.path.dirname(__file__), screenshot_path)
                        screenshots.append(screenshot_path)

                        if os.path.exists(screenshot_path):
                            await cl.Image(
                                path=screenshot_path,
                                name=f"Screenshot {len(screenshots)}",
                                display="inline",
                            ).send()

                    # Capture stop tool answer
                    if name == "stop" and isinstance(content, str):
                        try:
                            d = json.loads(content)
                            stop_ans = d.get("answer", "")
                        except (json.JSONDecodeError, TypeError):
                            stop_ans = content
                        if stop_ans and len(stop_ans) > 30:
                            answer_text = stop_ans

    # Finalize any remaining steps
    for step in active_steps.values():
        await step.update()

    # Check if graph hit an interrupt (needs human input)
    snapshot = rn.app.get_state(config)
    if snapshot.tasks and snapshot.tasks[0].interrupts:
        interrupt_value = snapshot.tasks[0].interrupts[0].value

        # Get agent's last message
        last_agent_msg = ""
        state_messages = snapshot.values.get("messages", [])
        for msg in reversed(state_messages):
            msg_content = getattr(msg, "content", "") or ""
            if isinstance(msg_content, str) and msg_content.strip():
                last_agent_msg = msg_content[:500]
                break

        hitl_reason = await classify_hitl(interrupt_value, last_agent_msg, answer_text)

        if hitl_reason:
            # Use AskUserMessage to get user input — this suspends until user responds
            user_response = await cl.AskUserMessage(
                content=hitl_reason,
                timeout=600,
            ).send()

            # Resume with user's response
            resume_input = Command(resume=user_response)
            step_count = 0
            answer_text = ""
            screenshots = []
            active_steps.clear()

            async for event in rn.app.astream(resume_input, config, stream_mode="updates"):
                for node, data in event.items():
                    msgs = data.get("messages", []) if isinstance(data, dict) else []

                    if node in ("nav_agent", "research_agent"):
                        for m in msgs:
                            tc = getattr(m, "tool_calls", []) or []
                            content = getattr(m, "content", "") or ""

                            if tc:
                                step_count += 1
                                for step in active_steps.values():
                                    await step.update()

                                summary = make_tool_summary(tc)
                                step = cl.Step(name=f"Step {step_count}", type="tool", output=summary)
                                await step.send()
                                active_steps[node] = step

                            elif isinstance(content, str) and content.strip() and len(content) > 80 and not tc:
                                answer_text = content

                    elif node in ("nav_tools", "research_tools"):
                        for m in msgs:
                            name = getattr(m, "name", "tool")
                            content = getattr(m, "content", "") or ""

                            if node in active_steps:
                                await active_steps[node].update()
                                del active_steps[node]

                            screenshot_path = None
                            if isinstance(content, str):
                                sp_match = re.search(r'"screenshot_path"\s*:\s*"([^"]+)"', content)
                                if sp_match:
                                    screenshot_path = sp_match.group(1)
                                else:
                                    sp_match = re.search(r"(logs[/\\][\w]+\.(?:png|jpg|jpeg))", content)
                                    if sp_match:
                                        screenshot_path = sp_match.group(1)

                            if screenshot_path:
                                if not os.path.isabs(screenshot_path):
                                    screenshot_path = os.path.join(os.path.dirname(__file__), screenshot_path)
                                screenshots.append(screenshot_path)
                                if os.path.exists(screenshot_path):
                                    await cl.Image(path=screenshot_path, name=f"Screenshot {len(screenshots)}", display="inline").send()

                            if name == "stop" and isinstance(content, str):
                                try:
                                    d = json.loads(content)
                                    stop_ans = d.get("answer", "")
                                except (json.JSONDecodeError, TypeError):
                                    stop_ans = content
                                if stop_ans and len(stop_ans) > 30:
                                    answer_text = stop_ans

            for step in active_steps.values():
                await step.update()

    # Save to history and send final answer
    history.append({"role": "assistant", "content": answer_text or "(no answer)"})
    cl.user_session.set("messages", history)

    if answer_text:
        await cl.Message(content=answer_text, author="Agent").send()
    else:
        await cl.Message(content="_(no answer returned)_", author="Agent").send()
