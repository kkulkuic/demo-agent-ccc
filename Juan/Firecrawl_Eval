import os
import asyncio
import time
import re
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from firecrawl import FirecrawlApp

# Load environment variables FIRST
load_dotenv()

# --- TRULENS IMPORTS ---
from trulens.core import TruSession, Metric
from trulens.apps.langchain import TruChain
from trulens.providers.litellm import LiteLLM

# --- LANGCHAIN & LANGGRAPH IMPORTS ---
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import ToolMessage, BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

import warnings
import logging

# Filter noisy warnings/logging
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.main")
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message="Failed to process and remove trivial statements")


# -------------------------------------------------------------------
# 1. STATE DEFINITION
# -------------------------------------------------------------------
class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# -------------------------------------------------------------------
# 2. FIRECRAWL CLIENT + HELPERS
# -------------------------------------------------------------------
firecrawl = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))


def is_pdf_url(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    return lower.endswith(".pdf") or ".pdf?" in lower


def get_latest_user_query(messages) -> str:
    """
    Use the latest meaningful human message for verification.
    Prevents 'exit' or stale follow-up commands from contaminating the audit.
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            text = str(msg.content).strip()
            if text.lower() not in {"exit", "quit"}:
                return text
    return str(messages[0].content) if messages else ""


# -------------------------------------------------------------------
# 3. TOOLS
# -------------------------------------------------------------------
@tool
async def search_firecrawl(query: str):
    """Search the web with Firecrawl and return non-PDF results."""
    try:
        result = await asyncio.to_thread(
            firecrawl.search,
            query=query,
            limit=5,
        )

        print("\n[DEBUG raw Firecrawl search result]")
        print(result)
        print("[END DEBUG]\n")

        # Handle different SDK response shapes
        if hasattr(result, "web") and result.web:
            data = result.web
        elif isinstance(result, dict):
            data = result.get("web", []) or result.get("data", []) or result.get("results", [])
        else:
            data = []

        cleaned = []

        for r in data:
            if hasattr(r, "url"):
                url = r.url
                title = getattr(r, "title", "")
                description = getattr(r, "description", "")
            elif isinstance(r, dict):
                url = r.get("url") or r.get("link") or r.get("source_url")
                title = r.get("title", "")
                description = r.get("description") or r.get("snippet") or ""
            else:
                continue

            if not url or is_pdf_url(url):
                continue

            cleaned.append({
                "title": title,
                "url": url,
                "description": description,
            })

        return cleaned if cleaned else "No non-PDF results found."

    except Exception as e:
        return f"Error during Firecrawl search: {str(e)}"


@tool
async def scrape_firecrawl(url: str):
    """Scrape a single non-PDF URL with Firecrawl."""
    if is_pdf_url(url):
        return f"Skipped PDF URL: {url}"

    try:
        try:
            result = await asyncio.to_thread(
                firecrawl.scrape_url,
                url=url,
                formats=["markdown"],
            )
        except TypeError:
            result = await asyncio.to_thread(
                firecrawl.scrape_url,
                url,
            )

        print("\n[DEBUG raw Firecrawl scrape result]")
        print(result)
        print("[END DEBUG]\n")

        markdown = ""

        if isinstance(result, dict):
            markdown = result.get("markdown", "") or result.get("content", "") or ""
        else:
            markdown = getattr(result, "markdown", "") or getattr(result, "content", "") or ""

        markdown = markdown[:4000] if markdown else ""
        return f"Content from {url}:\n\n{markdown}" if markdown else f"No content extracted from {url}"

    except Exception as e:
        return f"Error during Firecrawl scrape: {str(e)}"


tools = [search_firecrawl, scrape_firecrawl]
tool_node = ToolNode(tools)


# -------------------------------------------------------------------
# 4. LLM INITIALIZATION
# -------------------------------------------------------------------
llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0
).bind_tools(tools)

verifier_llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0
)


# -------------------------------------------------------------------
# 5. NODES
# -------------------------------------------------------------------
async def agent_node(state: State):
    """
    Main agent.
    Filters out verification reports so they do not pollute reasoning.
    If the previous audit found issues, pushes the agent to correct them.
    """
    clean_messages = [
        m for m in state["messages"]
        if "--- VERIFICATION REPORT ---" not in str(m.content)
    ]

    last_msg = state["messages"][-1]
    if "--- VERIFICATION REPORT ---" in str(last_msg.content):
        instruction = HumanMessage(content=(
            f"The auditor found issues: {last_msg.content}. "
            "Please fix them by searching more carefully or scraping better sources. "
            "Only include details supported by the retrieved data. "
            "If something is not available in the retrieved context, say so clearly."
        ))
        clean_messages.append(instruction)

    response = await llm.ainvoke(clean_messages)
    return {"messages": [response]}


async def verifier_node(state: State):
    """
    QA auditor for:
    - answer relevancy
    - groundedness
    - context precision

    Context precision here means:
    Of the retrieved tool results, how much of the context was actually useful
    for answering the user's request?
    """
    user_query = get_latest_user_query(state["messages"])

    last_ai_msg = ""
    for msg in reversed(state["messages"]):
        if (
            isinstance(msg, AIMessage)
            and not msg.tool_calls
            and "--- VERIFICATION REPORT ---" not in str(msg.content)
        ):
            last_ai_msg = str(msg.content)
            break

    tool_results = [str(m.content) for m in state["messages"] if isinstance(m, ToolMessage)]

    prompt = f"""
Audit this AI response for User Intent: "{user_query}"

RAW DATA FOUND:
{tool_results}

AGENT SUMMARY:
{last_ai_msg}

Evaluate the response on these dimensions:

1. Relevancy Score (1-5)
- 5/5 = fully answers the current user request with the available evidence

2. Groundedness
- YES = claims are supported by retrieved tool data
- NO = answer invents facts or materially overstates what was retrieved

3. Context Precision
This means: how much of the retrieved context was actually useful and relevant for answering the question?
- HIGH = most retrieved context was relevant/useful
- MEDIUM = some relevant, some noisy or unnecessary
- LOW = much of the retrieved context was irrelevant or distracting

4. Status
- FAIL if Relevancy Score < 4 or Groundedness is NO
- Otherwise PASS

Format exactly:

--- VERIFICATION REPORT ---
### 📊 Audit Summary
- **Relevancy Score:** [X/5]
- **GROUNDEDNESS:** [YES/NO]
- **Context Precision:** [HIGH/MEDIUM/LOW]
- **Status:** [PASS/FAIL]

### 🔍 Issues Found
- [List issues or 'None']

### 📝 Detailed Analysis
[Brief explanation of why the context precision rating was assigned]
"""

    report = await verifier_llm.ainvoke([HumanMessage(content=prompt)])
    return {"messages": [AIMessage(content=report.content)]}


def human_input_node(state: State):
    """HITL pause for next command."""
    user_input = interrupt("Agent logic complete. Enter next command:")
    return {"messages": [HumanMessage(content=user_input)]}


# -------------------------------------------------------------------
# 6. ROUTING LOGIC
# -------------------------------------------------------------------
def route_after_agent(state: State):
    last_msg = state["messages"][-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "tools"
    return "verify"


def route_after_verify(state: State):
    last_report = state["messages"][-1].content

    match = re.search(r"Relevancy Score:\s*\[?(\d)", last_report, re.IGNORECASE)
    score = int(match.group(1)) if match else 5

    grounded_match = re.search(r"GROUNDEDNESS:\s*\[?(YES|NO)", last_report, re.IGNORECASE)
    grounded = grounded_match.group(1).upper() if grounded_match else "YES"

    verify_attempts = sum(
        1 for m in state["messages"]
        if "--- VERIFICATION REPORT ---" in str(m.content)
    )

    if (score < 4 or grounded == "NO") and verify_attempts < 3:
        print(f"🔄 [QA FAIL - Score {score}/5 | Groundedness {grounded}] Retrying...")
        return "agent"

    print(f"✅ [QA DONE - Score {score}/5 | Groundedness {grounded}] Passing to User.")
    return "human_input"


# -------------------------------------------------------------------
# 7. GRAPH CONSTRUCTION
# -------------------------------------------------------------------
workflow = StateGraph(State)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)
workflow.add_node("verify", verifier_node)
workflow.add_node("human_input", human_input_node)

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", route_after_agent)
workflow.add_edge("tools", "agent")
workflow.add_conditional_edges("verify", route_after_verify)
workflow.add_edge("human_input", "agent")

app = workflow.compile(checkpointer=InMemorySaver())


# -------------------------------------------------------------------
# 8. TRULENS EVALUATION SETUP
# -------------------------------------------------------------------
tru = TruSession()
feedback_provider = LiteLLM(model_engine="claude-haiku-4-5-20251001")

# These stay generic and stable
f_relevance = Metric(feedback_provider.relevance).on_input_output()
f_groundedness = Metric(
    feedback_provider.groundedness_measure_with_cot_reasons
).on_input_output()

tru_recorder = TruChain(
    app,
    app_id="Capstone_Firecrawl_TruEval_Agent",
    feedbacks=[f_groundedness, f_relevance]
)


# -------------------------------------------------------------------
# 9. MAIN EXECUTION LOOP
# -------------------------------------------------------------------
async def main():
    config = {"configurable": {"thread_id": "capstone-firecrawl-tru-agent"}}

    print("\n" + "═" * 50)
    print(" 🚀 MULTI-AGENT FIRECRAWL + TRULENS SYSTEM ACTIVE")
    print("═" * 50)

    initial_prompt = input("\n[Prompt]: ").strip()
    if not initial_prompt:
        print("No prompt entered.")
        return

    start_time = time.perf_counter()
    with tru_recorder as recording:
        async for _ in app.astream({"messages": [HumanMessage(content=initial_prompt)]}, config):
            pass
    latency = time.perf_counter() - start_time

    while True:
        state = await app.aget_state(config)
        messages = state.values["messages"]

        agent_summary = ""
        verification_report = ""
        total_tokens = 0

        for msg in reversed(messages):
            if "--- VERIFICATION REPORT ---" in str(msg.content):
                if not verification_report:
                    verification_report = str(msg.content).replace("--- VERIFICATION REPORT ---", "").strip()
            elif isinstance(msg, AIMessage) and not msg.tool_calls and "--- VERIFICATION REPORT ---" not in str(msg.content):
                if not agent_summary:
                    agent_summary = str(msg.content)

        for msg in messages:
            if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                total_tokens += msg.usage_metadata.get("total_tokens", 0)

        print("\n🟢" + "─" * 48)
        print(" STEP 1: AGENT SUMMARY")
        print(f" [Latency: {latency:.2f}s | Session Tokens: {total_tokens}]")
        print("─" * 50)
        print(agent_summary if agent_summary else "Collecting data...")

        print("\n🛡️" + "─" * 48)
        print(" STEP 2: QUALITY ASSURANCE AUDIT (TRULENS INTEGRATED)")
        print("─" * 50)
        print(verification_report if verification_report else "Audit in progress.")

        print("\n💡" + "─" * 48)
        print(" STEP 3: NEXT ACTION")
        print("─" * 50)

        user_cmd = input("\n[Next Command/Exit]: ").strip()
        if user_cmd.lower() in ["exit", "quit"]:
            break

        start_time = time.perf_counter()
        with tru_recorder as recording:
            async for _ in app.astream(Command(resume=user_cmd), config):
                pass
        latency = time.perf_counter() - start_time

    print("\nSession ended. To view TruLens Dashboard, run: trulens-eval browse")


if __name__ == "__main__":
    asyncio.run(main())
