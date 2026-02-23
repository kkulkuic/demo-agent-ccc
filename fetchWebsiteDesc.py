import os
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from playwright.sync_api import sync_playwright




# --- 1. TOOL DEFINITION ---
@tool
def get_web_page_info(url: str):
    """
    Visits a URL using a headless browser and returns the page title 
    and a short description or text snippet.
    """
    with sync_playwright() as p:
        # Launching in headless mode for background execution
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, timeout=60000)
            title = page.title()
            
            # Attempt to find meta description
            description = page.locator('meta[name="description"]').get_attribute("content")
            
            # Fallback: If no meta description, grab the first 300 characters of the body text
            if not description:
                description = page.evaluate("() => document.body.innerText.slice(0, 300)")
                
            return {
                "url": url,
                "title": title,
                "description": description.strip() if description else "No description found."
            }
        except Exception as e:
            return {"error": f"Failed to load page: {str(e)}"}
        finally:
            browser.close()

# --- 2. GRAPH STATE & LOGIC ---
class State(TypedDict):
    # add_messages ensures new messages are appended to history rather than overwriting
    messages: Annotated[list, add_messages]

# Define the list of tools available to the agent
tools = [get_web_page_info]
tool_node = ToolNode(tools)

# Initialize the LLM and "bind" the tools so the model knows it can call them
llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    api_key = os.getenv("ANTHROPIC_API_KEY"),
    temperature=0
).bind_tools(tools)

def chatbot(state: State):
    """The node that decides what to do next based on the message history."""
    return {"messages": [llm.invoke(state["messages"])]}

# --- 3. GRAPH CONSTRUCTION ---
workflow = StateGraph(State)

# Add our two main nodes
workflow.add_node("agent", chatbot)
workflow.add_node("tools", tool_node)

# Set the entry point
workflow.set_entry_point("agent")

# Logic: After 'agent' node, check if LLM called a tool. 
# If yes, go to 'tools'. If no, finish (END).
workflow.add_conditional_edges("agent", tools_condition)

# After tools are finished, always go back to the agent to summarize the results
workflow.add_edge("tools", "agent")

# Compile the graph
app = workflow.compile()

# --- 4. EXECUTION BLOCK (Clean Output Version) ---
if __name__ == "__main__":
    print("--- Starting Extraction Task ---")
    
    query = "Visit 'https://www.wikipedia.org' and 'https://www.python.org'. Give me the title and a brief summary of each."
    inputs = {"messages": [("user", query)]}
    
    final_message = None

    # We iterate through the stream to keep track of progress
    for output in app.stream(inputs, stream_mode="values"):
        # The 'values' mode gives us the full message list at each step
        last_message = output["messages"][-1]
        
        # 1. If the AI is calling a tool, print a simple status update
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                url = tool_call['args'].get('url', 'the website')
                print(f"-> [Agent]: Navigating to {url}...")
        
        # 2. Store the last message so we can print the final answer later
        final_message = last_message

    # --- FINAL OUTPUT ---
    print("\n" + "="*30)
    print("FINAL SUMMARY FROM CLAUDE:")
    print("="*30)
    # Ensure we only print if the last message has actual text content
    if hasattr(final_message, 'content') and final_message.content:
        print(final_message.content)