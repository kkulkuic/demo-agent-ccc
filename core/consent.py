"""Cookie consent dismissal and bot/challenge detection."""
from typing import Optional

from core.visualization import highlight_locator

CONSENT_SELECTORS = [
    "button:has-text('Accept')",
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('Agree')",
    "button:has-text('I agree')",
    "button:has-text('OK')",
    "button:has-text('Okay')",
    "button:has-text('Got it')",
    "button:has-text('Continue')",
    "button:has-text('Reject')",
    "button:has-text('Reject all')",
    "button:has-text('Reject All')",
    "button:has-text('Decline')",
    "button:has-text('No thanks')",
    "button:has-text('Allow all')",
    "button:has-text('Allow All')",
    "button:has-text('Manage preferences')",
    "button:has-text('Manage Preferences')",
    "button:has-text('Confirm choices')",
    "button:has-text('Confirm Choices')",
    "[aria-label*='accept' i]",
    "[aria-label*='agree' i]",
    "[aria-label*='reject' i]",
    "[id*='accept' i]",
    "[id*='agree' i]",
    "[id*='reject' i]",
    "[class*='accept' i]",
    "[class*='agree' i]",
    "[class*='reject' i]",
    "[data-testid*='accept' i]",
    "[data-testid*='agree' i]",
    "[data-testid*='reject' i]",
]


def looks_like_bot_challenge(title: Optional[str], body_text: Optional[str]) -> bool:
    hay = f"{title or ''} {body_text or ''}".lower()
    keywords = [
        "not a robot",
        "verify you are human",
        "verification",
        "captcha",
        "access denied",
        "unusual traffic",
        "just a moment",
        "checking your browser",
        "cloudflare",
        "enable cookies",
        "are you human",
        "blocked",
        "security check",
    ]
    return any(k in hay for k in keywords)


def dismiss_cookie_consent(page) -> bool:
    """Try consent in main doc, then iframes. Returns True if clicked."""
    for sel in CONSENT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=350):
                highlight_locator(loc)
                page.wait_for_timeout(900)
                loc.click(timeout=2000)
                page.wait_for_timeout(350)
                return True
        except Exception:
            pass
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        for sel in CONSENT_SELECTORS:
            try:
                loc = frame.locator(sel).first
                if loc.is_visible(timeout=350):
                    highlight_locator(loc)
                    page.wait_for_timeout(900)
                    loc.click(timeout=2000)
                    page.wait_for_timeout(350)
                    return True
            except Exception:
                pass
    return False
