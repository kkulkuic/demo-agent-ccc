import os
import json
import re
from dotenv import load_dotenv
from anthropic import Anthropic
from playwright.sync_api import sync_playwright, TimeoutError

# =====================================================
# CONFIG
# =====================================================

load_dotenv()
API_KEY = os.getenv("ANTHROPIC_API_KEY")

MODEL = "claude-haiku-4-5-20251001"
MAX_STEPS = 20
MAX_RETRIES = 3
HEADLESS = False

if not API_KEY:
    raise ValueError("Missing ANTHROPIC_API_KEY")

client = Anthropic(api_key=API_KEY)

# =====================================================
# MEMORY
# =====================================================

class Memory:
    def __init__(self):
        self.history = []

    def add(self, thought, action, observation):
        self.history.append({
            "thought": thought,
            "action": action,
            "observation": observation
        })

    def context(self, last_n=5):
        context = ""
        for step in self.history[-last_n:]:
            context += f"""
Thought: {step['thought']}
Action: {step['action']}
Observation: {step['observation']}
"""
        return context


# =====================================================
# JSON SAFE PARSER
# =====================================================

def extract_json(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text

def safe_json_parse(raw):
    cleaned = extract_json(raw)
    try:
        return json.loads(cleaned)
    except:
        return None


# =====================================================
# CLAUDE CALL
# =====================================================

def call_claude(goal, memory, observation, reflection=None):

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
{memory}

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
        model=MODEL,
        max_tokens=800,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return response.content[0].text


# =====================================================
# INDUSTRIAL AGENT
# =====================================================

class IndustrialAgent:

    def __init__(self):
        self.memory = Memory()
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=HEADLESS)
        self.page = self.browser.new_page()

    def goto(self, url):
        self.page.goto(url)

    def observe(self):
        return self.page.content()[:7000]

    # ---------------------------
    # Robust Execution Layer
    # ---------------------------

    def safe_click(self, selector):
        try:
            self.page.locator(selector).first.click(timeout=4000)
            return "OK"
        except Exception as e:
            return f"ERROR: {str(e)}"

    def safe_type(self, selector, text):
        try:
            self.page.locator(selector).first.fill(text)
            return "OK"
        except Exception as e:
            return f"ERROR: {str(e)}"

    def safe_extract(self, selector, attr=None):
        try:
            element = self.page.locator(selector).first

            if not element.count():
                return "ERROR: Element not found"

            if attr and attr != "text":
                value = element.get_attribute(attr)
            else:
                value = element.inner_text()

            if value is None or value.strip() == "":
                return "ERROR: Empty extract"

            return value.strip()

        except Exception as e:
            return f"ERROR: {str(e)}"

    def execute(self, action):

        name = action["name"]
        args = action.get("args", {})

        if name == "click":
            return self.safe_click(args.get("selector"))

        elif name == "type":
            return self.safe_type(args.get("selector"), args.get("text"))

        elif name == "press":
            try:
                self.page.keyboard.press(args.get("key"))
                return "OK"
            except Exception as e:
                return f"ERROR: {str(e)}"

        elif name == "wait":
            self.page.wait_for_timeout(args.get("milliseconds", 2000))
            return "OK"

        elif name == "extract":
            return self.safe_extract(
                args.get("selector"),
                args.get("attribute")
            )

        elif name == "finish":
            return "FINISHED"

        return "ERROR: Unknown action"

    # ---------------------------
    # MAIN LOOP
    # ---------------------------

    def run(self, goal):

        observation = self.observe()

        for step in range(MAX_STEPS):

            print(f"\n================ STEP {step+1} ================\n")

            reflection = None

            for retry in range(MAX_RETRIES):

                raw = call_claude(
                    goal,
                    self.memory.context(),
                    observation,
                    reflection
                )

                print("Claude raw:\n", raw)

                parsed = safe_json_parse(raw)

                if not parsed:
                    reflection = "Invalid JSON output."
                    print("JSON parse failed, retrying...")
                    continue

                thought = parsed["thought"]
                action = parsed["action"]

                print("Thought:", thought)
                print("Action:", action)

                result = self.execute(action)

                if result is None:
                    result = "ERROR: None result"

                result = str(result)

                print("Execution Result:", result)

                if result == "FINISHED":
                    print("\n🎉 GOAL COMPLETED")
                    return

                if result.startswith("ERROR"):
                    reflection = f"Action failed: {result}"
                    print("Retrying with reflection...")
                    continue

                # Success
                self.memory.add(thought, action, result)
                observation = self.observe()
                break

        print("\nAgent stopped (max steps reached).")

    def close(self):
        self.browser.close()
        self.playwright.stop()


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    agent = IndustrialAgent()

    agent.goto("https://quotes.toscrape.com")

    agent.run(
        goal="Extract the first quote text and its author"
    )

    input("\nPress Enter to close browser...")
    agent.close()
