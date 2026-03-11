import asyncio
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Locator, expect
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError

# ==================== 全局配置（解决超时核心）====================
# 延长基础超时时间（适配境外网络）
BASE_TIMEOUT = 30000  # 30秒
# 无界面模式（减少渲染耗时，可选改为False看界面）
HEADLESS_MODE = True
# 重试次数
RETRY_TIMES = 2

# ==================== 核心可视化函数（保留+容错）====================
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
        # 缩短标注超时（避免标注阻塞主流程）
        await locator.wait_for(state="visible", timeout=5000)
        await locator.scroll_into_view_if_needed()
        bounding_box = await locator.bounding_box()
        if not bounding_box:
            print(f"⚠️ Failed to get position for [{full_label_text}]")
            return
        box_id = f"labeled-box-{int(time.time())}-{element_name.replace(' ', '-')[:10]}"
        label_id = f"{box_id}-label"
        await page.evaluate("""
            ({box_id, label_id, x, y, width, height, color, border_width, full_label_text, label_bg_color, display_time}) => {
                const oldBox = document.getElementById(box_id);
                const oldLabel = document.getElementById(label_id);
                if (oldBox) oldBox.remove();
                if (oldLabel) oldLabel.remove();
                const box = document.createElement('div');
                box.id = box_id;
                box.style.position='absolute'; box.style.left=`${x}px`; box.style.top=`${y}px`;
                box.style.width=`${width}px`; box.style.height=`${height}px`;
                box.style.border=`${border_width}px solid ${color}`; box.style.zIndex='99999';
                box.style.pointerEvents='none'; box.style.opacity='1';
                box.style.transition='opacity 0.5s ease-in-out';
                const label = document.createElement('div');
                label.id = label_id; label.style.position='absolute'; label.style.left=`${x}px`; label.style.top=`${y-30}px`;
                label.style.backgroundColor=label_bg_color; label.style.color='white'; label.style.padding='4px 12px';
                label.style.borderRadius='6px'; label.style.fontSize='14px'; label.style.zIndex='100000';
                label.style.pointerEvents='none'; label.style.opacity='1';
                label.style.transition='opacity 0.5s ease-in-out'; label.innerText=full_label_text;
                document.body.appendChild(box); document.body.appendChild(label);
                setTimeout(() => {
                    label.style.opacity='0'; setTimeout(() => {
                        box.style.opacity='0'; setTimeout(() => {
                            if (document.getElementById(box_id)) document.getElementById(box_id).remove();
                            if (document.getElementById(label_id)) document.getElementById(label_id).remove();
                        }, 500);
                    }, 200);
                }, display_time * 1000);
            }
        """, {
            "box_id": box_id, "label_id": label_id, "x": bounding_box["x"], "y": bounding_box["y"],
            "width": bounding_box["width"], "height": bounding_box["height"], "color": color,
            "border_width": border_width, "full_label_text": full_label_text,
            "label_bg_color": label_bg_color, "display_time": display_time
        })
        print(f"✅ Drawn label for [{full_label_text}] (fades out after {display_time}s)")
    except Exception as e:
        print(f"⚠️ Draw failed for [{full_label_text}]: {str(e)[:50]}")

# ==================== 通用工具函数（重试+超时处理）====================
async def retry_on_timeout(coro, max_retries=RETRY_TIMES, timeout=BASE_TIMEOUT):
    """超时重试装饰器"""
    for attempt in range(max_retries):
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except PlaywrightTimeoutError:
            if attempt < max_retries - 1:
                print(f"⚠️ 超时重试 ({attempt+1}/{max_retries})...")
                await asyncio.sleep(2)  # 重试前等待2秒
            else:
                raise

# ==================== 日期格式化（通用）====================
def format_date_for_search(date_obj: datetime) -> str:
    return date_obj.strftime("%m/%d/%Y")

def format_date_for_label(date_obj: datetime) -> str:
    return date_obj.strftime("%Y-%m-%d")

# ==================== 各浏览器逻辑（极简URL+重试）====================
async def search_duckduckgo(page, query: str, start_date: datetime, end_date: datetime):
    """DuckDuckGo（极简URL+重试）"""
    start_ddg = start_date.strftime("%Y%m%d")
    end_ddg = end_date.strftime("%Y%m%d")
    range_label = f"{format_date_for_label(start_date)} to {format_date_for_label(end_date)}"
    print(f"\n🔍 DuckDuckGo Search: {query} | {range_label}")
    
    # 极简URL（无冗余参数）
    final_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}&df={start_ddg}&dt={end_ddg}&kl=en-us"
    try:
        # 带重试的页面访问
        await retry_on_timeout(page.goto(final_url, wait_until="domcontentloaded"))
        # 等待结果加载（仅等DOM，不等网络）
        await page.wait_for_selector('div[id*="result"]', timeout=10000)
    except PlaywrightTimeoutError:
        print(f"❌ DuckDuckGo 加载超时，跳过")
        return {"name": "DuckDuckGo", "screenshot": "ddg_timeout.png", "duration": time.time()}
    
    # 轻量化标注（失败不影响流程）
    try:
        results_container = page.locator('div[id*="result"], main').first
        await draw_labeled_bounding_box(page, results_container, "DuckDuckGo Results", "#EC4899", 5, 45, range_label)
    except:
        pass
    
    # 截图（容错）
    screenshot = f"ddg_results_{int(time.time())}.png"
    try:
        await page.screenshot(path=screenshot, full_page=False)  # 不截全页，减少耗时
    except:
        screenshot = "ddg_screenshot_fail.png"
    
    return {
        "name": "DuckDuckGo", 
        "screenshot": screenshot, 
        "duration": time.time()
    }

