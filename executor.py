from playwright.sync_api import sync_playwright
import time

class BrowserAgent:

    def __init__(self, headless=False):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def navigate(self, url):
        self.page.goto(url, wait_until="networkidle")

    def robust_click(self, target):
        try:
            self.page.get_by_role("button", name=target).click()
        except:
            try:
                self.page.get_by_text(target).click()
            except:
                self.page.locator(f"text={target}").first.click()

    def execute(self, action):
        action_type = action.get("action")
        target = action.get("target")
        text = action.get("text", "")

        print(f"Executing: {action_type} -> {target}")

        if action_type == "click":
            self.robust_click(target)

        elif action_type == "type":
            self.page.get_by_label(target).fill(text)

        elif action_type == "navigate":
            self.page.goto(target)

        time.sleep(1)

    def snapshot(self, step):
        self.page.screenshot(path=f"screenshot_step_{step}.png")

    def get_context(self):
        return self.page.content()

    def close(self):
        self.browser.close()
        self.playwright.stop()
