# demo-agent-ccc

Hybrid research + navigation agent with multiple UI options.

## Branches

| Branch | Description |
|--------|-------------|
| `main` | Baseline scraper experiments |
| `research+navi` | Tavily-powered research + Playwright navigation (Streamlit) |
| `chainlit` | **This branch** — Chainlit UI version |

## Quick Start (chainlit branch)

### Prerequisites

- **Python 3.13** (required — Chainlit's WebSocket has compatibility issues with Python 3.14)
- Node.js (for Playwright)

### Setup

```bash
git clone https://github.com/kkulkuic/demo-agent-ccc.git
cd demo-agent-ccc
git checkout chainlit

# Create Python 3.13 venv
python3.13 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Configure API keys
cp .env.example .env
# Edit .env with your keys
```

### Required API Keys

| Key | Purpose | Get it |
|-----|---------|--------|
| `ANTHROPIC_API_KEY` | Claude (agent + intent classification) | [console.anthropic.com](https://console.anthropic.com) |
| `TAVILY_API_KEY` | Web search & scrape | [tavily.com](https://tavily.com) |

### Run

```bash
# Chainlit UI (port 8000)
chainlit run chainlit_app.py

# Or specify port
chainlit run chainlit_app.py --port 8001
```

## UI Options

| File | Framework | Port | Description |
|------|-----------|------|-------------|
| `chainlit_app.py` | Chainlit | 8000 | Chat UI with native tool steps & HITL |
| `app.py` | Streamlit | 8530 | Full-featured with tabs, pipeline, HITL (see `research+navi` branch) |

## Features

- **Semantic intent classification** — Claude Haiku auto-detects navigate vs research mode (~0.5s, ~$0.001/call)
- **Live browser navigation** — Playwright with stealth mode, screenshot capture
- **Web research** — Tavily search + deep scrape with multi-source synthesis
- **HITL (Human-in-the-Loop)** — Agent pauses for CAPTCHA, ambiguous choices, missing info
- **Screenshot display** — Inline screenshots during navigation
- **Step budgets** — Nav: 25 steps, Research: 12 steps (prevent runaway loops)
- **Detailed logging** — All agent reasoning, tool calls, and results logged to `logs/chainlit_app.log`

## File Structure

```
├── chainlit_app.py       # Chainlit UI (entry point)
├── research+navi.py      # LangGraph agent + all tools
├── pkg_resources_compat  # Python 3.13/3.14 compatibility shim
├── test_chainlit.py      # Test suite
├── logs/                 # Runtime logs (gitignored)
├── playwright/.auth/     # Browser session data (gitignored)
├── .env.example          # API key template
├── requirements.txt      # Python deps
└── README.md
```

## Testing

```bash
python test_chainlit.py
```

Tests cover:
- Intent classification (7 test cases)
- HITL classification (5 test cases)
- Research mode end-to-end
- Navigate mode end-to-end

## Architecture

```
User → chainlit_app.py → classify_intent() → research+navi.py (LangGraph)
                              ↓                        ↓
                         navigate mode           research mode
                              ↓                        ↓
                       Playwright browser      Tavily search/scrape
                              ↓                        ↓
                       Screenshot + result     Synthesized answer
                              ↓                        ↓
                       HITL if needed          HITL if needed
                              ↓                        ↓
                         Answer to user
```

## Known Issues

- **Python 3.14 incompatible** — `websockets` library breaks WebSocket handshake on 3.14. Use Python 3.13.
- **Google Maps SPA** — `page_text` may be empty for single-page apps; screenshots work fine.
- **InMemorySaver** — Agent state lost on restart (by design for this demo).
- **Stale interrupt state** — Handled automatically by creating new thread when generic interrupt detected.

## Switching from Streamlit

If you were using the `research+navi` branch with Streamlit:
- Core agent code (`research+navi.py`) is shared
- Chainlit version uses Python 3.13 venv (not 3.14)
- `playwright_stealth` API differs between versions — auto-detected at runtime

## License

MIT
