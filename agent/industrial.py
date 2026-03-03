"""Industrial agent: ReAct loop with Memory, delegating execution to BrowserAgent."""
import time
from typing import Optional, Callable, Any

from anthropic import Anthropic

import config
from core.json_parser import safe_json_parse
from executor import BrowserAgent


class Memory:
    """Standalone ReAct memory: thought, action, observation per step."""

    def __init__(self) -> None:
        self.history: list = []

    def add(self, thought: str, action: dict, observation: str) -> None:
        self.history.append({
            "thought": thought,
            "action": action,
            "observation": observation,
        })

    def context(self, last_n: int = 5) -> str:
        out = ""
        for step in self.history[-last_n:]:
            out += f"\nThought: {step['thought']}\nAction: {step['action']}\nObservation: {step['observation']}\n"
        return out


def _call_claude(goal: str, memory_context: str, observation: str, reflection: Optional[str] = None) -> str:
    """Call Claude for next thought/action. Uses config for API key and model."""
    client = Anthropic(api_key=config.get_api_key())
    model = config.get_industrial_model()
    system_prompt = """
You are an industrial browser agent using ReAct.
Rules:
- STRICT JSON output only
- One action per step
- If action fails, improve strategy
- Use simple selectors
- If done, call finish
"""
    user_prompt = f"""
GOAL:
{goal}

MEMORY:
{memory_context}

CURRENT PAGE (HTML truncated):
{observation}
"""
    if reflection:
        user_prompt += f"\nPrevious failure:\n{reflection}\nImprove strategy.\n"
    user_prompt += """
Return JSON:
{
  "thought": "...",
  "action": {
    "name": "...",
    "args": {}
  }
}
"""
    response = client.messages.create(
        model=model,
        max_tokens=800,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


class IndustrialAgent:
    """
    ReAct agent with Memory. Executes via BrowserAgent (shared or owned).
    Actions: click, type, press, wait, extract, finish.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        get_page: Optional[Callable[[str], Any]] = None,
        enable_viz: bool = False,
    ) -> None:
        self.memory = Memory()
        headless = config.get_default_headless()
        if session_id and get_page:
            page = get_page(session_id)
            self._executor = BrowserAgent(
                page=page,
                enable_viz=enable_viz,
            )
            self._owned = False
        else:
            self._executor = BrowserAgent(headless=headless, enable_viz=enable_viz)
            self._owned = True

    def goto(self, url: str) -> None:
        self._executor.navigate(url)

    def observe(self) -> str:
        return (self._executor.get_context() or "")[:7000]

    def execute(self, action: dict) -> str:
        """Execute one step. Returns result string or 'FINISHED' for finish."""
        name = action.get("name")
        args = action.get("args") or {}

        if name == "click":
            sel = args.get("selector") or args.get("target") or ""
            self._executor.execute({"action": "click", "target": sel})
            return "OK"

        if name == "type":
            sel = args.get("selector") or args.get("target") or ""
            text = args.get("text", "")
            self._executor.execute({"action": "type", "target": sel, "text": text})
            return "OK"

        if name == "navigate":
            url = args.get("url") or args.get("target") or ""
            self._executor.navigate(url)
            return "OK"

        if name == "press":
            try:
                self._executor.page.keyboard.press(args.get("key", ""))
                return "OK"
            except Exception as e:
                return f"ERROR: {str(e)}"

        if name == "wait":
            ms = args.get("milliseconds", 2000)
            self._executor.page.wait_for_timeout(ms)
            return "OK"

        if name == "extract":
            try:
                loc = self._executor.page.locator((args.get("selector") or "").strip()).first
                if loc.count() == 0:
                    return "ERROR: Element not found"
                attr = args.get("attribute")
                if attr and attr != "text":
                    value = loc.get_attribute(attr)
                else:
                    value = loc.inner_text()
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    return "ERROR: Empty extract"
                return (value or "").strip()
            except Exception as e:
                return f"ERROR: {str(e)}"

        if name == "finish":
            return "FINISHED"

        return "ERROR: Unknown action"

    def run(self, goal: str) -> None:
        """ReAct loop: observe -> plan -> execute -> memory. Uses config MAX_STEPS, MAX_RETRIES."""
        max_steps = config.get_max_steps()
        max_retries = config.get_max_retries()
        observation = self.observe()

        for step in range(max_steps):
            print(f"\n================ STEP {step + 1} ================\n")
            reflection: Optional[str] = None

            for retry in range(max_retries):
                raw = _call_claude(goal, self.memory.context(), observation, reflection)
                print("Claude raw:\n", raw)
                parsed = safe_json_parse(raw)
                if not parsed:
                    reflection = "Invalid JSON output."
                    print("JSON parse failed, retrying...")
                    continue
                thought = parsed.get("thought", "")
                action = parsed.get("action")
                if not action:
                    reflection = "Missing action in JSON."
                    continue
                print("Thought:", thought)
                print("Action:", action)
                result = self.execute(action)
                if result is None:
                    result = "ERROR: None result"
                result = str(result)
                print("Execution Result:", result)
                if result == "FINISHED":
                    print("\nGoal completed.")
                    return
                if result.startswith("ERROR"):
                    reflection = f"Action failed: {result}"
                    print("Retrying with reflection...")
                    continue
                self.memory.add(thought, action, result)
                observation = self.observe()
                break
        print("\nAgent stopped (max steps reached).")

    def close(self) -> None:
        if self._owned:
            self._executor.close()
