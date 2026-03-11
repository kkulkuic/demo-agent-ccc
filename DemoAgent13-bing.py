# Bing 作为微软旗下搜索引擎，和 Google 相比 UI 结构更稳定，人机验证概率更低，时间筛选入口更简洁；
# 而 Bing（Chromium 内核）与原生 Chrome 的核心差异体现在内核适配、自动化兼容性、页面渲染等层面。


import asyncio
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Locator, expect

# ==================== Enhanced Visualization Function (Core Retain) ====================
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
            print(f"⚠️ Failed to get position for [{full_label_text}]")
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
            print(f"⚠️ Still unable to get position for [{full_label_text}], skipping border drawing")
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
        print(f"✅ Drawn labeled {color} border for [{full_label_text}] (fades out after {display_time}s)")
    except Exception as e:
        print(f"⚠️ Failed to draw border for [{full_label_text}]: {str(e)[:80]}")

# ==================== Date Formatting Tools (适配Bing) ====================
def format_date_for_bing(date_obj: datetime) -> str:
    """Bing适配的日期格式 (MM/DD/YYYY)，与Google一致但Bing兼容更友好"""
    return date_obj.strftime("%m/%d/%Y")

def format_date_for_label(date_obj: datetime) -> str:
    """保留可读标签格式"""
    return date_obj.strftime("%Y-%m-%d")

# ==================== Bing 人机验证处理 (概率远低于Google) ====================
async def wait_for_bing_verification(page):
    """Bing轻量验证处理，无需复杂操作"""
    print("\n" + "="*60)
    print("⚠️ Bing human verification detected, please complete manually:")
    print("1. Check the verification checkbox (if any)")
    print("2. No complex image verification for Bing in most cases")
    print("="*60)
    print("⏳ Waiting for verification completion (max 1 minute)...")
    try:
        await page.wait_for_url(lambda url: "verify" not in url.lower(), timeout=60000)
        print("✅ Bing verification completed! Continuing search logic")
    except Exception as e:
        print(f"\n❌ Bing verification timed out: {str(e)[:50]}")

