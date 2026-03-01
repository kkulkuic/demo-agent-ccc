"""Chat mode: ReAct agent with headed browser tools; model fallback via config."""
from typing import List

from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

import config
from tools.headed_tools import (
    open_url_headed,
    read_page_headed,
    find_text_on_page,
    click_on_page,
    type_text_on_page,
    close_browser_headed,
    scrape_webpage_headed,
)


def is_model_not_found_error(e: Exception) -> bool:
    txt = str(e).lower()
    return ("not_found" in txt and "model" in txt) or ("not_found_error" in txt)


def build_chat_agent(model_name: str, session_id: str):
    llm = ChatAnthropic(
        model=model_name,
        api_key=config.get_api_key(),
        temperature=0.2,
    )
    system_prompt = f"""You are a web navigation assistant that helps the user complete tasks across websites
(e.g., paying bills, setting up accounts, updating profiles). You MUST narrate your work.

You have a persistent headed browser session available via tools. The current session_id is: {session_id}

Output format for each response:
- Goal: one sentence
- Plan: 1–3 bullets (high-level)
- Live Log: short step-by-step updates in plain English (what you did + why)
- Checkpoint: clearly state what you need from the user next (confirm / provide info / take over)
- Result: what you found / current state

Critical rules:
1) Never ask for or store passwords, MFA codes, or full sensitive credentials.
2) Never submit payments, place orders, or finalize account changes without an explicit user confirmation.
3) If an action would submit, pay, delete, sign, or finalize: STOP and ask for confirmation.
4) Prefer pause points. After each major step, include a Checkpoint so the user can read and decide.
5) If a site shows a bot/verification/CAPTCHA wall, explain it and ask the user to complete it manually in the opened browser.

Tool use guidance:
- If the user provides a URL or asks you to check/navigate a site: use open_url_headed(session_id, url) first.
- Use read_page_headed and find_text_on_page to understand where you are.
- Use click_on_page for navigation clicks. Use type_text_on_page for non-sensitive inputs (never passwords/OTP).
- Use close_browser_headed when done.
"""
    tools = [
        open_url_headed,
        read_page_headed,
        find_text_on_page,
        click_on_page,
        type_text_on_page,
        close_browser_headed,
        scrape_webpage_headed,
    ]
    return create_react_agent(model=llm, tools=tools, prompt=system_prompt)


def get_model_candidates() -> List[str]:
    return config.get_model_candidates()
