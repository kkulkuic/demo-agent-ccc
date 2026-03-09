import os
from dotenv import load_dotenv

load_dotenv()

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
MAX_STEPS = int(os.getenv("MAX_STEPS", "6"))
DEFAULT_SEARCH_LIMIT = int(os.getenv("DEFAULT_SEARCH_LIMIT", "5"))
DEFAULT_CRAWL_LIMIT = int(os.getenv("DEFAULT_CRAWL_LIMIT", "10"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "120"))