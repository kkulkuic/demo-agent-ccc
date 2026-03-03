"""
Demo: Headless mode with resource blocking and code extraction from Playwright docs.
Run from project root.
"""
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def safe_extract_text(locator, timeout=1000):
    try:
        await locator.wait_for(timeout=timeout)
        return await locator.inner_text()
    except Exception as e:
        print(f"Extract failed: {str(e)[:30]}")
        return ""


async def headless_playwright_automation():
    from playwright.async_api import async_playwright

    start_time = time.time()
    print("=" * 60)
    print(f"[Headless] Playwright automation started | {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            slow_mo=80,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-images", "--disable-fonts", "--disable-gpu"],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True,
            locale="en-US",
            bypass_csp=True,
        )
        page = await context.new_page()

        blocked = ["**/*.{png,jpg,jpeg,gif,svg}", "**/*.{woff,woff2,ttf}", "**/*analytics*", "**/*ads*"]
        for pattern in blocked:
            await page.route(pattern, lambda route: route.abort())

        print("\nVisit Playwright Python docs...")
        await page.goto("https://playwright.dev/python/docs/intro", wait_until="domcontentloaded", timeout=15000)
        print(f"Loaded: {page.url}")

        await page.evaluate("document.body.style.zoom = '1.1'")
        await page.evaluate("window.scrollTo(0, 600)")

        print("\nExtract Python code snippets...")
        code_content = ""
        code_blocks = page.locator("pre")
        count = await code_blocks.count()
        for i in range(min(count, 3)):
            block = code_blocks.nth(i)
            temp = await safe_extract_text(block)
            if any(k in temp for k in ["pip", "async def", "await", "python"]):
                code_content = temp
                print(f"Found Python block {i + 1}")
                break

        if not code_content:
            code_content = "# Playwright Python\npip install playwright\nplaywright install"

        code_file = f"playwright_python_code_headless_{int(time.time())}.txt"
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(code_content)
        print(f"Saved: {code_file}")

        screenshot_file = f"playwright_screenshot_headless_{int(time.time())}.png"
        await page.screenshot(path=screenshot_file, full_page=False)
        print(f"Screenshot: {screenshot_file}")

        new_page = await context.new_page()
        await new_page.goto("https://github.com/microsoft/playwright", timeout=10000)
        await new_page.close()

        await browser.close()

    duration = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"[Headless] Done | {duration:.2f}s | {code_file} | {screenshot_file}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(headless_playwright_automation())
