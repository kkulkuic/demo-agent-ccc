import asyncio
import os
import json
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox
from datetime import datetime
import warnings

# Suppress Redundant macOS System Warning Logs
warnings.filterwarnings("ignore")
os.environ["TK_SILENCE_DEPRECATION"] = "1"

import anthropic
from playwright.async_api import async_playwright

# ==================== LLM config ====================
API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5-20251001"
client = anthropic.Anthropic(api_key=API_KEY)

# ==================== LLM: Task Decision-Making ====================
def decide_task(user_input, log):
    system_prompt = """
You are an AI agent planner.

Decide the task.

Return JSON only.

{
  "task_type": "search_and_summarize",
  "search_query": "..."
}
"""
    try:
        res = client.messages.create(
            model=MODEL,
            max_tokens=200,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_input}]
        )
        text = res.content[0].text.strip()
        log(f"🧠 LLM决策: {text}", "info")
        return json.loads(text)
    except:
        return {"task_type": "search_and_summarize", "search_query": user_input}


# ==================== LLM: Summary ====================
def summarize_content(contents, log):
    joined = "\n\n".join(contents)[:12000]

    prompt = f"""
Summarize the following content clearly:

{joined}
"""

    res = client.messages.create(
        model=MODEL,
        max_tokens=500,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}]
    )

    summary = res.content[0].text
    log("✅ 已完成总结", "success")
    return summary


# ==================== Agent Execution Engine ====================
class TaskEngine:
    def __init__(self, log_cb, update_results_cb, show_summary_cb):
        self.log = log_cb
        self.update_results = update_results_cb
        self.show_summary = show_summary_cb

    async def execute(self, task_info):
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                slow_mo=200,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-notifications",
                    "--no-first-run",
                ]
            )

            context = await browser.new_context(
                locale="en-US",
                timezone_id="America/Chicago",
                viewport=None
            )

            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)

            page = await context.new_page()

            try:
                if task_info["task_type"] == "search_and_summarize":

                    query = task_info["search_query"]
                    self.log(f"🔍 搜索: {query}", "info")

                    await page.goto("https://www.google.com")
                    await page.fill('textarea[name="q"]', query)
                    await page.keyboard.press("Enter")
                    await page.wait_for_load_state("networkidle")

                    links = await page.locator("a:has(h3)").all()

                    results = []
                    contents = []

                    for i in range(min(3, len(links))):
                        try:
                            href = await links[i].get_attribute("href")
                            title = await links[i].inner_text()

                            results.append(title)

                            self.log(f"🌐 打开: {title}", "info")

                            new_page = await context.new_page()
                            await new_page.goto(href, timeout=15000)

                            text = await new_page.locator("body").inner_text()
                            contents.append(text[:3000])

                            await new_page.close()

                        except Exception as e:
                            self.log(f"⚠️ Skip Page: {str(e)}", "error")

                    self.update_results(results)

                    # 🧠 summary
                    summary = summarize_content(contents, self.log)
                    self.show_summary(summary)

            except Exception as e:
                self.log(f"❌ Execution Error: {str(e)}", "error")

            await browser.close()


# ==================== UI ====================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🔥 AI Agent Browser Assistant")
        self.geometry("1000x750")

        # 关键：禁止 Tkinter 触发 macOS 键盘警告
        self.createcommand('tk::mac::RevealFrontDocument', lambda: None)

        self.engine = TaskEngine(self.add_log, self.show_results, self.show_summary)
        self.setup_ui()

    def setup_ui(self):
        self.input = tk.Entry(self, font=("Arial", 14))
        self.input.pack(fill=tk.X, padx=10, pady=10)
        self.input.insert(0, "latest Tesla news")

        btn = tk.Button(self, text="运行 Agent", command=self.run)
        btn.pack()

        self.results = tk.Listbox(self)
        self.results.pack(fill=tk.X, padx=10, pady=10)

        self.summary = scrolledtext.ScrolledText(self, height=10)
        self.summary.pack(fill=tk.BOTH, expand=True)

        self.logbox = scrolledtext.ScrolledText(self, height=10, bg="black", fg="white")
        self.logbox.pack(fill=tk.BOTH, expand=True)

    def add_log(self, msg, level="info"):
        self.logbox.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.logbox.see(tk.END)

    def show_results(self, items):
        self.results.delete(0, tk.END)
        for i in items:
            self.results.insert(tk.END, i)

    def show_summary(self, text):
        self.summary.delete("1.0", tk.END)
        self.summary.insert(tk.END, text)

    def run(self):
        query = self.input.get().strip()
        if not query:
            messagebox.showwarning("提示", "请输入内容")
            return

        def thread():
            # 为子线程设置事件循环，彻底解决 asyncio 线程冲突
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            task = decide_task(query, self.add_log)
            loop.run_until_complete(self.engine.execute(task))

        threading.Thread(target=thread, daemon=True).start()


# ==================== start up ====================
if __name__ == "__main__":
    app = App()
    app.mainloop()



# ✅ LLM 决策
# 👉 decide_task()
# ✅ 自动执行链
# 👉 search → open → extract → summarize
# ✅ 多页面抓取
# ✅ UI + 实时日志