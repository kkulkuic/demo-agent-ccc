from planner import plan_actions
from executor import BrowserAgent

def run_agent(instruction, start_url):
    agent = BrowserAgent(headless=False)
    agent.navigate(start_url)

    context = agent.get_context()
    plan = plan_actions(instruction, context)

    for i, action in enumerate(plan["actions"]):
        agent.execute(action)
        agent.snapshot(i)

    agent.close()


if __name__ == "__main__":
    run_agent(
        instruction="Search for a product and add it to cart.",
        start_url="https://www.saucedemo.com/"
    )
