import asyncio
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Locator, expect

# ==================== 工具函数：可视化+日期处理 ====================
async def draw_bounding_box(page, locator: Locator, color: str = "red", line_width: int = 4):
    """绘制元素边框（bounding boxes），可视化定位结果"""
    try:
        # 先等待元素存在且可见，延长超时时间
        await locator.wait_for(state="visible", timeout=8000)
        # 强制滚动到元素可见区域
        await locator.scroll_into_view_if_needed()
        
        # 获取元素位置和尺寸
        bounding_box = await locator.bounding_box()
        if not bounding_box:
            print("⚠️ 无法获取元素边框位置，尝试强制计算")
            # 备选方案：通过evaluate获取元素位置
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
            print("⚠️ 仍然无法获取元素边框位置")
            return
        
        # 创建临时边框元素（不影响页面原有布局）
        box_id = f"bounding-box-{int(time.time())}"
        await page.evaluate("""
            ({box_id, x, y, width, height, color, line_width}) => {
                // 先移除同名边框（避免重复）
                const oldBox = document.getElementById(box_id);
                if (oldBox) oldBox.remove();
                
                // 创建边框元素
                const box = document.createElement('div');
                box.id = box_id;
                box.style.position = 'absolute';
                box.style.left = `${x}px`;
                box.style.top = `${y}px`;
                box.style.width = `${width}px`;
                box.style.height = `${height}px`;
                box.style.border = `${line_width}px solid ${color}`;
                box.style.zIndex = '99999';  // 提高层级，确保置顶
                box.style.pointerEvents = 'none';  // 不影响点击
                box.style.boxSizing = 'border-box';
                box.style.backgroundColor = 'transparent';
                document.body.appendChild(box);
                
                // 10秒后自动移除边框
                setTimeout(() => {
                    const el = document.getElementById(box_id);
                    if (el) el.remove();
                }, 10000);
            }
        """, {
            "box_id": box_id,
            "x": bounding_box["x"],
            "y": bounding_box["y"],
            "width": bounding_box["width"],
            "height": bounding_box["height"],
            "color": color,
            "line_width": line_width
        })
        print(f"✅ 已绘制 {color} 边框（10秒后自动消失）")
    except Exception as e:
        print(f"⚠️ 绘制边框失败：{str(e)[:80]}")

def format_date_for_google(date_obj: datetime) -> str:
    """格式化日期为Google搜索兼容格式（MM/DD/YYYY）"""
    return date_obj.strftime("%m/%d/%Y")

async def wait_for_human_verification(page):
    """【优先】等待用户手动完成Google人机验证"""
    print("\n" + "="*50)
    print("⚠️ 检测到Google人机验证，请手动完成：")
    print("1. 在浏览器窗口中勾选「I'm not a robot」复选框")
    print("2. 如有图片验证（选公交车/红绿灯/桥梁等），请手动选择对应图片")
    print("3. 完成后点击「验证」或「Next」按钮")
    print("4. 等待页面自动跳转到搜索结果页")
    print("="*50)
    print("⏳ 等待验证完成（最多等待3分钟）...")
    
    # 等待页面离开验证页（URL不再包含sorry/index/recaptcha）
    try:
        await page.wait_for_url(
            lambda url: "sorry/index" not in url and "recaptcha" not in url.lower(),
            timeout=180000  # 3分钟超时，足够完成手动验证
        )
        print("✅ 手动验证完成！继续执行搜索逻辑")
    except Exception as e:
        print(f"\n❌ 验证超时（3分钟）：{str(e)[:50]}")
        print("⚠️ 将尝试直接构造日期范围URL继续")

