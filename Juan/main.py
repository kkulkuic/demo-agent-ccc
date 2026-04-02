import json
import os

from dotenv import load_dotenv

from planner import plan_actions
from executor import AgentExecutor
from modes.hybrid_runner import HybridRunner
from rag_eval import evaluate_run_result, pretty_print_rag_eval

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

load_dotenv()

ENABLE_RAG_EVAL = True


def build_llm_client():
    """
    Build Claude client if the Anthropic SDK is installed and the API key exists.
    Returns None if not available, so the app can still run without LLM help.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if Anthropic is None:
        print("Anthropic SDK not installed. Running without Claude reasoning.")
        return None

    if not api_key:
        print("ANTHROPIC_API_KEY not found. Running without Claude reasoning.")
        return None

    try:
        client = Anthropic(api_key=api_key)
        print("Claude reasoning enabled.")
        return client
    except Exception as e:
        print(f"Could not initialize Claude client: {type(e).__name__}: {repr(e)}")
        print("Running without Claude reasoning.")
        return None


def save_trace(trace_logger, path: str = "latest_run_trace.json"):
    if hasattr(trace_logger, "save_json"):
        trace_logger.save_json(path)
    elif hasattr(trace_logger, "save"):
        trace_logger.save(path)
    else:
        print("Warning: TraceLogger has no save method; trace was not written to disk.")


def pretty_print_result(result):
    print("\n" + "=" * 80)
    print("OUTPUTS")
    print("=" * 80)

    for item in result.get("outputs", []):
        print(f"\nStep {item['step']} - {item['tool']}")
        print("Args:", item.get("args", {}))

        if "error" in item:
            print("Error:", repr(item["error"]))
            continue

        preview = str(item.get("result"))
        if len(preview) > 1000:
            preview = preview[:1000] + "..."
        print("Result preview:")
        print(preview)

    print("\n" + "=" * 80)
    print("TRACE SUMMARY")
    print("=" * 80)

    trace = result.get("trace", {})
    print("Run ID:", trace.get("run_id"))
    print("Instruction:", trace.get("instruction"))
    print("Mode:", trace.get("mode"))
    print("Total steps:", len(trace.get("steps", [])))

    total_duration = sum(
        step.get("duration_seconds", 0) for step in trace.get("steps", [])
    )
    print("Total duration (s):", round(total_duration, 4))

    for step in trace.get("steps", []):
        print(
            f"Step {step.get('step_number')} | "
            f"{step.get('tool')} | "
            f"{step.get('status')} | "
            f"{step.get('duration_seconds')}s | "
            f"error={repr(step.get('error', ''))}"
        )

    context = result.get("context", {})
    if context:
        print("\nContext keys:", list(context.keys()))

        if "original_instruction" in context:
            print("Original instruction:", context["original_instruction"])

        if "last_search_query" in context:
            print("Last search query:", context["last_search_query"])

        if "selected_url" in context:
            print("Selected URL:", context["selected_url"])

        if "selected_result" in context:
            sel = context["selected_result"]
            print("Selected result title:", sel.get("title", ""))
            print("Selected result URL:", sel.get("url", ""))

        if "opened_in_browser" in context:
            print("Opened in browser:", context["opened_in_browser"])

        if "page_title" in context:
            print("Opened page title:", context["page_title"])

        if "result_ranking_reasoning" in context:
            print("Result ranking reasoning:", context["result_ranking_reasoning"])

        if "results_preview" in context:
            print("\nTop Results Preview:")
            for idx, item in enumerate(context["results_preview"], start=1):
                print(f"\nResult {idx}")
                print(" Title:", item.get("title", ""))
                print(" URL:", item.get("url", ""))
                print(" Description:", item.get("description", ""))

        if "last_summary" in context:
            print("\nFinal Agent Answer:")
            print(context["last_summary"])


def run_rag_eval_if_enabled(result, llm_client):
    if not ENABLE_RAG_EVAL:
        return None

    eval_result = evaluate_run_result(result, llm_client=llm_client)
    pretty_print_rag_eval(eval_result)
    return eval_result


def build_firecrawl_headed_plan(instruction: str) -> list[dict]:
    """
    Firecrawl search -> open best URL in headed browser -> read page -> summarize.
    """
    return [
        {
            "tool": "search_web",
            "args": {
                "query": instruction,
                "limit": 10,
            },
        },
        {
            "tool": "open_best_search_result",
            "args": {},
        },
        {
            "tool": "read_opened_page",
            "args": {
                "max_chars": 5000,
            },
        },
        {
            "tool": "summarize_opened_page",
            "args": {
                "max_results": 8,
                "max_page_chars": 3500,
            },
        },
    ]


def main():
    instruction = input("Enter instruction: ").strip()

    if not instruction:
        print("No instruction entered. Exiting.")
        return

    llm_client = build_llm_client()

    print("\nPlanner output (for reference):")
    try:
        planner_preview = plan_actions(instruction, search_limit=25, summary_limit=8)
        print(json.dumps(planner_preview, indent=2))
    except Exception as e:
        print(f"Planner preview unavailable: {type(e).__name__}: {repr(e)}")

    mode = input(
        "\nEnter mode (firecrawl_headless/firecrawl_headed/hybrid): "
    ).strip().lower()

    if mode not in {"firecrawl_headless", "firecrawl_headed", "hybrid"}:
        print("Invalid mode. Defaulting to firecrawl_headless.")
        mode = "firecrawl_headless"

    if mode == "firecrawl_headless":
        print("\nRunning Firecrawl headless mode.")
        print("This uses your existing AgentExecutor path.")

        try:
            plan = plan_actions(instruction, search_limit=25, summary_limit=8)
        except Exception as e:
            print(f"Planner failed. Exiting. Error: {type(e).__name__}: {repr(e)}")
            return

        executor = AgentExecutor(
            instruction=instruction,
            mode=mode,
            llm_client=llm_client,
        )
        result = executor.run_plan(plan)
        pretty_print_result(result)
        run_rag_eval_if_enabled(result, llm_client)
        save_trace(executor.trace_logger, "latest_run_trace.json")

    else:
        print(f"\nRunning {mode} with Firecrawl search + headed browser open.")
        print("Flow: Firecrawl search -> pick best result -> open visible browser -> summarize.")

        plan = build_firecrawl_headed_plan(instruction)

        runner = HybridRunner(
            instruction=instruction,
            llm_client=llm_client,
            slow_mo=150,
        )
        result = runner.run_plan(plan)
        pretty_print_result(result)
        run_rag_eval_if_enabled(result, llm_client)
        save_trace(runner.trace_logger, "latest_run_trace.json")

    print("\nSaved trace to latest_run_trace.json")


if __name__ == "__main__":
    main()