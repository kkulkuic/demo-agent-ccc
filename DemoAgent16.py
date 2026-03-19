import asyncio
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Locator, expect
from typing import Optional, Dict, Any

# ==================== 核心工具函数（保留并优化） ====================
async def draw_labeled_bounding_box(
    page,
    locator: Locator,
    element_name: str,
    color: str = "red",
    border_width: int = 4,
    label_bg_color: str = None,
    display_time: int = 30,
    extra_info: str = ""
):
    """绘制带标签的高亮边框（保留原有逻辑）"""
    if label_bg_color is None:
        label_bg_color = color

    full_label_text = element_name
    if extra_info:
        full_label_text = f"{element_name}: {extra_info}"

    try:
        await locator.wait_for(state="visible", timeout=15000)
        await locator.scroll_into_view_if_needed()

        bounding_box = await locator.bounding_box()
        if not bounding_box:
            print(f"⚠️ 无法获取[{full_label_text}]的位置信息")
            bounding_box = await page.evaluate("""(element) => {
                const rect = element.getBoundingClientRect();
                return {
                    x: rect.left + window.scrollX,
                    y: rect.top + window.scrollY,
                    width: rect.width,
                    height: rect.height
                };
            }""", locator)

        if not bounding_box:
            print(f"⚠️ 仍然无法获取[{full_label_text}]的位置，跳过绘制")
            return

        box_id = f"labeled-box-{int(time.time())}-{element_name.replace(' ', '-')[:10]}"
        label_id = f"{box_id}-label"

        await page.evaluate("""
            ({
                box_id, label_id, x, y, width, height,
                color, border_width, full_label_text, label_bg_color, display_time
            }) => {
                const oldBox = document.getElementById(box_id);
                const oldLabel = document.getElementById(label_id);
                if (oldBox) oldBox.remove();
                if (oldLabel) oldLabel.remove();

                const box = document.createElement('div');
                box.id = box_id;
                box.style.position = 'absolute';
                box.style.left = `${x}px`;
                box.style.top = `${y}px`;
                box.style.width = `${width}px`;
                box.style.height = `${height}px`;
                box.style.border = `${border_width}px solid ${color}`;
                box.style.zIndex = '99999';
                box.style.pointerEvents = 'none';
                box.style.boxSizing = 'border-box';
                box.style.backgroundColor = 'transparent';
                box.style.opacity = '1';
                box.style.transition = 'opacity 0.5s ease-in-out, border 0.5s ease-in-out';
                box.style.outline = '1px solid rgba(255,255,255,0.5)';

                const label = document.createElement('div');
                label.id = label_id;
                label.style.position = 'absolute';
                label.style.left = `${x}px`;
                label.style.top = `${y - 30}px`;
                label.style.backgroundColor = label_bg_color;
                label.style.color = 'white';
                label.style.padding = '4px 12px';
                label.style.borderRadius = '6px';
                label.style.fontSize = '14px';
                label.style.fontWeight = '600';
                label.style.fontFamily = 'Arial, Helvetica, sans-serif';
                label.style.zIndex = '100000';
                label.style.pointerEvents = 'none';
                label.style.boxShadow = '0 3px 6px rgba(0,0,0,0.2)';
                label.style.whiteSpace = 'nowrap';
                label.style.opacity = '1';
                label.style.transition = 'opacity 0.5s ease-in-out, transform 0.3s ease';
                label.style.transform = 'translateY(0)';
                label.innerText = full_label_text;

                document.body.appendChild(box);
                document.body.appendChild(label);

                setTimeout(() => {
                    label.style.opacity = '0';
                    label.style.transform = 'translateY(-5px)';

                    setTimeout(() => {
                        box.style.opacity = '0';

                        setTimeout(() => {
                            if (document.getElementById(box_id)) document.getElementById(box_id).remove();
                            if (document.getElementById(label_id)) document.getElementById(label_id).remove();
                        }, 500);
                    }, 200);
                }, display_time * 1000);
            }
        """, {
            "box_id": box_id,
            "label_id": label_id,
            "x": bounding_box["x"],
            "y": bounding_box["y"],
            "width": bounding_box["width"],
            "height": bounding_box["height"],
            "color": color,
            "border_width": border_width,
            "full_label_text": full_label_text,
            "label_bg_color": label_bg_color,
            "display_time": display_time
        })

        print(f"✅ 已为[{full_label_text}]绘制{color}高亮边框（{display_time}秒后淡出）")

    except Exception as e:
        print(f"⚠️ 绘制[{full_label_text}]边框失败: {str(e)[:80]}")