async def search_google_with_date_range(page, search_query: str, start_date: datetime, end_date: datetime):
    """执行Google指定日期范围的搜索（优先手动验证）"""
    print(f"\n🔍 执行Google日期范围搜索：{search_query} | {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
    
    # Step 1: 访问Google搜索
    await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
    print("✅ 进入Google搜索页面")
    
    # Step 2: 定位并点击搜索框（绘制蓝色边框）
    search_box = page.locator('textarea[name="q"]').first
    await draw_bounding_box(page, search_box, "blue")
    await search_box.click()
    await search_box.fill(search_query)
    await page.keyboard.press("Enter")
    
    # Step 3: 检查是否触发人机验证，优先手动处理
    if "sorry/index" in page.url or "recaptcha" in page.url.lower():
        await wait_for_human_verification(page)
    else:
        await page.wait_for_load_state("networkidle", timeout=15000)
    
    print("✅ 提交搜索关键词")
    
    # Step 4: 点击「Tools」展开日期筛选（优化定位器）
    tools_btn = page.locator('//div[contains(@class, "hdtb-mitem") and (text()="Tools" or @aria-label="Tools")]').first
    try:
        await expect(tools_btn).to_be_visible(timeout=10000)
        await draw_bounding_box(page, tools_btn, "green")  # 绿色边框标记Tools按钮
        await tools_btn.click()
        # 等待工具菜单展开
        await page.wait_for_selector('//div[contains(@class, "hdtbUc")]', state="visible")
        print("✅ 展开Tools菜单")
    except Exception as e:
        print(f"⚠️ 点击Tools按钮失败：{str(e)[:50]}")
        # 备用方案：直接构造Google日期范围URL
        base_url = "https://www.google.com/search"
        search_params = f"q={search_query.replace(' ', '+')}"
        date_params = f"&tbs=cdr:1,cd_min:{format_date_for_google(start_date)},cd_max:{format_date_for_google(end_date)}"
        final_url = f"{base_url}?{search_params}{date_params}"
        print(f"⚠️ 尝试直接访问日期范围URL：{final_url[:100]}...")
        
        await page.goto(final_url, wait_until="domcontentloaded", timeout=15000)
        # 再次检查验证（防止URL跳转后触发验证）
        if "sorry/index" in page.url or "recaptcha" in page.url.lower():
            await wait_for_human_verification(page)
        # 直接返回截图路径，跳过后续日期选择步骤
        screenshot_path = f"google_search_date_range_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"✅ 搜索结果截图已保存：{screenshot_path}")
        return screenshot_path
    
    # Step 5: 选择「Any time」→「Custom range」
    any_time_btn = page.locator('//div[contains(@class, "hdtb-mitem") and (text()="Any time" or text()="任何时间")]').first
    await expect(any_time_btn).to_be_visible(timeout=5000)
    await any_time_btn.click()
    await page.wait_for_timeout(500)
    
    # 支持中英文自定义范围文本
    custom_range_btn = page.locator('//span[(text()="Custom range" or text()="自定义范围")]').first
    await expect(custom_range_btn).to_be_visible(timeout=5000)
    await draw_bounding_box(page, custom_range_btn, "orange")  # 橙色边框标记自定义范围
    await custom_range_btn.click()
    await page.wait_for_timeout(1000)
    
    # Step 6: 输入开始/结束日期（紫色边框）
    start_date_input = page.locator('input[aria-label="Start date"], input[aria-label="开始日期"]').first
    end_date_input = page.locator('input[aria-label="End date"], input[aria-label="结束日期"]').first
    
    await expect(start_date_input).to_be_editable(timeout=5000)
    await draw_bounding_box(page, start_date_input, "purple")
    await start_date_input.fill(format_date_for_google(start_date))
    
    await expect(end_date_input).to_be_editable(timeout=5000)
    await draw_bounding_box(page, end_date_input, "purple")
    await end_date_input.fill(format_date_for_google(end_date))
    
    # 确认日期选择（优先点击Apply，失败则按Enter）
    try:
        apply_btn = page.locator('//g-button[contains(text(), "Apply") or contains(text(), "应用")]').first
        if await apply_btn.count() > 0:
            await apply_btn.click()
        else:
            await page.keyboard.press("Enter")
    except:
        await page.keyboard.press("Enter")
    
    await page.wait_for_load_state("networkidle", timeout=15000)
    print(f"✅ 应用日期范围筛选：{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
    # Step 7: 截图保存搜索结果
    screenshot_path = f"google_search_date_range_{int(time.time())}.png"
    await page.screenshot(path=screenshot_path, full_page=True)
    print(f"✅ 搜索结果截图已保存：{screenshot_path}")
    
    return screenshot_path

# ==================== 主函数：Headful模式+Google搜索+手动验证 ====================
async def headful_browsing_google():
    """Headful模式：Google搜索+日期筛选+手动验证+边框可视化"""
    async with async_playwright() as p:
        # 1. 启动浏览器（优化参数，降低被检测为机器人的概率）
        browser = await p.chromium.launch(
            headless=False,  # 可视化模式，方便手动验证
            slow_mo=300,     # 模拟真人操作速度（300ms延迟）
            args=[
                "--start-maximized",  # 最大化窗口
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--lang=en-US",  # 强制英文界面，减少本地化问题
                "--disable-blink-features=AutomationControlled",  # 隐藏自动化特征
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"  # 真实UA
            ]
        )
        
        # 2. 创建浏览器上下文（禁用webdriver检测）
        context = await browser.new_context(
            viewport=None,  # 跟随窗口大小
            locale="en-US",
            java_script_enabled=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/"
            }
        )
        
        # 禁用navigator.webdriver（关键：避免被Google检测为自动化工具）
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        page = await context.new_page()
        page.set_default_timeout(20000)  # 延长默认超时时间
        
        # 3. 示例：搜索「Playwright latest updates 2026」+ 过去30天
        search_query = "Playwright latest updates 2026"
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # 4. 执行Google日期范围搜索（核心逻辑）
        try:
            await search_google_with_date_range(page, search_query, start_date, end_date)
        except Exception as e:
            print(f"❌ Google日期范围搜索失败：{str(e)[:80]}")
        
        # 5. 额外演示：Playwright文档交互（红色粗边框）
        print("\n📚 演示Playwright文档的Headful交互...")
        await page.goto("https://playwright.dev/python/docs/intro", wait_until="networkidle", timeout=20000)
        
        # 定位代码块（确保找到pip install代码）
        code_block = page.locator("div[class*='language-python'] pre").first
        await page.wait_for_selector("div[class*='language-python'] pre", state="visible", timeout=10000)
        await draw_bounding_box(page, code_block)  # 默认红色，4px粗，10秒显示
        
        # 点击复制按钮（绿色边框）
        copy_btn = page.locator("button[aria-label='Copy code to clipboard']").first
        if await copy_btn.count() > 0:
            await draw_bounding_box(page, copy_btn, "green")
            await copy_btn.click()
            print("✅ 点击代码复制按钮")
        
        # 截图保存文档页面
        docs_screenshot = f"playwright_docs_headful_{int(time.time())}.png"
        await page.screenshot(path=docs_screenshot, full_page=True)
        print(f"✅ 文档页面截图已保存：{docs_screenshot}")
        
        # 6. 保持浏览器打开，便于查看结果
        print("\n🎉 所有操作完成！浏览器将在15秒后关闭...")
        await page.wait_for_timeout(15000)
        
        # 7. 清理资源
        await browser.close()
        print("✅ 浏览器已关闭")

# ==================== 执行入口 ====================
if __name__ == "__main__":
    # 支持自定义日期范围示例：
    # start_date = datetime(2026, 1, 1)  # 固定开始日期
    # end_date = datetime(2026, 1, 31)    # 固定结束日期
    
    asyncio.run(headful_browsing_google())