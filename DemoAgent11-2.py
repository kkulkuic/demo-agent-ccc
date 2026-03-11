import asyncio
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Locator, expect

# ==================== Enhanced Visualization Function (Core Optimization) ====================
async def draw_labeled_bounding_box(
    page, 
    locator: Locator, 
    element_name: str, 
    color: str = "red", 
    border_width: int = 4,
    label_bg_color: str = None,
    display_time: int = 30,  # 3x longer display time (seconds)
    extra_info: str = ""     # Extra info (e.g., date value, appended to label)
):
    """
    Draw highlighted bounding box with rich info label + smooth fade-out effect
    :param page: Page object
    :param locator: Element locator
    :param element_name: Base element name
    :param color: Border color
    :param border_width: Border width
    :param label_bg_color: Label background color (uses border color by default)
    :param display_time: Border display duration (seconds)
    :param extra_info: Extra info (e.g., date value, automatically appended to label)
    """
    if label_bg_color is None:
        label_bg_color = color
    
    # Combine full label text (base name + extra info)
    full_label_text = element_name
    if extra_info:
        full_label_text = f"{element_name}: {extra_info}"
    
    try:
        # 1. Wait for element to be visible and scroll into view
        await locator.wait_for(state="visible", timeout=15000)
        await locator.scroll_into_view_if_needed()
        
        # 2. Get element position and size
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
        
        # 3. Generate unique ID
        box_id = f"labeled-box-{int(time.time())}-{element_name.replace(' ', '-')[:10]}"
        label_id = f"{box_id}-label"
        
        # 4. Inject JS to draw labeled border (optimized fade-out animation)
        await page.evaluate("""
            ({
                box_id, label_id, x, y, width, height, 
                color, border_width, full_label_text, label_bg_color, display_time
            }) => {
                // Remove existing elements with the same ID (avoid duplication)
                const oldBox = document.getElementById(box_id);
                const oldLabel = document.getElementById(label_id);
                if (oldBox) oldBox.remove();
                if (oldLabel) oldLabel.remove();

                // === 1. Create border element (optimized transition animation) ===
                const box = document.createElement('div');
                box.id = box_id;
                box.style.position = 'absolute';
                box.style.left = `${x}px`;
                box.style.top = `${y}px`;
                box.style.width = `${width}px`;
                box.style.height = `${height}px`;
                box.style.border = `${border_width}px solid ${color}`;
                box.style.zIndex = '99999';          // Always on top
                box.style.pointerEvents = 'none';    // Does not affect clicks
                box.style.boxSizing = 'border-box';
                box.style.backgroundColor = 'transparent';
                box.style.opacity = '1';             // Initial opacity
                // Optimized transition: apply to opacity and border (0.5s smooth transition)
                box.style.transition = 'opacity 0.5s ease-in-out, border 0.5s ease-in-out'; 
                box.style.outline = '1px solid rgba(255,255,255,0.5)'; // Add layering
                
                // === 2. Create text label (optimized style + transition) ===
                const label = document.createElement('div');
                label.id = label_id;
                label.style.position = 'absolute';
                label.style.left = `${x}px`;
                label.style.top = `${y - 30}px`;     // Label above border
                label.style.backgroundColor = label_bg_color;
                label.style.color = 'white';         // White text
                label.style.padding = '4px 12px';    // More comfortable padding
                label.style.borderRadius = '6px';    // Larger rounded corners
                label.style.fontSize = '14px';       // Clear font size
                label.style.fontWeight = '600';      // Semi-bold, readable but not obtrusive
                label.style.fontFamily = 'Arial, Helvetica, sans-serif';
                label.style.zIndex = '100000';       // Label above border
                label.style.pointerEvents = 'none';
                label.style.boxShadow = '0 3px 6px rgba(0,0,0,0.2)'; // Softer shadow
                label.style.whiteSpace = 'nowrap';   // Prevent text wrapping
                label.style.opacity = '1';           // Initial opacity
                label.style.transition = 'opacity 0.5s ease-in-out, transform 0.3s ease'; // Label transition
                label.style.transform = 'translateY(0)'; // Initial position
                label.innerText = full_label_text;   // Show full label text (including date)
                
                // === 3. Add to page ===
                document.body.appendChild(box);
                document.body.appendChild(label);
                
                // === 4. Smooth fade-out + removal (optimized animation timing) ===
                // Wait for specified duration before starting fade-out
                setTimeout(() => {
                    // Label moves up slightly + fade out for better visual experience
                    label.style.opacity = '0';
                    label.style.transform = 'translateY(-5px)';
                    
                    // Border fades out with slight delay (coordinate with label animation)
                    setTimeout(() => {
                        box.style.opacity = '0';
                        
                        // Fully remove elements after animation completes
                        setTimeout(() => {
                            if (document.getElementById(box_id)) document.getElementById(box_id).remove();
                            if (document.getElementById(label_id)) document.getElementById(label_id).remove();
                        }, 500); // Match transition duration
                    }, 200); // Border fade-out delay
                    
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
        
        print(f"✅ Drawn labeled {color} border for [{full_label_text}] (fades out smoothly after {display_time} seconds)")
        
    except Exception as e:
        print(f"⚠️ Failed to draw border for [{full_label_text}]: {str(e)[:80]}")

# ==================== Date Formatting Tools ====================
def format_date_for_google(date_obj: datetime) -> str:
    """Format date for Google search compatibility (MM/DD/YYYY)"""
    return date_obj.strftime("%m/%d/%Y")

def format_date_for_label(date_obj: datetime) -> str:
    """Format date for label display (YYYY-MM-DD, more readable)"""
    return date_obj.strftime("%Y-%m-%d")

# ==================== Manual Verification Handling ====================
async def wait_for_human_verification(page):
    """Wait for user to complete Google human verification manually"""
    print("\n" + "="*60)
    print("⚠️ Google human verification detected, please complete manually:")
    print("1. Check the 'I'm not a robot' checkbox in the browser window")
    print("2. If image verification appears (select buses/traffic lights/bridges etc.), choose the corresponding images manually")
    print("3. Click the 'Verify' or 'Next' button after completion")
    print("4. Wait for the page to automatically redirect to search results")
    print("="*60)
    print("⏳ Waiting for verification completion (max 3 minutes)...")
    
    try:
        await page.wait_for_url(
            lambda url: "sorry/index" not in url and "recaptcha" not in url.lower(),
            timeout=180000
        )
        print("✅ Manual verification completed! Continuing search logic")
    except Exception as e:
        print(f"\n❌ Verification timed out (3 minutes): {str(e)[:50]}")
        print("⚠️ Will attempt to continue with direct date range URL construction")

# ==================== Google Date Range Search Core Logic (Enhanced Labels) ====================
async def search_google_with_date_range(page, search_query: str, start_date: datetime, end_date: datetime):
    """Execute Google date range search (with rich date info label visualization)"""
    # Pre-format dates (for label display)
    start_date_google = format_date_for_google(start_date)
    end_date_google = format_date_for_google(end_date)
    start_date_label = format_date_for_label(start_date)
    end_date_label = format_date_for_label(end_date)
    date_range_label = f"{start_date_label} to {end_date_label}"
    
    print(f"\n🔍 Executing Google date range search: {search_query} | {date_range_label}")
    
    # Step 1: Access Google search homepage
    await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
    print("✅ Entered Google search page")
    
    # Step 2: Locate search box (blue border + label)
    search_box = page.locator('textarea[name="q"]').first
    await draw_labeled_bounding_box(
        page, search_box, 
        element_name="Search Box", 
        color="#2196F3",  # Google Blue
        border_width=4,
        display_time=30,
        extra_info=search_query  # Label includes search keyword
    )
    await search_box.click()
    await search_box.fill(search_query)
    await page.keyboard.press("Enter")
    
    # Step 3: Handle human verification
    if "sorry/index" in page.url or "recaptcha" in page.url.lower():
        await wait_for_human_verification(page)
    else:
        await page.wait_for_load_state("networkidle", timeout=15000)
    
    print("✅ Submitted search keyword")
    
    # Step 4: Locate Tools button (green border + label)
    tools_btn = page.locator('//div[contains(@class, "hdtb-mitem") and (text()="Tools" or @aria-label="Tools")]').first
    try:
        await expect(tools_btn).to_be_visible(timeout=10000)
        await draw_labeled_bounding_box(
            page, tools_btn, 
            element_name="Tools Button", 
            color="#4CAF50",  # Google Green
            border_width=4,
            display_time=30
        )
        await tools_btn.click()
        await page.wait_for_selector('//div[contains(@class, "hdtbUc")]', state="visible")
        print("✅ Expanded Tools menu")
    except Exception as e:
        print(f"⚠️ Failed to click Tools button: {str(e)[:50]}")
        # Alternative: Direct URL construction
        base_url = "https://www.google.com/search"
        search_params = f"q={search_query.replace(' ', '+')}"
        date_params = f"&tbs=cdr:1,cd_min:{start_date_google},cd_max:{end_date_google}"
        final_url = f"{base_url}?{search_params}{date_params}"
        print(f"⚠️ Attempting direct access to date range URL: {final_url[:100]}...")
        
        await page.goto(final_url, wait_until="domcontentloaded", timeout=15000)
        if "sorry/index" in page.url or "recaptcha" in page.url.lower():
            await wait_for_human_verification(page)
        
        # Highlight date range results (gold border + label with specific dates)
        try:
            date_range_display = page.locator('//span[contains(text(), "Showing results for") or contains(text(), "Displaying results for time range")]').first
            await draw_labeled_bounding_box(
                page, date_range_display, 
                element_name="Date Range Results", 
                color="#FFC107",  # Gold
                border_width=5,
                label_bg_color="#FF9800",  # Dark orange label
                display_time=45,  # 3x longer (15*3)
                extra_info=date_range_label  # Label includes full date range
            )
        except:
            print("⚠️ Failed to highlight date range display area")
        
        # Save screenshot
        screenshot_path = f"google_search_date_range_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"✅ Search results screenshot saved: {screenshot_path}")
        return screenshot_path
    
    # Step 5: Locate Any time button (cyan border + label)
    any_time_btn = page.locator('//div[contains(@class, "hdtb-mitem") and (text()="Any time" or text()="Any time")]').first
    await expect(any_time_btn).to_be_visible(timeout=5000)
    await draw_labeled_bounding_box(
        page, any_time_btn, 
        element_name="Time Filter Button", 
        color="#00BCD4",  # Cyan
        border_width=4,
        display_time=30
    )
    await any_time_btn.click()
    await page.wait_for_timeout(500)
    
    # Step 6: Locate Custom range button (orange border + label)
    custom_range_btn = page.locator('//span[(text()="Custom range" or text()="Custom range")]').first
    await expect(custom_range_btn).to_be_visible(timeout=5000)
    await draw_labeled_bounding_box(
        page, custom_range_btn, 
        element_name="Custom Time Range", 
        color="#FF9800",  # Orange
        border_width=4,
        display_time=30,
        extra_info=date_range_label  # Label includes target date range
    )
    await custom_range_btn.click()
    await page.wait_for_timeout(1000)
    
    # Step 7: Locate start date input (purple border + label with specific date)
    start_date_input = page.locator('input[aria-label="Start date"], input[aria-label="Start date"]').first
    await expect(start_date_input).to_be_editable(timeout=5000)
    await draw_labeled_bounding_box(
        page, start_date_input, 
        element_name="Start Date Input", 
        color="#9C27B0",  # Purple
        border_width=4,
        display_time=30,
        extra_info=start_date_google  # Label includes Google-formatted date
    )
    await start_date_input.fill(start_date_google)
    
    # Step 8: Locate end date input (purple border + label with specific date)
    end_date_input = page.locator('input[aria-label="End date"], input[aria-label="End date"]').first
    await expect(end_date_input).to_be_editable(timeout=5000)
    await draw_labeled_bounding_box(
        page, end_date_input, 
        element_name="End Date Input", 
        color="#9C27B0",  # Purple
        border_width=4,
        display_time=30,
        extra_info=end_date_google  # Label includes Google-formatted date
    )
    await end_date_input.fill(end_date_google)
    
    # Step 9: Locate Apply button (lime green border + label)
    try:
        apply_btn = page.locator('//g-button[contains(text(), "Apply") or contains(text(), "Apply")]').first
        await draw_labeled_bounding_box(
            page, apply_btn, 
            element_name="Apply Date Button", 
            color="#8BC34A",  # Lime Green
            border_width=4,
            display_time=30,
            extra_info=date_range_label  # Label includes date range to apply
        )
        if await apply_btn.count() > 0:
            await apply_btn.click()
        else:
            await page.keyboard.press("Enter")
    except:
        await page.keyboard.press("Enter")
    
    await page.wait_for_load_state("networkidle", timeout=15000)
    print(f"✅ Applied date range filter: {date_range_label}")
    
    # Step 10: Highlight final date range results (gold border + label, emphasized)
    try:
        date_range_result = page.locator('//div[contains(@class, "hdtb-tl") or contains(text(), start_date_label) or contains(text(), end_date_label)]').first
        await draw_labeled_bounding_box(
            page, date_range_result, 
            element_name="Final Date Range", 
            color="#FFC107",  # Gold
            border_width=5,   # Thicker border
            label_bg_color="#FF9800",  # Dark orange label
            display_time=45,  # 3x longer (15*3)
            extra_info=date_range_label  # Label includes full date range
        )
    except Exception as e:
        print(f"⚠️ Failed to highlight final date range: {str(e)[:50]}")
    
    # Step 11: Save screenshot
    screenshot_path = f"google_search_date_range_{int(time.time())}.png"
    await page.screenshot(path=screenshot_path, full_page=True)
    print(f"✅ Search results screenshot saved: {screenshot_path}")
    
    return screenshot_path

# ==================== Main Function ====================
async def headful_browsing_google():
    """Headful mode: Google search + visualization with rich date labels"""
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(
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
        
        # Create context
        context = await browser.new_context(
            viewport=None,
            locale="en-US",
            java_script_enabled=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/"
            }
        )
        
        # Disable webdriver detection
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        page = await context.new_page()
        page.set_default_timeout(20000)
        
        # Execute search
        search_query = "Playwright latest updates 2026"
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        try:
            await search_google_with_date_range(page, search_query, start_date, end_date)
        except Exception as e:
            print(f"❌ Google date range search failed: {str(e)[:80]}")
        
        # Playwright docs interaction demo (labeled border)
        print("\n📚 Demo: Playwright docs headful interaction...")
        await page.goto("https://playwright.dev/python/docs/intro", wait_until="networkidle", timeout=20000)
        
        # Locate code block (red border + label)
        code_block_locators = [
            page.locator("div[class*='language-python'] pre"),
            page.locator("pre:has-text('pip install playwright')"),
            page.locator("code:has-text('pip install')").locator("..")
        ]
        
        code_block = None
        for locator in code_block_locators:
            if await locator.count() > 0:
                code_block = locator.first
                break
        
        if code_block:
            await draw_labeled_bounding_box(
                page, code_block, 
                element_name="Playwright Installation Code Block", 
                color="#F44336",  # Google Red
                border_width=4,
                display_time=30,
                extra_info="pip install playwright"  # Label includes code content
            )
        else:
            print("⚠️ Code block element not found, skipping border drawing")
        
        # Locate copy button (green border + label)
        copy_btn_locators = [
            page.locator("button[aria-label='Copy code to clipboard']"),
            page.locator('button:has-text("Copy")'),
            page.locator("button[class*='copy-button']")
        ]
        
        copy_btn = None
        for locator in copy_btn_locators:
            if await locator.count() > 0:
                copy_btn = locator.first
                break
        
        if copy_btn:
            await draw_labeled_bounding_box(
                page, copy_btn, 
                element_name="Code Copy Button", 
                color="#4CAF50",  # Google Green
                border_width=4,
                display_time=30
            )
            await copy_btn.click()
            print("✅ Clicked code copy button")
        else:
            print("⚠️ Copy button not found")
        
        # Save screenshot
        docs_screenshot = f"playwright_docs_headful_{int(time.time())}.png"
        await page.screenshot(path=docs_screenshot, full_page=True)
        print(f"✅ Docs page screenshot saved: {docs_screenshot}")
        
        # Keep browser open
        print("\n🎉 All operations completed! Browser will close in 15 seconds...")
        await page.wait_for_timeout(15000)
        await browser.close()
        print("✅ Browser closed")

# ==================== Execution Entry ====================
if __name__ == "__main__":
    asyncio.run(headful_browsing_google())