import json
import os

from dotenv import load_dotenv

from planner import plan_actions
from executor import AgentExecutor
from modes.hybrid_runner import HybridRunner

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

load_dotenv()


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

        if "query_optimizer_reasoning" in context:
            print("Query optimizer reasoning:", context["query_optimizer_reasoning"])

        if "selected_result_indices" in context:
            print("Selected result indices:", context["selected_result_indices"])

        if "result_ranking_reasoning" in context:
            print("Result ranking reasoning:", context["result_ranking_reasoning"])

        if "last_scraped_url" in context:
            print("Last scraped URL:", context["last_scraped_url"])

        if "last_scraped_urls" in context:
            print("Last scraped URLs:")
            for url in context["last_scraped_urls"]:
                print(" -", url)

        if "page_summaries" in context:
            print("\nMini Summaries:")
            for idx, item in enumerate(context["page_summaries"], start=1):
                print(f"\nSource {idx}: {item.get('url')}")
                print(item.get("mini_summary", ""))

        if "last_summary" in context:
            print("\nFinal Agent Answer:")
            print(context["last_summary"])


def main():
    instruction = input("Enter instruction: ").strip()
    mode = input("Enter mode (headless/hybrid): ").strip().lower()

    plan = plan_actions(instruction)

    print("\nPlanned actions:")
    print(json.dumps(plan, indent=2))

    llm_client = build_llm_client()

    if mode == "hybrid":
        runner = HybridRunner(
            instruction=instruction,
            llm_client=llm_client,
        )
        result = runner.run_plan(plan)
        pretty_print_result(result)
        save_trace(runner.trace_logger, "latest_run_trace.json")
    else:
        executor = AgentExecutor(instruction=instruction)
        result = executor.run_plan(plan)
        pretty_print_result(result)
        save_trace(executor.trace_logger, "latest_run_trace.json")

    print("\nSaved trace to latest_run_trace.json")


if __name__ == "__main__":
    main()