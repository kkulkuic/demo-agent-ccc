"""Terminal HITL demo: LangGraph with human_input node and interrupt; headless tools."""
import os
from typing import Annotated, TypedDict
from langchain_core.messages import ToolMessage

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from playwright.sync_api import sync_playwright
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

# --- 1. STATE DEFINITION ---
class State(TypedDict):
    messages: Annotated[list, add_messages]

# --- 2. TOOL DEFINITIONS ---
@tool
def get_web_page_info(url: str):
    """
    Visits a URL using a headless browser and returns the page title
    and a short description or text snippet.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        try:
            page.goto(url, timeout=60000)
            title = page.title()
            description = page.locator('meta[name="description"]').get_attribute("content")
            if not description:
                description = page.evaluate("""() => {
                    const header = document.querySelector('h1')?.innerText || document.querySelector('h2')?.innerText;
                    return header ? 'Headline: ' + header : document.body.innerText.slice(0, 300);
                }""")
            return {
                "url": url,
                "title": title,
                "description": description.strip() if description else "No description found."
            }
        except Exception as e:
            return {"error": f"Failed to load page: {str(e)}"}
        finally:
            browser.close()

@tool
def click_element(url: str, selector: str):
    """Navigates to a URL and clicks a specific button using its CSS selector."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url)
            page.click(selector)
            new_url = page.url
            return f"Successfully clicked {selector}. Current URL is now: {new_url}"
        except Exception as e:
            return f"Error clicking element: {str(e)}"
        finally:
            browser.close()

@tool
def ask_human_for_help(reason: str):
    """
    Call this tool when you need more information from the user,
    when you are stuck, or when you need confirmation to proceed.
    """
    return f"Requesting help because: {reason}"

# --- 3. GRAPH NODES & LOGIC ---
tools = [get_web_page_info, click_element, ask_human_for_help]
tool_node = ToolNode(tools)

llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    api_key=os.getenv("API-KEY") or os.getenv("ANTHROPIC_API_KEY"),
    temperature=0,
).bind_tools(tools)

def chatbot(state: State):
    return {"messages": [llm.invoke(state["messages"])]}

def human_review_node(state: State):
    print("\n--- ⏸️ AGENT READY: WAITING FOR YOUR COMMAND ---")
    if state["messages"]:
        last_message = state["messages"][-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            tool_call_id = last_message.tool_calls[0]["id"]
            user_input = interrupt("Agent needs help. Type your response:")
            return {"messages": [ToolMessage(tool_call_id=tool_call_id, content=user_input)]}
    user_input = interrupt("What website should I visit? (or type 'exit')")
    return {"messages": [("user", user_input)]}

# --- 4. GRAPH CONSTRUCTION ---
workflow = StateGraph(State)
workflow.add_node("agent", chatbot)
workflow.add_node("tools", tool_node)
workflow.add_node("human_input", human_review_node)
workflow.set_entry_point("human_input")

def route_after_agent(state: State):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            if tool_call["name"] == "ask_human_for_help":
                return "human_input"
        return "tools"
    return "human_input"

workflow.add_conditional_edges("agent", route_after_agent)
workflow.add_edge("human_input", "agent")
workflow.add_edge("tools", "agent")

memory = InMemorySaver()
app = workflow.compile(checkpointer=memory)

# --- 5. EXECUTION ---
if __name__ == "__main__":
    print("--- Starting Demo Agent (HITL Mode) ---")
    run_config = {"configurable": {"thread_id": "capstone-session-v4"}}

    def run_graph(input_data):
        last_msg = None
        for chunk in app.stream(input_data, run_config, stream_mode="updates"):
            for node_name, data in chunk.items():
                if "messages" in data:
                    new_msg = data["messages"][-1]
                    if hasattr(new_msg, 'tool_calls') and new_msg.tool_calls:
                        print(f"-> [System]: AI calling tool: {new_msg.tool_calls[0]['name']}")
                        continue
                    if hasattr(new_msg, 'content') and new_msg.content:
                        print(f"\n[AI Agent]: {new_msg.content}")
                        last_msg = new_msg
        return last_msg

    run_graph({"messages": []})

    while True:
        state = app.get_state(run_config)
        if state.next and "human_input" in state.next:
            print("\n" + "-"*40)
            user_response = input("TYPE YOUR COMMAND: ")
            print("-"*40 + "\n")
            if user_response.lower() in ['exit', 'quit']:
                print("Exiting...")
                break
            run_graph(Command(resume=user_response))
        else:
            break

    print("\n" + "="*30)
    print("DEMO AGENT SESSION COMPLETE")
    print("="*30)
