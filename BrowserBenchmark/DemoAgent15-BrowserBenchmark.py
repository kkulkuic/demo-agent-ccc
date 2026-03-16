import asyncio
import time
import csv
import json
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError

try:
    import matplotlib.pyplot as plt
except:
    plt = None


# ==============================
# GLOBAL CONFIG
# ==============================

QUERY = "Playwright automation framework 2026"

HEADLESS = True
TIMEOUT = 30000
RETRY = 2

RESULT_DIR = "research_results"
Path(RESULT_DIR).mkdir(exist_ok=True)

BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
EDGE_PATH = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"

# ==============================
# SEARCH URLS
# ==============================

def build_url(engine, query):

    q = query.replace(" ", "+")

    if engine == "duckduckgo":
        return f"https://duckduckgo.com/?q={q}"

    if engine == "brave":
        return f"https://search.brave.com/search?q={q}"

    if engine == "bing":
        return f"https://cn.bing.com/search?q={q}"

    raise ValueError(engine)


# ==============================
# RETRY WRAPPER
# ==============================

async def retry(func):

    for i in range(RETRY):

        try:
            return await func()

        except TimeoutError:

            if i == RETRY - 1:
                raise

            await asyncio.sleep(2)


# ==============================
# CAPTCHA DETECTION
# ==============================

async def detect_captcha(page):

    keywords = [
        "captcha",
        "verify you are human",
        "robot check",
        "security check"
    ]

    content = await page.content()

    for k in keywords:
        if k.lower() in content.lower():
            return True

    return False


# ==============================
# NETWORK ANALYSIS
# ==============================

async def capture_network(page):

    requests = []

    page.on(
        "request",
        lambda req: requests.append({
            "url": req.url,
            "method": req.method
        })
    )

    return requests


# ==============================
# PAGE PERFORMANCE
# ==============================

async def measure_performance(page, url):

    start = time.time()

    await retry(lambda: page.goto(url, wait_until="domcontentloaded"))

    dom_loaded = time.time()

    await page.goto(url, wait_until="domcontentloaded")


    end = time.time()

    return {

        "ttfb": round(dom_loaded - start, 3),
        "dom_load": round(dom_loaded - start, 3),
        "total_load": round(end - start, 3)

    }


# ==============================
# DOM ELEMENT ANALYSIS
# ==============================

async def analyze_dom(page):

    elements = await page.evaluate("""

        () => {

            return {

                links: document.querySelectorAll("a").length,
                images: document.querySelectorAll("img").length,
                scripts: document.querySelectorAll("script").length

            }

        }

    """)

    return elements


# ==============================
# SCREENSHOT
# ==============================

async def screenshot(page, name):

    path = f"{RESULT_DIR}/{name}.jpg"

    await page.screenshot(
        path=path,
        type="jpeg",
        quality=80
    )

    return path


# ==============================
# SINGLE EXPERIMENT
# ==============================

async def run_experiment(browser_name, browser, engine):

    page = await browser.new_page(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X)"
    )

    url = build_url(engine, QUERY)

    network = await capture_network(page)

    print(f"\n🔬 {browser_name} → {engine}")

    success = True

    try:

        perf = await measure_performance(page, url)

        dom = await analyze_dom(page)

        captcha = await detect_captcha(page)

        shot = await screenshot(page, f"{browser_name}_{engine}")

    except Exception as e:

        print("⚠️ Experiment failed:", e)

        success = False

        perf = {"ttfb": None, "dom_load": None, "total_load": None}
        dom = {"links": None, "images": None, "scripts": None}
        captcha = None
        shot = "timeout"

    await page.close()

    return {

        "browser": browser_name,
        "engine": engine,
        "success": success,
        "captcha_detected": captcha,
        "network_requests": len(network),
        "screenshot": shot,

        **perf,
        **dom

    }


# ==============================
# CSV REPORT
# ==============================

def save_csv(results):

    path = f"{RESULT_DIR}/research_data.csv"

    keys = results[0].keys()

    with open(path, "w", newline="") as f:

        writer = csv.DictWriter(f, fieldnames=keys)

        writer.writeheader()

        writer.writerows(results)

    print("📄 CSV saved:", path)


# ==============================
# JSON LOG
# ==============================

def save_json(results):

    path = f"{RESULT_DIR}/research_log.json"

    with open(path, "w") as f:

        json.dump(results, f, indent=2)

    print("🧾 JSON log saved:", path)


# ==============================
# VISUALIZATION
# ==============================

def visualize(results):

    if not plt:
        print("⚠️ matplotlib not installed, skipping charts")
        return

    names = []
    times = []

    for r in results:

        if r["total_load"]:

            names.append(f"{r['browser']}-{r['engine']}")
            times.append(r["total_load"])

    plt.figure(figsize=(10,6))

    plt.bar(names, times)

    plt.title("Browser Research Benchmark")

    plt.ylabel("Load Time (seconds)")

    plt.xticks(rotation=30)

    path = f"{RESULT_DIR}/benchmark_chart.png"

    plt.savefig(path)

    print("📊 Chart saved:", path)


# ==============================
# MAIN
# ==============================

async def main():

    results = []

    async with async_playwright() as p:

        chromium = await p.chromium.launch(headless=HEADLESS)

        results.append(
            await run_experiment("Chromium", chromium, "duckduckgo")
        )

        await chromium.close()

        brave = await p.chromium.launch(
            executable_path=BRAVE_PATH,
            headless=HEADLESS
        )

        results.append(
            await run_experiment("Brave", brave, "brave")
        )

        await brave.close()

        firefox = await p.firefox.launch(headless=HEADLESS)

        results.append(
            await run_experiment("Firefox", firefox, "bing")
        )

        await firefox.close()

        edge = await p.chromium.launch(
            executable_path=EDGE_PATH,
            headless=HEADLESS
        )

        results.append(
            await run_experiment("Edge", edge, "bing")
        )

        await edge.close()

    save_csv(results)

    save_json(results)

    visualize(results)

    print("\n🎉 Playwright Research Framework Finished")


# ==============================

if __name__ == "__main__":

    asyncio.run(main())
