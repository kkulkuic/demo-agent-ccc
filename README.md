# demo-agent-ccc

Hybrid research + navigation agent with Streamlit UI.

## Branches

| Branch | Description |
|--------|-------------|
| `main` | Baseline scraper experiments |
| `research+navi` | **This branch** — Tavily-powered research + Playwright navigation agent |

## Quick Start (research+navi branch)

```bash
git clone https://github.com/kkulkuic/demo-agent-ccc.git
cd demo-agent-ccc
git checkout research+navi

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Configure API keys
cp .env.example .env
# Edit .env with your keys:
#   - ANTHROPIC_API_KEY (Claude)
#   - TAVILY_API_KEY (web search)
#   - GOOGLE_PLACES_API_KEY (optional)

# Run
streamlit run app.py --server.port 8530
```

## UI Options

| File | Framework | Port | Description |
|------|-----------|------|-------------|
| `app.py` | Streamlit | 8530 | Full-featured with tabs, pipeline, HITL |
| `chainlit_app.py` | Chainlit | 8000 | Lightweight chat UI, native tool steps |

```bash
# Streamlit
streamlit run app.py --server.port 8530

# Chainlit
chainlit run chainlit_app.py --port 8000
```

## Testing

```bash
python test_chainlit.py
```

## Features

- **Semantic intent classification** — LLM decides navigate vs research
- **HITL (Human-in-the-Loop)** — Agent asks for help on CAPTCHA, ambiguous choices
- **Screenshot display** — Visual pipeline in Streamlit tabs
- **Step budgets** — Nav: 25 steps, Research: 12 steps (prevent runaway loops)

## File Structure

```
├── app.py              # Streamlit UI (entry point)
├── chainlit_app.py     # Chainlit UI (lightweight alternative)
├── research+navi.py    # LangGraph agent + tools
├── test_chainlit.py    # Test suite
├── .env.example        # API key template
├── requirements.txt    # Python deps
└── README.md
```

## Known Issues

- Google Maps SPA pages return empty `page_text` — use `browser_inspect()` (screenshot) instead
- Some browser tools still have upstream bugs (being fixed)

## License

MIT
