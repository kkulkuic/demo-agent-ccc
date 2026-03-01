"""Auto mode: plan from instruction + page context, then execute with shared browser session."""
from typing import Optional

from core.browser import get_page
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
    Uses shared browser session via session_id; does not close the browser.
    """
    page = get_page(session_id)
    page.goto(start_url, wait_until="networkidle")
    page.wait_for_timeout(500)
    dismiss_cookie_consent(page)

    context = page.content()
    plan = plan_actions(instruction, context)
    actions = plan.get("actions") or []

    agent = BrowserAgent(
        page=page,
        enable_viz=enable_viz,
    )

    for i, action in enumerate(actions):
        agent.execute(action)
        path = None
        if snapshot_dir:
            import os
            os.makedirs(snapshot_dir, exist_ok=True)
            path = os.path.join(snapshot_dir, f"screenshot_step_{i}.png")
        agent.snapshot(i, path=path)

    # Do not close browser; session remains for app
    return {"steps": len(actions), "plan": plan}
