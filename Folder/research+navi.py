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
from PIL import Image, ImageDraw, ImageFont
from firecrawl import FirecrawlApp

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
    """
    Inject a live red bounding box overlay in the browser for `duration` seconds.
    Forces a repaint after injection so the overlay is guaranteed visible before
    the sleep starts. Called automatically before every click.
    Silently no-ops on any JS error.
    """
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

            // Inject keyframe animation if not already present
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

            // Force a synchronous reflow so the overlay paints before we return
            return ov.getBoundingClientRect().width;
        }""", [box["x"], box["y"], box["width"], box["height"], lbl])

        # Give the browser a frame to paint before we start the timer
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
    """
    Silently dismiss cookie banners, GDPR notices, chat widgets, and modal overlays.
    Tries JS-based removal first (instant), then clicks common dismiss buttons.
    Returns list of what was dismissed — empty list if nothing found.
    Called automatically after every browser_navigate (twice: on load + after settle).
    """
    dismissed = []
    try:
        removed = await page.evaluate("""() => {
            const removed = [];
            const overlaySelectors = [
                // Cookie banners
                '#onetrust-banner-sdk', '#onetrust-consent-sdk',
                '#cookie-banner', '#cookie-notice', '#cookie-law-info-bar',
                '.cookie-banner', '.cookie-notice', '.cookie-consent',
                '[id*="cookie"]', '[class*="cookie-banner"]',
                '[id*="gdpr"]', '[class*="gdpr"]',
                '[id*="consent"]', '[class*="consent-banner"]',
                // Chat / sales widgets — cover all major vendors
                '#drift-widget-container', '#drift-frame-controller',
                '#intercom-container', '#intercom-frame',
                '#hubspot-messages-iframe-container',
                '[id*="chat-widget"]', '[class*="chat-widget"]',
                '[id*="chat-container"]', '[class*="chat-container"]',
                '[id*="live-chat"]', '[class*="live-chat"]',
                // Akamai/Linode specific: Kai AI widget
                '[class*="AkamaiChat"]', '[id*="AkamaiChat"]',
                '[class*="kai-chat"]', '[id*="kai-chat"]',
                '[class*="sales-chat"]', '[id*="sales-widget"]',
                // All chat iframes regardless of src
                'iframe[src*="drift"]', 'iframe[src*="intercom"]',
                'iframe[src*="hubspot"]', 'iframe[src*="zendesk"]',
                'iframe[src*="livechat"]', 'iframe[src*="crisp"]',
                'iframe[src*="tawk"]', 'iframe[src*="chat"]',
                // Generic modals
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
            // Nuke ALL iframes not in the main content — chat widgets always use iframes
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
            // Remove fixed/sticky overlays covering >20% of viewport
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

        # ── Click dismiss/accept buttons if banners still present ─────────
        dismiss_texts = [
            "accept all", "accept cookies", "accept all cookies",
            "agree", "i agree", "got it", "ok", "okay",
            "close", "dismiss", "no thanks", "reject all",
            "×", "✕", "✖", "x",
        ]
        buttons = await page.query_selector_all("button, [role=button], a[href='#']")
        for btn in buttons[:40]:
            try:
                text = (await btn.inner_text()).strip().lower()
                aria = (await btn.get_attribute("aria-label") or "").lower()
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

        # Dismiss cookie banners and chat widgets (first pass — catches early loaders)
        await _dismiss_popups(page)

        # Scroll nudge — triggers lazy-render and intersection observers on SPAs
        await page.evaluate("() => { window.scrollBy(0, 100); window.scrollBy(0, -100); }")
        await asyncio.sleep(1.0)

        # Second dismiss pass — catches late-loading widgets (Kai, Intercom, etc.)
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

        # Scroll element into view so the flash is always on screen
        await el.scroll_into_view_if_needed()
        await asyncio.sleep(0.3)   # let scroll settle

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
    """Press a key or chord: 'Enter', 'Escape', 'Tab', 'ArrowDown', 'Control+a'."""
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
        await page.evaluate("""(sel, px) => {
            const el = document.querySelector(sel);
            if (el) el.scrollTop += px;
        }""", selector, move)
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
        snap = await page.accessibility.snapshot()
        def flat(node, d=0):
            if not node: return []
            lines = []
            r, n, v = node.get("role",""), node.get("name",""), node.get("value","")
            if r not in ("none","presentation","generic",""):
                parts = [f"{'  '*d}[{r}]"]
                if n: parts.append(f'"{n}"')
                if v: parts.append(f'= "{v}"')
                lines.append(" ".join(parts))
            for c in node.get("children",[]): lines.extend(flat(c, d+1))
            return lines
        return {"status": "success", "tree": "\n".join(flat(snap)[:300]), "url": page.url}
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

        # Scroll to first meaningful content — table, or first h2/h3 after page title
        await page.evaluate("""() => {
            const targets = [
                'table',
                'h2', 'h3',
                '[class*="pricing"]', '[class*="price"]',
                '[class*="rate"]',    '[class*="tier"]',
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
# 4. RESEARCH TOOLS  (Firecrawl — no browser)
# ─────────────────────────────────────────────

def _fc() -> FirecrawlApp:
    key = os.getenv("FIRECRAWL_API_KEY")
    if not key:
        raise ValueError("FIRECRAWL_API_KEY not set in .env")
    return FirecrawlApp(api_key=key)


@tool
async def web_search(query: str, num_results: int = 5) -> str:
    """Search the web for any topic — news, facts, product info, stats."""
    try:
        result = await asyncio.to_thread(_fc().search, query, limit=num_results)
        if not result or "data" not in result:
            return "No results."
        chunks = []
        for i, item in enumerate(result["data"], 1):
            chunks.append(
                f"[{i}] {item.get('title','')}\n"
                f"URL: {item.get('url','')}\n"
                f"{item.get('markdown', item.get('content',''))[:1500]}"
            )
        return "\n\n---\n\n".join(chunks)
    except Exception as e:
        return f"web_search error: {e}"


@tool
async def deep_scrape(url: str) -> str:
    """
    Extract full structured content from a specific URL as markdown.
    Use when web_search snippets are not detailed enough.
    """
    try:
        result = await asyncio.to_thread(_fc().scrape_url, url, formats=["markdown"])
        return result.get("markdown", result.get("content", "No content."))[:4000]
    except Exception as e:
        return f"deep_scrape error: {e}"


@tool
async def compare_prices(product: str) -> str:
    """
    Search Amazon, eBay, and the web for a product's price.
    Always highlights the cheapest option found.
    """
    try:
        queries = [
            f"{product} price site:amazon.com",
            f"{product} price site:ebay.com",
            f"buy {product} cheapest price",
        ]
        results = []
        for q in queries:
            r = await asyncio.to_thread(_fc().search, q, limit=2)
            if r and "data" in r:
                for item in r["data"]:
                    results.append(
                        f"Source: {item.get('url','')}\n"
                        f"{item.get('markdown', item.get('content',''))[:600]}"
                    )
        return (f"Price results for '{product}':\n\n" +
                "\n\n---\n\n".join(results)) if results else "No results."
    except Exception as e:
        return f"compare_prices error: {e}"


@tool
async def extract_structured(url: str, fields: str) -> str:
    """
    Extract specific fields from a URL using LLM extraction.
    fields: comma-separated, e.g. "title, price, rating, description".
    Returns JSON.
    """
    try:
        import json
        schema = {f.strip(): {"type": "string"} for f in fields.split(",")}
        result = await asyncio.to_thread(
            _fc().scrape_url, url,
            formats=["extract"],
            extract={"schema": {"type": "object", "properties": schema}}
        )
        return json.dumps(result.get("extract", {}), indent=2)
    except Exception as e:
        return f"extract_structured error: {e}"


RESEARCH_TOOLS = [web_search, deep_scrape, compare_prices, extract_structured]

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
    1. get_accessibility_tree → click Directions button
    2. browser_type() origin → browser_click_coords for first suggestion
    3. browser_type() destination → browser_click_coords for first suggestion
    4. browser_inspect() to see routes
    5. browser_scroll_element('div[role=main]') to reveal alternate routes
    6. Do NOT click gray map canvas lines — unreliable

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
    1. Scroll to the relevant content so it's visible on screen
    2. browser_inspect() to visually confirm the right content is showing
    3. call stop(answer=...)

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

━━ RESUMING AFTER HUMAN INPUT ━━
  Check url in state. Use dom_snapshot before calling read_page."""


RESEARCH_SYSTEM_PROMPT = """You are a Research Assistant with web search and scraping tools.

TOOLS:
  web_search(query)              → search for any topic, news, facts, product info
  deep_scrape(url)               → extract full markdown from a specific URL
  compare_prices(product)        → search Amazon, eBay, web for cheapest price
  extract_structured(url,fields) → extract specific fields as JSON from a URL

RULES:
1. Use web_search first. Use deep_scrape when snippets are not enough.
2. Use extract_structured for specific fields (price, title, rating) from a known URL.
3. Use compare_prices when the user asks about buying, cost, or pricing.
4. Write a clear summary after gathering info: bullet points, bold key facts, source URLs.
5. Do NOT open a browser or navigate anywhere.
6. After summarising, return control to the human. Do not ask follow-up questions.

LOCAL BUSINESS QUERIES (restaurants, shops, services in a specific area):
  web_search alone returns generic pages — not structured listings.
  Step 1: web_search("site:yelp.com pizza west loop chicago")
  Step 2: deep_scrape the Yelp search results URL from the results
  Step 3: Filter by the user's criteria and present a clean list.
  If Yelp fails: deep_scrape("https://www.tripadvisor.com/Search?q=pizza+west+loop+chicago")"""

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
    """
    Entry point — always pauses here. Asks the human for their task,
    then immediately asks whether they want to navigate or research.
    Stores both answers before routing.
    """
    # Step 1: get the task
    task = interrupt("What would you like to do?")

    # Step 2: ask mode — show the task back so they have context
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
    """
    Mode is already set by human_input_node — just route to the right agent.
    Falls back to human_input if mode is unknown (first boot with empty state).
    """
    mode = state.get("mode", "unknown")
    if mode not in ("navigate", "research"):
        return {"mode": "wait"}
    return {"mode": mode}


async def nav_agent_node(state: State) -> dict:
    raw   = state["messages"]
    steps = _steps_since_human(raw)

    if steps >= 30:
        ans = _best_answer(raw)
        print(f"\n🚨 [Budget] {steps} steps — stopping.")
        if "Step budget reached" in ans or len(ans) < 50:
            ans = ("I reached the step limit before completing the task. "
                   "The browser is still open. Tell me what you see or give a more specific step.")
        return {"messages": [AIMessage(content=ans, tool_calls=[
            {"name": "stop", "args": {"answer": ans}, "id": "budget_stop", "type": "tool_call"}
        ])]}

    step_warn = ""
    if steps >= 25:
        print(f"\n⚠️  [Budget] {steps}/30.")
        step_warn = (f"\n\n*** {steps}/30 steps. Call stop(answer=...) NOW "
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
    raw      = state["messages"]
    safe     = _safe_messages(raw)
    response = await research_llm.ainvoke([SystemMessage(content=RESEARCH_SYSTEM_PROMPT)] + safe)

    c = response.content
    if isinstance(c, str) and c.strip(): print(f"\n🔍 {c}")
    elif isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text" and b["text"].strip():
                print(f"\n🔍 {b['text']}")

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
    """Read the current interrupt prompt from graph state."""
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
    print("  🔍  r → research  (web search, scrape, compare prices)")
    print("  🌐  n → navigate  (live browser, click, fill)\n")

    # Boot the graph — immediately hits first interrupt (task question)
    await stream_run({"messages": [], "mode": "unknown"}, config)

    while True:
        # Read what the graph is currently waiting for
        prompt = _get_interrupt_value(config) or "Input"

        if "n or r" in prompt.lower():
            # Mode selection — show compact prompt
            label = "[n=navigate / r=research]: "
        elif "exit" in prompt.lower() or not prompt:
            label = "\n[Task / 'exit']: "
        else:
            label = f"\n[{prompt[:60]}]: " if len(prompt) > 5 else "\n[Task / 'exit']: "

        cmd = input(label).strip()

        if cmd.lower() == "exit":
            print("\nShutting down..."); break
        if not cmd:
            cmd = "n"   # default to navigate if blank on mode question

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
