#!/usr/bin/env python3
"""
Evaluation using TruLens with 5 search adapters:
- Brave, Tavily, SerpAPI, Firecrawl, Exa

Uses TruLens-style groundedness/relevance scores + token usage tracking.

Run:
    python eval_trulens.py
"""

import os
import re
import time
import json
import sys
from dataclasses import dataclass, asdict
from typing import List, Tuple, Dict

# ─── Load .env ────────────────────────────────────────────────────────────────
def load_env():
    for env_file in [
        "/home/ubuntu/.openclaw/workspace/.env",
        "/home/ubuntu/.openclaw/workspace/projects/sales-ai/scout/.env",
    ]:
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        os.environ.setdefault(key.strip(), value.strip())
load_env()

# ─── API Keys ────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
EXA_API_KEY = os.getenv("EXA_API_KEY", "")

MODEL = "claude-haiku-4-5-20251001"
PRICE_IN  = 1.00  # $/M input tokens
PRICE_OUT = 5.00  # $/M output tokens

# ─── Queries ─────────────────────────────────────────────────────────────────
EVAL_QUERIES = [
    "Find the top-rated shoe repair shops in Chicago with their phone numbers and opening hours.",
    "What are the 'People Also Ask' questions for 'reverse logistics startup ideas'?",
    "List the top 5 organic search results for 'sustainable clothing brands' in the UK vs. the US.",
    "Find the current price and availability of the 'Sony WH-1000XM5' from the Google Shopping tab.",
    "Get the latest news snippets from Google News about 'retail returns crisis 2026'.",
    "What are the top 5 news stories in the retail sector from the last 24 hours?",
    "List all funding rounds for logistics startups announced in the last 7 days.",
    "Find the most recent Reddit discussions about 'Shopify returns' from the past month.",
    "What is the current stock price of Amazon and how has it changed in the last 1 hour?",
]

# ─── Search Adapters ─────────────────────────────────────────────────────────

def search_brave(query: str) -> str:
    try:
        import requests
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY},
            params={"q": query, "count": 5}, timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("web", {}).get("results", [])[:5]:
            results.append(
                f"Title: {item.get('title','')}\nURL: {item.get('url','')}\nSnippet: {item.get('description','')}"
            )
        return "\n\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Brave search error: {e}"


def search_tavily(query: str) -> str:
    try:
        import requests
        resp = requests.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json={"api_key": TAVILY_API_KEY, "query": query, "max_results": 5},
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        results = []
        for item in result.get("results", [])[:5]:
            results.append(
                f"Title: {item.get('title','')}\nURL: {item.get('url','')}\nSnippet: {item.get('content','')[:300]}"
            )
        return "\n\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Tavily search error: {e}"


def search_serpapi(query: str) -> str:
    try:
        import serpapi
        client = serpapi.Client(api_key=SERPAPI_API_KEY)
        results = client.search(q=query, num=5, engine="google")
        if "error" in results:
            return f"SERPAPI error: {results['error']}"
        organic = results.get("organic_results", [])
        if not organic:
            return "No results found."
        out = []
        for r in organic[:5]:
            out.append(f"Title: {r.get('title','')}\nURL: {r.get('link','')}\nSnippet: {r.get('snippet','')}")
        return "\n\n".join(out)
    except Exception as e:
        return f"SERPAPI search error: {e}"


