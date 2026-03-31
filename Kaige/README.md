# Search Adapter Evaluation — TruLens Benchmark

## Overview

This evaluation benchmarks **5 search API adapters** (Brave, Tavily, SerpAPI, Firecrawl, Exa) for a RAG (Retrieval-Augmented Generation) application using **TruLens** official feedback functions for scoring.

The evaluation:
- Sends 9 standardized queries through each search adapter
- Generates answers using a simple RAG chain (search → LLM)
- Scores each answer using TruLens's NLI-based groundedness and relevance functions
- Compares adapters on quality (groundedness, relevance) and latency

## Search Adapters Tested

| Adapter | Source | Auth Method |
|---------|--------|-------------|
| Brave Search | [Brave Search API](https://brave.com/search/api/) | `X-Subscription-Token` header |
| Tavily AI | [Tavily API](https://tavily.com/) | API key in request body |
| SerpAPI | [SerpAPI](https://serpapi.com/) | `serpapi` Python client |
| Firecrawl | [Firecrawl API](https://www.firecrawl.dev/) | `Authorization: Bearer` header |
| Exa | [Exa API](https://exa.ai/) | `x-api-key` header |

## Evaluation Method

### Scoring (TruLens Official)

We use TruLens's built-in feedback functions from `trulens.providers.litellm.LiteLLM`:

**Groundedness** (`groundedness_measure_with_cot_reasons`):
- Uses NLI (Natural Language Inference) to check if the answer is logically entailed by the context
- Score range: 0–1 (normalized to 0–5 for display)
- Higher = answer is more directly supported by the retrieved context

**Context Relevance** (`context_relevance`):
- Checks if the retrieved context is relevant to the query
- Score range: 0–1 (normalized to 0–5 for display)
- Higher = the search results better match what the query is asking

### Judge Model

- Model: `claude-haiku-4-5-20251001` (via Anthropic API)
- Provider: `trulens.providers.litellm.LiteLLM`

### Evaluation Queries

9 queries covering different search scenarios:
1. Find top-rated shoe repair shops in Chicago (local business)
2. People Also Ask questions for 'reverse logistics startup ideas' (PAA)
3. Top 5 organic search results for sustainable clothing brands UK vs US (geo comparison)
4. Current price of Sony WH-1000XM5 (product pricing)
5. Latest news snippets about 'retail returns crisis 2026' (news)
6. Top 5 news stories in retail sector last 24h (news)
7. Funding rounds for logistics startups last 7 days (funding)
8. Recent Reddit discussions about 'Shopify returns' (forum)
9. Current stock price of Amazon with 1h change (finance)

## How to Run

### 1. Install Dependencies

```bash
pip install trulens langchain-anthropic serpapi requests python-dotenv anthropic
```

### 2. Set API Keys

Create a `.env` file (or set environment variables):

```bash
ANTHROPIC_API_KEY=sk-ant-...
BRAVE_API_KEY=BSA...
TAVILY_API_KEY=tvly-...
SERPAPI_API_KEY=...
FIRECRAWL_API_KEY=fc-...
EXA_API_KEY=...
```

The script loads keys from `~/.openclaw/workspace/.env` and `~/.openclaw/workspace/projects/sales-ai/scout/.env` automatically.

Adapters without API keys are **skipped** with a warning — you don't need all 5 to run.

### 3. Run

```bash
cd eval
python eval_trulens.py
```

Results are saved to `colleague_results_trulens.json`.

## TruLens Bug Fix (Required)

TruLens 2.7.1 has a bug: the `trulens.apps.langchain` module was removed but still referenced in `trulens/_mods.py`, causing import failures.

**`tru_langchain_fix.py`** patches this by creating mock modules in `sys.modules` before TruLens imports happen. The script auto-imports it at the start of `eval_trulens.py`.

### What the patch does

```python
# Creates mock modules for the removed langchain integration
import sys
from types import ModuleType

mock_langchain = ModuleType('trulens.apps.langchain')
mock_langchain.guardrails = ModuleType('trulens.apps.langchain.guardrails')
mock_langchain.langchain = ModuleType('trulens.apps.langchain.langchain')
mock_langchain.tru_chain = ModuleType('trulens.apps.langchain.tru_chain')

sys.modules['trulens.apps.langchain'] = mock_langchain
sys.modules['trulens.apps.langchain.guardrails'] = mock_langchain.guardrails
# ... etc.
```

This allows `from trulens.providers.litellm import LiteLLM` to work without crashing.

## Results

### Combined Summary

| Adapter | Groundedness | Relevance | Latency | Query Rate |
|---------|-------------|-----------|---------|------------|
| Tavily | 4.61 | 2.04 | 1871ms | 9/9 |
| Brave | 4.58 | 2.41 | 1946ms | 9/9 |
| SerpAPI | 4.48 | 2.59 | 1613ms | 9/9 |
| Exa | 4.14 | 3.33 | 1703ms | 9/9 |
| Firecrawl | 3.83 | 1.11 | 3956ms | 9/9 |

### Per-Adapter Breakdown

#### Brave Search
| Q | Groundedness | Relevance | Latency |
|---|-------------|-----------|---------|
| 1 | 5.0 | 3.3 | 2473ms |
| 2 | 5.0 | 0.0 | 1332ms |
| 3 | 5.0 | 1.7 | 1422ms |
| 4 | 3.8 | 1.7 | 1896ms |
| 5 | 4.4 | 3.3 | 2019ms |
| 6 | 4.2 | 1.7 | 2201ms |
| 7 | 4.4 | 3.3 | 1628ms |
| 8 | 5.0 | 5.0 | 2694ms |
| 9 | 4.4 | 1.7 | 1846ms |

#### Tavily AI
| Q | Groundedness | Relevance | Latency |
|---|-------------|-----------|---------|
| 1 | 5.0 | 5.0 | 1813ms |
| 2 | 5.0 | 0.0 | 1283ms |
| 3 | 5.0 | 1.7 | 1078ms |
| 4 | 3.8 | 1.7 | 2502ms |
| 5 | 3.8 | 3.3 | 2083ms |
| 6 | 5.0 | 1.7 | 1893ms |
| 7 | 4.6 | 1.7 | 1978ms |
| 8 | 4.4 | 1.7 | 1964ms |
| 9 | 5.0 | 1.7 | 2248ms |

#### SerpAPI
| Q | Groundedness | Relevance | Latency |
|---|-------------|-----------|---------|
| 1 | 3.6 | 3.3 | 2118ms |
| 2 | 5.0 | 1.7 | 1207ms |
| 3 | 4.0 | 1.7 | 1697ms |
| 4 | 3.8 | 1.7 | 1336ms |
| 5 | 5.0 | 3.3 | 1349ms |
| 6 | 4.5 | 3.3 | 2044ms |
| 7 | 5.0 | 3.3 | 1676ms |
| 8 | 4.4 | 3.3 | 1470ms |
| 9 | 5.0 | 1.7 | 1619ms |

#### Firecrawl
| Q | Groundedness | Relevance | Latency |
|---|-------------|-----------|---------|
| 1 | 3.3 | 1.7 | 4375ms |
| 2 | 3.3 | 0.0 | 4113ms |
| 3 | 4.6 | 1.7 | 6217ms |
| 4 | 3.3 | 1.7 | 3719ms |
| 5 | 3.8 | 1.7 | 4332ms |
| 6 | 4.4 | 1.7 | 3442ms |
| 7 | 3.3 | 1.7 | 4119ms |
| 8 | 5.0 | 0.0 | 943ms |
| 9 | 3.3 | 0.0 | 4348ms |

#### Exa
| Q | Groundedness | Relevance | Latency |
|---|-------------|-----------|---------|
| 1 | 3.3 | 3.3 | 1432ms |
| 2 | 5.0 | 0.0 | 1455ms |
| 3 | 4.0 | 5.0 | 1716ms |
| 4 | 4.6 | 1.7 | 1682ms |
| 5 | 3.8 | 5.0 | 1651ms |
| 6 | 5.0 | 5.0 | 2248ms |
| 7 | 5.0 | 5.0 | 1206ms |
| 8 | 2.0 | 3.3 | 1864ms |
| 9 | 4.6 | 1.7 | 2075ms |

## Limitations & Known Issues

### 1. Token tracking doesn't capture TruLens internal costs
TruLens's provider functions make their own LLM calls internally (e.g., to score groundedness via NLI). These calls go through LiteLLM, not through our LangChain chain, so they are **not tracked by our token counter**. The token and cost columns will always show 0 when using the official TruLens provider.

To track TruLens internal costs, you would need to either:
- Configure LiteLLM callbacks to log token usage
- Use a custom TruLens provider that wraps token tracking

### 2. Groundedness score range varies
TruLens's `groundedness_measure_with_cot_reasons` returns scores in 0–1 range, but the actual float values depend on how the NLI model decomposes the answer into statements. Scores like 0.667 (2/3), 0.75 (3/4), 0.889 (8/9) are common because the answer is split into N statements and the score = (supported_statements / total_statements). This means groundedness is more granular but also more variable than a simple 0-3 scale.

### 3. Context relevance score is a 0-3 integer normalized to 0-1
The `context_relevance` function returns a tuple `(float, dict)` where the float is already normalized to 0-1 (derived from a 0-3 integer score in the reason dict). This means you can only get 4 possible raw relevance values: 0.0, 0.33, 0.67, 1.0 — there's no granularity between these levels.

### 4. Firecrawl returns raw page content, not structured snippets
Firecrawl's search endpoint returns the full page content in the `content` field, not structured `title/url/description` like other search engines. This makes the context very long and noisy, which likely hurts relevance scores. A better approach would be to use Firecrawl's `scrape` endpoint with content extraction, or truncate aggressively.

### 5. Exa API key validity
The Exa API key used in this evaluation may have usage limits. The 402 Payment Required error observed during earlier runs suggests the account may need to be upgraded for higher volume.

### 6. RAG chain is minimal
The evaluation uses a bare-bones RAG chain: search results → context → LLM → answer. There is no:
- Query rewriting or expansion
- Reranking of search results
- Chunking or summarization of long contexts
- Conversation memory

This means the scores reflect raw search adapter quality, not the full potential of a well-engineered RAG system.

### 7. Only 9 evaluation queries
The benchmark uses 9 hand-picked queries. This is too small for statistical significance. A production evaluation would need 50–100+ queries across diverse categories with human-annotated ground truth.

### 10. "I don't know" inflates groundedness scores
TruLens's NLI-based groundedness checks whether the answer is logically entailed by the context. An answer like "I don't have enough information to answer this" is technically **fully grounded** (G=1.0) because it makes no falsifiable claims. This means an adapter that returns empty/irrelevant results will still score well on groundedness — the LLM just says "I can't answer" and gets a perfect groundedness score. This makes groundedness a **misleading metric when comparing search adapter quality**, because adapters that return nothing score just as well as adapters that return good results.

A more meaningful metric in this context would be **answer coverage** — did the adapter return enough relevant context for the LLM to actually answer the question? Groundedness alone doesn't capture this.

### 11. Single judge model
All scores come from one judge model (Claude Haiku 4.5). Different judge models might give different scores. A more robust evaluation would use multiple judges and report inter-rater reliability.

### 12. No ground truth comparison
The evaluation uses TruLens's reference-free scoring (no human-annotated correct answers). This is useful for relative comparison between adapters but doesn't measure absolute accuracy. For absolute measurement, you'd need human-annotated reference answers.

## Files

| File | Purpose |
|------|---------|
| `eval_trulens.py` | Main evaluation script — runs all adapters through TruLens scoring |
| `tru_langchain_fix.py` | Patches TruLens 2.7.1 broken `trulens.apps.langchain` import |
| `colleague_results_trulens.json` | Raw results (auto-generated, not committed) |

## Dependencies

```
trulens>=2.7.1
langchain-anthropic
serpapi
requests
python-dotenv
anthropic
```

## Changelog

- **2026-03-31**: Initial evaluation with 5 adapters + TruLens official scoring
