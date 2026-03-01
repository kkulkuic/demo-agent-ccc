---
name: HITL Testing Guide
overview: How to run and test the existing terminal HITL demo (HITL_terminal.py), and optionally add a short testing section to the README.
todos: []
isProject: false
---

# HITL Testing Plan

## Current HITL Entry Point

The HITL demo in this project is **[HITL_terminal.py](c:\Users\admin\Downloads\Agent-Broswer\HITL_terminal.py)**: LangGraph-based, terminal-driven, using `interrupt()` to pause and wait for user input. Tools use a **headless** browser (no visible window).

- **Entry**: The `human_input` node runs first, prints a prompt, and calls `interrupt("What website should I visit? (or type 'exit')")`.
- **Tools**: `get_web_page_info(url)`, `click_element(url, selector)`, `ask_human_for_help(reason)`. When the agent calls `ask_human_for_help`, the graph routes back to `human_input`, which calls `interrupt("Agent needs help. Type your response:")`.
- **Loop**: After each agent reply, control returns to `human_input`; the terminal prints `TYPE YOUR COMMAND:` and the user types the next instruction or `exit`/`quit` to stop.

---

## How to Run and Test

**1. Environment**

- Same as for Streamlit: install `playwright`, `langchain-anthropic`, `langgraph`, etc., and set `ANTHROPIC_API_KEY` or `API-KEY` (system environment or project root `.env`).
- Open a terminal in the **project root** (same directory as `HITL_terminal.py`).

**2. Start**

```bash
python HITL_terminal.py
```

**3. Expected Flow**

1. Terminal prints: `--- Starting Demo Agent (HITL Mode) ---`, then `--- AGENT READY: WAITING FOR YOUR COMMAND ---`, and waits for input.
2. **First input**: e.g. `https://www.wikipedia.org` or “Open Wikipedia and tell me the title”. The agent may call `get_web_page_info` or other tools; the terminal shows `-> [System]: AI calling tool: get_web_page_info` (or another tool name), then `[AI Agent]: ...` with the reply.
3. When `TYPE YOUR COMMAND:` appears again, type another instruction (e.g. another URL or “click on some link”) or `exit` / `quit` to end.
4. **Trigger “ask human for help”**: To see the `ask_human_for_help` HITL interrupt, use a vague or confirmation-style instruction (e.g. “I need help deciding what to do”) so the model may call that tool; then you’ll see “Agent needs help. Type your response:” and can type any reply for the agent to continue.

**4. Verification**

- Startup shows the initial prompt and “TYPE YOUR COMMAND” (or equivalent).
- After entering a URL, `get_web_page_info` is called and the agent returns title/description-like content.
- After entering `exit`, the process exits and prints “DEMO AGENT SESSION COMPLETE”.

---

## Optional: Add Testing Steps to README

To document this, you can add to [README.md](c:\Users\admin\Downloads\Agent-Broswer\README.md) in the “Optional” section (or a new “Testing HITL” section):

- The run command and prerequisites (API key, dependencies).
- Short test steps: first input a URL, observe tool calls, then a second input or exit.
- A note that `HITL_terminal.py` uses a headless browser and is separate from the Streamlit headed session.

You can test HITL without any code changes by following the steps above; the README update is only to make reproduction and handoff easier.
