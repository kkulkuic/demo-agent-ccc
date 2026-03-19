import os
import asyncio
import time
import re
from typing import Annotated, TypedDict, Union
from dotenv import load_dotenv

from serpapi import GoogleSearch
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import ToolMessage, BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

from playwright.async_api import async_playwright

# Load keys from .env
load_dotenv()

# --- 1. STATE DEFINITION ---
class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

# --- 2. BROWSER & TOOLS ---
browser_session = {"playwright": None, "browser": None, "page": None}

async def get_session():
    if browser_session["page"] is None:
        browser_session["playwright"] = await async_playwright().start()
        browser_session["browser"] = await browser_session["playwright"].chromium.launch(headless=True)
        context = await browser_session["browser"].new_context(viewport={'width': 1280, 'height': 720})
        browser_session["page"] = await context.new_page()
    return browser_session["page"]

@tool
async def search_google_serpapi(query: str):
    """Search Google via SerpApi for clean, structured results."""
    params = {"q": query, "api_key": os.getenv("SERPAPI_API_KEY"), "num": 5}
    search = await asyncio.to_thread(GoogleSearch(params).get_dict)
    organic = search.get("organic_results", [])
    return [{"title": r.get("title"), "link": r.get("link")} for r in organic] if organic else "No results."

@tool
async def navigate_to_url(url: str):
    """Navigates to a URL and extracts content."""
    page = await get_session()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        content = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
        return f"Content from {url}:\n\n{content}"
    except Exception as e:
        return f"Error: {str(e)}"

tools = [search_google_serpapi, navigate_to_url]
tool_node = ToolNode(tools)

# --- 3. LLM INITIALIZATION ---
# Agent (The Doer)
llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0
).bind_tools(tools)

# Verifier (The Critic)
verifier_llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0
)

# --- 4. NODES ---

async def agent_node(state: State):
    """Agent Node: Processes query and handles critiques."""
    # Filter out internal audit messages so agent doesn't hallucinate them into summary
    clean_messages = [m for m in state["messages"] if "--- VERIFICATION REPORT ---" not in str(m.content)]
    
    # Check if the most recent message was a FAIL report
    last_msg = state["messages"][-1]
    if "--- VERIFICATION REPORT ---" in str(last_msg.content):
        instruction = HumanMessage(content=(
            f"The auditor found issues: {last_msg.content}. "
            "Please fix these by searching more deeply or extracting missing data."
        ))
        clean_messages.append(instruction)
    
    response = await llm.ainvoke(clean_messages)
    return {"messages": [response]}

async def verifier_node(state: State):
    """Verifier Node: Audits the agent's work."""
    user_query = state["messages"][0].content
    
    # Get last actual agent summary
    last_ai_msg = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls and "--- VERIFICATION REPORT ---" not in str(msg.content):
            last_ai_msg = str(msg.content)
            break
            
    tool_results = [str(m.content) for m in state["messages"] if isinstance(m, ToolMessage)]
    
    prompt = f"""
    Audit this AI response for User Intent: "{user_query}"
    
    RAW DATA FOUND: {tool_results}
    AGENT SUMMARY: {last_ai_msg}

    Format exactly:
    --- VERIFICATION REPORT ---
    ### 📊 Audit Summary
    - **Relevancy Score:** [X/5]
    - **GROUNDEDNESS:** [YES/NO]
    - **Status:** [PASS/FAIL] - (FAIL if score < 4 or Groundedness is NO)

    ### 🔍 Issues Found
    - [List issues or 'None']
    """
    report = await verifier_llm.ainvoke([HumanMessage(content=prompt)])
    return {"messages": [AIMessage(content=report.content)]}

def human_input_node(state: State):
    user_input = interrupt("Report ready. Enter next command:")
    return {"messages": [HumanMessage(content=user_input)]}

# --- 5. MULTI-AGENT ROUTING ---

def route_after_agent(state: State):
    last_msg = state["messages"][-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "tools"
    return "verify"

def route_after_verify(state: State):
    last_report = state["messages"][-1].content
    
    # Regex to find the most recent score
    match = re.search(r"Relevancy Score:\s*\[?(\d)", last_report, re.IGNORECASE)
    score = int(match.group(1)) if match else 5
    
    verify_attempts = sum(1 for m in state["messages"] if "--- VERIFICATION REPORT ---" in str(m.content))
    
    if score < 4 and verify_attempts < 3:
        print(f"🔄 [QA FAIL - Score {score}/5] Retrying...")
        return "agent"
    
    print(f"✅ [QA DONE - Score {score}/5] Passing to User.")
    return "human_input"

# --- 6. GRAPH CONSTRUCTION ---
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

# --- 7. MAIN LOOP ---
async def main():
    config = {"configurable": {"thread_id": "multi-agent-final"}}
    print("\n" + "═"*50 + "\n 🚀 MULTI-AGENT INTERFACE ACTIVE \n" + "═"*50)
    
    prompt = input("\n[Prompt]: ")
    start_time = time.perf_counter()
    async for _ in app.astream({"messages": [HumanMessage(content=prompt)]}, config):
        pass
    latency = time.perf_counter() - start_time

    while True:
        state = await app.aget_state(config)
        messages = state.values["messages"]
        
        agent_summary = ""
        verification_report = ""
        total_tokens = 0
        
        # --- ROBUST EXTRACTION ---
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

        # STEP 1: AGENT OUTPUT
        print("\n🟢" + "─"*48)
        print(f" STEP 1: AGENT SUMMARY")
        print(f" [Latency: {latency:.2f}s | Tokens: {total_tokens}]")
        print("─"*50)
        print(agent_summary if agent_summary else "No summary available.")
        
        # STEP 2: VERIFICATION REPORT
        print("\n🛡️" + "─"*48)
        print(f" STEP 2: QUALITY ASSURANCE AUDIT")
        print("─"*50)
        print(verification_report if verification_report else "Audit pending.")
        
        # STEP 3: USER INPUT
        print("\n💡" + "─"*48)
        print(f" STEP 3: NEXT ACTION")
        print("─"*50)
        
        user_cmd = input("\n[Next Command]: ")
        if user_cmd.lower() in ['exit', 'quit']: break
        
        start_time = time.perf_counter()
        async for _ in app.astream(Command(resume=user_cmd), config):
            pass
        latency = time.perf_counter() - start_time

    if browser_session["browser"]:
        await browser_session["browser"].close()
        await browser_session["playwright"].stop()

if __name__ == "__main__":
    asyncio.run(main())