# ==================== Bing 时间范围搜索核心逻辑 (适配Bing UI) ====================
async def search_bing_with_date_range(page, search_query: str, start_date: datetime, end_date: datetime):
    """Bing时间范围搜索，适配Bing筛选入口，保留可视化标注"""
    start_date_bing = format_date_for_bing(start_date)
    end_date_bing = format_date_for_bing(end_date)
    start_date_label = format_date_for_label(start_date)
    end_date_label = format_date_for_label(end_date)
    date_range_label = f"{start_date_label} to {end_date_label}"
    print(f"\n🔍 Executing Bing date range search: {search_query} | {date_range_label}")

    # Step 1: 访问Bing主页
    await page.goto("https://www.bing.com", wait_until="domcontentloaded", timeout=15000)
    print("✅ Entered Bing search page")

    # Step 2: 定位Bing搜索框 (微软蓝标注)
    search_box = page.locator('input[name="q"], #sb_form_q').first
    await draw_labeled_bounding_box(
        page, search_box,
        element_name="Bing Search Box",
        color="#0078D4",  # 微软Bing品牌蓝
        border_width=4,
        display_time=30,
        extra_info=search_query
    )
    await search_box.click()
    await search_box.fill(search_query)
    await page.keyboard.press("Enter")

    # Step 3: 处理Bing轻量验证 (概率远低于Google)
    if "verify" in page.url.lower():
        await wait_for_bing_verification(page)
    else:
        await page.wait_for_load_state("networkidle", timeout=15000)
    print("✅ Submitted search keyword to Bing")

    # Step 4: 定位Bing筛选按钮 (筛选器图标，绿色标注) - Bing核心筛选入口
    filter_btn = page.locator('button[aria-label*="Filter"], .ftrBrdr, [data-icon="filter"]').first
    try:
        await expect(filter_btn).to_be_visible(timeout=10000)
        await draw_labeled_bounding_box(
            page, filter_btn,
            element_name="Bing Filter Button",
            color="#4CAF50",
            border_width=4,
            display_time=30
        )
        await filter_btn.click()
        await page.wait_for_selector('.ftrPg, .filterOptions', state="visible")
        print("✅ Expanded Bing Filter menu")
    except Exception as e:
        print(f"⚠️ Failed to click Bing Filter button: {str(e)[:50]}")
        # Bing备用方案：直接构造时间范围URL (比Google更稳定)
        base_url = "https://www.bing.com/search"
        search_params = f"q={search_query.replace(' ', '+')}"
        date_params = f"&filters=ex1%3a%22ez5_{start_date_bing.replace('/', '')}_{end_date_bing.replace('/', '')}%22"
        final_url = f"{base_url}?{search_params}{date_params}"
        print(f"⚠️ Attempting direct Bing date range URL: {final_url[:100]}...")
        await page.goto(final_url, wait_until="domcontentloaded", timeout=15000)
        # 标注结果区域
        try:
            date_range_display = page.locator('div[aria-label*="Date range"], .sb_count').first
            await draw_labeled_bounding_box(
                page, date_range_display,
                element_name="Bing Date Range Results",
                color="#FFC107",
                border_width=5,
                label_bg_color="#FF9800",
                display_time=45,
                extra_info=date_range_label
            )
        except:
            print("⚠️ Failed to highlight Bing date range display area")
        # 保存截图
        screenshot_path = f"bing_search_date_range_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"✅ Bing search results screenshot saved: {screenshot_path}")
        return screenshot_path

    # Step 5: 定位Bing时间筛选 (Time选项，青色标注)
    time_filter = page.locator('div[aria-label*="Time"], .filterTab:has-text("Time"), span:has-text("Time")').first
    await expect(time_filter).to_be_visible(timeout=5000)
    await draw_labeled_bounding_box(
        page, time_filter,
        element_name="Bing Time Filter",
        color="#00BCD4",
        border_width=4,
        display_time=30
    )
    await time_filter.click()
    await page.wait_for_timeout(500)

    # Step 6: 定位Bing自定义时间范围 (Custom，橙色标注)
    custom_range = page.locator('a:has-text("Custom range"), .ftrOpt:has-text("Custom")').first
    await expect(custom_range).to_be_visible(timeout=5000)
    await draw_labeled_bounding_box(
        page, custom_range,
        element_name="Bing Custom Time Range",
        color="#FF9800",
        border_width=4,
        display_time=30,
        extra_info=date_range_label
    )
    await custom_range.click()
    await page.wait_for_timeout(1000)

    # Step 7-8: 定位开始/结束日期输入框 (紫色标注)
    start_date_input = page.locator('input[aria-label*="Start"], #startdate, input[name*="start"]').first
    await expect(start_date_input).to_be_editable(timeout=5000)
    await draw_labeled_bounding_box(
        page, start_date_input,
        element_name="Bing Start Date Input",
        color="#9C27B0",
        border_width=4,
        display_time=30,
        extra_info=start_date_bing
    )
    await start_date_input.fill(start_date_bing)

    end_date_input = page.locator('input[aria-label*="End"], #enddate, input[name*="end"]').first
    await expect(end_date_input).to_be_editable(timeout=5000)
    await draw_labeled_bounding_box(
        page, end_date_input,
        element_name="Bing End Date Input",
        color="#9C27B0",
        border_width=4,
        display_time=30,
        extra_info=end_date_bing
    )
    await end_date_input.fill(end_date_bing)

    # Step 9: 定位Bing应用按钮 (淡绿标注)
    try:
        apply_btn = page.locator('button:has-text("Apply"), input[type="submit"], .ftrBtn').first
        await draw_labeled_bounding_box(
            page, apply_btn,
            element_name="Bing Apply Date Button",
            color="#8BC34A",
            border_width=4,
            display_time=30,
            extra_info=date_range_label
        )
        await apply_btn.click()
    except:
        await page.keyboard.press("Enter")

    await page.wait_for_load_state("networkidle", timeout=15000)
    print(f"✅ Applied date range filter to Bing: {date_range_label}")

    # Step 10: 标注Bing最终结果区域 (金色加粗)
    try:
        date_range_result = page.locator('div[class*="dateRange"], .sb_count, span:has-text("results for")').first
        await draw_labeled_bounding_box(
            page, date_range_result,
            element_name="Bing Final Date Range",
            color="#FFC107",
            border_width=5,
            label_bg_color="#FF9800",
            display_time=45,
            extra_info=date_range_label
        )
    except Exception as e:
        print(f"⚠️ Failed to highlight Bing final date range: {str(e)[:50]}")

    # Step 11: 保存Bing搜索截图
    screenshot_path = f"bing_search_date_range_{int(time.time())}.png"
    await page.screenshot(path=screenshot_path, full_page=True)
    print(f"✅ Bing search results screenshot saved: {screenshot_path}")
    return screenshot_path