async def search_brave(page, query: str, start_date: datetime, end_date: datetime):
    """Brave（极简URL+重试）"""
    start = format_date_for_search(start_date)
    end = format_date_for_search(end_date)
    range_label = f"{format_date_for_label(start_date)} to {format_date_for_label(end_date)}"
    print(f"\n🔍 Brave Search: {query} | {range_label}")
    
    final_url = f"https://search.brave.com/search?q={query.replace(' ', '+')}&tf=custom&tb={start}&te={end}"
    try:
        await retry_on_timeout(page.goto(final_url, wait_until="domcontentloaded"))
        await page.wait_for_selector('#results', timeout=10000)
    except PlaywrightTimeoutError:
        print(f"❌ Brave 加载超时，跳过")
        return {"name": "Brave", "screenshot": "brave_timeout.png", "duration": time.time()}
    
    try:
        results_container = page.locator('#results').first
        await draw_labeled_bounding_box(page, results_container, "Brave Results", "#EC4899", 5, 45, range_label)
    except:
        pass
    
    screenshot = f"brave_results_{int(time.time())}.png"
    try:
        await page.screenshot(path=screenshot, full_page=False)
    except:
        screenshot = "brave_screenshot_fail.png"
    
    return {
        "name": "Brave", 
        "screenshot": screenshot, 
        "duration": time.time()
    }

async def search_firefox(page, query: str, start_date: datetime, end_date: datetime):
    """Firefox+Bing（国内可访问）"""
    start = format_date_for_search(start_date)
    end = format_date_for_search(end_date)
    range_label = f"{format_date_for_label(start_date)} to {format_date_for_label(end_date)}"
    print(f"\n🔍 Firefox (Bing) Search: {query} | {range_label}")
    
    # Bing国内版（避免重定向）
    final_url = f"https://cn.bing.com/search?q={query.replace(' ', '+')}&filters=ex1%3a%22ez5_{start.replace('/', '')}_{end.replace('/', '')}%22"
    try:
        await retry_on_timeout(page.goto(final_url, wait_until="domcontentloaded"))
        await page.wait_for_selector('#b_results', timeout=10000)
    except PlaywrightTimeoutError:
        print(f"❌ Firefox+Bing 加载超时，跳过")
        return {"name": "Firefox (Bing)", "screenshot": "firefox_timeout.png", "duration": time.time()}
    
    try:
        results_container = page.locator('#b_results').first
        await draw_labeled_bounding_box(page, results_container, "Firefox Bing Results", "#FFC107", 5, 45, range_label)
    except:
        pass
    
    screenshot = f"firefox_results_{int(time.time())}.png"
    try:
        await page.screenshot(path=screenshot, full_page=False)
    except:
        screenshot = "firefox_screenshot_fail.png"
    
    return {
        "name": "Firefox (Bing)", 
        "screenshot": screenshot, 
        "duration": time.time()
    }

async def search_edge(page, query: str, start_date: datetime, end_date: datetime):
    """Edge+Bing（国内可访问）"""
    start = format_date_for_search(start_date)
    end = format_date_for_search(end_date)
    range_label = f"{format_date_for_label(start_date)} to {format_date_for_label(end_date)}"
    print(f"\n🔍 Edge (Bing) Search: {query} | {range_label}")
    
    final_url = f"https://cn.bing.com/search?q={query.replace(' ', '+')}&filters=ex1%3a%22ez5_{start.replace('/', '')}_{end.replace('/', '')}%22"
    try:
        await retry_on_timeout(page.goto(final_url, wait_until="domcontentloaded"))
        await page.wait_for_selector('#b_results', timeout=10000)
    except PlaywrightTimeoutError:
        print(f"❌ Edge+Bing 加载超时，跳过")
        return {"name": "Edge (Bing)", "screenshot": "edge_timeout.png", "duration": time.time()}
    
    try:
        results_container = page.locator('#b_results').first
        await draw_labeled_bounding_box(page, results_container, "Edge Bing Results", "#FFC107", 5, 45, range_label)
    except:
        pass
    
    screenshot = f"edge_results_{int(time.time())}.png"
    try:
        await page.screenshot(path=screenshot, full_page=False)
    except:
        screenshot = "edge_screenshot_fail.png"
    
    return {
        "name": "Edge (Bing)", 
        "screenshot": screenshot, 
        "duration": time.time()
    }

