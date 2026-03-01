import asyncio
import time
from playwright.async_api import async_playwright

# 工具函数：安全点击（简化版，仅传page+selector）
async def safe_click(page, selector, timeout=1000):
    try:
        loc = page.locator(selector).first
        await loc.wait_for(timeout=timeout, state="visible")
        await loc.click(timeout=timeout)
        return True
    except Exception as e:
        print(f"⚠️ 点击失败 [{selector}]：{str(e)[:30]}")
        return False

# 工具函数：安全提取文本（修复参数，适配locator直接传入）
async def safe_extract_text(locator, timeout=1000):
    """直接传入locator，无需selector，避免参数错误"""
    try:
        await locator.wait_for(timeout=timeout)
        return await locator.inner_text()
    except Exception as e:
        print(f"⚠️ 提取文本失败：{str(e)[:30]}")
        return ""

# 主函数：无头模式后台运行（彻底修复）
async def headless_playwright_automation():
    # 日志头部
    start_time = time.time()
    print("="*60)
    print(f"【无头模式】Playwright 自动化开始运行 | {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    async with async_playwright() as p:
        # 1. 启动无头浏览器
        browser = await p.chromium.launch(
            headless=True,
            slow_mo=80,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-images",
                "--disable-fonts",
                "--disable-gpu",
            ]
        )

        # 2. 创建上下文（适配无头模式）
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True,
            locale="en-US",
            bypass_csp=True
        )
        page = await context.new_page()

        # 3. 拦截无用资源
        blocked_resources = [
            "**/*.{png,jpg,jpeg,gif,svg}",
            "**/*.{woff,woff2,ttf}",
            "**/*analytics*",
            "**/*ads*",
        ]
        for pattern in blocked_resources:
            await page.route(pattern, lambda route: route.abort())

        # 4. 核心操作流程（修复所有错误）
        # Step 1: 访问Python文档
        print("\n🌐 访问 Playwright Python 文档...")
        try:
            await page.goto(
                "https://playwright.dev/python/docs/intro",
                wait_until="domcontentloaded",
                timeout=15000
            )
            print(f"✅ 文档加载完成 | URL: {page.url}")
        except Exception as e:
            print(f"❌ 文档访问失败：{str(e)[:50]}")
            await browser.close()
            return

        # Step 2: 页面缩放（无头模式生效）
        await page.evaluate("document.body.style.zoom = '1.1'")
        print("🔍 页面缩放至 110% 完成")

        # Step 3: 跳过侧边栏操作（无头模式下定位不稳定，直接跳过）
        print("📂 跳过侧边栏操作（无头模式优化）")

        # Step 4: 滚动到代码区域
        await page.evaluate("window.scrollTo(0, 600)")
        print("📜 滚动到代码区域完成")

        # Step 5: 提取Python代码（修复参数错误，核心修复）
        print("\n📝 提取 Python 代码片段...")
        code_content = ""
        code_blocks = page.locator("pre")  # 所有代码块
        block_count = await code_blocks.count()

        # 遍历代码块（修复：传入locator而非selector）
        if block_count > 0:
            for i in range(min(block_count, 3)):
                block_locator = code_blocks.nth(i)  # 获取第i个代码块的locator
                temp_code = await safe_extract_text(block_locator)  # 直接传locator
                # 筛选Python代码
                if any(key in temp_code for key in ["pip", "async def", "await", "python"]):
                    code_content = temp_code
                    print(f"✅ 找到 Python 代码块（第{i+1}段）")
                    break

        # 兜底逻辑：确保代码有内容
        if not code_content:
            code_content = """# Playwright Python 安装与使用
pip install playwright
playwright install

# 基础示例
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://playwright.dev/python")
        await browser.close()

asyncio.run(main())"""
            print("⚠️ 未找到代码块，使用兜底 Python 代码")

        # 保存代码
        code_file = f"playwright_python_code_headless_{int(time.time())}.txt"
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(code_content)
        print(f"✅ 代码已保存 | 文件：{code_file}")
        print(f"📄 代码预览：\n{code_content[:150]}...\n")

        # Step 6: 无头模式截图（稳定）
        print("📸 无头模式截图...")
        screenshot_file = f"playwright_screenshot_headless_{int(time.time())}.png"
        try:
            await page.screenshot(path=screenshot_file, full_page=False)
            print(f"✅ 截图保存 | 文件：{screenshot_file}")
        except Exception as e:
            print(f"❌ 截图失败：{str(e)[:50]}")

        # Step 7: 多标签操作（稳定）
        print("\n🌐 新开标签页访问 GitHub...")
        try:
            new_page = await context.new_page()
            await new_page.goto("https://github.com/microsoft/playwright", timeout=10000)
            await new_page.close()
            print("✅ GitHub 标签页操作完成")
        except Exception as e:
            print(f"❌ 多标签操作失败：{str(e)[:50]}")

        # Step 8: 还原缩放
        await page.evaluate("document.body.style.zoom = '1'")
        print("🔙 页面缩放还原完成")

        # 关闭资源
        await browser.close()

        # 运行结果汇总
        end_time = time.time()
        duration = end_time - start_time
        print("\n" + "="*60)
        print(f"【无头模式】自动化运行完成 | {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️  总耗时：{duration:.2f} 秒")
        print(f"📁 生成文件：{code_file} | {screenshot_file}")
        print("="*60)

# 执行入口
if __name__ == "__main__":
    asyncio.run(headless_playwright_automation())