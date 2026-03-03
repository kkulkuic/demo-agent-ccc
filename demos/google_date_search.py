"""
Demo: Headful browsing with date-range search on Google.
Uses tools.debug_tools and core.visualization. Run from project root.
"""
import asyncio
import time
from datetime import datetime, timedelta

from playwright.async_api import async_playwright

# Import from merged project (run from Agent-Broswer root)
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.debug_tools import search_with_date_range_async, format_date_for_search


async def headful_browsing_with_date_search():
    """Headful mode: click, screenshot, bounding box + date range search."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=200,
            args=["--start-maximized", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(viewport=None, locale="en-US", java_script_enabled=True)
        page = await context.new_page()
        page.set_default_timeout(10000)

        search_query = "Playwright latest updates 2026"
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        try:
            path = await search_with_date_range_async(page, search_query, start_date, end_date)
            if path:
                print(f"Search result screenshot: {path}")
        except Exception as e:
            print(f"Date range search failed: {str(e)[:80]}")

        print("\nDemo: Playwright docs headful interaction...")
        await page.goto("https://playwright.dev/python/docs/intro", wait_until="domcontentloaded")
        code_block = page.locator("pre:has-text('pip install')").first
        try:
            box = await code_block.bounding_box()
            if box:
                await page.evaluate("""({box_id, x, y, w, h}) => {
                    const el = document.createElement('div');
                    el.id = box_id;
                    el.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;border:2px solid red;z-index:9999;pointer-events:none`;
                    document.body.appendChild(el);
                    setTimeout(() => document.getElementById(box_id)?.remove(), 5000);
                }""", {"box_id": f"box-{int(time.time())}", "x": box["x"], "y": box["y"], "w": box["width"], "h": box["height"]})
        except Exception:
            pass
        copy_btn = page.locator('button:has-text("Copy")').first
        if await copy_btn.count() > 0:
            await copy_btn.click()
        screenshot_path = f"playwright_docs_headful_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"Docs screenshot: {screenshot_path}")
        await page.wait_for_timeout(10000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(headful_browsing_with_date_search())