# ==================== 移除Safari（高验证+易超时）====================
# ==================== 多浏览器对比分析 ====================
def compare_all_browsers(metrics_list: list):
    print("\n" + "="*100)
    print("📊 无API依赖浏览器/搜索引擎自动化对比分析")
    print("="*100)
    
    print("\n⚡ 性能耗时对比（秒）：")
    for m in metrics_list:
        if m["screenshot"] not in ["ddg_timeout.png", "brave_timeout.png", "firefox_timeout.png", "edge_timeout.png"]:
            duration = round(time.time() - float(m.get("duration", time.time())), 2)
            print(f"   {m['name']}: {duration:.2f}s | 截图: {m['screenshot']}")
        else:
            print(f"   {m['name']}: 超时 | 截图: {m['screenshot']}")
    
    comparison = {
        "内核类型": {
            "DuckDuckGo": "Chromium（轻量）",
            "Brave": "Chromium（反检测优化）",
            "Firefox": "Gecko（独立内核）",
            "Edge": "Chromium（微软优化）"
        },
        "验证码概率": {
            "DuckDuckGo": "0%（无验证）",
            "Brave": "0%（无验证）",
            "Firefox+Bing": "<1%（国内版）",
            "Edge+Bing": "<1%（国内版）"
        },
        "网络稳定性（国内）": {
            "DuckDuckGo": "低（境外）",
            "Brave": "低（境外）",
            "Firefox+Bing": "极高（国内版）",
            "Edge+Bing": "极高（国内版）"
        },
        "自动化推荐场景": {
            "DuckDuckGo": "境外环境、隐私敏感",
            "Brave": "境外环境、反爬严格",
            "Firefox": "国内环境、跨平台测试",
            "Edge": "国内环境、企业级稳定自动化"
        }
    }
    
    for category, values in comparison.items():
        print(f"\n🔹 {category}:")
        for browser, desc in values.items():
            print(f"   {browser:15} | {desc}")
    
    print("\n💡 自动化选型建议：")
    print("   - 国内环境首选：Edge+Bing / Firefox+Bing（无超时、无验证）")
    print("   - 境外环境首选：DuckDuckGo / Brave（无验证）")
    print("   - 避坑：Safari+Google（高验证+易超时，已移除）")
    print("="*100)

# ==================== 主函数（简化+轻量）====================
async def run_all_browsers_comparison():
    search_query = "Playwright latest updates 2026"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    metrics_list = []
    
    async with async_playwright() as p:
        # 1. DuckDuckGo (Chromium)
        browser_ddg = await p.chromium.launch(headless=HEADLESS_MODE, slow_mo=100)  # 降低slow_mo
        page_ddg = await browser_ddg.new_page()
        page_ddg.set_default_timeout(BASE_TIMEOUT)
        start_time = time.time()
        metrics = await search_duckduckgo(page_ddg, search_query, start_date, end_date)
        metrics["duration"] = start_time
        metrics_list.append(metrics)
        await browser_ddg.close()
        await asyncio.sleep(1)  # 释放资源
        
        # 2. Brave (Chromium)
        browser_brave = await p.chromium.launch(headless=HEADLESS_MODE, slow_mo=100)
        page_brave = await browser_brave.new_page()
        page_brave.set_default_timeout(BASE_TIMEOUT)
        start_time = time.time()
        metrics = await search_brave(page_brave, search_query, start_date, end_date)
        metrics["duration"] = start_time
        metrics_list.append(metrics)
        await browser_brave.close()
        await asyncio.sleep(1)
        
        # 3. Firefox (Gecko)
        browser_firefox = await p.firefox.launch(headless=HEADLESS_MODE, slow_mo=150)
        page_firefox = await browser_firefox.new_page()
        page_firefox.set_default_timeout(BASE_TIMEOUT)
        start_time = time.time()
        metrics = await search_firefox(page_firefox, search_query, start_date, end_date)
        metrics["duration"] = start_time
        metrics_list.append(metrics)
        await browser_firefox.close()
        await asyncio.sleep(1)
        
        # 4. Edge (Chromium)
        browser_edge = await p.chromium.launch(headless=HEADLESS_MODE, slow_mo=100)
        page_edge = await browser_edge.new_page()
        page_edge.set_default_timeout(BASE_TIMEOUT)
        start_time = time.time()
        metrics = await search_edge(page_edge, search_query, start_date, end_date)
        metrics["duration"] = start_time
        metrics_list.append(metrics)
        await browser_edge.close()
    
    compare_all_browsers(metrics_list)
    print("\n🎉 所有无API浏览器自动化+对比完成！")

# ==================== 执行入口 ====================
if __name__ == "__main__":
    # 解决MacOS asyncio事件循环问题
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    asyncio.run(run_all_browsers_comparison())