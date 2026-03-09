import json
import pandas as pd
import streamlit as st

from planner import plan_actions
from executor import AgentExecutor
from modes.hybrid_runner import HybridRunner

st.set_page_config(page_title="Firecrawl Demo Agent", layout="wide")

st.title("Firecrawl Research Agent")
st.caption("Search → Scrape → Summarize with execution tracing")

mode = st.selectbox(
    "Execution Mode",
    [
        "firecrawl_headless",
        "hybrid",
    ],
    index=0
)

instruction = st.text_area(
    "Enter instruction",
    placeholder="Example: latest firecrawl documentation",
    height=120
)

run_btn = st.button("Run Agent")


def extract_search_results(result_obj):
    results = []

    if hasattr(result_obj, "web") and result_obj.web:
        for item in result_obj.web:
            results.append({
                "title": getattr(item, "title", ""),
                "url": getattr(item, "url", ""),
                "description": getattr(item, "description", "")
            })

    elif isinstance(result_obj, dict):
        for item in result_obj.get("web", []):
            if isinstance(item, dict):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", "")
                })

    return results


def extract_markdown(result_obj):
    if hasattr(result_obj, "markdown"):
        return result_obj.markdown or ""
    if isinstance(result_obj, dict):
        return result_obj.get("markdown", "") or ""
    return str(result_obj)


if run_btn:
    if not instruction.strip():
        st.warning("Please enter an instruction.")
        st.stop()

    plan = plan_actions(instruction)

    st.subheader("Planned Actions")
    st.code(json.dumps(plan, indent=2), language="json")

    if mode == "firecrawl_headless":
        executor = AgentExecutor(instruction=instruction, mode=mode)
        result = executor.run_plan(plan)

    elif mode == "hybrid":
        runner = HybridRunner(instruction=instruction)
        result = runner.run_google_search_flow()

    else:
        st.error("Mode not implemented yet.")
        st.stop()

    context = result.get("context", {})
    trace = result.get("trace", {})
    steps = trace.get("steps", [])

    hitl_triggered = context.get("hitl_triggered", False)
    hitl_resume_time = context.get("hitl_resume_time_seconds", 0.0)

    st.subheader("Final Agent Answer")
    st.write(f"**Mode:** {mode}")

    summary = context.get("last_summary")
    if summary:
        st.success(summary)
    else:
        st.info("No final summary produced.")

    st.subheader("Execution Metrics")

    if steps:
        total_runtime = sum(step["duration_seconds"] for step in steps)
        avg_runtime = total_runtime / len(steps)
        slowest = max(steps, key=lambda x: x["duration_seconds"])

        col1, col2, col3, col4, col5, col6 = st.columns(6)

        col1.metric("Total Runtime (s)", round(total_runtime, 3))
        col2.metric("Steps Executed", len(steps))
        col3.metric("Average Step Time (s)", round(avg_runtime, 3))
        col4.metric(
            "Slowest Step",
            f"{slowest['tool']} ({round(slowest['duration_seconds'], 3)}s)"
        )
        col5.metric("Mode", mode)
        col6.metric("HITL", "Yes" if hitl_triggered else "No")

        if hitl_triggered:
            st.info(
                f"HITL triggered due to bot verification. "
                f"Resume delay: {hitl_resume_time} seconds."
            )

    st.subheader("Step Outputs")

    for item in result["outputs"]:
        tool = item["tool"]

        with st.expander(f"Step {item['step']} — {tool}", expanded=True):
            st.write("Args:", item["args"])

            if "error" in item:
                st.error(item["error"])
                continue

            step_result = item["result"]

            if tool == "search_web":
                search_results = extract_search_results(step_result)

                if search_results:
                    for idx, res in enumerate(search_results, start=1):
                        st.markdown(f"**{idx}. {res['title']}**")
                        st.write(res["url"])
                        st.write(res["description"])
                        st.markdown("---")
                else:
                    st.text(str(step_result)[:2000])

            elif tool in ["scrape_first_search_result", "scrape_url", "scrape_url_fc"]:
                markdown_text = extract_markdown(step_result)

                scraped_url = context.get("last_scraped_url") or context.get("playwright_final_url")
                if scraped_url:
                    st.markdown("**Scraped URL:**")
                    st.write(scraped_url)

                st.markdown("**Markdown Preview**")
                st.text(markdown_text[:3500])

            elif tool == "summarize_last_scrape":
                st.markdown("**Summary Output**")
                st.text(str(step_result))

            else:
                st.text(str(step_result)[:2000])

    st.subheader("Execution Trace")

    if steps:
        trace_df = pd.DataFrame(steps)[
            ["step_number", "tool", "duration_seconds", "status"]
        ]
        st.dataframe(trace_df, use_container_width=True)

    with st.expander("Raw Trace JSON"):
        st.code(json.dumps(trace, indent=2), language="json")