def search_firecrawl(query: str) -> str:
    """Search using Firecrawl API.  Returns full-page content, so truncate."""
    try:
        import requests
        resp = requests.post(
            "https://api.firecrawl.dev/v0/search",
            headers={
                "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"query": query, "limit": 5},
            timeout=20,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("success"):
            return f"Firecrawl error: {result.get('error', 'unknown')}"

        # Firecrawl returns {data: [{content, metadata: {sourceURL, ...}}]}
        results = []
        for item in result.get("data", [])[:5]:
            content = item.get("content", "")
            url = item.get("metadata", {}).get("sourceURL", item.get("url", ""))
            snippet = content[:500]  # Truncate raw page content
            results.append(f"URL: {url}\nSnippet: {snippet}")
        return "\n\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Firecrawl search error: {e}"


def search_exa(query: str) -> str:
    """Search using Exa API."""
    try:
        import requests
        resp = requests.post(
            "https://api.exa.ai/search",
            headers={
                "x-api-key": EXA_API_KEY,  # Exa uses x-api-key header
                "Content-Type": "application/json",
            },
            json={"query": query, "numResults": 5, "text": {"maxCharacters": 1000}},
            timeout=20,
        )
        resp.raise_for_status()
        result = resp.json()
        results = []
        for item in result.get("results", [])[:5]:
            results.append(
                f"Title: {item.get('title','')}\nURL: {item.get('url','')}\nSnippet: {item.get('text','')[:300]}"
            )
        return "\n\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Exa search error: {e}"


ADAPTERS = {
    "brave":     {"fn": search_brave,     "key": BRAVE_API_KEY,     "name": "Brave Search"},
    "tavily":    {"fn": search_tavily,    "key": TAVILY_API_KEY,    "name": "Tavily AI"},
    "serpapi":   {"fn": search_serpapi,   "key": SERPAPI_API_KEY,   "name": "SerpAPI"},
    "firecrawl": {"fn": search_firecrawl, "key": FIRECRAWL_API_KEY, "name": "Firecrawl"},
    "exa":       {"fn": search_exa,       "key": EXA_API_KEY,       "name": "Exa"},
}

# ─── RAG Chain (with token tracking) ────────────────────────────────────────

def make_rag_chain(search_fn):
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage

    llm = ChatAnthropic(model=MODEL, api_key=ANTHROPIC_API_KEY, temperature=0)

    class Chain:
        def __init__(self):
            self.search_fn = search_fn
            self.last_context = ""
            self.last_tokens = {"input": 0, "output": 0}

        def invoke(self, query: str) -> str:
            context = self.search_fn(query)
            self.last_context = context
            prompt = (
                f"Using only the context below, answer the question.\n\n"
                f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
            )
            resp = llm.invoke([HumanMessage(content=prompt)])
            # Track tokens
            usage = getattr(resp, "response_metadata", {})
            usage = usage.get("token_usage", usage) or {}
            self.last_tokens = {
                "input": usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0),
                "output": usage.get("output_tokens", 0) or usage.get("completion_tokens", 0),
            }
            content = getattr(resp, "content", str(resp))
            if isinstance(content, list):
                return " ".join(
                    b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "")
                    for b in content
                    if (isinstance(b, dict) and b.get("type") == "text") or hasattr(b, "type") and b.type == "text"
                )
            return str(content)

        def get_context(self) -> str:
            return self.last_context

        def get_tokens(self) -> Dict:
            return dict(self.last_tokens)

    return Chain()


# ─── TruLens-style Feedback ──────────────────────────────────────────────────

def trulens_evaluate(answer: str, context: str, query: str) -> Tuple[float, float, Dict]:
    """
    Use TruLens provider for groundedness + relevance.
    No fallback — fails explicitly if TruLens unavailable.
    Returns (gnd_0_5, rel_0_5, token_usage).
    """
    import tru_langchain_fix  # noqa: F401
    from trulens.providers.litellm import LiteLLM

    tokens = {"input": 0, "output": 0}

    provider = LiteLLM(model_engine="anthropic/claude-haiku-4-5-20251001",
                       completion_kwargs={"api_key": ANTHROPIC_API_KEY})

    ctx = context[:2000]
    ans = answer[:1000]

    # Groundedness via TruLens provider (NLI-based, 0-1 scale from provider)
    gnd_result, gnd_reasons = provider.groundedness_measure_with_cot_reasons(source=ctx, statement=ans)
    print(f"    GND raw: {gnd_result} ({_score_from_reasons(gnd_reasons)})")
    gnd_01 = _extract_score(gnd_result)
    gnd_05 = gnd_01 * 5.0  # 0-1 → 0-5

    # Context Relevance via TruLens provider (returns tuple: (score, reasons_dict))
    rel_result = provider.context_relevance(question=query, context=ctx)
    rel_03 = _extract_score(rel_result)  # Already 0-1 from provider
    rel_05 = rel_03 * 5.0  # 0-1 → 0-5
    print(f"    REL raw: {rel_result} → score={rel_03:.2f} → {rel_05:.1f}")

    return gnd_05, rel_05, tokens


def _score_from_reasons(reasons) -> str:
    """Extract score from reasons dict for logging."""
    if isinstance(reasons, dict):
        r = reasons.get("reason", {})
        if isinstance(r, dict):
            return f"score={r.get('score','?')}"
        return str(r)[:60]
    return str(reasons)[:60]


