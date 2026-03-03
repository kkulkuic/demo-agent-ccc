"""Headless fetch tools: get page title and description without a visible browser."""
from typing import Any, Dict

from langchain_core.tools import tool
from playwright.sync_api import sync_playwright


def get_web_page_info_headless(url: str) -> Dict[str, Any]:
    """
    Visit a URL using a headless browser and return page title and a short description or text snippet.
    Used when a headed browser is not needed (e.g. Chat/HITL background fetch).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, timeout=60000)
            title = page.title()
            description = page.locator('meta[name="description"]').get_attribute("content")
            if not description:
                description = page.evaluate("() => document.body.innerText.slice(0, 300)")
            return {
                "url": url,
                "title": title,
                "description": (description or "").strip() or "No description found.",
            }
        except Exception as e:
            return {"url": url, "title": None, "description": None, "error": str(e)}
        finally:
            browser.close()


@tool
def get_web_page_info(url: str) -> str:
    """
    Visits a URL using a headless browser and returns the page title
    and a short description or text snippet.
    """
    result = get_web_page_info_headless(url)
    if "error" in result and result["error"]:
        return f"Error: {result['error']}"
    return f"Title: {result.get('title', '')}\nDescription: {result.get('description', '')}"
