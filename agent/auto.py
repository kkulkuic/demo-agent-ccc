"""Auto mode: plan from instruction + page context, then execute with shared browser session."""
from typing import Optional
import os

from core.browser import run_in_browser_thread
from core.consent import dismiss_cookie_consent
from planner import plan_actions
from executor import BrowserAgent


def run_auto_agent(
    instruction: str,
    start_url: str,
    session_id: str,
    enable_viz: bool = False,
    snapshot_dir: Optional[str] = None,
):
    """
    Run the automatic pipeline: navigate, get context, plan, execute each action.
    Uses shared browser session via session_id; all page ops run on the browser thread.
    """
    def _nav_and_context(page):
        page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(500)
        dismiss_cookie_consent(page)
        return page.content() or ""

    context = run_in_browser_thread(session_id, _nav_and_context)
    MAX_PLANNER_CONTEXT_CHARS = 80_000
    if len(context) > MAX_PLANNER_CONTEXT_CHARS:
        context = context[:MAX_PLANNER_CONTEXT_CHARS]
    plan = plan_actions(instruction, context)
    actions = plan.get("actions") or []

    for i, action in enumerate(actions):
        def _run_one(page, a=action, idx=i):
            agent = BrowserAgent(page=page, enable_viz=enable_viz)
            agent.execute(a)
            path = None
            if snapshot_dir:
                os.makedirs(snapshot_dir, exist_ok=True)
                path = os.path.join(snapshot_dir, f"screenshot_step_{idx}.png")
            agent.snapshot(idx, path=path)
        run_in_browser_thread(session_id, lambda page, a=action, idx=i: _run_one(page, a, idx))

    return {"steps": len(actions), "plan": plan}