def _extract_score(result) -> float:
    """Extract normalized 0-1 score from various TruLens return formats."""
    if isinstance(result, tuple):
        result = result[0]
    if isinstance(result, (int, float)):
        return max(0.0, min(1.0, float(result)))
    if isinstance(result, str):
        m = re.search(r'\d+\.?\d*', result)
        if m:
            return max(0.0, min(1.0, float(m.group())))
    if isinstance(result, dict):
        return max(0.0, min(1.0, float(result.get("score", 0))))
    if isinstance(result, list) and len(result) > 0:
        first = result[0]
        if isinstance(first, (int, float)):
            return max(0.0, min(1.0, float(first)))
        if isinstance(first, dict):
            return max(0.0, min(1.0, float(first.get("score", 0))))
    return 0.0


# ─── Data Class ──────────────────────────────────────────────────────────────
@dataclass
class Result:
    adapter: str
    query_num: int
    query: str
    tru_gnd: float
    tru_rel: float
    latency_ms: float
    llm_tokens_input: int
    llm_tokens_output: int
    judge_tokens_input: int
    judge_tokens_output: int
    total_cost_usd: float
    answer: str
    error: str = ""


# ─── Eval Loop ───────────────────────────────────────────────────────────────
def run_adapter_eval(adapter_name: str, search_fn, queries: List[str]) -> List[Result]:
    adapter_full_name = ADAPTERS.get(adapter_name, {}).get("name", adapter_name)
    print(f"\n{'='*80}\n  Adapter: {adapter_full_name}\n{'='*80}")

    app = make_rag_chain(search_fn)
    results = []

    for i, query in enumerate(queries, 1):
        print(f"\n[{i}/9] {query[:70]}...")
        start = time.perf_counter()
        try:
            answer = app.invoke(query)
            context = app.get_context()
            latency_ms = (time.perf_counter() - start) * 1000

            llm_tok = app.get_tokens()

            tru_gnd, tru_rel, judge_tok = trulens_evaluate(answer, context, query)

            cost = (
                (llm_tok["input"] + judge_tok["input"]) * PRICE_IN / 1e6
                + (llm_tok["output"] + judge_tok["output"]) * PRICE_OUT / 1e6
            )

            r = Result(
                adapter=adapter_name, query_num=i, query=query,
                tru_gnd=tru_gnd, tru_rel=tru_rel, latency_ms=latency_ms,
                llm_tokens_input=llm_tok["input"], llm_tokens_output=llm_tok["output"],
                judge_tokens_input=judge_tok["input"], judge_tokens_output=judge_tok["output"],
                total_cost_usd=cost, answer=answer[:200],
            )
            results.append(r)
            print(f"  Tru G={tru_gnd:.1f} R={tru_rel:.1f} | "
                  f"Tokens: {llm_tok['input']}+{judge_tok['input']}in / {llm_tok['output']}+{judge_tok['output']}out | "
                  f"Cost: ${cost:.4f} | {latency_ms:.0f}ms")
        except Exception as e:
            import traceback; traceback.print_exc()
            results.append(Result(
                adapter=adapter_name, query_num=i, query=query,
                tru_gnd=0, tru_rel=0, latency_ms=(time.perf_counter()-start)*1000,
                llm_tokens_input=0, llm_tokens_output=0,
                judge_tokens_input=0, judge_tokens_output=0,
                total_cost_usd=0, answer="", error=str(e)[:200],
            ))
            print(f"  ERROR: {e}")
    return results


def print_summary(results: List[Result]):
    name = ADAPTERS.get(results[0].adapter, {}).get("name", results[0].adapter) if results else ""
    valid = [r for r in results if not r.error]
    if not valid:
        return

    g = sum(r.tru_gnd for r in valid) / len(valid)
    r = sum(r.tru_rel for r in valid) / len(valid)
    lat = sum(r.latency_ms for r in valid) / len(valid)
    llm_in = sum(r.llm_tokens_input for r in valid)
    llm_out = sum(r.llm_tokens_output for r in valid)
    j_in = sum(r.judge_tokens_input for r in valid)
    j_out = sum(r.judge_tokens_output for r in valid)
    cost = sum(r.total_cost_usd for r in valid)

    print(f"\n{'='*80}\n  {name.upper()} RESULTS\n{'='*80}")
    print(f"\n  {'Q':<2}  {'Query':<45}  {'Tru G':>6}  {'Tru R':>6}  {'LLM in':>7}  {'LLM out':>8}  {'Judge in':>9}  {'Judge out':>10}  {'Cost':>8}  {'ms':>8}")
    print(f"  {'─'*2}  {'─'*45}  {'─'*6}  {'─'*6}  {'─'*7}  {'─'*8}  {'─'*9}  {'─'*10}  {'─'*8}  {'─'*8}")
    for rr in valid:
        qq = rr.query[:42] + "..." if len(rr.query) > 42 else rr.query
        print(f"  {rr.query_num:<2}  {qq:<45}  {rr.tru_gnd:>6.1f}  {rr.tru_rel:>6.1f}  "
              f"{rr.llm_tokens_input:>7}  {rr.llm_tokens_output:>8}  "
              f"{rr.judge_tokens_input:>9}  {rr.judge_tokens_output:>10}  "
              f"${rr.total_cost_usd:>6.4f}  {rr.latency_ms:>8.0f}")

    print(f"\n  {'AVG':<2}  {'':<45}  {g:>6.2f}  {r:>6.2f}  {llm_in:>7}  {llm_out:>8}  "
          f"{j_in:>9}  {j_out:>10}  ${cost:>6.4f}  {lat:>8.0f}")
    print(f"  Queries: {len(valid)}/{len(results)}")


