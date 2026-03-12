# Folder_Tavily - Tavily Search Metrics

This folder contains the minimal runnable code used to evaluate search output
with these four metrics:

- Query Type
- Latency (ms) for tool call only
- Extraction Quality (LLM-as-judge, Good/Bad)
- Tokens consumed (LLM total)

## Setup

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Set environment variables:
   - `TAVILY_API_KEY`
   - `ANTHROPIC_API_KEY` (or `API-KEY`)
3. Run benchmark:
   - `python -m eval.tavily_benchmark`

Output CSV:
- `eval/tavily_results.csv`
