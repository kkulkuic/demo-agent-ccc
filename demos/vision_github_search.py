"""
Demo: GitHub search via vision (screenshot -> Claude -> Playwright code).
Uses tools.vision_tools. Run from project root.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright
from tools.vision_tools import parse_instruction_to_code_async, execute_action_code_async


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--lang=en-US"],
        )
        page = await browser.new_page(viewport={"width": 1920, "height": 1080}, locale="en-US")
        await page.goto("https://github.com", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        print("\n=== Parse natural language instruction ===")
        instruction = "On GitHub home, type 'playwright' in the search box and press Enter"
        action_code, narration = await parse_instruction_to_code_async(page, instruction)
        print("Narration:", narration)
        print("Action code:", action_code[:200] if action_code else "(none)")

        print("\n=== Execute browser actions ===")
        success, msg = await execute_action_code_async(page, action_code)
        print(f"Result: {msg}")

        await page.wait_for_timeout(5000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