def print_combined(all_results: List[Result]):
    print(f"\n{'='*80}\n  COMBINED SUMMARY\n{'='*80}")
    for adapter in sorted(set(r.adapter for r in all_results)):
        rr = [r for r in all_results if r.adapter == adapter and not r.error]
        if not rr:
            continue
        name = ADAPTERS.get(adapter, {}).get("name", adapter)
        g = sum(r.tru_gnd for r in rr) / len(rr)
        r_ = sum(r.tru_rel for r in rr) / len(rr)
        lat = sum(r.latency_ms for r in rr) / len(rr)
        llm_in = sum(r.llm_tokens_input for r in rr)
        llm_out = sum(r.llm_tokens_output for r in rr)
        j_in = sum(r.judge_tokens_input for r in rr)
        j_out = sum(r.judge_tokens_output for r in rr)
        cost = sum(r.total_cost_usd for r in rr)
        print(f"\n  {name}:")
        print(f"    G={g:.2f}  R={r_:.2f}  Latency={lat:.0f}ms  Queries={len(rr)}/9")
        print(f"    Tokens: {llm_in}+{j_in}in / {llm_out}+{j_out}out  Cost=${cost:.4f}")

    valid = [r for r in all_results if not r.error]
    if valid:
        total_llm_in = sum(r.llm_tokens_input for r in valid)
        total_llm_out = sum(r.llm_tokens_output for r in valid)
        total_j_in = sum(r.judge_tokens_input for r in valid)
        total_j_out = sum(r.judge_tokens_output for r in valid)
        total_cost = sum(r.total_cost_usd for r in valid)
        print(f"\n  OVERALL TOTALS:")
        print(f"    G={sum(r.tru_gnd for r in valid)/len(valid):.2f}  "
              f"R={sum(r.tru_rel for r in valid)/len(valid):.2f}")
        print(f"    LLM tokens: {total_llm_in} in / {total_llm_out} out")
        print(f"    Judge tokens: {total_j_in} in / {total_j_out} out")
        print(f"    Total cost: ${total_cost:.4f}")


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*80}\n  TRULENS EVALUATION (5 Adapters + Token Tracking)\n{'='*80}")
    print(f"  Model: {MODEL}")
    print("\nAPI Key Status:")
    for name in ["ANTHROPIC", "BRAVE", "TAVILY", "SERPAPI", "FIRECRAWL", "EXA"]:
        print(f"  {name}_API_KEY: {'✓' if os.getenv(f'{name}_API_KEY') else '✗'}")

    if not ANTHROPIC_API_KEY:
        print("\nERROR: ANTHROPIC_API_KEY required!"); sys.exit(1)

    available = [n for n, i in ADAPTERS.items() if i.get("key")]
    if not available:
        print("\nERROR: No search API keys!"); sys.exit(1)
    print(f"\n  Available: {', '.join(available)}")

    all_results = []
    for name in ["brave", "tavily", "serpapi", "firecrawl", "exa"]:
        info = ADAPTERS.get(name, {})
        if not info.get("key"):
            print(f"\n  SKIPPING {info.get('name', name)}")
            continue
        rr = run_adapter_eval(name, info["fn"], EVAL_QUERIES)
        all_results.extend(rr)
        print_summary(rr)

    print_combined(all_results)

    failed = [r for r in all_results if r.error]
    if failed:
        print(f"\nFAILED:")
        for r in failed:
            print(f"  [{r.adapter}] Q{r.query_num}: {r.error[:80]}")

    out = "/home/ubuntu/.openclaw/workspace/projects/cccis-onboarding/agent-browser/eval/colleague_results_trulens.json"
    with open(out, "w") as f:
        json.dump([asdict(r) for r in all_results], f, indent=2, default=str)
    print(f"\n💾 Saved: {out}")


if __name__ == "__main__":
    main()