def format_date_for_google(date_obj: datetime) -> str:
    return date_obj.strftime("%m/%d/%Y")

def format_date_for_label(date_obj: datetime) -> str:
    return date_obj.strftime("%Y-%m-%d")

async def wait_for_human_verification(page):
    """等待人工验证（保留原有逻辑）"""
    print("\n" + "="*60)
    print("⚠️ 检测到Google人机验证，请手动完成：")
    print("1. 勾选浏览器中的'I'm not a robot'复选框")
    print("2. 若出现图片验证（选择公交车/红绿灯/桥梁等），手动选择对应图片")
    print("3. 完成后点击'Verify'或'Next'按钮")
    print("4. 等待页面自动跳转到搜索结果")
    print("="*60)
    print("⏳ 等待验证完成（最长3分钟）...")

    try:
        await page.wait_for_url(
            lambda url: "sorry/index" not in url and "recaptcha" not in url.lower(),
            timeout=180000
        )
        print("✅ 人工验证完成！继续执行搜索逻辑")
    except Exception as e:
        print(f"\n❌ 验证超时（3分钟）: {str(e)[:50]}")
        print("⚠️ 将尝试直接构造日期范围URL继续执行")

# ==================== Agent核心类（新增） ====================
class GoogleSearchAgent:
    """Google搜索Agent，处理用户输入的任务并执行"""
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.supported_tasks = [
            "google_search",  # Google日期范围搜索
            "playwright_docs" # Playwright文档交互
        ]

    async def initialize(self):
        """初始化浏览器环境"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            slow_mo=300,
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--lang=en-US",
                "--disable-blink-features=AutomationControlled",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ]
        )

        self.context = await self.browser.new_context(
            viewport=None,
            locale="en-US",
            java_script_enabled=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/"
            }
        )

        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        self.page = await self.context.new_page()
        self.page.set_default_timeout(20000)
        print("✅ Agent浏览器环境初始化完成")

    async def parse_user_task(self, user_input: str) -> Dict[str, Any]:
        """解析用户输入的任务，提取关键参数"""
        task_info = {
            "task_type": None,
            "search_query": None,
            "days_range": 30,  # 默认近30天
            "error": None
        }

        # 简单的任务解析逻辑（可扩展为更复杂的NLP解析）
        user_input_lower = user_input.lower().strip()

        # 匹配Google搜索任务
        if "google搜索" in user_input_lower or "google search" in user_input_lower:
            task_info["task_type"] = "google_search"
            # 提取搜索关键词（截取"搜索"后到"近"前的内容）
            if "搜索" in user_input_lower:
                query_part = user_input_lower.split("搜索")[1]
                if "近" in query_part:
                    query_part = query_part.split("近")[0]
                task_info["search_query"] = query_part.strip() or "Playwright latest updates 2026"
            # 提取时间范围（如"近7天"）
            import re
            day_match = re.search(r"近(\d+)天", user_input)
            if day_match:
                task_info["days_range"] = int(day_match.group(1))

        # 匹配Playwright文档任务
        elif "playwright文档" in user_input_lower or "playwright docs" in user_input_lower:
            task_info["task_type"] = "playwright_docs"

        else:
            task_info["error"] = f"不支持的任务类型！支持的任务：{', '.join(self.supported_tasks)}"

        return task_info

    async def execute_google_search(self, search_query: str, days_range: int = 30):
        """执行Google日期范围搜索任务"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_range)

        start_date_google = format_date_for_google(start_date)
        end_date_google = format_date_for_google(end_date)
        start_date_label = format_date_for_label(start_date)
        end_date_label = format_date_for_label(end_date)
        date_range_label = f"{start_date_label} to {end_date_label}"

        print(f"\n🔍 执行Google日期范围搜索: {search_query} | {date_range_label}")

        # 访问Google主页
        await self.page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
        print("✅ 进入Google搜索页面")

        # 搜索框操作
        search_box = self.page.locator('textarea[name="q"]').first
        await draw_labeled_bounding_box(
            self.page, search_box,
            element_name="Search Box",
            color="#2196F3",
            border_width=4,
            display_time=30,
            extra_info=search_query
        )
        await search_box.click()
        await search_box.fill(search_query)
        await self.page.keyboard.press("Enter")

        # 处理人机验证
        if "sorry/index" in self.page.url or "recaptcha" in self.page.url.lower():
            await wait_for_human_verification(self.page)
        else:
            await self.page.wait_for_load_state("networkidle", timeout=15000)

        print("✅ 提交搜索关键词")

        # 尝试点击Tools按钮（失败则直接构造URL）
        try:
            tools_btn = self.page.locator('//div[contains(@class, "hdtb-mitem") and (text()="Tools" or @aria-label="Tools")]').first
            await expect(tools_btn).to_be_visible(timeout=10000)
            await draw_labeled_bounding_box(
                self.page, tools_btn,
                element_name="Tools Button",
                color="#4CAF50",
                border_width=4,
                display_time=30
            )
            await tools_btn.click()
            await self.page.wait_for_selector('//div[contains(@class, "hdtbUc")]', state="visible")
            print("✅ 展开Tools菜单")

            # 时间筛选操作
            any_time_btn = self.page.locator('//div[contains(@class, "hdtb-mitem") and (text()="Any time" or text()="Any time")]').first
            await expect(any_time_btn).to_be_visible(timeout=5000)
            await draw_labeled_bounding_box(
                self.page, any_time_btn,
                element_name="Time Filter Button",
                color="#00BCD4",
                border_width=4,
                display_time=30
            )
            await any_time_btn.click()
            await self.page.wait_for_timeout(500)

            custom_range_btn = self.page.locator('//span[(text()="Custom range" or text()="Custom range")]').first
            await expect(custom_range_btn).to_be_visible(timeout=5000)
            await draw_labeled_bounding_box(
                self.page, custom_range_btn,
                element_name="Custom Time Range",
                color="#FF9800",
                border_width=4,
                display_time=30,
                extra_info=date_range_label
            )
            await custom_range_btn.click()
            await self.page.wait_for_timeout(1000)

            # 开始日期输入
            start_date_input = self.page.locator('input[aria-label="Start date"], input[aria-label="Start date"]').first
            await expect(start_date_input).to_be_editable(timeout=5000)
            await draw_labeled_bounding_box(
                self.page, start_date_input,
                element_name="Start Date Input",
                color="#9C27B0",
                border_width=4,
                display_time=30,
                extra_info=start_date_google
            )
            await start_date_input.fill(start_date_google)

            # 结束日期输入
            end_date_input = self.page.locator('input[aria-label="End date"], input[aria-label="End date"]').first
            await expect(end_date_input).to_be_editable(timeout=5000)
            await draw_labeled_bounding_box(
                self.page, end_date_input,
                element_name="End Date Input",
                color="#9C27B0",
                border_width=4,
                display_time=30,
                extra_info=end_date_google
            )
            await end_date_input.fill(end_date_google)

            # 应用日期筛选
            try:
                apply_btn = self.page.locator('//g-button[contains(text(), "Apply") or contains(text(), "Apply")]').first
                await draw_labeled_bounding_box(
                    self.page, apply_btn,
                    element_name="Apply Date Button",
                    color="#8BC34A",
                    border_width=4,
                    display_time=30,
                    extra_info=date_range_label
                )
                if await apply_btn.count() > 0:
                    await apply_btn.click()
                else:
                    await self.page.keyboard.press("Enter")
            except:
                await self.page.keyboard.press("Enter")

            await self.page.wait_for_load_state("networkidle", timeout=15000)
            print(f"✅ 应用日期范围筛选: {date_range_label}")

            # 高亮最终结果
            try:
                date_range_result = self.page.locator('//div[contains(@class, "hdtb-tl") or contains(text(), start_date_label) or contains(text(), end_date_label)]').first
                await draw_labeled_bounding_box(
                    self.page, date_range_result,
                    element_name="Final Date Range",
                    color="#FFC107",
                    border_width=5,
                    label_bg_color="#FF9800",
                    display_time=45,
                    extra_info=date_range_label
                )
            except Exception as e:
                print(f"⚠️ 高亮最终日期范围失败: {str(e)[:50]}")

        except Exception as e:
            print(f"⚠️ 点击Tools按钮失败: {str(e)[:50]}")
            # 直接构造URL
            base_url = "https://www.google.com/search"
            search_params = f"q={search_query.replace(' ', '+')}"
            date_params = f"&tbs=cdr:1,cd_min:{start_date_google},cd_max:{end_date_google}"
            final_url = f"{base_url}?{search_params}{date_params}"
            print(f"⚠️ 尝试直接访问日期范围URL: {final_url[:100]}...")

            await self.page.goto(final_url, wait_until="domcontentloaded", timeout=15000)
            if "sorry/index" in self.page.url or "recaptcha" in self.page.url.lower():
                await wait_for_human_verification(self.page)

            # 高亮日期范围结果
            try:
                date_range_display = self.page.locator('//span[contains(text(), "Showing results for") or contains(text(), "Displaying results for time range")]').first
                await draw_labeled_bounding_box(
                    self.page, date_range_display,
                    element_name="Date Range Results",
                    color="#FFC107",
                    border_width=5,
                    label_bg_color="#FF9800",
                    display_time=45,
                    extra_info=date_range_label
                )
            except:
                print("⚠️ 高亮日期范围显示区域失败")

        # 保存截图
        screenshot_path = f"google_search_date_range_{int(time.time())}.png"
        await self.page.screenshot(path=screenshot_path, full_page=True)
        print(f"✅ 搜索结果截图已保存: {screenshot_path}")
        return screenshot_path

    async def execute_playwright_docs(self):
        """执行Playwright文档交互任务"""
        print("\n📚 执行Playwright文档交互任务...")
        await self.page.goto("https://playwright.dev/python/docs/intro", wait_until="networkidle", timeout=20000)

        # 定位代码块并绘制边框
        code_block_locators = [
            self.page.locator("div[class*='language-python'] pre"),
            self.page.locator("pre:has-text('pip install playwright')"),
            self.page.locator("code:has-text('pip install')").locator("..")
        ]

        code_block = None
        for locator in code_block_locators:
            if await locator.count() > 0:
                code_block = locator.first
                break

        if code_block:
            await draw_labeled_bounding_box(
                self.page, code_block,
                element_name="Playwright Installation Code Block",
                color="#F44336",
                border_width=4,
                display_time=30,
                extra_info="pip install playwright"
            )
        else:
            print("⚠️ 未找到代码块元素，跳过边框绘制")

        # 定位复制按钮并绘制边框
        copy_btn_locators = [
            self.page.locator("button[aria-label='Copy code to clipboard']"),
            self.page.locator('button:has-text("Copy")'),
            self.page.locator("button[class*='copy-button']")
        ]

        copy_btn = None
        for locator in copy_btn_locators:
            if await locator.count() > 0:
                copy_btn = locator.first
                break

        if copy_btn:
            await draw_labeled_bounding_box(
                self.page, copy_btn,
                element_name="Code Copy Button",
                color="#4CAF50",
                border_width=4,
                display_time=30
            )
            await copy_btn.click()
            print("✅ 点击代码复制按钮")
        else:
            print("⚠️ 未找到复制按钮")

        # 保存截图
        docs_screenshot = f"playwright_docs_headful_{int(time.time())}.png"
        await self.page.screenshot(path=docs_screenshot, full_page=True)
        print(f"✅ 文档页面截图已保存: {docs_screenshot}")
        return docs_screenshot

    async def run_task(self, user_input: str):
        """执行用户输入的任务"""
        # 解析任务
        task_info = await self.parse_user_task(user_input)
        if task_info["error"]:
            print(f"❌ 任务解析失败: {task_info['error']}")
            return

        # 初始化浏览器
        await self.initialize()

        # 执行对应任务
        try:
            if task_info["task_type"] == "google_search":
                await self.execute_google_search(
                    search_query=task_info["search_query"],
                    days_range=task_info["days_range"]
                )
            elif task_info["task_type"] == "playwright_docs":
                await self.execute_playwright_docs()
            print("\n🎉 任务执行完成！")
        except Exception as e:
            print(f"❌ 任务执行失败: {str(e)[:80]}")
        finally:
            # 保留浏览器15秒后关闭
            print("⏳ 浏览器将在15秒后关闭...")
            await self.page.wait_for_timeout(15000)
            await self.cleanup()

    async def cleanup(self):
        """清理浏览器资源"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("✅ 浏览器资源已清理")

# ==================== 交互式入口（新增） ====================
async def interactive_chat():
    """交互式聊天界面，接收用户任务并执行"""
    print("="*80)
    print("🤖 Google Search Agent 已启动！")
    print("📋 支持的任务示例：")
    print("   1. Google搜索 Playwright最新更新 近7天")
    print("   2. 搜索 Python教程 近30天")
    print("   3. Playwright文档")
    print("💡 输入'退出'或'exit'结束程序")
    print("="*80)

    agent = GoogleSearchAgent()

    while True:
        # 获取用户输入
        user_input = input("\n请输入你要执行的任务: ").strip()

        # 退出条件
        if user_input.lower() in ["退出", "exit", "quit"]:
            print("👋 程序已退出")
            break

        # 空输入处理
        if not user_input:
            print("⚠️ 请输入有效的任务！")
            continue

        # 执行任务
        await agent.run_task(user_input)

# ==================== 执行入口 ====================
if __name__ == "__main__":
    asyncio.run(interactive_chat())