"""Debug tools: bounding box overlay, date formatting, optional date-range search. No agent/UI deps."""
from datetime import datetime
from typing import Optional


def draw_bounding_box_on_locator(page, locator, color: str = "red", line_width: int = 2) -> None:
    """Thin wrapper over core.visualization.draw_bounding_box for a given locator."""
    from core.visualization import draw_bounding_box
    draw_bounding_box(page, locator, color=color, line_width=line_width, auto_remove_seconds=5)


def format_date_for_search(date_obj: datetime) -> str:
    """Format date for search (e.g. MM/DD/YYYY for Google)."""
    return date_obj.strftime("%m/%d/%Y")


def search_with_date_range(page, search_query: str, start_date: datetime, end_date: datetime) -> Optional[str]:
    """
    Google date-range search workflow: goto Google, search, open Tools -> Custom range, fill dates.
    page: sync Playwright page. Returns screenshot path or None.
    """
    import time as _time
    try:
        page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
        search_box = page.locator('textarea[name="q"]').first
        draw_bounding_box_on_locator(page, search_box, "blue")
        search_box.click()
        search_box.fill(search_query)
        page.keyboard.press("Enter")
        page.wait_for_load_state("domcontentloaded")
        tools_btn = page.locator('div:has-text("Tools")').first
        draw_bounding_box_on_locator(page, tools_btn, "green")
        tools_btn.click()
        page.wait_for_timeout(1000)
        page.locator('span:has-text("Any time")').first.click()
        page.wait_for_timeout(500)
        page.locator('span:has-text("Custom range")').first.click()
        page.wait_for_timeout(1000)
        start_input = page.locator('input[aria-label="Start date"]').first
        end_input = page.locator('input[aria-label="End date"]').first
        draw_bounding_box_on_locator(page, start_input, "purple")
        start_input.fill(format_date_for_search(start_date))
        end_input.fill(format_date_for_search(end_date))
        page.keyboard.press("Enter")
        page.wait_for_load_state("domcontentloaded")
        path = f"google_search_date_range_{int(_time.time())}.png"
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return None


async def search_with_date_range_async(page, search_query: str, start_date: datetime, end_date: datetime) -> Optional[str]:
    """Async version of Google date-range search for async Playwright page."""
    import time as _time
    try:
        await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
        search_box = page.locator('textarea[name="q"]').first
        await search_box.click()
        await search_box.fill(search_query)
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("domcontentloaded")
        tools_btn = page.locator('div:has-text("Tools")').first
        await tools_btn.click()
        await page.wait_for_timeout(1000)
        await page.locator('span:has-text("Any time")').first.click()
        await page.wait_for_timeout(500)
        await page.locator('span:has-text("Custom range")').first.click()
        await page.wait_for_timeout(1000)
        start_input = page.locator('input[aria-label="Start date"]').first
        end_input = page.locator('input[aria-label="End date"]').first
        await start_input.fill(format_date_for_search(start_date))
        await end_input.fill(format_date_for_search(end_date))
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("domcontentloaded")
        path = f"google_search_date_range_{int(_time.time())}.png"
        await page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return None
