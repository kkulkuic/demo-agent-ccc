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
load_dotenv(override=True)

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
from PIL import Image, ImageDraw, ImageFont
from tavily import TavilyClient

os.makedirs("logs", exist_ok=True)
os.makedirs("playwright/.auth", exist_ok=True)

MODEL_ID = "claude-haiku-4-5-20251001"

# ─────────────────────────────────────────────
# SCREENSHOT SESSION LOG
# ─────────────────────────────────────────────

_screenshot_log: list[dict] = []

def _log_screenshot(tool: str, path: str, annotated: str | None = None):
    _screenshot_log.append({
        "tool":      tool,
        "path":      path,
        "annotated": annotated,
        "ts":        time.strftime("%H:%M:%S"),
    })

def _print_screenshot_summary(label: str = "Navigation"):
    if not _screenshot_log:
        return
    print(f"\n{'─'*54}")
    print(f"  📸  {label} — screenshots ({len(_screenshot_log)} total)")
    print(f"{'─'*54}")
    for i, entry in enumerate(_screenshot_log, 1):
        ann = f"\n       ↳ annotated: {entry['annotated']}" if entry["annotated"] else ""
        print(f"  [{i:02d}] {entry['ts']}  {entry['tool']:<28} {entry['path']}{ann}")
    print(f"{'─'*54}\n")
    _screenshot_log.clear()

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
            slow_mo=120,
            args=["--window-position=0,0", "--window-size=1280,900"],
        )
        browser_session["context"] = ctx

        async def on_page(page):
            await stealth_async(page)
            await page.bring_to_front()
            browser_session["page"] = page
            print(f"  🔀 [New tab] {page.url or 'loading...'}")

        ctx.on("page", on_page)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await stealth_async(page)
        await page.bring_to_front()
        browser_session["page"] = page

    return browser_session["page"]

# ─────────────────────────────────────────────
# 2. SHARED HELPERS
# ─────────────────────────────────────────────

async def dom_snapshot() -> dict:
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

            const ch = {};
            ch.has_canvas  = document.querySelectorAll('canvas').length > 0;
            ch.has_map     = !!(
                document.querySelector('.mapboxgl-map,.leaflet-container,#map,[class*="gm-style"]') ||
                document.querySelector('[class*="map-container"],[class*="mapCanvas"]') ||
                document.querySelector('img[src*="maps.googleapis"],[src*="tile.openstreetmap"]')
            );
            ch.is_spa = !!(
                document.querySelector('[data-reactroot],[data-react-helmet],#__NEXT_DATA__') ||
                window.__NEXT_DATA__ || window.__NUXT__ ||
                document.querySelector('[ng-version],[data-ng-version]') ||
                document.querySelector('[data-v-app]') ||
                window.__REACT_DEVTOOLS_GLOBAL_HOOK__
            );
            ch.has_products  = !!(
                document.querySelector('[data-asin],[data-product-id]') ||
                document.querySelectorAll('.product-card,.s-result-item,[class*="product-tile"]').length > 2
            );
            ch.is_form_heavy = document.querySelectorAll('input,select,textarea').length >= 5;
            ch.has_jobs      = !!(
                document.querySelector('[class*="job-card"],[class*="jobCard"],[data-job-id]') ||
                (lc.includes('salary') && (lc.includes('apply') || lc.includes('job')))
            );
            ch.has_listings  = !!(
                document.querySelector('[class*="listing-card"],[data-listing-id],[class*="property-card"]') ||
                (lc.includes('bed') && lc.includes('bath') && lc.includes('rent'))
            );
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
    _log_screenshot(prefix, path)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return {"screenshot_path": path, "screenshot_b64": b64}


