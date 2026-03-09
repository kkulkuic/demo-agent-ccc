from core.browser_session import BrowserSession
from tools.headed_tools import (
    open_url_headed,
    type_text_on_page,
    read_page_headed,
    get_current_url,
    close_browser_headed,
)

session = BrowserSession(headless=False, slow_mo=150)

try:
    print(open_url_headed(session, "https://www.google.com"))
    print(type_text_on_page(session, 'textarea[name="q"]', "latest firecrawl documentation", press_enter=True))
    print(get_current_url(session))
    print(read_page_headed(session, max_chars=1500))
finally:
    print(close_browser_headed(session))