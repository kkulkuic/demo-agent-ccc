
import asyncio
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Locator

# ==================== 工具函数：可视化+日期处理 ====================
async def draw_bounding_box(page, locator: Locator, color: str = "red", line_width: int = 2):
    """绘制元素边框（bounding boxes），可视化定位结果"""
    try:
        # 获取元素位置和尺寸
        bounding_box = await locator.bounding_box()
        if not bounding_box:
            print("⚠️ 无法获取元素边框位置")
            return
        
        # 创建临时边框元素（不影响页面原有布局）
        box_id = f"bounding-box-{int(time.time())}"
        await page.evaluate("""
            ({box_id, x, y, width, height, color, line_width}) => {
                // 创建边框元素
                const box = document.createElement('div');
                box.id = box_id;
                box.style.position = 'absolute';
                box.style.left = `${x}px`;
                box.style.top = `${y}px`;
                box.style.width = `${width}px`;
                box.style.height = `${height}px`;
                box.style.border = `${line_width}px solid ${color}`;
                box.style.zIndex = '9999';  // 置顶显示
                box.style.pointerEvents = 'none';  // 不影响点击
                document.body.appendChild(box);
                // 5秒后自动移除边框
                setTimeout(() => {
                    const el = document.getElementById(box_id);
                    if (el) el.remove();
                }, 5000);
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
        print(f"✅ 已绘制 {color} 边框（5秒后自动消失）")
    except Exception as e:
        print(f"⚠️ 绘制边框失败：{str(e)[:50]}")

def format_date_for_search(date_obj: datetime) -> str:
    """格式化日期为搜索兼容格式（MM/DD/YYYY）"""
    return date_obj.strftime("%m/%d/%Y")

async def search_with_date_range(page, search_query: str, start_date: datetime, end_date: datetime):
    """执行指定日期范围的搜索（Google搜索适配）"""
    print(f"\n🔍 执行日期范围搜索：{search_query} | {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
    
    # Step 1: 访问Google搜索
    await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
    print("✅ 进入Google搜索页面")
    
    # Step 2: 定位并点击搜索框（绘制边框）
    search_box = page.locator('textarea[name="q"]').first
    await draw_bounding_box(page, search_box, "blue")  # 蓝色边框标记搜索框
    await search_box.click()
    await search_box.fill(search_query)
    await page.keyboard.press("Enter")
    await page.wait_for_load_state("domcontentloaded")
    print("✅ 提交搜索关键词")
    
    # Step 3: 点击「工具」展开日期筛选
    tools_btn = page.locator('div:has-text("Tools")').first
    await draw_bounding_box(page, tools_btn, "green")  # 绿色边框标记工具按钮
    await tools_btn.click()
    await asyncio.sleep(1)
    
    # Step 4: 选择「自定义时间范围」
    any_time_btn = page.locator('span:has-text("Any time")').first
    await any_time_btn.click()
    await asyncio.sleep(0.5)
    
    custom_range_btn = page.locator('span:has-text("Custom range")').first
    await draw_bounding_box(page, custom_range_btn, "orange")  # 橙色边框标记自定义范围
    await custom_range_btn.click()
    await asyncio.sleep(1)
    
    # Step 5: 输入日期范围
    start_date_input = page.locator('input[aria-label="Start date"]').first
    end_date_input = page.locator('input[aria-label="End date"]').first
    
    # 填充开始日期（绘制边框）
    await draw_bounding_box(page, start_date_input, "purple")
    await start_date_input.fill(format_date_for_search(start_date))
    
    # 填充结束日期（绘制边框）
    await draw_bounding_box(page, end_date_input, "purple")
    await end_date_input.fill(format_date_for_search(end_date))
    
    # 确认日期选择
    await page.keyboard.press("Enter")
    await page.wait_for_load_state("domcontentloaded")
    print(f"✅ 应用日期范围筛选：{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
    # Step 6: 截图保存搜索结果（包含所有边框）
    screenshot_path = f"google_search_date_range_{int(time.time())}.png"
    await page.screenshot(path=screenshot_path, full_page=True)
    print(f"✅ 搜索结果截图已保存：{screenshot_path}")
    
    return screenshot_path

# ==================== 主函数：Headful浏览+日期搜索 ====================
async def headful_browsing_with_date_search():
    """Headful模式：点击+截图+绘制边框 + 指定日期范围搜索"""
    async with async_playwright() as p:
        # 1. 启动Headful浏览器（可视化模式）
        browser = await p.chromium.launch(
            headless=False,  # 启用可视化窗口
            slow_mo=200,     # 真人级操作速度
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        
        context = await browser.new_context(
            viewport=None,  # 最大化窗口
            locale="en-US",
            java_script_enabled=True
        )
        page = await context.new_page()
        page.set_default_timeout(10000)
        
        # 2. 示例：搜索「Playwright最新更新」+ 过去30天日期范围
        search_query = "Playwright latest updates 2026"
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)  # 过去30天
        
        # 3. 执行日期范围搜索（核心功能）
        try:
            await search_with_date_range(page, search_query, start_date, end_date)
        except Exception as e:
            print(f"❌ 日期范围搜索失败：{str(e)[:80]}")
        
        # 4. 额外演示：Playwright文档的Headful交互（点击+截图+边框）
        print("\n📚 演示Playwright文档的Headful交互...")
        await page.goto("https://playwright.dev/python/docs/intro", wait_until="domcontentloaded")
        
        # 定位代码块，绘制红色边框
        code_block = page.locator("pre:has-text('pip install')").first
        await draw_bounding_box(page, code_block)
        
        # 点击代码块复制按钮（如果存在）
        copy_btn = page.locator('button:has-text("Copy")').first
        if await copy_btn.count() > 0:
            await draw_bounding_box(page, copy_btn, "green")
            await copy_btn.click()
            print("✅ 点击代码复制按钮")
        
        # 截图保存文档页面（包含边框）
        docs_screenshot = f"playwright_docs_headful_{int(time.time())}.png"
        await page.screenshot(path=docs_screenshot, full_page=True)
        print(f"✅ 文档页面截图已保存：{docs_screenshot}")
        
        # 5. 保持浏览器打开10秒，便于查看效果
        print("\n🎉 所有操作完成！浏览器将在10秒后关闭...")
        await page.wait_for_timeout(10000)
        
        # 6. 清理资源
        await browser.close()
        print("✅ 浏览器已关闭")

# ==================== 执行入口 ====================
if __name__ == "__main__":
    # 支持的日期范围扩展示例：
    # - 过去24小时：start_date = datetime.now() - timedelta(hours=24)
    # - 过去7天：start_date = datetime.now() - timedelta(days=7)
    # - 自定义固定日期：start_date = datetime(2026, 1, 1), end_date = datetime(2026, 1, 31)
    
    asyncio.run(headful_browsing_with_date_search())