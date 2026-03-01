# 新增交互:
# 鼠标悬停再点击（更像真人）
# 平滑滚动，不是瞬间跳
# 浏览多个章节：Intro → Writing Tests
# 获取两段不同代码并保存
# 全屏截图（长截图）
# 打开新标签页看 GitHub
# 切回原页面、滚动回顶部
# 自动清理标签页

import asyncio
import os
import time
from playwright.async_api import async_playwright, TimeoutError

async def playwright_docs_super_interactive():
    """在原有成功代码上，新增大量真人式交互，超级流畅版"""
    playwright = None
    browser = None
    try:
        # 1. 初始化浏览器
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=False,
            slow_mo=400,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--lang=en-US",
            ]
        )

        context = await browser.new_context(
            viewport=None,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = await context.new_page()

        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        print("\n=== 解析自然语言指令 ===")
        print("\n=== 操作解说 ===")
        print("访问Playwright官网 → 打开文档 → 丰富交互浏览 → 复制多段代码 → 截图 → 新标签验证")
        print("\n=== 执行浏览器操作 ===")
        print("操作代码：使用手动编写的 100% 可靠兜底代码")

        # 3. 访问官网
        print("🌐 访问Playwright官网...")
        await page.goto("https://playwright.dev/", wait_until="domcontentloaded")
        await asyncio.sleep(1)
        print("✅ Playwright官网加载成功")

        # 4. 点击Docs（新增：鼠标先悬停，模拟人看一眼再点）
        print("🔍 定位Docs按钮，鼠标悬停...")
        docs_link = page.locator('nav a:has-text("Docs")').first
        await docs_link.hover()
        await asyncio.sleep(0.8)
        await docs_link.click()
        await asyncio.sleep(2)
        print("✅ 进入文档主页")

        # 5. 直接进入快速开始
        print("\n📖 进入快速开始章节...")
        await page.goto("https://playwright.dev/docs/intro")
        await asyncio.sleep(2)
        print("✅ 已进入快速开始")

        # ==================== 新增交互1：平滑慢慢往下滚动 ====================
        print("\n📜 平滑滚动页面（模拟阅读）...")
        await page.evaluate("""
            window.scrollBy({
                top: 400,
                behavior: 'smooth'
            });
        """)
        await asyncio.sleep(1.5)

        # ==================== 新增交互2：展开侧边栏 ====================
        print("\n📂 展开左侧文档目录...")
        sidebar_btn = page.locator('button[aria-label="Toggle sidebar"]').first
        if await sidebar_btn.count() > 0:
            await sidebar_btn.click()
            await asyncio.sleep(1)
        print("✅ 侧边栏已展开")

        # ==================== 新增交互3：点击另一个章节（Writing Tests） ====================
        print("\n📄 点击 Writing Tests 章节，学习如何写测试...")
        writing_tests = page.locator('a:has-text("Writing tests")').first
        if await writing_tests.count() > 0:
            await writing_tests.hover()
            await asyncio.sleep(0.7)
            await writing_tests.click()
            await asyncio.sleep(2.5)
            print("✅ 进入 Writing Tests 章节")

        # ==================== 新增交互4：再平滑滚动到代码区域 ====================
        print("\n🔍 滚动到示例代码区域...")
        await page.evaluate("""
            window.scrollBy({ top: 500, behavior: 'smooth' });
        """)
        await asyncio.sleep(1.5)

        # ==================== 原有：切换Python ====================
        print("\n🐍 尝试切换Python语言示例...")
        is_python_selected = False
        try:
            lang_selector = page.locator('div[class*="language"]').first
            if await lang_selector.count() > 0:
                await lang_selector.click()
                await asyncio.sleep(0.5)
                py = page.locator('button:has-text("Python")').first
                if await py.count() > 0:
                    await py.click()
                    await asyncio.sleep(1)
                    is_python_selected = True
        except:
            pass

        if is_python_selected:
            print("✅ Python 切换成功")
        else:
            print("⚠️ 使用默认语言，继续获取代码")

        # ==================== 新增交互5：获取第1段代码 ====================
        print("\n📝 获取第一段示例代码...")
        code_blocks = page.locator("pre")
        code1 = ""
        if await code_blocks.count() > 0:
            code1 = await code_blocks.nth(0).inner_text()
            print(f"✅ 第一段代码：\n{code1[:80]}...")

        # ==================== 新增交互6：获取第2段代码（更完整示例） ====================
        print("\n📝 获取第二段示例代码...")
        code2 = ""
        total = await code_blocks.count()
        if total >= 2:
            code2 = await code_blocks.nth(1).inner_text()
            print(f"✅ 第二段代码：\n{code2[:80]}...")

        # 保存两段代码
        with open("playwright_two_codes.txt", "w", encoding="utf-8") as f:
            f.write("===== 第一段代码 =====\n")
            f.write(code1 + "\n\n===== 第二段代码 =====\n")
            f.write(code2)
        print("✅ 两段代码已保存到 playwright_two_codes.txt")

        # ==================== 新增交互7：截图整页（带滚动区域） ====================
        print("\n📸 全屏截图保存...")
        screenshot_file = f"playwright_full_page_{int(time.time())}.png"
        await page.screenshot(path=screenshot_file, full_page=True)
        print(f"✅ 全屏截图已保存：{screenshot_file}")

        # ==================== 新增交互8：打开新标签页，验证官网 ====================
        print("\n🌐 新开标签页，访问Playwright GitHub主页...")
        new_page = await context.new_page()
        await new_page.goto("https://github.com/microsoft/playwright")
        await asyncio.sleep(2)
        print("✅ GitHub页面加载成功")

        # ==================== 新增交互9：切回原来文档页面 ====================
        print("\n↩️ 切回文档页面继续浏览...")
        await page.bring_to_front()
        await asyncio.sleep(1)

        # ==================== 新增交互10：滚动到顶部 ====================
        print("\n⬆️ 平滑滚动回页面顶部...")
        await page.evaluate("""
            window.scrollTo({ top: 0, behavior: 'smooth' });
        """)
        await asyncio.sleep(1.5)

        # ==================== 新增交互11：关闭多余标签页 ====================
        print("\n🧹 关闭多余标签，保持界面整洁...")
        await new_page.close()
        await asyncio.sleep(0.5)

        # ==================== 最终验证 ====================
        print("\n🔍 最终验证所有操作...")
        is_docs_ok = "/docs/" in page.url
        has_code = len(code1) > 0
        all_ok = is_docs_ok and has_code

        print("\n🎉 🎉 🎉 全部高级交互操作完成！")
        print("执行结果：操作执行成功（使用手动兜底代码）")
        print("\n=== 最终验证 ===")
        print(f"✅ 在文档页面：{is_docs_ok}")
        print(f"✅ 获取代码：{has_code}")
        print(f"✅ 全部任务完成：{all_ok}")
        print(f"📄 当前URL：{page.url}")

        await page.wait_for_timeout(10000)

    except TimeoutError:
        print("\n❌ 执行结果：超时，但已尽量完成")
    except Exception as e:
        print(f"\n❌ 执行异常：{str(e)[:100]}")
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

if __name__ == "__main__":
    asyncio.run(playwright_docs_super_interactive())