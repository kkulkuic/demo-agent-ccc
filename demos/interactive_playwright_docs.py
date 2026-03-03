"""
Demo: Interactive Playwright docs – hover, smooth scroll, multi-tab, extract code.
All labels and prints in English. Run from project root.
"""
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def playwright_docs_interactive():
    from playwright.async_api import async_playwright

    playwright = None
    browser = None
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=False,
            slow_mo=400,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized", "--no-sandbox", "--lang=en-US"],
        )
        context = await browser.new_context(viewport=None, locale="en-US")
        page = await context.new_page()

        print("\nVisit Playwright site...")
        await page.goto("https://playwright.dev/", wait_until="domcontentloaded")
        await asyncio.sleep(1)

        print("Hover and click Docs...")
        docs_link = page.locator('nav a:has-text("Docs")').first
        await docs_link.hover()
        await asyncio.sleep(0.8)
        await docs_link.click()
        await asyncio.sleep(2)

        print("\nGo to Intro...")
        await page.goto("https://playwright.dev/docs/intro")
        await asyncio.sleep(2)

        print("\nSmooth scroll...")
        await page.evaluate("window.scrollBy({ top: 400, behavior: 'smooth' });")
        await asyncio.sleep(1.5)

        print("\nToggle sidebar...")
        sidebar_btn = page.locator('button[aria-label="Toggle sidebar"]').first
        if await sidebar_btn.count() > 0:
            await sidebar_btn.click()
            await asyncio.sleep(1)

        print("\nClick Writing Tests...")
        writing_tests = page.locator('a:has-text("Writing tests")').first
        if await writing_tests.count() > 0:
            await writing_tests.hover()
            await writing_tests.click()
            await asyncio.sleep(2.5)

        await page.evaluate("window.scrollBy({ top: 500, behavior: 'smooth' });")
        await asyncio.sleep(1.5)

        code_blocks = page.locator("pre")
        code1 = await code_blocks.nth(0).inner_text() if await code_blocks.count() > 0 else ""
        code2 = await code_blocks.nth(1).inner_text() if await code_blocks.count() >= 2 else ""

        with open("playwright_two_codes.txt", "w", encoding="utf-8") as f:
            f.write("===== First block =====\n")
            f.write(code1 + "\n\n===== Second block =====\n")
            f.write(code2)
        print("Saved two code blocks to playwright_two_codes.txt")

        screenshot_file = f"playwright_full_page_{int(time.time())}.png"
        await page.screenshot(path=screenshot_file, full_page=True)
        print(f"Full page screenshot: {screenshot_file}")

        print("\nOpen new tab (GitHub)...")
        new_page = await context.new_page()
        await new_page.goto("https://github.com/microsoft/playwright")
        await asyncio.sleep(2)

        print("\nBring doc page to front, scroll to top...")
        await page.bring_to_front()
        await page.evaluate("window.scrollTo({ top: 0, behavior: 'smooth' });")
        await asyncio.sleep(1.5)

        await new_page.close()

        print("\nAll interactive steps done.")
        await page.wait_for_timeout(10000)

    except Exception as e:
        print(f"Error: {str(e)[:100]}")
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


if __name__ == "__main__":
    asyncio.run(playwright_docs_interactive())
