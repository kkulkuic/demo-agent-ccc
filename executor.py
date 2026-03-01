"""Browser executor: supports injected page (session) or owned playwright; optional visualization."""
import time
from typing import Optional, Callable, Any

from playwright.sync_api import Page


class BrowserAgent:
    """Execute planned actions (click, type, navigate). Can use an injected page or own browser."""

    def __init__(
        self,
        headless: bool = False,
        page: Optional[Page] = None,
        session_id: Optional[str] = None,
        get_page: Optional[Callable[[str], Any]] = None,
        enable_viz: bool = False,
    ):
        self._owned_playwright = None
        self._owned_browser = None
        self._owned_context = None
        self._page = page
        self._session_id = session_id
        self._get_page = get_page
        self._enable_viz = enable_viz
        self._viz_installed = False

        if page is not None:
            self.page = page
            return
        if session_id and get_page:
            self.page = get_page(session_id)
            return
        from playwright.sync_api import sync_playwright
        self._owned_playwright = sync_playwright().start()
        self._owned_browser = self._owned_playwright.chromium.launch(headless=headless)
        self._owned_context = self._owned_browser.new_context()
        self.page = self._owned_context.new_page()

    def _ensure_viz(self) -> None:
        if not self._enable_viz or self._viz_installed:
            return
        try:
            from core.visualization import install_dot, install_highlighter
            install_dot(self.page)
            install_highlighter(self.page, show_label=True)
            self._viz_installed = True
        except Exception:
            pass

    def _highlight_then_click(self, target: str) -> None:
        from core.visualization import ensure_overlays_installed, highlight_element_for_agent
        self._ensure_viz()
        loc = None
        try:
            loc = self.page.get_by_role("button", name=target).first
            if loc.count() > 0 and self._enable_viz:
                ensure_overlays_installed(self.page, show_label=True)
                highlight_element_for_agent(self.page, loc, target)
                time.sleep(0.3)
            loc.click()
            return
        except Exception:
            pass
        try:
            loc = self.page.get_by_text(target).first
            if loc.count() > 0 and self._enable_viz:
                ensure_overlays_installed(self.page, show_label=True)
                highlight_element_for_agent(self.page, loc, target)
                time.sleep(0.3)
            loc.click()
            return
        except Exception:
            pass
        try:
            loc = self.page.locator(f"text={target}").first
            if loc.count() > 0 and self._enable_viz:
                ensure_overlays_installed(self.page, show_label=True)
                highlight_element_for_agent(self.page, loc, target)
                time.sleep(0.3)
            loc.click()
        except Exception:
            raise

    def navigate(self, url: str) -> None:
        self.page.goto(url, wait_until="networkidle")
        self._viz_installed = False

    def robust_click(self, target: str) -> None:
        if self._enable_viz:
            self._highlight_then_click(target)
        else:
            try:
                self.page.get_by_role("button", name=target).click()
            except Exception:
                try:
                    self.page.get_by_text(target).click()
                except Exception:
                    self.page.locator(f"text={target}").first.click()

    def execute(self, action: dict) -> None:
        action_type = action.get("action")
        target = action.get("target")
        text = action.get("text", "")

        print(f"Executing: {action_type} -> {target}")

        if action_type == "click":
            self.robust_click(target)
        elif action_type == "type":
            if self._enable_viz:
                self._ensure_viz()
                try:
                    loc = self.page.get_by_label(target).first
                    if loc.count() > 0:
                        from core.visualization import ensure_overlays_installed, highlight_element_for_agent
                        ensure_overlays_installed(self.page, show_label=True)
                        highlight_element_for_agent(self.page, loc, target)
                        time.sleep(0.3)
                except Exception:
                    pass
            self.page.get_by_label(target).fill(text)
        elif action_type == "navigate":
            self.page.goto(target)
            self._viz_installed = False
            self.page.wait_for_timeout(500)
            try:
                from core.consent import dismiss_cookie_consent
                dismiss_cookie_consent(self.page)
            except Exception:
                pass
            if self._enable_viz:
                self._ensure_viz()

        time.sleep(1)

    def snapshot(self, step: int, path: Optional[str] = None) -> None:
        if path is None:
            path = f"screenshot_step_{step}.png"
        self.page.screenshot(path=path)

    def get_context(self) -> str:
        return self.page.content()

    def close(self) -> None:
        if self._owned_browser is not None:
            self._owned_browser.close()
        if self._owned_playwright is not None:
            self._owned_playwright.stop()
        self._owned_browser = None
        self._owned_playwright = None
        self._owned_context = None
