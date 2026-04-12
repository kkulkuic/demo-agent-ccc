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
import time
import logging

# ─── Detailed Logging Setup ───
LOG_FILE = os.path.join(os.path.dirname(__file__), "logs", "chainlit_app.log")
os.makedirs(os.path.join(os.path.dirname(__file__), "logs"), exist_ok=True)

logger = logging.getLogger("chainlit_app")
logger.setLevel(logging.DEBUG)
# File handler — detailed
fh = logging.FileHandler(LOG_FILE, mode="a")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(fh)

# Python 3.14 compat: websockets uses asyncio_timeout incorrectly
try:
    import asyncio_timeout
except ImportError:
    asyncio_timeout = None
if asyncio_timeout is not None and not hasattr(asyncio_timeout, 'timeout'):
    asyncio_timeout.timeout = asyncio.timeout

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

@cl.set_starters
async def set_starters():
    return [
        cl.Starter("🔍 Search trails", "Search for the best hiking trails near me", ""),
        cl.Starter("🗺 Navigate", "Navigate to the nearest coffee shop", ""),
        cl.Starter("💰 Compare prices", "Compare iPhone 15 prices across retailers", ""),
        cl.Starter("📄 Research", "Research climate change effects on agriculture", ""),
    ]


@cl.on_chat_start
async def on_chat_start():
    session_id = str(uuid.uuid4())[:8]
    thread_id = f"chainlit-{session_id}"
    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("messages", [])
    cl.user_session.set("stop_flag", False)
    cl.user_session.set("current_mode", "research")
    logger.info("=" * 60)
    logger.info(f"NEW SESSION | thread={thread_id}")
    logger.info("=" * 60)

    await cl.Message(
        content=(
            "# 🌐 Hybrid Agent — Research & Navigate\n\n"
            "I can **research** (web search, scrape, price compare) or **navigate** (live browser interaction, maps, directions).\n\n"
            "Try one of the examples below or ask me anything!"
        ),
        author="Agent",
    ).send()


# ─────────────────────────────────────────────────────────────────
# Tool icons
# ─────────────────────────────────────────────────────────────────

