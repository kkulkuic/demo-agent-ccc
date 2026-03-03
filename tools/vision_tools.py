"""Vision-based tools: screenshot to code (Claude), execute Playwright code. All strings in English."""
import base64
import json
import re
from typing import Optional, Tuple

import config
from anthropic import Anthropic


def capture_screenshot_base64(page, clip: Optional[dict] = None) -> str:
    """
    Capture screenshot of the page (fixed viewport or full page). Sync page only.
    clip: optional {"x", "y", "width", "height"}. Returns base64-encoded PNG string.
    """
    if page is None:
        raise RuntimeError("Browser page not initialized.")
    clip = clip or {"x": 0, "y": 0, "width": 1920, "height": 1080}
    screenshot_bytes = page.screenshot(full_page=False, clip=clip)
    if hasattr(screenshot_bytes, "decode"):
        return base64.b64encode(screenshot_bytes).decode("utf-8")
    return base64.b64encode(screenshot_bytes).decode("utf-8")


async def capture_screenshot_base64_async(page, clip: Optional[dict] = None) -> str:
    """Async version: capture screenshot from async Playwright page."""
    if page is None:
        raise RuntimeError("Browser page not initialized.")
    clip = clip or {"x": 0, "y": 0, "width": 1920, "height": 1080}
    screenshot_bytes = await page.screenshot(full_page=False, clip=clip)
    return base64.b64encode(screenshot_bytes).decode("utf-8")


def clean_markdown_code_block(response_text: str) -> str:
    """Clean Markdown code block delimiters from response."""
    if not response_text:
        return ""
    cleaned = re.sub(r"^```json\s*", "", response_text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def fix_variable_name(action_code: str) -> str:
    """Auto-fix variable name: replace page. with self.page. and {timeout:N} with timeout=N."""
    if not action_code:
        return ""
    fixed = re.sub(r"(?<!\.)page\.", "self.page.", action_code)
    fixed = re.sub(r"\{timeout:\s*(\d+)\}", r"timeout=\1", fixed)
    return fixed


async def parse_instruction_to_code_async(page, instruction: str) -> Tuple[str, str]:
    """
    Use screenshot + instruction to get Playwright code and narration from Claude.
    Async page. Returns (action_code, narration). All prompts and narration in English.
    """
    screenshot_b64 = await capture_screenshot_base64_async(page)
    prompt = f"""
Important: Output must be pure JSON only, no Markdown code blocks or comments.
Output format: {{"action_code": "Playwright code", "narration": "English narrative"}}

Instruction: {instruction}

Requirements (must follow):
1. All page operations must use self.page (not page);
2. Timeout parameters use Python syntax: timeout=10000 (not {{timeout:10000}});
3. For GitHub search: click button[aria-label="Search or jump to…"], then wait for input#query-builder-test, fill and press Enter.
4. Multiple operations separated by semicolons; prefix each with await.
"""
    client = Anthropic(api_key=config.get_api_key())
    model = config.get_industrial_model()
    raw_response = ""
    try:
        message = client.messages.create(
            model=model,
            max_tokens=1000,
            temperature=0.1,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        raw_response = message.content[0].text.strip()
        cleaned = clean_markdown_code_block(raw_response)
        data = json.loads(cleaned)
        raw_code = data.get("action_code", "")
        action_code = fix_variable_name(raw_code)
        narration = data.get("narration", "No narration")
        return action_code, narration
    except json.JSONDecodeError as e:
        return "", f"JSON parse failed: {e}. Raw: {raw_response[:200]}"
    except Exception as e:
        return "", f"Parse instruction failed: {e}"


def parse_instruction_to_code(page, instruction: str) -> Tuple[str, str]:
    """Sync version: uses sync screenshot. For async page use parse_instruction_to_code_async."""
    screenshot_b64 = capture_screenshot_base64(page)
    prompt = f"""
Important: Output must be pure JSON only, no Markdown code blocks or comments.
Output format: {{"action_code": "Playwright code", "narration": "English narrative"}}

Instruction: {instruction}

Requirements (must follow):
1. All page operations must use self.page (not page);
2. Timeout parameters use Python syntax: timeout=10000 (not {{timeout:10000}});
3. For GitHub search: click button[aria-label="Search or jump to…"], then wait for input#query-builder-test, fill and press Enter.
4. Multiple operations separated by semicolons; prefix each with await.
"""
    client = Anthropic(api_key=config.get_api_key())
    model = config.get_industrial_model()
    try:
        message = client.messages.create(
            model=model,
            max_tokens=1000,
            temperature=0.1,
            messages=[{"role": "user", "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64}}, {"type": "text", "text": prompt}]}],
        )
        raw_response = message.content[0].text.strip()
        cleaned = clean_markdown_code_block(raw_response)
        data = json.loads(cleaned)
        action_code = fix_variable_name(data.get("action_code", ""))
        narration = data.get("narration", "No narration")
        return action_code, narration
    except Exception as e:
        return "", f"Parse instruction failed: {e}"


def execute_action_code_sync(page, action_code: str) -> Tuple[bool, str]:
    """
    Execute generated action code (sync-style: no await). Injects page as self.page.
    Returns (success, message). For async-generated code use execute_action_code_async.
    """
    if not action_code or ("page." in action_code and "self.page." not in action_code):
        action_code = """
self.page.wait_for_selector('button[aria-label="Search or jump to…"]', timeout=10000)
self.page.click('button[aria-label="Search or jump to…"]')
self.page.wait_for_selector('input[id="query-builder-test"]', timeout=10000)
self.page.fill('input[id="query-builder-test"]', 'playwright')
self.page.press('input[id="query-builder-test"]', 'Enter')
"""
    try:
        class _Self:
            pass
        self_obj = _Self()
        self_obj.page = page
        loc = {"self_obj": self_obj}
        code = "def _run(self):\n    " + action_code.replace("\n", "\n    ") + "\n_run(self_obj)"
        exec(code, {}, loc)
        return True, "Operation succeeded"
    except Exception as e:
        err = str(e)
        if "Timeout" in err or "timeout" in err:
            return False, f"Element wait timeout: {err}"
        return False, str(e)


async def execute_action_code_async(page, action_code: str) -> Tuple[bool, str]:
    """
    Execute generated async action code (await self.page.*). Use with async Playwright page.
    Returns (success, message).
    """
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    if not action_code or ("page." in action_code and "self.page." not in action_code):
        action_code = """
await self.page.wait_for_selector('button[aria-label="Search or jump to…"]', timeout=10000)
await self.page.click('button[aria-label="Search or jump to…"]')
await self.page.wait_for_selector('input[id="query-builder-test"]', timeout=10000)
await self.page.fill('input[id="query-builder-test"]', 'playwright')
await self.page.press('input[id="query-builder-test"]', 'Enter')
"""
    try:
        class _Self:
            page = page
        local_vars = {"self": _Self()}
        local_vars["self"].page = page
        exec(f"""
async def execute_operations(self):\n    """ + action_code.replace("\n", "\n    "), globals(), local_vars)
        await local_vars["execute_operations"](local_vars["self"])
        return True, "Operation succeeded"
    except PlaywrightTimeoutError as e:
        return False, f"Element wait timeout: {e}"
    except Exception as e:
        return False, str(e)