def _annotate_screenshot(path: str, boxes: list[dict]) -> tuple[str, str]:
    """Draw numbered markers on a screenshot. Returns (annotated_path, b64)."""
    annotated_path = path.replace(".png", "_annotated.png")
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
    except Exception:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        except Exception:
            font = ImageFont.load_default()

    with Image.open(path) as img:
        draw = ImageDraw.Draw(img, "RGBA")
        for box in boxes:
            x, y, w, h = box["x"], box["y"], box["width"], box["height"]
            idx   = box.get("index", 1)
            label = box.get("label", "")
            draw.rectangle([x, y, x+w, y+h], fill=(255,0,0,40), outline=(255,0,0,255), width=3)
            badge_r = 14
            bx, by  = x + badge_r, y + badge_r
            draw.ellipse([bx-badge_r, by-badge_r, bx+badge_r, by+badge_r], fill=(255,0,0,255))
            draw.text((bx, by), str(idx), font=font, fill="white", anchor="mm")
            if label:
                draw.rectangle([x, max(0,y-26), x+len(label)*11+8, y], fill=(255,0,0,200))
                draw.text((x+4, max(0,y-24)), label, font=font, fill="white")
        img.save(annotated_path)

    with open(annotated_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return annotated_path, b64


async def _flash_highlight(page, box: dict, label: str = "", duration: float = 1.5):
    lbl = label[:60] if label else ""
    try:
        await page.evaluate("""([x, y, w, h, lbl]) => {
            document.getElementById('__agent_flash__')?.remove();
            const ov = document.createElement('div');
            ov.id = '__agent_flash__';
            Object.assign(ov.style, {
                position: 'fixed', pointerEvents: 'none',
                left: x+'px', top: y+'px', width: w+'px', height: h+'px',
                background: 'rgba(255,30,30,0.25)',
                border: '4px solid rgba(255,30,30,1)',
                boxSizing: 'border-box', zIndex: '2147483647',
                animation: 'agentPulse 0.4s ease-in-out infinite alternate',
            });

            if (!document.getElementById('__agent_flash_style__')) {
                const style = document.createElement('style');
                style.id = '__agent_flash_style__';
                style.textContent = `
                    @keyframes agentPulse {
                        from { box-shadow: 0 0 0 0 rgba(255,30,30,0.7); }
                        to   { box-shadow: 0 0 0 8px rgba(255,30,30,0); }
                    }`;
                document.head.appendChild(style);
            }

            if (lbl) {
                const badge = document.createElement('div');
                badge.textContent = '🎯 ' + lbl;
                Object.assign(badge.style, {
                    position: 'absolute', bottom: '100%', left: '0',
                    background: 'rgba(200,0,0,0.95)', color: '#fff',
                    fontSize: '12px', fontWeight: 'bold',
                    padding: '3px 10px', borderRadius: '3px 3px 0 0',
                    whiteSpace: 'nowrap', maxWidth: '320px',
                    overflow: 'hidden', textOverflow: 'ellipsis',
                    boxShadow: '0 -2px 6px rgba(0,0,0,0.3)',
                });
                ov.appendChild(badge);
            }

            const dot = document.createElement('div');
            Object.assign(dot.style, {
                position: 'absolute',
                left: (w/2-6)+'px', top: (h/2-6)+'px',
                width: '12px', height: '12px', borderRadius: '50%',
                background: 'rgba(255,30,30,1)', border: '2px solid white',
                boxShadow: '0 0 4px rgba(0,0,0,0.5)',
            });
            ov.appendChild(dot);
            document.body.appendChild(ov);

            return ov.getBoundingClientRect().width;
        }""", [box["x"], box["y"], box["width"], box["height"], lbl])

        await page.evaluate("() => new Promise(r => requestAnimationFrame(r))")
        await asyncio.sleep(duration)
    except Exception:
        pass
    finally:
        try:
            await page.evaluate("""() => {
                document.getElementById('__agent_flash__')?.remove();
            }""")
        except Exception:
            pass

async def _dismiss_popups(page) -> list[str]:
    dismissed = []
    try:
        removed = await page.evaluate("""() => {
            const removed = [];
            const overlaySelectors = [
                '#onetrust-banner-sdk', '#onetrust-consent-sdk',
                '#cookie-banner', '#cookie-notice', '#cookie-law-info-bar',
                '.cookie-banner', '.cookie-notice', '.cookie-consent',
                '[id*="cookie"]', '[class*="cookie-banner"]',
                '[id*="gdpr"]', '[class*="gdpr"]',
                '[id*="consent"]', '[class*="consent-banner"]',
                '#drift-widget-container', '#drift-frame-controller',
                '#intercom-container', '#intercom-frame',
                '#hubspot-messages-iframe-container',
                '[id*="chat-widget"]', '[class*="chat-widget"]',
                '[id*="chat-container"]', '[class*="chat-container"]',
                '[id*="live-chat"]', '[class*="live-chat"]',
                '[class*="AkamaiChat"]', '[id*="AkamaiChat"]',
                '[class*="kai-chat"]', '[id*="kai-chat"]',
                '[class*="sales-chat"]', '[id*="sales-widget"]',
                'iframe[src*="drift"]', 'iframe[src*="intercom"]',
                'iframe[src*="hubspot"]', 'iframe[src*="zendesk"]',
                'iframe[src*="livechat"]', 'iframe[src*="crisp"]',
                'iframe[src*="tawk"]', 'iframe[src*="chat"]',
                '[class*="modal-overlay"]', '[class*="overlay--visible"]',
                '[role="dialog"][aria-modal="true"]',
            ];
            for (const sel of overlaySelectors) {
                document.querySelectorAll(sel).forEach(el => {
                    if (el && el.offsetHeight > 0) {
                        el.remove();
                        removed.push(sel);
                    }
                });
            }
            document.querySelectorAll('iframe').forEach(el => {
                const src = el.src || '';
                const id  = el.id  || '';
                const cls = el.className || '';
                const isContent = el.closest('main, article, [role=main], .content');
                if (!isContent && (
                    src.includes('chat') || src.includes('widget') ||
                    src.includes('support') || src.includes('bot') ||
                    id.includes('chat') || cls.includes('chat') ||
                    id.includes('widget') || cls.includes('widget')
                )) {
                    el.remove();
                    removed.push('iframe:' + (src || id).substring(0, 40));
                }
            });
            document.querySelectorAll('body > div, body > section, body > aside').forEach(el => {
                const s = window.getComputedStyle(el);
                const r = el.getBoundingClientRect();
                if ((s.position === 'fixed' || s.position === 'sticky') &&
                    r.width  > window.innerWidth  * 0.2 &&
                    r.height > window.innerHeight * 0.1 &&
                    el.id !== '__agent_flash__' &&
                    el.id !== '__agent_flash_style__') {
                    el.remove();
                    removed.push('fixed:' + (el.id || el.className).substring(0, 30));
                }
            });
            return removed;
        }""")
        if removed:
            dismissed.extend(removed)

        dismiss_texts = [
            "accept all", "accept cookies", "accept all cookies",
            "agree", "i agree", "got it", "ok", "okay",
            "close", "dismiss", "no thanks", "reject all",
            "×", "✕", "✖", "x",
        ]
        # Skip Chrome restore/crash banners — never click Restore
        chrome_skip = ["restore", "send crash", "help make google chrome"]

        buttons = await page.query_selector_all("button, [role=button], a[href='#']")
        for btn in buttons[:40]:
            try:
                text = (await btn.inner_text()).strip().lower()
                aria = (await btn.get_attribute("aria-label") or "").lower()
                # Skip Chrome crash/restore dialog buttons
                if any(s in text for s in chrome_skip):
                    continue
                if any(t in text or t in aria for t in dismiss_texts):
                    box = await btn.bounding_box()
                    if box and box["width"] > 0:
                        await btn.click()
                        dismissed.append(f"clicked: {text[:30]}")
                        await asyncio.sleep(0.3)
                        break
            except Exception:
                continue

    except Exception:
        pass

    if dismissed:
        print(f"  🧹 Dismissed: {', '.join(d[:25] for d in dismissed[:3])}")
    return dismissed


# ─────────────────────────────────────────────
# 3. NAV TOOLS
# ─────────────────────────────────────────────

@tool
async def browser_navigate(url: str, visual: bool = False):
    """
    Navigate to a URL. Returns dom_snapshot (url, title, page_text, buttons, inputs).

    visual=False (default): DOM snapshot only — standard pages, forms, APIs.
    visual=True:            DOM + screenshot — maps, canvas, SPAs, unfamiliar sites.
                            Always use visual=True on first load of an unfamiliar site.

    Automatically dismisses cookie banners and chat popups after loading.
    Waits for networkidle and triggers a scroll nudge to force SPA lazy-rendering.
    If page_text < 200 chars a render_warning is set — call browser_inspect() first.
    """
    page = await get_session()
    try:
        await page.bring_to_front()
        print(f"  🌐 → {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            await asyncio.sleep(2)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        await _dismiss_popups(page)
        await page.evaluate("() => { window.scrollBy(0, 100); window.scrollBy(0, -100); }")
        await asyncio.sleep(1.0)
        await _dismiss_popups(page)

        dom = await dom_snapshot()

        if len(dom.get("page_text", "").strip()) < 200:
            dom["render_warning"] = (
                "Page text is very short — SPA may not have rendered yet. "
                "Call browser_inspect() before reading content."
            )
            print(f"  ⚠️  Page may not have rendered ({len(dom.get('page_text','').strip())} chars)")

        if visual:
            ss = await _screenshot("nav_visual")
            return {"status": "navigated", **dom, **ss}
        return {"status": "navigated", **dom}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_click(selector: str):
    """
    Click by CSS selector. Scrolls the element into the viewport first,
    then flashes a live red highlight so it's always visible on screen before clicking.
    """
    page = await get_session()
    try:
        await page.bring_to_front()
        el  = await page.wait_for_selector(selector, timeout=8000)
        await el.scroll_into_view_if_needed()
        await asyncio.sleep(0.3)
        box = await el.bounding_box()
        if box:
            print(f"  🎯 clicking '{selector}' @ ({box['x']:.0f},{box['y']:.0f})")
            await _flash_highlight(page, box, selector)
        await page.click(selector)
        await asyncio.sleep(0.5)
        return {"status": "clicked", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_fill(selector: str, text: str, press_enter: bool = False):
    """
    Clear a field and type text. press_enter=False by default.
    Set True only for search bars and login forms — never for filter inputs.
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
    Use for Google Maps autocomplete, DuckDuckGo, any dynamic search field.
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
    """Press a key or chord: 'Enter', 'Escape', 'Tab', 'ArrowDown', 'Control+a',
    'PageDown', 'PageUp', 'Home', 'End'."""
    page = await get_session()
    try:
        # Normalize common key names
        _key_map = {
            "Page_Down": "PageDown", "Page_Up": "PageUp",
            "page_down": "PageDown", "page_up": "PageUp",
        }
        key = _key_map.get(key, key)
        await page.keyboard.press(key)
        await asyncio.sleep(0.4)
        return {"status": f"pressed '{key}'", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_click_coords(x: float, y: float):
    """
    Click at pixel coordinates. Fallback when no stable CSS selector exists.
    Flashes a 40x40px target marker before clicking.
    """
    page = await get_session()
    try:
        await page.bring_to_front()
        print(f"  🎯 clicking coords ({x:.0f},{y:.0f})")
        await _flash_highlight(page,
            {"x": x-20, "y": y-20, "width": 40, "height": 40},
            f"({x:.0f},{y:.0f})")
        await page.mouse.click(x, y)
        await asyncio.sleep(0.5)
        return {"status": f"clicked ({x},{y})", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_scroll_element(selector: str, direction: str = "down", amount: int = 300):
    """
    Scroll a specific element (not the whole page) by pixel amount.
    Use for Google Maps left panel, search sidebars, overflow modals.
    """
    page = await get_session()
    try:
        move = amount if direction == "down" else -amount
        await page.evaluate("""([sel, px]) => {
            const el = document.querySelector(sel);
            if (el) el.scrollTop += px;
        }""", [selector, move])
        await asyncio.sleep(0.5)
        return {"status": f"scrolled '{selector}' {direction} {amount}px",
                **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_select(selector: str, value: str):
    """Select a <select> dropdown option by value."""
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
    """Hover to reveal dropdowns or tooltips. Revealed elements appear in dom_snapshot."""
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
    """Go back in browser history."""
    page = await get_session()
    try:
        await page.go_back(wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(0.5)
        return {"status": "back", **await dom_snapshot()}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_wait(seconds: float = 2.0):
    """Wait for JS/network to settle. Returns dom_snapshot after waiting."""
    await asyncio.sleep(seconds)
    return {"status": f"waited {seconds}s", **await dom_snapshot()}


@tool
async def browser_read_page(full_page: bool = False):
    """
    Read the current page in depth. Returns inputs, buttons, links, headings, tables, meta.

    full_page=False  use when you need headings/links/tables/meta that dom_snapshot lacks.
                     Do NOT call right after browser_navigate — that already returned page_text.
    full_page=True   auto-scrolls entire page up to 50,000 chars.
                     Use for articles, job descriptions, long listings, product detail pages.
    """
    page = await get_session()
    try:
        if full_page:
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
            const MAX  = fullPage ? 50000 : 8000;
            const raw  = document.body.innerText;
            const text = raw.substring(0, MAX);

            const inputs = [...document.querySelectorAll('input,textarea,select')]
                .filter(e => e.getBoundingClientRect().width > 0)
                .map(e => ({id:e.id||null, name:e.name||null, type:e.type||null,
                            ph:e.placeholder||null, aria:e.getAttribute('aria-label')||null,
                            val:e.value?e.value.substring(0,120):null}));

            const buttons = [...document.querySelectorAll(
                'button,[role=button],input[type=submit],input[type=button]'
            )].filter(e => e.getBoundingClientRect().width > 0)
              .map(e => ({id:e.id||null,
                          text:e.innerText?e.innerText.substring(0,80).trim():null,
                          aria:e.getAttribute('aria-label')||null}));

            const links = [...document.querySelectorAll('a[href]')]
                .slice(0,60).map(e => ({href:e.href,
                    text:e.innerText?e.innerText.substring(0,80).trim():null}))
                .filter(l => l.text && l.text.length > 0);

            const headings = [...document.querySelectorAll('h1,h2,h3')]
                .map(e => ({level:e.tagName.toLowerCase(),
                            text:e.innerText.trim().substring(0,120)}))
                .filter(h => h.text.length > 0);

            const tables = [...document.querySelectorAll('table')].slice(0,3)
                .map(tbl => [...tbl.querySelectorAll('tr')].map(tr =>
                    [...tr.querySelectorAll('td,th')]
                        .map(cell => cell.innerText.trim().substring(0,60))
                ).filter(row => row.length > 0)).filter(t => t.length > 0);

            const meta = {
                description: document.querySelector('meta[name=description]')
                                ?.getAttribute('content')||null,
                og_title:    document.querySelector('meta[property="og:title"]')
                                ?.getAttribute('content')||null,
                og_desc:     document.querySelector('meta[property="og:description"]')
                                ?.getAttribute('content')||null,
                canonical:   document.querySelector('link[rel=canonical]')
                                ?.getAttribute('href')||null,
            };

            return {url:location.href, title:document.title, text,
                    text_length:raw.length, is_truncated:raw.length>MAX,
                    inputs, buttons, links, headings, tables, meta};
        }""", full_page)

        return {"status": "success", **result}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_evaluate(js_expression: str):
    """
    Run arbitrary JS in the browser. Use only for:
      JSON API fields:  JSON.parse(document.body.innerText).field_name
      DOM state reads:  document.querySelector('sel').innerText
    Do NOT use to get the current URL — every tool response already includes url.
    Returns status=not_found if null/undefined — never navigate to null.
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
    Structured role/name tree — fallback for React, Maps, Angular pages where
    browser_read_page misses dynamically generated elements.
    """
    page = await get_session()
    try:
        # Use CDP session for accessibility snapshot (Playwright 1.58+)
        cdp = await page.context.new_cdp_session(page)
        snap = await cdp.send("Accessibility.getFullAXTree")
        
        def flat(nodes, d=0):
            lines = []
            for node in nodes:
                r = node.get("role", {}).get("value", "")
                n = node.get("name", {}).get("value", "")
                v = node.get("value", {}).get("value", "")
                if r and r not in ("none", "presentation", "generic", ""):
                    parts = [f"{'  '*d}[{r}]"]
                    if n: parts.append(f'"{n}"')
                    if v: parts.append(f'= "{v}"')
                    lines.append(" ".join(parts))
                # Children are in nested structure
                for c in node.get("children", []):
                    lines.extend(flat([c], d+1))
            return lines
        
        nodes = snap.get("nodes", [])
        tree_str = "\n".join(flat(nodes)[:200])
        await cdp.detach()
        return {"status": "success", "tree": tree_str, "url": page.url}
    except Exception as e:
        return {"error": str(e)}


@tool
async def browser_inspect():
    """
    Take a screenshot of the current page and return as base64 + dom_snapshot.
    Use to visually confirm page state: maps, charts, canvas, CAPTCHAs.
    Always call before stop() to confirm the right content is visible on screen.
    """
    ss  = await _screenshot("inspect")
    dom = await dom_snapshot()
    return {"status": "visual", **ss, **dom}


@tool
async def dismiss_popups():
    """
    Manually dismiss cookie banners, GDPR notices, chat widgets, and modal overlays
    on the current page. Called automatically after browser_navigate, but call this
    manually if a popup appears mid-session after a click or scroll.
    Returns list of what was dismissed.
    """
    page = await get_session()
    dismissed = await _dismiss_popups(page)
    dom = await dom_snapshot()
    return {"status": "dismissed", "removed": dismissed, **dom}


@tool
async def stop(answer: str):
    """
    Signal task complete. ALWAYS call this as a tool — never write answer as plain text.
    Before calling stop():
      1. Scroll to the relevant content so it's visible on screen
      2. browser_inspect() to confirm the right content is showing
      3. Then call stop(answer=...)
    Auto-scrolls to first table or h2/h3 heading before final screenshot
    so the browser always shows actual content, not the page intro.
    """
    print(f"\n✅ [STOP] {answer}")
    try:
        page = await get_session()
        await page.bring_to_front()
        await page.evaluate("""() => {
            // Scroll back to top first, then find first meaningful content
            window.scrollTo(0, 0);
            const targets = [
                'table',
                '[class*="pricing"]', '[class*="price"]',
                '[class*="rate"]',    '[class*="tier"]',
                '[class*="cost"]',    '[class*="plan"]',
                // GCP / cloud doc specific
                'devsite-table', 'devsite-section',
                '[class*="devsite"]',
                '[data-custom-type="pricing"]',
                'h2', 'h3', 'h1',
            ];
            for (const sel of targets) {
                const el = document.querySelector(sel);
                if (el) {
                    el.scrollIntoView({ behavior: 'instant', block: 'start' });
                    return;
                }
            }
        }""")
        await asyncio.sleep(1.0)
        path = f"logs/final_{int(time.time())}.png"
        await page.screenshot(path=path)
        _log_screenshot("stop_final", path)
        print(f"  📷 Final browser state → {path}")
    except Exception as e:
        print(f"  ⚠️  Final screenshot failed: {e}")
    return {"status": "stopped", "answer": answer}


NAV_TOOLS = [
    browser_navigate,
    browser_click,
    browser_fill,
    browser_type,
    browser_key_press,
    browser_click_coords,
    browser_scroll_element,
    browser_select,
    browser_hover,
    browser_go_back,
    browser_wait,
    browser_read_page,
    browser_evaluate,
    get_accessibility_tree,
    browser_inspect,
    dismiss_popups,
    stop,
]

# ─────────────────────────────────────────────
# 4. RESEARCH TOOLS  (Tavily)
# ─────────────────────────────────────────────

def _tv() -> TavilyClient:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise ValueError("TAVILY_API_KEY not set in .env")
    return TavilyClient(api_key=key)


@tool
async def web_search(query: str, num_results: int = 7) -> str:
    """Search the web for any topic — news, facts, product info, stats."""
    try:
        result = await asyncio.to_thread(
            _tv().search, query, max_results=num_results, include_answer=True
        )
        chunks = []
        if result.get("answer"):
            chunks.append(f"Summary: {result['answer']}\n")
        for i, item in enumerate(result.get("results", []), 1):
            chunks.append(
                f"[{i}] {item.get('title', '')}\n"
                f"URL: {item.get('url', '')}\n"
                f"{item.get('content', '')[:1500]}"
            )
        return "\n\n---\n\n".join(chunks) if chunks else "No results."
    except Exception as e:
        return f"web_search error: {e}"


@tool
async def deep_scrape(url: str) -> str:
    """
    Extract full structured content from a specific URL.
    Use when web_search snippets are not detailed enough.
    """
    try:
        result = await asyncio.to_thread(_tv().extract, urls=[url])
        items = result.get("results", [])
        if not items:
            return "No content extracted."
        return items[0].get("raw_content", "No content.")[:4000]
    except Exception as e:
        return f"deep_scrape error: {e}"



@tool
async def web_fetch(url: str) -> str:
    """
    Fetch a URL directly via HTTP — no Tavily, no browser.
    Use when deep_scrape fails or returns empty content (some insurance/finance
    sites block Tavily extraction). Returns raw page text up to 5000 chars.
    Falls back gracefully if the site blocks bots or requires JS rendering.
    """
    try:
        import httpx
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            raw = resp.text

        # Strip HTML tags for readable text
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        if len(text) < 100:
            return f"web_fetch: page returned very little text — site may require JS rendering. Try deep_scrape instead."

        return text[:5000]
    except Exception as e:
        return f"web_fetch error: {e}"


RESEARCH_TOOLS = [web_search, deep_scrape, web_fetch]

# ─────────────────────────────────────────────
# 5. SYSTEM PROMPTS
# ─────────────────────────────────────────────

NAV_SYSTEM_PROMPT = """You are a Browser Navigation Agent controlling a real Chrome browser.

━━ WHAT EVERY TOOL RESPONSE INCLUDES ━━

Every tool automatically returns a dom_snapshot:
  url, title      : current page — already here, never call browser_evaluate for URL
  page_text       : 5000 chars visible text
  buttons         : up to 30 visible buttons (id/text/aria-label)
  inputs          : up to 20 visible inputs  (id/name/type/placeholder)
  alerts          : CAPTCHA_DETECTED | ACCESS_BLOCKED | LOGIN_WALL
  characteristics : page type flags — read these first

━━ STRATEGY BY PAGE TYPE ━━

  has_map=true OR has_canvas=true
    → browser_navigate(url, visual=True)   load + screenshot in one call
    → get_accessibility_tree               map UIs have no stable CSS IDs
    → browser_inspect()                    screenshot after subsequent actions only

    Google Maps directions:
    1. browser_navigate("https://www.google.com/maps", visual=True)
    2. dismiss_popups() once to clear Chrome restore banners before doing anything
    3. browser_click('button[aria-label="Directions"]') to open directions panel
    4. browser_click origin input → browser_type() the starting location
    5. browser_wait(1) to let suggestions load
       → call get_accessibility_tree() to read the suggestion list
       → find the best matching suggestion by name in the tree
       → call browser_inspect() to get a screenshot
       → use browser_click_coords() on the suggestion position from the screenshot
       → NEVER click (200,100) or any hardcoded coordinate before doing these steps
    6. browser_click destination input → browser_type() the destination
    7. Repeat step 5 for destination — same process, no guessing
    8. browser_wait(2) then browser_inspect() to confirm route is drawn on map
    9. The route panel MUST be visible before calling stop() — if map is zoomed out
       with no route shown, the directions panel has collapsed:
       → browser_click('div[id="omnibox-directions"]') to reopen it
       → or browser_navigate to direct URL format:
         https://www.google.com/maps/dir/ORIGIN/DESTINATION
       → then browser_inspect() to confirm route is visible before stop()

    Google Maps transport modes — ALWAYS check all 4 by default:
    The mode buttons (Drive/Transit/Walk/Cycle) appear at the top of the directions panel.
    NEVER modify the URL to switch modes — always click the buttons in the panel.
    Strategy:
    1. After route loads, browser_inspect() to see all 4 mode buttons at top of panel
    2. get_accessibility_tree() to find exact button positions and labels
    3. Click each mode button one at a time using browser_click_coords():
         - Car/Drive icon  → first button  (coords approx x=155, y=57)
         - Transit icon    → second button (coords approx x=203, y=57)
         - Walk icon       → third button  (coords approx x=251, y=57)
         - Cycle icon      → fourth button (coords approx x=299, y=57)
    4. After each click: browser_wait(1) then browser_inspect() to read the result
    5. Note each mode time/distance, then move to next mode button
    6. Compile all 4 results into a single summary
    If a mode button click does not change the view — browser_inspect() first to
    confirm button positions from screenshot, then retry with corrected coordinates.
    NEVER navigate to a new URL to switch transport modes.
    ALWAYS check all transport modes for any route query.

  is_spa=true
    → browser_navigate(url, visual=True)   always visual on SPA first load
    → render_warning present → browser_wait(2) then browser_inspect()
    → get_accessibility_tree               read_page may miss dynamic elements
    → browser_click_coords from tree       more reliable than CSS on SPAs

  render_warning in navigate response
    → page is blank — JS hasn't rendered yet
    → ALWAYS call browser_inspect() before reading any content
    → if still blank: browser_wait(3) then browser_inspect() again
    → never read_page on a blank page

  has_products=true
    → browser_click(sort selector) to sort, then browser_read_page()
    → find first non-sponsored complete product → browser_navigate to its url
    Sort URL params if click fails: Amazon "&s=price-asc-rank", Zillow "&sort=paymentAsc"

  is_form_heavy=true
    → browser_fill(sel, val, press_enter=False)  never auto-submit filter inputs
    → click Apply/Done button separately

  has_jobs=true OR has_listings=true
    → browser_read_page(full_page=True) to get content below the fold

  is_json=true
    → browser_evaluate("JSON.parse(document.body.innerText).field_name")

  standard HTML
    → check dom_snapshot first — often enough without an extra read_page call
    → browser_read_page() only when you need headings/links/tables/meta

━━ TOOL SELECTION RULES ━━

  Screenshots:
    browser_navigate(visual=True)  → first load of a visual/SPA page
    browser_inspect()              → any screenshot after first load
    Never call both on the same page load

  Page reading:
    dom_snapshot (automatic)       → free after every action, check it first
    browser_read_page()            → only for extra fields or full_page=True
    Never call right after navigate

  URL:
    Already in every response — never call browser_evaluate for URL

  JS reads:
    browser_evaluate()             → JSON API fields, specific DOM state only

━━ VISUAL GROUNDING ━━

  Every click flashes a live red bounding box in the browser automatically.
  browser_click(selector)      → red box on element then clicks
  browser_click_coords(x, y)  → 40x40px target marker then clicks
  browser_inspect()            → screenshot on demand — always call before stop()
  dismiss_popups()             → call manually if a popup appears after a click/scroll
                                 IMPORTANT: call it ONCE. If popup persists after one
                                 dismiss_popups() call — ignore it and proceed with the
                                 task. Never spend more than 1 tool call fighting a popup.

━━ ALWAYS END WITH stop() ━━
  NEVER write the answer as plain text — always call stop() as a tool.
  Before calling stop():
    1. Scroll back to the TOP of the page first (browser_key_press("Control+Home"))
    2. Then scroll DOWN to the first pricing table or main content section
    3. browser_inspect() to visually confirm pricing/content is visible on screen
    4. ONLY call stop(answer=...) when pricing tables or main content are in the screenshot
    5. NEVER call stop() when the screenshot shows a footer, nav menu, or blank area

━━ DROPDOWN / AUTOCOMPLETE RULE ━━
  Whenever a dropdown or autocomplete suggestion list appears after typing:
    1. browser_wait(1) — let suggestions fully load
    2. get_accessibility_tree() — read suggestion labels and positions
    3. browser_inspect() — take a screenshot to visually confirm positions
    4. browser_click_coords() — click using coordinates from the screenshot
  NEVER click a dropdown suggestion with a guessed coordinate before doing steps 1-3.
  If the suggestion is not found in the tree — browser_inspect() first, then click.

━━ FALLBACK CHAIN ━━
  1. dom_snapshot buttons/inputs → browser_click(id or [aria-label='...'])
  2. fails → browser_click_coords(x, y)
  3. not found → get_accessibility_tree → browser_click_coords
  4. still stuck → stop() and ask human

━━ HARD STOPS ━━
  CAPTCHA_DETECTED → STOP IMMEDIATELY. Say:
                     "Bot check on [site]. Please solve in browser, then type done."
                     Do NOT try other URLs. Do NOT switch sites. WAIT for human.
  ACCESS_BLOCKED   → ask human to navigate manually
  LOGIN_WALL       → ask for credentials
  Same approach failed twice → switch strategy or ask human

━━ NEVER INVENT URLS ━━
  Only navigate to URLs found in page content or dom_snapshot.
  If browser_evaluate returns not_found — do not navigate to null.

━━ VISUAL HONESTY RULE ━━
  NEVER describe or assert page state between screenshots.
  If you have not called browser_inspect() since your last action,
  you do NOT know what the page looks like — do not guess or assume.
  Only report what you can see in the most recent screenshot.
  Before stating ANY result (route time, price, form state, button label):
    → call browser_inspect() first to confirm it is actually on screen.
  "appears to be", "I can see", "it shows" are only valid after a fresh screenshot.
  For Google Maps specifically:
    -> NEVER call stop() if the final screenshot shows a zoomed-out map with no
       route line drawn — that means the directions panel has closed.
    -> Always confirm the blue route line AND travel time are visible before stop().

━━ PERSONAL INFO RULE ━━
  NEVER invent or assume personal details — DOB, name, address, phone, email, SSN.
  If a form requires personal info not provided by the user in their task:
    1. call stop() immediately
    2. list exactly which fields are needed
    3. ask the user to provide them
  Example stop() message:
    "This form needs: date of birth, full name, and street address.
     Please provide these and I will continue filling the form."
  Only use personal details the user has explicitly stated in their task.

━━ RESUMING AFTER HUMAN INPUT ━━
  Check url in state. Use dom_snapshot before calling read_page."""


RESEARCH_SYSTEM_PROMPT = """You are a Research Assistant with two tools: web_search and deep_scrape.

TOOLS:
  web_search(query)   → find relevant URLs and summaries for any topic
  deep_scrape(url)    → extract full content from a specific URL via Tavily
  web_fetch(url)      → fetch a URL directly via HTTP — use when deep_scrape fails or returns empty

STRICT WORKFLOW — follow this order every time:
  Step 1: ALWAYS do 2-3 web_searches with DIFFERENT angles/keywords — never repeat the same query.
           This applies to ALL queries, simple or complex. More searches = more URLs = better answer.
      -> Examples for "hiking near Chicago":
           Search 1: "best hiking trails near Chicago Illinois"
           Search 2: "Forest Preserves Cook County hiking trails"
           Search 3: "state parks day hikes near Chicago 2025"
      -> Examples for "best auto insurance Chicago 2025":
           Search 1: "best auto insurance rates Chicago Illinois 2025"
           Search 2: "auto insurance discounts Illinois 2025"
           Search 3: "cheapest auto insurance 2022 Honda Civic Chicago"
      -> Examples for a simple query like "Starved Rock address":
           Search 1: "Starved Rock State Park address"
           Search 2: "Starved Rock State Park location hours"
           Search 3: "Starved Rock State Park visitor info 2025"

  Step 2: deep_scrape OR web_fetch the top URLs collected across ALL searches
           -> scrape at least 4-6 URLs total for broad queries, 2-3 for simple queries
           -> try deep_scrape first on each URL
           -> if deep_scrape returns empty or very little text, retry with web_fetch
           -> do NOT stop scraping early — more sources = better answer
  Step 3: compile everything into a final summary — STOP, do not search or scrape again

RULES:
1. NEVER call web_search after you have started scraping — plan all searches first, then scrape.
2. Every web_search call MUST use different keywords — never repeat a query.
3. ALWAYS scrape at least 4-6 URLs for broad queries before summarizing.
4. Use web_fetch only as a fallback when deep_scrape fails on the same URL.
5. Write a clean, well-formatted summary: bullet points, bold key facts, prices, discounts.
6. Do NOT open a browser or navigate anywhere — text tools only.
7. After summarising, return control to the human. Do not ask follow-up questions.

CITATIONS - MANDATORY:
  Write a clean summary first (no inline URLs cluttering the text).
  At the very end, add a "## Sources" section listing every URL scraped, one per line.
  Example:
  ## Sources
  - https://moneygeek.com/insurance/auto/honda-civic-insurance/
  - https://bankrate.com/insurance/car/..."""

# ─────────────────────────────────────────────
# 6. LOOP & STEP GUARDS
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
# 7. CONTEXT HELPER
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
        if not isinstance(msg, ToolMessage):
            out.append(msg)
            continue
        try: d = json.loads(msg.content) if isinstance(msg.content, str) else {}
        except Exception: d = {}

        b64 = d.get("screenshot_b64") if isinstance(d, dict) else None
        if b64:
            if i == last_ss:
                td = {k: v for k, v in d.items() if k != "screenshot_b64"}
                out.append(HumanMessage(content=[
                    {"type": "tool_result", "tool_use_id": msg.tool_call_id, "content": [
                        {"type": "text", "text": json.dumps(td)},
                        {"type": "image", "source": {"type": "base64",
                                                      "media_type": "image/png", "data": b64}},
                    ]}
                ]))
            else:
                td = {k: v for k, v in d.items() if k != "screenshot_b64"}
                out.append(ToolMessage(content=json.dumps(td),
                                       tool_call_id=msg.tool_call_id,
                                       name=getattr(msg, "name", None)))
            continue

        tool_indices = [j for j, m in enumerate(messages) if isinstance(m, ToolMessage)]
        is_recent = i in tool_indices[-3:]
        if isinstance(d, dict) and not is_recent:
            d.pop("page_text", None)
            d.pop("buttons", None)
            d.pop("inputs", None)
            msg = ToolMessage(content=json.dumps(d),
                              tool_call_id=msg.tool_call_id,
                              name=getattr(msg, "name", None))
        out.append(msg)
    return out

# ─────────────────────────────────────────────
# 8. STATE & LLMs
# ─────────────────────────────────────────────

class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    mode:     str   # "research" | "navigate" | "wait"

_base = ChatAnthropic(
    model=MODEL_ID, api_key=os.getenv("ANTHROPIC_API_KEY"), temperature=0
)
nav_llm      = _base.bind_tools(NAV_TOOLS)
research_llm = _base.bind_tools(RESEARCH_TOOLS)

# ─────────────────────────────────────────────
# 9. NODES
# ─────────────────────────────────────────────

def human_input_node(state: State) -> dict:
    task = interrupt("What would you like to do?")
    mode_answer = interrupt(
        f"Task: \"{task}\"\n"
        f"Mode: navigate (live browser) or research (web search/scrape)? "
        f"Type n or r:"
    )
    mode = "navigate" if mode_answer.strip().lower().startswith("n") else "research"
    print(f"\n  → Mode: {'🌐' if mode == 'navigate' else '🔍'} {mode}")
    return {
        "messages": [HumanMessage(content=task)],
        "mode":     mode,
    }


def intent_router_node(state: State) -> dict:
    mode = state.get("mode", "unknown")
    if mode not in ("navigate", "research"):
        return {"mode": "wait"}
    return {"mode": mode}


async def nav_agent_node(state: State) -> dict:
    raw   = state["messages"]
    steps = _steps_since_human(raw)

    if steps >= 25:
        ans = _best_answer(raw)
        print(f"\n🚨 [Budget] {steps} steps — stopping.")
        if "Step budget reached" in ans or len(ans) < 50:
            ans = ("I reached the step limit before completing the task. "
                   "The browser is still open. Tell me what you see or give a more specific step.")
        return {"messages": [AIMessage(content=ans, tool_calls=[
            {"name": "stop", "args": {"answer": ans}, "id": "budget_stop", "type": "tool_call"}
        ])]}

    step_warn = ""
    if steps >= 20:
        print(f"\n⚠️  [Budget] {steps}/25.")
        step_warn = (f"\n\n*** {steps}/25 steps. Call stop(answer=...) NOW "
                     f"with what you have. ***")

    loop_warn = _detect_loop(raw)
    if loop_warn and _consecutive_warnings(raw) >= 3:
        print("\n🚨 [Loop] Hard stop.")
        return {"messages": [AIMessage(content=(
            "🚨 Stuck in a loop. Please check browser and tell me what you see, "
            "or type 'done' if CAPTCHA was solved."))]}
    if loop_warn:
        print("\n⚠️  [Loop] Warning injected.")

    safe     = _safe_messages(raw)
    prompt   = NAV_SYSTEM_PROMPT + (loop_warn or "") + step_warn
    response = await nav_llm.ainvoke([SystemMessage(content=prompt)] + safe)

    raw_text = response.content if isinstance(response.content, str) else \
               " ".join(b.get("text","") for b in response.content if isinstance(b,dict))
    if "<stop>" in raw_text.lower() and not response.tool_calls:
        m = re.search(r'<stop>(.*?)</stop>', raw_text, re.DOTALL | re.IGNORECASE)
        ans = re.sub(r'^answer\s*=\s*', '', (m.group(1) if m else raw_text)).strip()
        print("\n⚠️  [Fix] <stop> as text → tool call.")
        return {"messages": [AIMessage(content=ans, tool_calls=[
            {"name": "stop", "args": {"answer": ans}, "id": "stop_fix", "type": "tool_call"}
        ])]}

    c = response.content
    if isinstance(c, str) and c.strip(): print(f"\n🟢 {c}")
    elif isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text" and b["text"].strip():
                print(f"\n🟢 {b['text']}")

    return {"messages": [response]}


async def research_agent_node(state: State) -> dict:
    from collections import Counter
    raw   = state["messages"]
    steps = _steps_since_human(raw)

    # Detect looping vs legitimate multi-site research.
    # Looping = same keywords repeating across queries.
    # Multi-site research = different queries each time — that's fine.
    search_queries: list[str] = []
    for msg in reversed(raw):
        if isinstance(msg, HumanMessage): break
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.get("name") == "web_search":
                    search_queries.append(tc.get("args", {}).get("query", "").lower())

    # Keyword appearing 3+ times across queries = spinning on the same topic
    word_counts: Counter = Counter()
    for q in search_queries:
        for word in q.split():
            if len(word) > 4:
                word_counts[word] += 1
    is_looping = any(count >= 3 for count in word_counts.values()) and steps >= 6
    hard_limit = steps >= 12  # absolute ceiling for research tasks

    if hard_limit or is_looping:
        reason = "hard limit (12 calls)" if hard_limit else f"redundant searches detected after {steps} calls"
        print(f"\n[Research Budget] {reason} -- forcing final summary.")
        prompt = RESEARCH_SYSTEM_PROMPT + (
            f"\n\n*** HARD STOP: {reason}. "
            f"You CANNOT call any more tools. "
            f"Write your final summary NOW using only what you have already gathered. ***"
        )
        # _base has no tools bound -- model physically cannot call more tools
        response = await _base.ainvoke([SystemMessage(content=prompt)] + _safe_messages(raw))

    elif steps >= 8:
        print(f"\n[Research Budget] {steps} calls -- nudging toward summary.")
        prompt = RESEARCH_SYSTEM_PROMPT + (
            f"\n\n*** NOTE: {steps} tool calls made. "
            f"You have enough data. Make at most 1 more targeted deep_scrape if genuinely needed, "
            f"then write your final summary immediately. ***"
        )
        response = await research_llm.ainvoke([SystemMessage(content=prompt)] + _safe_messages(raw))

    else:
        response = await research_llm.ainvoke(
            [SystemMessage(content=RESEARCH_SYSTEM_PROMPT)] + _safe_messages(raw)
        )

    c = response.content
    if isinstance(c, str) and c.strip(): print(f"\n[research] {c}")
    elif isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text" and b["text"].strip():
                print(f"\n[research] {b['text']}")

    return {"messages": [response]}


# ─────────────────────────────────────────────
# 10. ROUTERS
# ─────────────────────────────────────────────

def route_after_intent(state: State) -> str:
    if state["mode"] == "wait":
        return "human_input"
    return "research_agent" if state["mode"] == "research" else "nav_agent"


def route_after_nav(state: State) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "nav_tools"
    if _screenshot_log:
        _print_screenshot_summary("Navigation complete")
    return "human_input"


def route_after_nav_tools(state: State) -> str:
    last = state["messages"][-1]
    if isinstance(last, ToolMessage) and getattr(last, "name", "") == "stop":
        if _screenshot_log:
            _print_screenshot_summary("Navigation complete")
        return "human_input"
    return "nav_agent"


def route_after_research(state: State) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "research_tools"
    return "human_input"

# ─────────────────────────────────────────────
# 11. GRAPH
# ─────────────────────────────────────────────

workflow = StateGraph(State)

workflow.add_node("human_input",    human_input_node)
workflow.add_node("intent_router",  intent_router_node)
workflow.add_node("nav_agent",      nav_agent_node)
workflow.add_node("nav_tools",      ToolNode(NAV_TOOLS))
workflow.add_node("research_agent", research_agent_node)
workflow.add_node("research_tools", ToolNode(RESEARCH_TOOLS))

workflow.add_edge(START,            "intent_router")
workflow.add_edge("human_input",    "intent_router")
workflow.add_conditional_edges("intent_router", route_after_intent,
    {"nav_agent": "nav_agent", "research_agent": "research_agent", "human_input": "human_input"})

workflow.add_conditional_edges("nav_agent",     route_after_nav,
    {"nav_tools": "nav_tools", "human_input": "human_input"})
workflow.add_conditional_edges("nav_tools",     route_after_nav_tools,
    {"nav_agent": "nav_agent", "human_input": "human_input"})

workflow.add_conditional_edges("research_agent", route_after_research,
    {"research_tools": "research_tools", "human_input": "human_input"})
workflow.add_edge("research_tools", "research_agent")

app = workflow.compile(checkpointer=InMemorySaver())

# ─────────────────────────────────────────────
# 12. MAIN
# ─────────────────────────────────────────────

async def stream_run(input_data, config):
    async for event in app.astream(input_data, config, stream_mode="updates"):
        for node, data in event.items():
            if node == "nav_tools":
                msgs = data.get("messages", [])
                if msgs:
                    print(f"  🔧 [{getattr(msgs[-1], 'name', 'tool')}]")
            elif node == "research_tools":
                msgs = data.get("messages", [])
                if msgs:
                    print(f"  📡 [{getattr(msgs[-1], 'name', 'tool')}]")


def _get_interrupt_value(config: dict) -> str | None:
    try:
        snapshot = app.get_state(config)
        if snapshot.tasks and snapshot.tasks[0].interrupts:
            return snapshot.tasks[0].interrupts[0].value
    except Exception:
        pass
    return None


async def main():
    sid    = str(uuid.uuid4())[:8]
    config = {"configurable": {"thread_id": f"nav-{sid}"}}

    print("\n  🤖  BROWSER + RESEARCH AGENT  v8")
    print("  🔍  r → research  (web search, deep scrape, web fetch)")
    print("  🌐  n → navigate  (live browser, click, fill)\n")

    await stream_run({"messages": [], "mode": "unknown"}, config)

    while True:
        prompt = _get_interrupt_value(config) or "Input"

        if "n or r" in prompt.lower():
            label = "[n=navigate / r=research]: "
        elif "exit" in prompt.lower() or not prompt:
            label = "\n[Task / 'exit']: "
        else:
            label = f"\n[{prompt[:60]}]: " if len(prompt) > 5 else "\n[Task / 'exit']: "

        cmd = input(label).strip()


        # Exit check — catches exit/quit/q at ANY prompt before hitting the graph
        if cmd.lower() in ("exit", "quit", "q"):
            print("\nShutting down..."); break
        if not cmd:
            cmd = "n"

        print("\n⏳ Working...\n")
        try:
            await stream_run(Command(resume=cmd), config)
        except Exception as e:
            print(f"❌ {e}"); break

    if browser_session["context"]: await browser_session["context"].close()
    if browser_session["playwright"]: await browser_session["playwright"].stop()
    _print_screenshot_summary("Session ended")
    print("\n✅ Done.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted.")
