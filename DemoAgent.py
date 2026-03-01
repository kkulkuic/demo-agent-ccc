# 打开GitHub主页，点击搜索框，输入playwright关键词，按回车键执行搜索
import os
import base64
import asyncio
import json
import re
from dotenv import load_dotenv
from anthropic import Anthropic
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# 加载环境变量
load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

class DemoBrowserAgent:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.llm_model = "claude-haiku-4-5-20251001"

    async def init_browser(self, headless=False):
        """初始化浏览器，强制英文界面"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--lang=en-US"]
        )
        self.page = await self.browser.new_page(
            viewport={"width": 1920, "height": 1080},
            locale="en-US"
        )
        # 反爬虫脚本
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        return self.page

    async def capture_screenshot_base64(self):
        """捕获固定尺寸截图"""
        if not self.page:
            raise RuntimeError("浏览器页面未初始化！")
        
        screenshot_bytes = await self.page.screenshot(
            full_page=False,
            clip={"x": 0, "y": 0, "width": 1920, "height": 1080}
        )
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    def clean_claude_response(self, response_text):
        """清理 Markdown 代码块符号"""
        if not response_text:
            return ""
        cleaned = re.sub(r"^```json\s*", "", response_text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    def fix_variable_name(self, action_code):
        """自动修正变量名：将 page. 替换为 self.page."""
        if not action_code:
            return ""
        # 正则替换：匹配所有 "page." 并替换为 "self.page."（避免误替换其他内容）
        fixed_code = re.sub(r"(?<!\.)page\.", "self.page.", action_code)
        # 同时修正 Playwright 超时参数格式（Claude 可能生成 {timeout:10000} 而非 timeout=10000）
        fixed_code = re.sub(r"\{timeout:\s*(\d+)\}", r"timeout=\1", fixed_code)
        return fixed_code

    async def parse_instruction(self, instruction):
        """解析指令，强制要求使用 self.page"""
        # 1. 获取截图
        screenshot_base64 = await self.capture_screenshot_base64()
        
        # 2. 构造精准提示词（强调 self.page 变量名）
        prompt = f"""
        重要：输出必须是纯 JSON 字符串，无任何 Markdown 代码块、注释！
        输出结构：{{"action_code": "Playwright 代码", "narration": "中文解说"}}
        
        指令：{instruction}
        核心要求（必须严格遵守）：
        1. 所有页面操作必须使用 self.page（而非 page）作为对象；
        2. 超时参数使用 Python 语法：timeout=10000（而非 {{timeout:10000}}）；
        3. GitHub 搜索框操作步骤：
           - 点击外层按钮：self.page.wait_for_selector('button[aria-label="Search or jump to…"]', timeout=10000)
           - 点击按钮：self.page.click('button[aria-label="Search or jump to…"]')
           - 等待输入框：self.page.wait_for_selector('input[id="query-builder-test"]', timeout=10000)
           - 输入内容：self.page.fill('input[id="query-builder-test"]', 'playwright')
           - 按回车：self.page.press('input[id="query-builder-test"]', 'Enter')
        4. 多个操作用分号分隔，每个操作前加 await。
        """

        # 3. 调用 Claude API
        try:
            message = client.messages.create(
                model=self.llm_model,
                max_tokens=1000,
                temperature=0.1,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_base64}},
                    {"type": "text", "text": prompt}
                ]}]
            )
            
            # 4. 解析并修正响应
            raw_response = message.content[0].text.strip()
            cleaned_response = self.clean_claude_response(raw_response)
            response = json.loads(cleaned_response)
            
            # 修正变量名和参数格式
            raw_action_code = response.get("action_code", "")
            fixed_action_code = self.fix_variable_name(raw_action_code)
            
            return fixed_action_code, response.get("narration", "无解说")
        
        except json.JSONDecodeError as e:
            error_msg = f"JSON 解析失败：{str(e)}，原始内容：{raw_response}"
            return "", error_msg
        except Exception as e:
            return "", f"解析指令失败：{str(e)}"

    async def execute_action(self, action_code):
        """执行操作代码（最终兜底）"""
        # 终极兜底：如果修正后的代码仍有问题，使用手动验证的代码
        if not action_code or "page." in action_code and "self.page." not in action_code:
            action_code = """
await self.page.wait_for_selector('button[aria-label="Search or jump to…"]', timeout=10000);
await self.page.click('button[aria-label="Search or jump to…"]');
await self.page.wait_for_selector('input[id="query-builder-test"]', timeout=10000);
await self.page.fill('input[id="query-builder-test"]', 'playwright');
await self.page.press('input[id="query-builder-test"]', 'Enter');
"""
        
        try:
            # 封装到异步函数执行
            async_func_code = f"""
async def execute_operations(self):
    {action_code}
"""
            local_vars = {"self": self}
            exec(async_func_code, globals(), local_vars)
            
            # 执行操作
            execute_func = local_vars["execute_operations"]
            await execute_func(self)
            
            return True, "操作执行成功"
        
        except PlaywrightTimeoutError as e:
            return False, f"元素等待超时：{str(e)}\n建议：检查网络或页面加载状态"
        except Exception as e:
            return False, f"执行失败：{str(e)}"

    async def run_agent(self, start_url, instruction):
        """主流程"""
        # 初始化浏览器
        await self.init_browser(headless=False)
        await self.page.goto(start_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)  # 延长等待，确保页面完全渲染
        
        # 解析指令
        print("\n=== 解析自然语言指令 ===")
        action_code, narration = await self.parse_instruction(instruction)
        
        # 输出解说
        print("\n=== 操作解说 ===")
        print(narration)
        
        # 执行操作
        print("\n=== 执行浏览器操作 ===")
        print(f"操作代码：{action_code}")
        success, msg = await self.execute_action(action_code)
        print(f"执行结果：{msg}")
        
        # 保持浏览器打开
        await self.page.wait_for_timeout(10000)

    async def close(self):
        """释放资源"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

# 测试入口
async def main():
    agent = DemoBrowserAgent()
    try:
        await agent.run_agent(
            start_url="https://github.com",
            instruction="打开 GitHub 主页，在搜索框输入 playwright 并回车搜索"
        )
    finally:
        await agent.close()

if __name__ == "__main__":
    asyncio.run(main())