TOOL_ICONS = {
    "browser_navigate": "🌐",
    "open_url_headed": "🌐",
    "browser_click": "🖱️",
    "click_on_page": "🖱️",
    "browser_fill": "⌨️",
    "type_text_on_page": "⌨️",
    "browser_type": "⌨️",
    "browser_key_press": "⌨️",
    "maps_reviews": "⭐",
    "places_search": "📍",
    "place_details": "📋",
    "web_search": "📡",
    "deep_scrape": "📄",
    "compare_prices": "💰",
    "browser_inspect": "📸",
    "stop": "⏹️",
    "get_directions": "🧭",
    "search": "🔎",
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
    try:
        logger.info("=" * 60)
        logger.info(f"ON_MESSAGE TRIGGERED | content={message.content[:200]}")
    except Exception as e:
        logger.error(f"LOG ERROR: {e}")

    try:
        rn = get_rn_module()
    except Exception as e:
        logger.error(f"get_rn_module FAILED: {e}")
        await cl.Message(content=f"Error loading agent: {e}", author="System").send()
        return

    user_input = message.content
    history = cl.user_session.get("messages", [])
    thread_id = cl.user_session.get("thread_id")
    config = {"configurable": {"thread_id": thread_id}}

    logger.info("-" * 60)
    logger.info(f"USER INPUT | thread={thread_id} | input={user_input[:200]}")

    # Reset stop flag for new run
    cl.user_session.set("stop_flag", False)

    # Add user message to history
    history.append({"role": "user", "content": user_input})

    # Check if resuming from HITL interrupt
    snapshot = rn.app.get_state(config)
    has_interrupt = snapshot.tasks and snapshot.tasks[0].interrupts

    start_time = time.time()
    mode = "research"
    current_reasoning = ""

    if has_interrupt:
        interrupt_val = snapshot.tasks[0].interrupts[0].value
        interrupt_str = str(interrupt_val)[:200]
        logger.info(f"HITL RESUME | interrupt={interrupt_str}")
        
        # Generic "What would you like to do?" interrupt is for CLI mode
        # In Chainlit UI, treat it as a new task instead of resuming
        if "What would you like to do?" in interrupt_str:
            logger.info("GENERIC INTERRUPT — treating as new task")
            mode = await classify_intent(user_input, history)
            cl.user_session.set("current_mode", mode)
            logger.info(f"INTENT | mode={mode}")
            run_input = {"messages": [HumanMessage(content=user_input)], "mode": mode}
        else:
            # Real HITL interrupt (CAPTCHA, ambiguous choice, etc.)
            await cl.Message(
                content="🔔 **Agent paused — need your input to continue**\n\nThe agent encountered a step requiring human feedback. Please provide your response below.",
                author="System",
            ).send()
            run_input = Command(resume=user_input)
    else:
        mode = await classify_intent(user_input, history)
        cl.user_session.set("current_mode", mode)
        logger.info(f"INTENT | mode={mode}")
        run_input = {"messages": [HumanMessage(content=user_input)], "mode": mode}

    # State tracking for this run
    step_count = 0
    answer_text = ""
    screenshots = []

    # Track active steps per node
    active_steps: dict[str, cl.Step] = {}

    # Helper to create enhanced step
    async def create_enhanced_step(step_num, reasoning, tool_calls, node):
        nonlocal current_reasoning
        summary = make_tool_summary(tool_calls)

        # Create step with reasoning as description
        step = cl.Step(
            name=f"Step {step_num}",
            type="tool",
        )
        step.output = summary
        # Show reasoning in description if available
        if reasoning and len(reasoning) > 10:
            step.description = f"💭 {reasoning[:200]}{'...' if len(reasoning) > 200 else ''}"
        await step.send()
        active_steps[node] = step
        return step

    # Helper to update step with tool result preview
    async def update_step_with_result(step, tool_result):
        if tool_result and isinstance(tool_result, str):
            preview = tool_result[:150] + "..." if len(tool_result) > 150 else tool_result
            step.output = f"{step.output}\n\n📋 Result: {preview}"
            await step.update()

    async for event in rn.app.astream(run_input, config, stream_mode="updates"):
        # Check stop flag
        if cl.user_session.get("stop_flag", False):
            await cl.Message(content="⏹️ **Run stopped by user**", author="System").send()
            break

        for node, data in event.items():
            msgs = data.get("messages", []) if isinstance(data, dict) else []

            if node in ("nav_agent", "research_agent"):
                for m in msgs:
                    tc = getattr(m, "tool_calls", []) or []
                    content = getattr(m, "content", "") or ""

                    # Capture reasoning (AIMessage content before tool_calls)
                    if isinstance(content, str) and content.strip() and not tc:
                        if len(content) > 10:
                            current_reasoning = content
                            logger.info(f"REASONING | node={node} | {content[:300]}")

                    if tc:
                        step_count += 1

                        # End any existing step
                        for step in active_steps.values():
                            await step.update()

                        # Log tool calls
                        for t in tc:
                            logger.info(f"TOOL_CALL | step={step_count} | {t.get('name','?')} | args={json.dumps(t.get('args',{}), ensure_ascii=False)[:200]}")
                        # Create new enhanced step
                        await create_enhanced_step(step_count, current_reasoning, tc, node)
                        current_reasoning = ""

                    elif (
                        isinstance(content, str)
                        and content.strip()
                        and len(content) > 80
                        and not tc
                    ):
                        answer_text = content
                        logger.info(f"ANSWER | node={node} | {len(content)} chars | {content[:200]}")

            elif node in ("nav_tools", "research_tools"):
                for m in msgs:
                    name = getattr(m, "name", "tool")
                    content = getattr(m, "content", "") or ""

                    # Update step with tool result preview before ending
                    if node in active_steps and content:
                        await update_step_with_result(active_steps[node], content)
                        logger.info(f"TOOL_RESULT | {name} | {str(content)[:300]}")

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
                            # Send screenshot as a message with image element
                            msg = cl.Message(content=f"📸 Screenshot {len(screenshots)}", author="Agent")
                            msg.elements = [cl.Image(path=screenshot_path, name=f"Screenshot {len(screenshots)}", display="inline")]
                            await msg.send()

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
    # Skip generic "What would you like to do?" interrupt if we already have an answer
    snapshot = rn.app.get_state(config)
    if snapshot.tasks and snapshot.tasks[0].interrupts and not answer_text:
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
            # Show HITL context message
            await cl.Message(
                content=f"🤔 **Agent needs your help:**\n\n{hitl_reason}",
                author="System",
            ).send()

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
            current_reasoning = ""

            async for event in rn.app.astream(resume_input, config, stream_mode="updates"):
                # Check stop flag
                if cl.user_session.get("stop_flag", False):
                    await cl.Message(content="⏹️ **Run stopped by user**", author="System").send()
                    break

                for node, data in event.items():
                    msgs = data.get("messages", []) if isinstance(data, dict) else []

                    if node in ("nav_agent", "research_agent"):
                        for m in msgs:
                            tc = getattr(m, "tool_calls", []) or []
                            content = getattr(m, "content", "") or ""

                            if isinstance(content, str) and content.strip() and not tc:
                                if len(content) > 10:
                                    current_reasoning = content

                            if tc:
                                step_count += 1
                                for step in active_steps.values():
                                    await step.update()

                                await create_enhanced_step(step_count, current_reasoning, tc, node)
                                current_reasoning = ""

                            elif isinstance(content, str) and content.strip() and len(content) > 80 and not tc:
                                answer_text = content

                    elif node in ("nav_tools", "research_tools"):
                        for m in msgs:
                            name = getattr(m, "name", "tool")
                            content = getattr(m, "content", "") or ""

                            if node in active_steps and content:
                                await update_step_with_result(active_steps[node], content)

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
                                    msg = cl.Message(content=f"📸 Screenshot {len(screenshots)}", author="Agent")
                                    msg.elements = [cl.Image(path=screenshot_path, name=f"Screenshot {len(screenshots)}", display="inline")]
                                    await msg.send()

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

    # Calculate duration
    duration = time.time() - start_time
    logger.info(f"DEBUG before complete | answer_text={repr(answer_text[:100]) if answer_text else 'EMPTY'}")
    logger.info(f"RUN COMPLETE | steps={step_count} | answer={len(answer_text)} chars | duration={duration:.1f}s | mode={mode} | screenshots={len(screenshots)}")

    # Save to history and send final answer
    history.append({"role": "assistant", "content": answer_text or "(no answer)"})
    cl.user_session.set("messages", history)

    # Send answer with stop button
    if answer_text:
        answer_msg = cl.Message(content=answer_text, author="Agent")
        await answer_msg.send()
    else:
        answer_msg = cl.Message(content="_(no answer returned)_", author="Agent")
        await answer_msg.send()

    # Show metrics summary
    mode_display = cl.user_session.get("current_mode", mode)
    metrics_content = (
        f"📊 **Run Summary**\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Steps | {step_count} |\n"
        f"| Answer length | {len(answer_text)} chars |\n"
        f"| Duration | {duration:.1f}s |\n"
        f"| Mode | {mode_display} |\n"
        f"| Screenshots | {len(screenshots)} |"
    )
    await cl.Message(content=metrics_content, author="System").send()

    # Stop button attached to the answer message
    answer_msg = cl.Message(content="", author="Agent")
    await answer_msg.send()
    cl.user_session.set("answer_msg_id", answer_msg.id)

    # Add stop action to the answer message
    stop_action = cl.Action(name="stop_run", label="⏹️ Stop", payload={"value": "stop"})
    await stop_action.send(for_id=answer_msg.id)
    cl.user_session.set("stop_action_id", stop_action.id)


@cl.action_callback("stop_run")
async def on_stop_run(action: cl.Action):
    """Handle stop button click to cancel current run."""
    cl.user_session.set("stop_flag", True)
    await cl.Message(content="⏹️ **Stop requested...**", author="System").send()
