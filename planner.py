import os
import json
from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL_NAME = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """
You are a browser automation planner.
Return ONLY valid JSON.
Format:
{
  "actions": [
    {"action": "click", "target": "..."},
    {"action": "type", "target": "...", "text": "..."},
    {"action": "navigate", "target": "..."}
  ]
}

"""

def plan_actions(user_instruction, page_context=""):
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=800,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"""
Instruction:
{user_instruction}

Page context:
{page_context}
"""}
        ]
    )

    content = response.content[0].text
    return json.loads(content)
