import os
import re
import asyncio
import time
import base64
import warnings
import uuid
from typing import Annotated, TypedDict
from dotenv import load_dotenv
from playwright_stealth import stealth_async

warnings.filterwarnings("ignore")
load_dotenv()

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
)
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

from playwright.async_api import async_playwright
from PIL import Image, ImageDraw

os.makedirs("logs", exist_ok=True)
os.makedirs("playwright/.auth", exist_ok=True)

MODEL_ID = "claude-haiku-4-5-20251001"

# ─────────────────────────────────────────────
# 1. BROWSER SESSION
# ─────────────────────────────────────────────

browser_session = {"playwright": None, "context": None, "page": None}


async def get_session():
    if browser_session["playwright"] is None:
        print("🌐 Starting browser...")
        browser_session["playwright"] = await async_playwright().start()
        ctx = await browser_session["playwright"].chromium.launch_persistent_context(
            user_data_dir="playwright/.auth",
            headless=False,
            channel="chrome",
            locale="en-US",
            timezone_id="America/Chicago",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        browser_session["context"] = ctx

        async def on_page(page):
            await stealth_async(page)
            browser_session["page"] = page
            print(f"  🔀 [New tab] {page.url or 'loading...'}")

        ctx.on("page", on_page)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await stealth_async(page)
        browser_session["page"] = page

    return browser_session["page"]


# ─────────────────────────────────────────────
# 2. SHARED HELPERS
# ─────────────────────────────────────────────

async def dom_snapshot() -> dict:
    """
    Lightweight page snapshot returned by every action tool automatically.
    No screenshot — text only. Contains:
      page_text       : 5000 chars of visible body text
      buttons         : up to 30 visible buttons (id, text, aria-label)
      inputs          : up to 20 visible inputs  (id, name, type, placeholder, aria-label)
      alerts          : CAPTCHA_DETECTED | ACCESS_BLOCKED | LOGIN_WALL
      characteristics : what kind of page this is — drives tool strategy
      url, title
    """
    page = await get_session()
    try:
        return await page.evaluate("""() => {
            const text = document.body.innerText.substring(0, 5000);
            const lc   = text.toLowerCase();

            const btns = [...document.querySelectorAll(
                'button,[role=button],input[type=submit],input[type=button],a[role=button]'
            )].filter(e => { const r = e.getBoundingClientRect(); return r.width>0 && r.height>0; })
             .slice(0,30).map(e => ({
                id:   e.id||null,
                text: (e.innerText||e.value||'').trim().substring(0,60),
                aria: e.getAttribute('aria-label')||null,
                tag:  e.tagName.toLowerCase(),
             }));

            const inps = [...document.querySelectorAll('input,textarea,select')]
             .filter(e => { const r = e.getBoundingClientRect(); return r.width>0 && r.height>0; })
             .slice(0,20).map(e => ({
                id:   e.id||null,   name: e.name||null,
                type: e.type||null, ph:   e.placeholder||null,
                aria: e.getAttribute('aria-label')||null,
                val:  e.value ? e.value.substring(0,80) : null,
             }));

            const alerts = [];
            if (lc.includes('captcha')||lc.includes('verify you are human')||
                lc.includes('press & hold')||lc.includes('press and hold')||
                lc.includes('are you a robot')||lc.includes('bot verification')||
                lc.includes('select all squares')||lc.includes('confirm you are human'))
                alerts.push('CAPTCHA_DETECTED');
            if (lc.includes('access denied')||lc.includes('403 forbidden')||
                (lc.includes('blocked')&&lc.includes('security')))
                alerts.push('ACCESS_BLOCKED');
            const main = (document.querySelector('main,[role=main],form')||document.body)
                         .innerText.toLowerCase();
            if (main.includes('login required')||main.includes('please sign in to continue')||
                main.includes('you must be logged in')||
                (document.querySelector('input[type=password]')&&
                 document.querySelectorAll('input').length<=3))
                alerts.push('LOGIN_WALL');

            // ── Page characteristic detection ─────────────────────────────
            // Detects what kind of page this is from its actual content/structure,
            // not from the URL — works on unknown sites too.
            const ch = {};

            // Canvas / visual content — needs browser_inspect
            ch.has_canvas = document.querySelectorAll('canvas').length > 0;

            // Map tiles (Google Maps, Leaflet, Mapbox, OpenStreetMap, HERE)
            ch.has_map = !!(
                document.querySelector('.mapboxgl-map,.leaflet-container,#map,[class*="gm-style"]') ||
                document.querySelector('[class*="map-container"],[class*="mapCanvas"]') ||
                document.querySelector('img[src*="maps.googleapis"],[src*="tile.openstreetmap"]')
            );

            // React / Next.js / Angular / Vue SPA — DOM selectors unstable,
            // prefer get_accessibility_tree
            ch.is_spa = !!(
                document.querySelector('[data-reactroot],[data-react-helmet],#__NEXT_DATA__') ||
                window.__NEXT_DATA__ || window.__NUXT__ ||
                document.querySelector('[ng-version],[data-ng-version]') ||
                document.querySelector('[data-v-app]') ||
                window.__REACT_DEVTOOLS_GLOBAL_HOOK__
            );

            // E-commerce product cards — use browser_get_products
            ch.has_products = !!(
                document.querySelector('[data-asin],[data-product-id]') ||
                document.querySelectorAll('.product-card,.s-result-item,[class*="product-tile"]').length > 2
            );

            // Price filter / heavy form — use press_enter=False on fills
            ch.is_form_heavy = document.querySelectorAll('input,select,textarea').length >= 5;

            // Job listings — read from text, expect login walls
            ch.has_jobs = !!(
                document.querySelector('[class*="job-card"],[class*="jobCard"],[data-job-id]') ||
                (lc.includes('salary') && (lc.includes('apply') || lc.includes('job')))
            );

            // Rental / real estate listings
            ch.has_listings = !!(
                document.querySelector('[class*="listing-card"],[data-listing-id],[class*="property-card"]') ||
                (lc.includes('bed') && lc.includes('bath') && lc.includes('rent'))
            );

            // JSON / API response — use browser_evaluate for field extraction
            ch.is_json = (function() {
                try { JSON.parse(document.body.innerText); return true; } catch(e) { return false; }
            })();

            return { url: location.href, title: document.title,
                     page_text: text, buttons: btns, inputs: inps,
                     alerts, characteristics: ch };
        }""")
    except Exception as e:
        return {"url":"","title":"","page_text":"","buttons":[],"inputs":[],
                "alerts":[],"characteristics":{},"error":str(e)}


async def _screenshot(prefix: str) -> dict:
    page = await get_session()
    path = f"logs/{prefix}_{int(time.time())}.png"
    await page.screenshot(path=path)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return {"screenshot_path": path, "screenshot_b64": b64}


async def _extract_products(page, max_results: int = 10) -> list:
    """
    Extract structured product cards from the current page.
    Shared by browser_navigate (when visual=True) and browser_click_sort.
    Consolidation #2: auto-called after sort, not a separate tool call.
    """
    try:
        products = await page.evaluate("""(max) => {
            const out = [];
            // Amazon search result cards
            const cards = [...document.querySelectorAll(
                '[data-component-type="s-search-result"],[data-asin]'
            )].filter(c => (c.getAttribute('data-asin')||'').length > 0);

            for (const card of cards.slice(0, max)) {
                const titleEl = card.querySelector('h2 a span, h2 span, .a-size-medium');
                const priceEl = card.querySelector('.a-price .a-offscreen, .a-price-whole');
                const linkEl  = card.querySelector('h2 a[href], a.a-link-normal[href*="/dp/"]');
                const spons   = !!card.querySelector(
                    '.s-sponsored-label-info-icon,[aria-label*="Sponsored"]');
                const title   = titleEl ? titleEl.innerText.trim() : '';
                const price   = priceEl ? priceEl.innerText.trim().replace(/[^0-9$.]/g,'') : '';
                const href    = linkEl
                    ? (linkEl.href.startsWith('http') ? linkEl.href
                       : 'https://www.amazon.com' + linkEl.getAttribute('href'))
                    : '';
                if (title && href) out.push({title, price, url: href,
                                              asin: card.getAttribute('data-asin')||'',
                                              sponsored: spons});
            }
            // Generic fallback for non-Amazon
            if (out.length === 0) {
                [...document.querySelectorAll('a[href*="/dp/"],a[href*="product"],a[href*="item"]')]
                .filter(a => a.innerText.trim().length > 10).slice(0, max)
                .forEach(a => out.push({title: a.innerText.trim().substring(0,120),
                                        price:'', url: a.href, asin:'', sponsored:false}));
            }
            return out;
        }""", max_results)
        organic = [p for p in products if not p.get("sponsored")]
        return {"all": products, "organic": organic}
    except Exception:
        return {"all": [], "organic": []}


async def _verify_sort(label: str, timeout_s: float = 4.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        snap = await dom_snapshot()
        if label.lower() in snap.get("page_text", "").lower():
            return True
        await asyncio.sleep(0.4)
    return False


# ─────────────────────────────────────────────
# 3. ACTION TOOLS
# ─────────────────────────────────────────────

@tool
async def browser_navigate(url: str, visual: bool = False):
    """
    Navigate to a URL. Returns DOM snapshot automatically.

    visual=False (default): DOM snapshot only — fast, no screenshot.
                            Use for forms, search pages, text content, APIs.
    visual=True:            DOM snapshot + screenshot — use for maps, charts,
                            canvas, any page where you need to SEE what loaded.

    Consolidation #3: visual parameter replaces the pattern of
    browser_navigate → browser_inspect as two separate calls.
    """
    page = await get_session()
    try:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            await asyncio.sleep(2)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(0.5)
        dom = await dom_snapshot()
        if visual:
            ss = await _screenshot("nav_visual")
            return {"status": "navigated", **dom, **ss}
        return {"status": "navigated", **dom}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_click(selector: str):
    """Click by CSS selector. Returns DOM snapshot to confirm what changed."""
    page = await get_session()
    try:
        await page.wait_for_selector(selector, timeout=8000)
        await page.click(selector)
        await asyncio.sleep(0.5)
        return {"status": "clicked", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_click_sort(selector: str, expected_sort_label: str):
    """
    Click a sort button AND verify the sort applied. Returns DOM snapshot
    + sort_verified (bool) + products (organic list, sponsored filtered).

    Consolidation #2: auto-extracts product cards after sort so you don't
    need a separate browser_get_products call. One tool does click+verify+extract.

    expected_sort_label: text that must appear in page after sort.
      Amazon:  "Price: Low to High"
      Zillow:  "Payment (Low to High)"
      Newegg:  "Price: Low to High"
    If sort_verified=False: use URL-based sort fallback in e-commerce rules.
    """
    page = await get_session()
    try:
        await page.wait_for_selector(selector, timeout=8000)
        await page.click(selector)
        verified = await _verify_sort(expected_sort_label)
        dom      = await dom_snapshot()
        products = await _extract_products(page) if verified else {"all":[], "organic":[]}
        return {"status": "sort_clicked", "sort_verified": verified,
                "expected_label": expected_sort_label, **dom, **products}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_fill(selector: str, text: str, press_enter: bool = False):
    """
    Clear a field and type text. press_enter=False by default.
    Set press_enter=True only for search bars and login forms — never for
    price/quantity/filter fields (would submit the form prematurely).
    """
    page = await get_session()
    try:
        await page.wait_for_selector(selector, timeout=8000)
        await page.fill(selector, text)
        if press_enter:
            await page.keyboard.press("Enter")
            await asyncio.sleep(1.5)
        else:
            await asyncio.sleep(0.3)
        return {"status": f"filled '{text}'" + (" + Enter" if press_enter else ""),
                **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_type(text: str, delay_ms: int = 50):
    """
    Type into the currently focused element — no selector needed.
    Call after browser_click/browser_click_coords to focus the field first.
    Does not clear existing text. Does not press Enter.
    Use for: Google Maps, autocomplete inputs, DuckDuckGo, any dynamic field.
    Suggestions appear in dom_snapshot page_text and buttons after typing.
    """
    page = await get_session()
    try:
        await page.keyboard.type(text, delay=delay_ms)
        await asyncio.sleep(0.6)
        return {"status": f"typed '{text}'", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_key_press(key: str):
    """
    Press a key or chord. Examples: 'Enter','Escape','Tab','ArrowDown','Control+a'.
    Use to submit after browser_type, dismiss modals, navigate dropdown lists.
    """
    page = await get_session()
    try:
        await page.keyboard.press(key)
        await asyncio.sleep(0.4)
        return {"status": f"pressed '{key}'", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_click_coords(x: float, y: float):
    """
    Click at pixel coordinates (x, y). Fallback when CSS selector unavailable.
    Prefer browser_click(selector) when a stable selector exists.
    """
    page = await get_session()
    try:
        await page.mouse.click(x, y)
        await asyncio.sleep(0.5)
        return {"status": f"clicked ({x},{y})", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_scroll_element(selector: str, direction: str = "down", amount: int = 300):
    """
    Scroll a SPECIFIC element (not the whole page) by pixel amount.
    Use when content is inside a scrollable panel — e.g. Google Maps left panel,
    a search results sidebar, a dropdown list, or a modal with overflow:scroll.

    Examples:
      Google Maps route panel: selector = 'div[role=main]'
      Amazon filter sidebar:   selector = '#s-refinements'
      Any overflow div:        selector = '[class*="sidebar"], [class*="panel"]'

    Returns DOM snapshot after scrolling.
    """
    page = await get_session()
    try:
        move = amount if direction == "down" else -amount
        await page.evaluate(f"""(sel, px) => {{
            const el = document.querySelector(sel);
            if (el) el.scrollTop += px;
        }}""", selector, move)
        await asyncio.sleep(0.5)
        return {"status": f"scrolled element '{selector}' {direction} {amount}px",
                **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}
    page = await get_session()
    try:
        await page.evaluate(f"window.scrollBy(0, {amount if direction=='down' else -amount})")
        await asyncio.sleep(0.5)
        return {"status": f"scrolled {direction}", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_select(selector: str, value: str):
    """Select a <select> dropdown option by value. Returns DOM snapshot."""
    page = await get_session()
    try:
        await page.wait_for_selector(selector, timeout=8000)
        await page.select_option(selector, value=value)
        await asyncio.sleep(0.3)
        return {"status": f"selected '{value}'", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_hover(selector: str):
    """
    Hover to reveal dropdowns or tooltips. Revealed elements appear in
    dom_snapshot buttons list. Use browser_inspect if you need to SEE visually.
    """
    page = await get_session()
    try:
        await page.wait_for_selector(selector, timeout=8000)
        await page.hover(selector)
        await asyncio.sleep(0.5)
        return {"status": "hovered", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_go_back():
    """Go back in browser history. Returns DOM snapshot of landing page."""
    page = await get_session()
    try:
        await page.go_back(wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(0.5)
        return {"status": "back", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_wait(seconds: float = 2.0):
    """Wait for JS/network to settle. Returns DOM snapshot after waiting."""
    await asyncio.sleep(seconds)
    return {"status": f"waited {seconds}s", **await dom_snapshot()}


# ─────────────────────────────────────────────
# 4. READING TOOLS
# ─────────────────────────────────────────────

@tool
async def browser_read_page(full_page: bool = False):
    """
    Read the current page comprehensively. Returns:
      - text:       visible body text. full_page=False → 8000 chars visible area only.
                    full_page=True  → scrolls the entire page and collects ALL text
                    (up to 50,000 chars). Use for articles, job descriptions, long listings.
      - inputs:     all form fields (id, name, type, placeholder, aria-label, value)
      - buttons:    all buttons (id, text, aria-label)
      - links:      first 60 links (href, text)
      - headings:   all h1-h3 headings — gives page structure at a glance
      - tables:     first 3 tables as row arrays — extracts structured tabular data
      - meta:       description, og:title, og:description — useful for articles/products
      - url, title, text_length, is_truncated

    full_page=False (default): fast — reads only what is currently visible.
                               Use for search results, filter pages, interactive UIs.
    full_page=True:            slow — auto-scrolls to bottom collecting all text.
                               Use for: articles, job descriptions, product detail pages,
                               apartment listings, any page where content is below the fold.
    """
    page = await get_session()
    try:
        if full_page:
            # Auto-scroll to collect all text before reading
            await page.evaluate("""async () => {
                let last = 0;
                for (let i = 0; i < 15; i++) {
                    window.scrollBy(0, window.innerHeight);
                    await new Promise(r => setTimeout(r, 300));
                    if (document.body.scrollHeight === last) break;
                    last = document.body.scrollHeight;
                }
                window.scrollTo(0, 0);
            }""")
            await asyncio.sleep(0.5)

        result = await page.evaluate("""(fullPage) => {
            // ── Text extraction ────────────────────────────────────────────
            const MAX   = fullPage ? 50000 : 8000;
            const raw   = document.body.innerText;
            const text  = raw.substring(0, MAX);
            const is_truncated = raw.length > MAX;

            // ── Inputs ─────────────────────────────────────────────────────
            const inputs = [...document.querySelectorAll('input,textarea,select')]
                .filter(e => e.getBoundingClientRect().width > 0)
                .map(e => ({
                    id:   e.id   || null,
                    name: e.name || null,
                    type: e.type || null,
                    ph:   e.placeholder || null,
                    aria: e.getAttribute('aria-label') || null,
                    val:  e.value ? e.value.substring(0, 120) : null,
                }));

            // ── Buttons ────────────────────────────────────────────────────
            const buttons = [...document.querySelectorAll(
                'button,[role=button],input[type=submit],input[type=button]'
            )].filter(e => e.getBoundingClientRect().width > 0)
              .map(e => ({
                id:   e.id || null,
                text: e.innerText ? e.innerText.substring(0, 80).trim() : null,
                aria: e.getAttribute('aria-label') || null,
              }));

            // ── Links ──────────────────────────────────────────────────────
            const links = [...document.querySelectorAll('a[href]')]
                .slice(0, 60)
                .map(e => ({
                    href: e.href,
                    text: e.innerText ? e.innerText.substring(0, 80).trim() : null,
                }))
                .filter(l => l.text && l.text.length > 0);

            // ── Headings — page structure at a glance ──────────────────────
            const headings = [...document.querySelectorAll('h1,h2,h3')]
                .map(e => ({
                    level: e.tagName.toLowerCase(),
                    text:  e.innerText.trim().substring(0, 120),
                }))
                .filter(h => h.text.length > 0);

            // ── Tables — structured data extraction ────────────────────────
            const tables = [...document.querySelectorAll('table')]
                .slice(0, 3)
                .map(tbl => {
                    const rows = [...tbl.querySelectorAll('tr')].map(tr =>
                        [...tr.querySelectorAll('td,th')]
                            .map(cell => cell.innerText.trim().substring(0, 60))
                    ).filter(row => row.length > 0);
                    return rows;
                })
                .filter(t => t.length > 0);

            // ── Meta — article/product metadata ───────────────────────────
            const meta = {
                description: document.querySelector('meta[name=description]')
                                ?.getAttribute('content') || null,
                og_title:    document.querySelector('meta[property="og:title"]')
                                ?.getAttribute('content') || null,
                og_desc:     document.querySelector('meta[property="og:description"]')
                                ?.getAttribute('content') || null,
                canonical:   document.querySelector('link[rel=canonical]')
                                ?.getAttribute('href') || null,
            };

            return {
                url:        location.href,
                title:      document.title,
                text,
                text_length: raw.length,
                is_truncated,
                inputs,
                buttons,
                links,
                headings,
                tables,
                meta,
            };
        }""", full_page)

        return {"status": "success", **result}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_get_products(max_results: int = 10):
    """
    Extract structured product cards from the current e-commerce search page.
    Returns:
      organic[]  — non-sponsored products: {title, price, url, asin}
      all[]      — all products including sponsored

    Use this on Amazon, Newegg, Google Shopping AFTER sorting.
    Find the first organic item whose title describes a complete product (not accessory).
    Then browser_navigate to its url field.
    Do NOT use browser_evaluate to find product links — this is more reliable.
    """
    page = await get_session()
    try:
        result = await _extract_products(page, max_results)
        return {"status": "success", "url": page.url, **result,
                "tip": "Read organic[] for non-sponsored. Navigate to item url for details."}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_evaluate(js_expression: str):
    """
    Run arbitrary JS in the browser. Returns status='not_found' if null/undefined.
    Use for:
      JSON API fields:  JSON.parse(document.body.innerText).stargazers_count
      Current URL:      window.location.href
    Do NOT use to find product links — use browser_get_products instead.
    Always check status before using result. Never navigate to 'null'.
    """
    page = await get_session()
    try:
        result = await page.evaluate(f"""() => {{
            const v = {js_expression};
            return (v===null||v===undefined) ? '__NOT_FOUND__' : String(v);
        }}""")
        if result == "__NOT_FOUND__":
            return {"status": "not_found", "result": None, "url": page.url}
        return {"status": "success", "result": result, "url": page.url}
    except Exception as e:
        return {"error": str(e)}


@tool
async def get_accessibility_tree():
    """
    Structured role/name tree — fallback for JS-heavy pages (React, Maps, Angular)
    where browser_read_page misses dynamically generated elements.
    """
    page = await get_session()
    try:
        snap = await page.accessibility.snapshot()
        def flat(node, d=0):
            if not node: return []
            lines = []
            r,n,v = node.get("role",""),node.get("name",""),node.get("value","")
            if r not in ("none","presentation","generic",""):
                parts = [f"{'  '*d}[{r}]"]
                if n: parts.append(f'"{n}"')
                if v: parts.append(f'= "{v}"')
                lines.append(" ".join(parts))
            for c in node.get("children",[]): lines.extend(flat(c,d+1))
            return lines
        return {"status":"success","tree":"\n".join(flat(snap)[:300]),"url":page.url}
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────
# 5. VISUAL TOOLS
# ─────────────────────────────────────────────

@tool
async def browser_inspect():
    """
    Take a screenshot of the current page and return as base64 + DOM snapshot.
    Use when visual context is essential:
      - Maps, charts, canvas elements
      - CAPTCHA or image-based challenge (alerts will say CAPTCHA_DETECTED)
      - Spatial layout questions
    Do NOT use for routine post-action confirmation — dom_snapshot is enough.
    Use browser_navigate(url, visual=True) to get a screenshot on first load.
    """
    ss  = await _screenshot("inspect")
    dom = await dom_snapshot()
    return {"status": "visual", **ss, **dom}


@tool
async def browser_highlight(selector: str):
    """Screenshot with red box around an element — visual proof it was found."""
    page = await get_session()
    try:
        el  = await page.wait_for_selector(selector, timeout=8000)
        box = await el.bounding_box()
        path = f"logs/hl_{int(time.time())}.png"
        await page.screenshot(path=path)
        if box:
            with Image.open(path) as img:
                ImageDraw.Draw(img).rectangle(
                    [box['x'],box['y'],box['x']+box['width'],box['y']+box['height']],
                    outline="red", width=6)
                img.save(path)
        with open(path,"rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return {"status":"highlighted","screenshot_path":path,"screenshot_b64":b64}
    except Exception as e:
        return {"error": str(e)}


@tool
def stop(answer: str):
    """Signal task complete. Call as a tool — never write <stop> as text."""
    print(f"\n✅ [STOP] {answer}")
    return {"status": "stopped", "answer": answer}


# ─────────────────────────────────────────────
# 6. TOOL REGISTRY  (16 tools, no overlaps)
# ─────────────────────────────────────────────

tools = [
    # Reading ────────────────────────────────
    browser_read_page,       # structure + text in one call (replaces page_info + get_text)
    browser_get_products,    # e-commerce product cards with sponsored filter
    browser_evaluate,        # JS execution for exact values / JSON APIs
    get_accessibility_tree,  # JS-heavy page fallback

    # Navigation ─────────────────────────────
    browser_navigate,        # visual=False (default) or visual=True for maps/charts
    browser_go_back,
    browser_wait,
    browser_scroll_element,  # scroll specific panel/sidebar/modal

    # Clicking ───────────────────────────────
    browser_click,           # by CSS selector
    browser_click_sort,      # sort + auto-verify + auto-extract products
    browser_click_coords,    # by coordinates (fallback)
    browser_hover,

    # Typing ─────────────────────────────────
    browser_fill,            # clear + type (press_enter=False default)
    browser_type,            # type into focused element (autocomplete)
    browser_key_press,       # single key or chord
    browser_select,          # <select> dropdown

    # Visual ─────────────────────────────────
    browser_inspect,         # screenshot on demand
    browser_highlight,       # screenshot with red box

    # Completion ─────────────────────────────
    stop,
]


# ─────────────────────────────────────────────
# 7. SYSTEM PROMPT  (lean — hard cases in code)
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Browser Navigation Agent controlling a real Chrome browser.

━━ HOW TO CHOOSE YOUR STRATEGY ━━

Every dom_snapshot includes a characteristics field that tells you what kind of
page you are on. Read it after every navigate and choose tools accordingly:

  characteristics.has_canvas    = true  visual content (canvas elements)
  characteristics.has_map       = true  map tiles — Google Maps, Leaflet, Mapbox, etc.
  characteristics.is_spa        = true  React/Next/Angular/Vue — DOM selectors unstable
  characteristics.has_products  = true  e-commerce product cards
  characteristics.is_form_heavy = true  5+ inputs — careful with press_enter
  characteristics.has_jobs      = true  job listings — read from page_text
  characteristics.has_listings  = true  rental/real estate listings
  characteristics.is_json       = true  API response — use browser_evaluate for fields

Strategy by characteristic:

  has_map=true OR has_canvas=true
    → browser_navigate(url, visual=True)   see the page first
    → get_accessibility_tree               find inputs — map UIs have no stable IDs
    → browser_inspect()                    confirm visual result after acting

    Google Maps directions specifically:
    1. Click Directions button via get_accessibility_tree
    2. browser_type() origin → click first suggestion via coords from browser_inspect
    3. browser_type() destination → click first suggestion via coords
    4. Wait for routes to load → browser_inspect to see route panel
    5. Alternative routes are listed in the LEFT PANEL — scroll it with:
       browser_evaluate("document.querySelector('div[role=main]').scrollTop += 300")
       Then get_accessibility_tree to read all route options (time, distance, via)
    6. Do NOT click gray lines on the map canvas — they are not reliably clickable
    7. Read all route times and via-roads from the left panel text

  is_spa=true (no map/canvas)
    → get_accessibility_tree first         read_page may miss dynamic elements
    → browser_click_coords from tree       coordinates more reliable than selectors
    → for filter/modal panels on SPAs:     browser_inspect first to SEE the panel,
                                           then browser_click_coords directly
                                           do NOT try CSS selectors or browser_evaluate
                                           on filter panels — they have no stable IDs

  has_products=true
    → browser_click_sort → organic[]       no separate browser_get_products needed
    → first organic item that IS the product → browser_navigate to its url

  is_form_heavy=true
    → browser_fill(sel, val, press_enter=False)  never auto-submit filter inputs
    → click Apply/Done button separately

  has_jobs=true OR has_listings=true
    → browser_read_page() → read text field for listings
    → apply filters from buttons/inputs lists

  is_json=true
    → browser_evaluate("JSON.parse(document.body.innerText).field_name")

  none of the above (standard HTML)
    → browser_read_page() → click/fill by ID → read dom_snapshot to confirm

━━ WHAT EVERY ACTION TOOL RETURNS ━━

Every tool automatically returns a dom_snapshot:
  page_text       : 5000 chars visible text
  buttons         : up to 30 visible buttons (id/text/aria-label)
  inputs          : up to 20 visible inputs  (id/name/type/placeholder)
  alerts          : CAPTCHA_DETECTED | ACCESS_BLOCKED | LOGIN_WALL
  characteristics : page type flags (read these first)
  url, title

━━ YOUR TOOLS (18 total) ━━

Reading:
  browser_read_page(full_page=False)
                         full_page=False: inputs+buttons+links+headings+tables+meta+8000 chars text
                         full_page=True:  same + auto-scrolls entire page → up to 50,000 chars
                         Use full_page=True for articles, job descriptions, long listings,
                         product detail pages — any page where content is below the fold
                         Use full_page=False (default) for search results and filter UIs
  browser_get_products     e-commerce: {title,price,url} cards, organic[] pre-filtered
  browser_evaluate         JS for exact values. status=not_found means absent — never navigate to null
  get_accessibility_tree   SPA/React/Maps — use when read_page misses elements

Navigation:
  browser_navigate(url, visual=False)   DOM only — standard pages, forms, text, APIs
  browser_navigate(url, visual=True)    DOM + screenshot — maps, canvas, first visual load
  browser_go_back              back
  browser_wait                 wait for JS
  browser_scroll_element(sel)  scroll a specific panel div — use for Maps left panel,
                               search sidebars, modals. Not whole-page scroll.

Clicking:
  browser_click(selector)               CSS selector — preferred
  browser_click_sort(sel, label)        sort + auto-verify + auto-extract products
  browser_click_coords(x, y)           coordinate fallback
  browser_hover(selector)              reveal dropdowns

Typing:
  browser_fill(sel, text, press_enter=False)  clear+type. True only for search/login
  browser_type(text)                          into focused element — autocomplete
  browser_key_press(key)                      'Enter','Tab','Escape','ArrowDown'
  browser_select(sel, value)                  <select> dropdown

Visual:
  browser_inspect          screenshot of current page
  browser_highlight(sel)   screenshot with red box

Completion:
  stop(answer)             MUST be a tool call — never write <stop> as text

━━ FALLBACK CHAIN ━━
  1. browser_read_page → browser_click(id or [aria-label='...'])
  2. fails → browser_click_coords(x, y)
  3. not found → get_accessibility_tree → browser_click_coords
  4. still stuck → STOP and ask human

━━ HARD STOPS ━━
  CAPTCHA_DETECTED → "Bot check on [site]. Please solve in browser, then type done."
                     Do NOT try to solve it. Do NOT switch sites.
  LOGIN_WALL       → ask for credentials
  ACCESS_BLOCKED   → ask human to navigate manually
  Same approach failed twice → switch strategy or ask human

━━ NEVER INVENT URLS ━━
Only navigate to URLs you read from the page.
If browser_evaluate returns not_found — do not navigate to null.

━━ E-COMMERCE SORTING ━━
  browser_click_sort returns sort_verified + organic[] automatically.
  If sort_verified=False:
    url = browser_evaluate("window.location.href") result
    Zillow:  browser_navigate(url + "&sort=paymentAsc")
    Amazon:  browser_navigate(url + "&s=price-asc-rank")
  Skip items whose title describes a part/accessory — find the complete product.

━━ RESUMING AFTER HUMAN INPUT ━━
Call browser_read_page() to re-read page state before continuing."""


# ─────────────────────────────────────────────
# 8. LOOP & STEP GUARDS
# ─────────────────────────────────────────────

def _detect_loop(messages: list, limit: int = 3) -> str | None:
    full, names = [], []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage): break
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                full.append((tc.get("name",""), str(sorted(tc.get("args",{}).items()))))
                names.append(tc.get("name",""))

    if len(full) >= limit and len(set(full[:limit])) == 1:
        return (f"\n\n*** IDENTICAL LOOP: called '{full[0][0]}' with same args {limit}x. "
                f"STOP. Use get_accessibility_tree or ask human. ***")

    osc = limit * 2
    if len(names) >= osc:
        tail = names[:osc]
        if len(set(tail)) <= 2:
            dom = max(set(tail), key=tail.count)
            if tail.count(dom) >= limit:
                return (f"\n\n*** OSCILLATION LOOP: '{dom}' called {tail.count(dom)}x "
                        f"in last {osc} actions. Call browser_read_page() and compile answer. ***")
    return None


def _consecutive_warnings(messages: list) -> int:
    count = 0
    positions = [(i, m) for i, m in enumerate(messages) if isinstance(m, AIMessage)]
    for _, (idx, _) in enumerate(reversed(positions)):
        if _detect_loop(messages[:idx]): count += 1
        else: break
    return count


def _steps_since_human(messages: list) -> int:
    n = 0
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage): break
        if isinstance(msg, AIMessage) and msg.tool_calls: n += len(msg.tool_calls)
    return n


def _best_answer(messages: list) -> str:
    """
    Extract best answer from history when step budget fires.
    Skips mid-task reasoning ("Let me...", "Now I need to...") and
    prefers text that contains actual results (prices, addresses, ratings).
    """
    answer_signals  = ['$', '/mo', '/month', 'address', 'located', 'available',
                       'bedroom', 'result', 'found', 'cheapest', 'rating', 'stars',
                       'price', 'cost', 'route', 'minutes', 'miles', 'via',
                       'salary', 'apply', 'listed', 'sqft']
    reasoning_noise = ['let me', "now i need", "i'll try", "i will", "i need to",
                       "let me try", "good!", "perfect!", "excellent!", "great!",
                       "i can see", "now let me", "first, let me", "let me click",
                       "let me navigate", "let me read"]

    candidates = []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage): break
        if isinstance(msg, AIMessage):
            c = msg.content
            t = (c if isinstance(c, str) else
                 " ".join(b.get("text","") for b in c if isinstance(b,dict))).strip()
            if len(t) < 100: continue
            t_lc = t.lower()
            if any(n in t_lc[:80] for n in reasoning_noise): continue
            score = sum(1 for s in answer_signals if s in t_lc)
            if score > 0:
                candidates.append((score, len(t), t))

    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return candidates[0][2]

    # Fallback — longest non-reasoning text
    best = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage): break
        if isinstance(msg, AIMessage):
            c = msg.content
            t = (c if isinstance(c, str) else
                 " ".join(b.get("text","") for b in c if isinstance(b,dict))).strip()
            t_lc = t.lower()
            if (len(t) > len(best) and len(t) > 100 and
                    not any(n in t_lc[:80] for n in reasoning_noise)):
                best = t
    return best or ("Step budget reached before task completed. "
                    "Please check the browser and tell me what you see.")


# ─────────────────────────────────────────────
# 9. CONTEXT HELPER (screenshot token management)
# ─────────────────────────────────────────────

def _safe_messages(messages: list) -> list:
    import json
    last_ss = None
    for i, msg in enumerate(messages):
        if isinstance(msg, ToolMessage):
            try:
                d = json.loads(msg.content) if isinstance(msg.content, str) else {}
                if isinstance(d, dict) and d.get("screenshot_b64"): last_ss = i
            except Exception: pass

    out = []
    for i, msg in enumerate(messages):
        if not isinstance(msg, ToolMessage): out.append(msg); continue
        try: d = json.loads(msg.content) if isinstance(msg.content, str) else {}
        except Exception: d = {}
        b64 = d.get("screenshot_b64") if isinstance(d, dict) else None
        if not b64: out.append(msg); continue
        if i == last_ss:
            td = {k:v for k,v in d.items() if k!="screenshot_b64"}
            out.append(HumanMessage(content=[
                {"type":"tool_result","tool_use_id":msg.tool_call_id,"content":[
                    {"type":"text","text":json.dumps(td)},
                    {"type":"image","source":{"type":"base64",
                                              "media_type":"image/png","data":b64}},
                ]}
            ]))
        else:
            td = {k:v for k,v in d.items() if k!="screenshot_b64"}
            out.append(ToolMessage(content=json.dumps(td),
                                   tool_call_id=msg.tool_call_id,
                                   name=getattr(msg,"name",None)))
    return out


# ─────────────────────────────────────────────
# 10. AGENT NODE
# ─────────────────────────────────────────────

class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

llm = ChatAnthropic(
    model=MODEL_ID, api_key=os.getenv("ANTHROPIC_API_KEY"), temperature=0
).bind_tools(tools)


async def agent_node(state: State):
    raw   = state["messages"]
    steps = _steps_since_human(raw)

    # Step budget: hard stop at 20, warn at 15
    if steps >= 20:
        ans = _best_answer(raw)
        print(f"\n🚨 [Budget] {steps} steps — stopping.")
        # If no real answer found, give an honest status message
        if "Step budget reached" in ans or len(ans) < 50:
            ans = ("I reached the 20-step limit before completing the task. "
                   "The browser is still open at the current page. "
                   "Please tell me what you see or give me a more specific next step.")
        return {"messages": [AIMessage(content=ans, tool_calls=[
            {"name":"stop","args":{"answer":ans},"id":"budget_stop","type":"tool_call"}
        ])]}

    step_warn = ""
    if steps >= 15:
        print(f"\n⚠️  [Budget] {steps}/20.")
        step_warn = (f"\n\n*** {steps}/20 steps. Call stop(answer=...) NOW "
                     f"with what you have. No more tool calls. ***")

    # Loop guard
    loop_warn = _detect_loop(raw)
    if loop_warn and _consecutive_warnings(raw) >= 3:
        print("\n🚨 [Loop] Hard stop.")
        return {"messages": [AIMessage(content=(
            "🚨 Stuck in a loop. Please check browser and tell me what you see, "
            "or type 'done' if CAPTCHA was solved."))]}
    if loop_warn:
        print("\n⚠️  [Loop] Warning injected.")

    # LLM call
    safe     = _safe_messages(raw)
    prompt   = SYSTEM_PROMPT + (loop_warn or "") + step_warn
    response = await llm.ainvoke([SystemMessage(content=prompt)] + safe)

    # Intercept <stop> written as text
    raw_text = response.content if isinstance(response.content, str) else \
               " ".join(b.get("text","") for b in response.content if isinstance(b,dict))
    if "<stop>" in raw_text.lower() and not response.tool_calls:
        m = re.search(r'<stop>(.*?)</stop>', raw_text, re.DOTALL | re.IGNORECASE)
        ans = re.sub(r'^answer\s*=\s*','', (m.group(1) if m else raw_text)).strip()
        print("\n⚠️  [Fix] <stop> as text → tool call.")
        return {"messages": [AIMessage(content=ans, tool_calls=[
            {"name":"stop","args":{"answer":ans},"id":"stop_fix","type":"tool_call"}
        ])]}

    c = response.content
    if isinstance(c, str) and c.strip(): print(f"\n🟢 {c}")
    elif isinstance(c, list):
        for b in c:
            if isinstance(b,dict) and b.get("type")=="text" and b["text"].strip():
                print(f"\n🟢 {b['text']}")

    return {"messages": [response]}


def human_input_node(state: State):
    return {"messages": [HumanMessage(content=interrupt("Waiting:"))]}


def router(state: State):
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls: return "tools"
    return "human_input"


def tools_router(state: State):
    last = state["messages"][-1]
    if isinstance(last, ToolMessage) and getattr(last,"name","") == "stop":
        return "human_input"
    return "agent"


# ─────────────────────────────────────────────
# 11. GRAPH
# ─────────────────────────────────────────────

workflow = StateGraph(State)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(tools))
workflow.add_node("human_input", human_input_node)
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", router)
workflow.add_conditional_edges("tools", tools_router)
workflow.add_edge("human_input", "agent")
app = workflow.compile(checkpointer=InMemorySaver())


# ─────────────────────────────────────────────
# 12. MAIN
# ─────────────────────────────────────────────

async def stream_run(input_data, config):
    async for event in app.astream(input_data, config, stream_mode="updates"):
        for node, data in event.items():
            if node == "tools":
                msgs = data.get("messages", [])
                if msgs: print(f"  🔧 [{getattr(msgs[-1],'name','tool')}]")


async def main():
    sid    = str(uuid.uuid4())[:8]
    config = {"configurable": {"thread_id": f"nav-{sid}"}}

    print("\n  🌐  BROWSER AGENT  v7\n")

    prompt = input("\n[Task]: ").strip()
    if not prompt or prompt.lower() == "exit": return

    print("\n⏳ Starting...\n")
    await stream_run({"messages": [HumanMessage(content=prompt)]}, config)

    while True:
        cmd = input("\n[Reply / 'exit']: ").strip()
        if cmd.lower() == "exit":
            print("\nShutting down..."); break
        if not cmd: cmd = "Please continue."
        print("\n⏳ Resuming...\n")
        try:
            await stream_run(Command(resume=cmd), config)
        except Exception as e:
            print(f"❌ {e}"); break

    if browser_session["context"]: await browser_session["context"].close()
    if browser_session["playwright"]: await browser_session["playwright"].stop()
    print("\n✅ Done.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted.")
