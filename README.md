# Agent-Browser

Browser automation driven by natural language: one Streamlit app with **Auto** (plan + execute) and **Chat** (ReAct + headed browser) modes, shared session, and optional behavior visualization (dot cursor, element highlight, bounding box). Both modes use a single default model (override via `PLANNER_MODEL`).

## How to run

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# API key: set in system env (ANTHROPIC_API_KEY or API-KEY), or in project .env

# Single entry: Streamlit app (Auto + Chat modes)
streamlit run app.py
```

- **Chat**: natural language commands; agent uses tools to open URLs, read pages, click, type (no passwords).
- **Auto**: enter an instruction and start URL; planner produces a step list and the executor runs it in the shared browser.
- **Visualization**: in the sidebar, enable "Show dot + element highlight" to see a red dot and element overlay during actions.
- **Cookie consent**: the app tries to click common consent buttons (Accept, Agree, etc.) after opening a page or navigating, in both Auto and Chat modes. **Bot verification (CAPTCHA, Cloudflare, “verify you are human”)** cannot be automated; when detected, the agent asks you to complete it manually in the opened browser, then continue.

Optional:

```bash
# One-off auto run (creates and closes its own session)
python main.py

# Terminal HITL demo (headless tools, interrupt for human input)
python HITL_terminal.py
```

## Testing HITL

The terminal HITL demo (`HITL_terminal.py`) uses a **headless** browser and is separate from the Streamlit app’s headed session. Same prerequisites: API key (system env or `.env`), and dependencies above.

**Run:** From the project root, `python HITL_terminal.py`.

**Quick test:**

1. When you see the prompt, type a URL (e.g. `https://www.wikipedia.org`) or a short instruction (e.g. “Open Wikipedia and tell me the title”).
2. Watch the terminal for `-> [System]: AI calling tool: get_web_page_info` (or another tool) and then `[AI Agent]: ...` with the reply.
3. When `TYPE YOUR COMMAND:` appears again, type another instruction or `exit` / `quit` to end the session.
4. To trigger the “ask human for help” interrupt, try a vague or confirmation-style request (e.g. “I need help deciding what to do”); when the agent calls that tool, you’ll get “Agent needs help. Type your response:”.

**Check:** Startup shows the initial prompt, a URL input leads to tool use and a reply, and `exit` closes with “DEMO AGENT SESSION COMPLETE”.

## Environment variables

The app reads the API key from **system environment variables** first. If you install `python-dotenv`, it will also load a project `.env` file (system env still wins).

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` or `API-KEY` | Claude API key |
| `PLANNER_MODEL` | Model for both Auto and Chat (default: claude-haiku-4-5-20251001) |
| `MAX_STEPS` | Max steps for ReAct-style loops (default: 20) |
| `MAX_RETRIES` | Max retries per step (default: 3) |
| `DEFAULT_HEADLESS` | Default headless mode for browser (default: false) |
| `VIZ_MODE` | Visualization: `dot_hilite`, `bounding_box`, or `both` |

## Project structure

```
Agent-Broswer/
├── app.py              # Entry: Streamlit (Auto / Chat), visualization toggle
├── config.py           # API key, models, MAX_STEPS, MAX_RETRIES, VIZ_MODE
├── main.py             # CLI for Auto
├── planner.py          # plan_actions(instruction, context) → JSON actions
├── executor.py         # BrowserAgent(enable_viz, viz_mode), robust_click, bounding box
├── HITL_terminal.py    # Terminal HITL with headless tools
├── requirements.txt    # playwright, anthropic, streamlit, langchain, langgraph
├── core/
│   ├── browser.py      # get_page(session_id), start/stop_session, safe_page_snapshot
│   ├── consent.py      # dismiss_cookie_consent, looks_like_bot_challenge
│   ├── visualization.py # install_dot, install_highlighter, draw_bounding_box
│   └── json_parser.py  # extract_json_from_markdown, safe_json_parse
├── agent/
│   ├── auto.py         # run_auto_agent(instruction, start_url, session_id, enable_viz)
│   ├── chat.py         # build_chat_agent(model, session_id)
│   └── industrial.py   # IndustrialAgent (ReAct + Memory), for CLI/other use
├── tools/
│   ├── headed_tools.py # open_url_headed, read_page_headed, click_on_page, etc.
│   ├── vision_tools.py # capture_screenshot_base64, parse_instruction_to_code, execute_action_code
│   ├── debug_tools.py # draw_bounding_box_on_locator, format_date_for_search, search_with_date_range
│   └── fetch_tools.py  # get_web_page_info (headless fetch)
└── demos/
    ├── google_date_search.py      # Headful + date-range search
    ├── vision_github_search.py    # GitHub search via vision
    ├── headless_extraction.py     # Headless + code extraction
    └── interactive_playwright_docs.py # Hover, scroll, multi-tab
```

- **One entry**: `streamlit run app.py`; mode and visualization in the UI.
- **Shared session**: both Auto and Chat use `core.browser.get_page(session_id)`.
- **Visualization**: from `Borderering-cursor.txt` (dot + overlay); used in executor and in Chat tools when enabled.
