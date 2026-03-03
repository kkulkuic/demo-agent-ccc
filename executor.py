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
        viz_mode: Optional[str] = None,
    ):
        import config
        self._owned_playwright = None
        self._owned_browser = None
        self._owned_context = None
        self._page = page
        self._session_id = session_id
        self._get_page = get_page
        self._enable_viz = enable_viz
        self._viz_mode = (viz_mode if viz_mode is not None else config.get_viz_mode())
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

    def _draw_bbox_if_needed(self, loc) -> None:
        if not self._enable_viz or self._viz_mode not in ("bounding_box", "both"):
            return
        try:
            from core.visualization import draw_bounding_box
            if loc.count() > 0:
                draw_bounding_box(self.page, loc, color="red", line_width=2, auto_remove_seconds=5)
                time.sleep(0.2)
        except Exception:
            pass

    def _looks_like_selector(self, target: str) -> bool:
        """True if target is likely a CSS selector (e.g. #id, .class, [attr])."""
        t = (target or "").strip()
        return bool(t and (t.startswith("#") or t.startswith(".") or t.startswith("[") or ("[" in t and "]" in t)))

    def _highlight_then_click(self, target: str) -> None:
        from core.visualization import ensure_overlays_installed, highlight_element_for_agent
        if self._viz_mode in ("dot_hilite", "both"):
            self._ensure_viz()
        loc = None
        if self._looks_like_selector(target):
            try:
                loc = self.page.locator(target).first
                if loc.count() > 0:
                    if self._enable_viz:
                        if self._viz_mode in ("dot_hilite", "both"):
                            ensure_overlays_installed(self.page, show_label=True)
                            highlight_element_for_agent(self.page, loc, target)
                        self._draw_bbox_if_needed(loc)
                        time.sleep(0.3)
                    loc.click()
                    return
            except Exception as e:
                raise
        try:
            loc = self.page.get_by_role("button", name=target).first
            if loc.count() > 0 and self._enable_viz:
                if self._viz_mode in ("dot_hilite", "both"):
                    ensure_overlays_installed(self.page, show_label=True)
                    highlight_element_for_agent(self.page, loc, target)
                self._draw_bbox_if_needed(loc)
                time.sleep(0.3)
            loc.click()
            return
        except Exception:
            pass
        try:
            loc = self.page.get_by_text(target).first
            if loc.count() > 0 and self._enable_viz:
                if self._viz_mode in ("dot_hilite", "both"):
                    ensure_overlays_installed(self.page, show_label=True)
                    highlight_element_for_agent(self.page, loc, target)
                self._draw_bbox_if_needed(loc)
                time.sleep(0.3)
            loc.click()
            return
        except Exception:
            pass
        try:
            loc = self.page.locator(f"text={target}").first
            if loc.count() > 0 and self._enable_viz:
                if self._viz_mode in ("dot_hilite", "both"):
                    ensure_overlays_installed(self.page, show_label=True)
                    highlight_element_for_agent(self.page, loc, target)
                self._draw_bbox_if_needed(loc)
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
            return
        if self._looks_like_selector(target):
            try:
                self.page.locator(target).first.click()
                return
            except Exception:
                raise
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
            if self._looks_like_selector(target):
                loc = self.page.locator(target).first
                if self._enable_viz and loc.count() > 0:
                    if self._viz_mode in ("dot_hilite", "both"):
                        self._ensure_viz()
                        try:
                            from core.visualization import ensure_overlays_installed, highlight_element_for_agent
                            ensure_overlays_installed(self.page, show_label=True)
                            highlight_element_for_agent(self.page, loc, target)
                            time.sleep(0.3)
                        except Exception:
                            pass
                    self._draw_bbox_if_needed(loc)
                loc.fill(text)
            else:
                loc = self.page.get_by_label(target).first
                if self._enable_viz and loc.count() > 0:
                    if self._viz_mode in ("dot_hilite", "both"):
                        self._ensure_viz()
                        try:
                            from core.visualization import ensure_overlays_installed, highlight_element_for_agent
                            ensure_overlays_installed(self.page, show_label=True)
                            highlight_element_for_agent(self.page, loc, target)
                            time.sleep(0.3)
                        except Exception:
                            pass
                    self._draw_bbox_if_needed(loc)
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
