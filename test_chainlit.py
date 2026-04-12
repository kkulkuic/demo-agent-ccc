#!/usr/bin/env python3
"""
Test chainlit_app.py core functions (without running the full Chainlit server)

Tests:
1. Intent classification (navigate vs research)
2. HITL classification (needs human help or not)
3. Research mode execution
4. Navigate mode execution
"""

import os
import sys
import asyncio

# Setup paths and patches
sys.path.insert(0, os.path.dirname(__file__))
import pkg_resources_compat as pkg_resources
sys.modules['pkg_resources'] = pkg_resources
import playwright_stealth

# Load env
from dotenv import load_dotenv
load_dotenv()

# Import the functions we want to test
from chainlit_app import classify_intent, classify_hitl, get_rn_module

# Check API keys
print("=== API Keys Check ===")
print(f"ANTHROPIC_API_KEY: {'✓' if os.getenv('ANTHROPIC_API_KEY') else '✗ MISSING'}")
print(f"TAVILY_API_KEY: {'✓' if os.getenv('TAVILY_API_KEY') else '✗ MISSING'}")
print()

async def test_intent_classification():
    """Test semantic intent classification"""
    print("=== Intent Classification Tests ===")
    
    tests = [
        ("what is cloud run pricing", None, "research"),
        ("navigate to google.com", None, "navigate"),
        ("show me the fastest route to starved rock", None, "navigate"),
        ("find restaurants near downtown chicago", None, "research"),
        ("open amazon and find cheapest headphones", None, "navigate"),
        # Context-aware tests
        ("from uic", [
            {"role": "user", "content": "look for hiking places near chicago"},
            {"role": "assistant", "content": "Here are hiking places: Starved Rock, Indiana Dunes..."},
        ], "navigate"),
        ("show me the fastest route", [
            {"role": "user", "content": "find national parks near chicago"},
            {"role": "assistant", "content": "Indiana Dunes is the nearest..."},
        ], "navigate"),
    ]
    
    for user_input, history, expected in tests:
        result = await classify_intent(user_input, history)
        icon = "🧭" if result == "navigate" else "🔍"
        status = "✅" if result == expected else "❌"
        ctx = "w/ context" if history else "no context"
        print(f"  {status} {icon} {result:10s} | {user_input[:40]:40s} | {ctx}")
    print()

async def test_hitl_classification():
    """Test HITL reason classification"""
    print("=== HITL Classification Tests ===")
    
    tests = [
        # Should return empty (no help needed)
        ("What would you like to do?", "I found the answer: Cloud Run is...", "Cloud Run pricing...", ""),
        ("What would you like to do?", "Here are the results...", "Indiana Dunes is 50 miles away", ""),
        # Should return prompt (needs help)
        ("CAPTCHA detected, please solve it", "I'm stuck on a verification page", "", "CAPTCHA"),
        ("Please check the browser window", "The page seems blank", "", "browser"),
        ("Choose: A) $50 B) $80 C) $120", "I found multiple options", "", "choose"),
    ]
    
    for interrupt, agent_msg, answer, expected_keyword in tests:
        result = await classify_hitl(interrupt, agent_msg, answer)
        if expected_keyword:
            status = "✅" if expected_keyword.lower() in result.lower() else "❌"
            print(f"  {status} HITL needed: {result[:60]}")
        else:
            status = "✅" if not result else "❌"
            print(f"  {status} No HITL: '{result[:30] if result else '(empty)'}'")
    print()

async def test_research_mode():
    """Test research agent execution"""
    print("=== Research Mode Test ===")
    
    rn = get_rn_module()
    from langchain_core.messages import HumanMessage
    
    config = {"configurable": {"thread_id": "test-chainlit-research"}, "recursion_limit": 50}
    input_data = {"messages": [HumanMessage(content="what is cloud run pricing")], "mode": "research"}
    
    step = 0
    answer = ""
    
    async for event in rn.app.astream(input_data, config, stream_mode="updates"):
        for node, data in event.items():
            if node == "research_agent":
                msgs = data.get("messages", []) if isinstance(data, dict) else []
                for m in msgs:
                    tc = getattr(m, 'tool_calls', []) or []
                    content = getattr(m, 'content', '') or ''
                    if tc:
                        step += 1
                        tools = [t.get('name') for t in tc]
                        print(f"  Step {step}: {tools}")
                    elif content and len(content) > 100 and not tc:
                        answer = content
    
    print(f"  Total steps: {step}")
    print(f"  Answer length: {len(answer)} chars")
    print(f"  Status: {'✅ Got answer' if answer else '❌ No answer'}")
    print()

async def test_navigate_mode():
    """Test navigate agent execution (short test)"""
    print("=== Navigate Mode Test ===")
    
    rn = get_rn_module()
    from langchain_core.messages import HumanMessage
    
    config = {"configurable": {"thread_id": "test-chainlit-nav"}, "recursion_limit": 50}
    input_data = {"messages": [HumanMessage(content="go to example.com")], "mode": "navigate"}
    
    step = 0
    stopped = False
    
    async for event in rn.app.astream(input_data, config, stream_mode="updates"):
        for node, data in event.items():
            if node == "nav_agent":
                msgs = data.get("messages", []) if isinstance(data, dict) else []
                for m in msgs:
                    tc = getattr(m, 'tool_calls', []) or []
                    if tc:
                        step += 1
                        tools = [t.get('name') for t in tc]
                        print(f"  Step {step}: {tools}")
                        if 'stop' in tools:
                            stopped = True
    
    print(f"  Total steps: {step}")
    print(f"  Stopped: {'✅' if stopped else '❌'}")
    
    # Check if browser session exists
    if rn.browser_session.get("page"):
        print(f"  Browser: ✅ Running")
    else:
        print(f"  Browser: ❌ Not started")
    print()

async def main():
    await test_intent_classification()
    await test_hitl_classification()
    await test_research_mode()
    await test_navigate_mode()
    
    print("=== All Tests Complete ===")

if __name__ == "__main__":
    asyncio.run(main())