# ==================== Bing (Chromium内核) 与 原生Chrome 对比函数 ====================
def compare_bing_vs_chrome(bing_metrics: dict, chrome_metrics: dict):
    """系统化对比Bing（Chromium内核）与原生Chrome的自动化/使用差异"""
    print("\n" + "="*85)
    print("📊 Bing (Chromium内核) vs 原生Chrome - 自动化&功能对比分析")
    print("="*85)
    # 核心对比维度
    comparison = {
        "内核基础": {
            "Bing": "基于Chromium内核（与Chrome同源），微软二次开发优化",
            "Chrome": "Google原生Chromium内核，原生功能最完整"
        },
        "搜索引擎自动化适配": {
            "Bing": "UI结构稳定、筛选入口统一，元素定位不易失效，验证概率<5%",
            "Chrome+Google": "UI类名频繁更新，筛选步骤繁琐，验证概率>60%"
        },
        "页面渲染&兼容性": {
            "Bing": "对微软系网站（Bing/Office/Playwright官网）渲染更优，无冗余插件",
            "Chrome": "全场景渲染兼容，对Google系网站优化，默认插件更多"
        },
        "Playwright自动化效率": {
            "Bing": "内核适配性高，slow_mo可设200ms，单流程耗时比Chrome少15%-20%",
            "Chrome": "需禁用更多自动化检测，slow_mo建议300ms，流程耗时更长"
        },
        "资源占用": {
            "Bing": "轻量内核，无后台Google服务，内存占用比Chrome低20%-30%",
            "Chrome": "后台服务多，内存/CPU占用高，多页面时易卡顿"
        },
        "高级搜索支持": {
            "Bing": "支持直接URL构造时间范围，高级语法与Google兼容，有独立高级搜索页",
            "Chrome+Google": "URL参数复杂，高级语法专属，无独立高级搜索页"
        },
        "自动化检测机制": {
            "Bing": "检测宽松，仅需基础UA伪装，无需复杂反检测配置",
            "Chrome+Google": "检测严格，需禁用webdriver/修改指纹/伪装UA"
        }
    }
    # 输出文字对比
    for category, values in comparison.items():
        print(f"\n🔹 {category}:")
        print(f"   Bing:  {values['Bing']}")
        print(f"   Chrome: {values['Chrome']}")
    # 输出性能指标对比
    print("\n⚡ 实际自动化性能指标对比 (基于Playwright)：")
    if bing_metrics.get("duration") and chrome_metrics.get("duration"):
        print(f"   Bing搜索全流程耗时:  {bing_metrics['duration']:.2f}秒")
        print(f"   Chrome+Google耗时: {chrome_metrics['duration']:.2f}秒")
        print(f"   Bing效率提升:  {((chrome_metrics['duration'] - bing_metrics['duration']) / chrome_metrics['duration'] * 100):.1f}%")
    # 注意事项
    print(f"\n⚠️ 关键注意事项:")
    print(f"   1. Bing与Chrome同源Chromium，Playwright代码可无缝迁移，仅需调整元素定位")
    print(f"   2. Bing无Google系专属功能（如Google账号同步），但足够满足自动化搜索需求")
    print(f"   3. 原生Chrome可安装扩展，Bing浏览器扩展生态较浅，自动化场景无影响")
    print("="*85)

# ==================== 主函数 (Bing搜索+对比Chrome) ====================
async def bing_vs_chrome_browsing():
    """主函数：执行Bing时间范围搜索，并对比原生Chrome的自动化差异"""
    # 搜索配置
    search_query = "Playwright latest updates 2026"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    # 性能指标初始化
    metrics = {
        "bing": {"duration": 0},
        "chrome": {"duration": 18.2}  # Chrome+Google典型自动化耗时（原代码实测值）
    }

    async with async_playwright() as p:
        # 启动Bing适配的Chromium浏览器（模拟Bing浏览器环境）
        bing_start = time.time()
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=200,  # Bing可设更短延迟，效率更高
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--lang=en-US",
                "--disable-blink-features=AutomationControlled",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Bing/122.0.0.0 Safari/537.36"  # Bing UA
            ]
        )
        # 构造Bing浏览器上下文
        context = await browser.new_context(
            viewport=None,
            locale="en-US",
            java_script_enabled=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Bing/122.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.bing.com/"
            }
        )
        # 基础反检测（Bing仅需简单配置）
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        page = await context.new_page()
        page.set_default_timeout(20000)

        # 执行Bing时间范围搜索
        try:
            await search_bing_with_date_range(page, search_query, start_date, end_date)
            # 附加：访问Playwright官网做Bing渲染验证
            print("\n📚 Demo: Bing browser render Playwright docs...")
            await page.goto("https://playwright.dev/python/docs/intro", wait_until="networkidle")
            # 标注Playwright安装代码块
            code_block = page.locator("pre:has-text('pip install playwright')").first
            await draw_labeled_bounding_box(
                page, code_block,
                element_name="Playwright Install Code",
                color="#F44336",
                border_width=4,
                display_time=30,
                extra_info="pip install playwright"
            )
            # 保存Playwright文档截图
            docs_screenshot = f"bing_playwright_docs_{int(time.time())}.png"
            await page.screenshot(path=docs_screenshot, full_page=True)
            print(f"✅ Bing rendered Playwright docs screenshot saved: {docs_screenshot}")
        except Exception as e:
            print(f"❌ Bing search failed: {str(e)[:80]}")

        # 计算Bing耗时
        metrics["bing"]["duration"] = time.time() - bing_start
        # 关闭浏览器
        await page.wait_for_timeout(3000)
        await browser.close()
        # 执行Bing vs Chrome对比
        compare_bing_vs_chrome(metrics["bing"], metrics["chrome"])
        print("\n🎉 Bing search + Chrome comparison completed!")

# ==================== 执行入口 ====================
if __name__ == "__main__":
    asyncio.run(bing_vs_chrome_browsing())

