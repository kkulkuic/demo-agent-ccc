"""Legacy entry: one-off auto run. For integrated app use: streamlit run app.py"""
from core.browser import start_browser_session, stop_browser_session
from agent.auto import run_auto_agent

def run_agent(instruction: str, start_url: str, session_id: str = None, enable_viz: bool = False):
    sid = session_id or "main-script-session"
    start_browser_session(sid)
    try:
        return run_auto_agent(instruction=instruction, start_url=start_url, session_id=sid, enable_viz=enable_viz)
    finally:
        if session_id is None:
            stop_browser_session(sid)


if __name__ == "__main__":
    run_agent(
        instruction="Search for a product and add it to cart.",
        start_url="https://www.saucedemo.com/",
    )
    print("Done. Browser closed.")
