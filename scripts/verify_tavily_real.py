"""One-Time Real Tavily Search Integration Verification Script

Strictly executes exactly ONE live web search request to https://api.tavily.com/search
using the configured TAVILY_API_KEY. Prints only sanitized metadata.
Never prints or logs secret credentials.
"""

import asyncio
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.app.config import get_settings
from backend.app.services.tavily_search import default_tavily_service, TavilySearchError


async def run_single_tavily_verification():
    settings = get_settings()
    if not settings.tavily_api_key or not settings.tavily_api_key.strip():
        print("[SKIP] TAVILY_API_KEY is not configured in backend/.env or environment.")
        return False

    print("==================================================")
    print("REAL TAVILY WEB SEARCH INTEGRATION VERIFICATION")
    print("==================================================")
    print("Executing EXACTLY ONE live Tavily search request...")
    print(f"Target Endpoint: {settings.tavily_api_url}")
    print("Query: 'latest AI developments'")
    print("--------------------------------------------------")

    try:
        start_time = time.perf_counter()
        response = await default_tavily_service.search(
            query="latest AI developments",
            max_results=3,
        )
        latency_ms = (time.perf_counter() - start_time) * 1000

        print("[SUCCESS] Real Tavily Search Call Succeeded!")
        print(f"Query: {response.query}")
        print(f"Results Retrieved: {len(response.results)}")
        print(f"Roundtrip Latency: {latency_ms:.2f} ms")
        for i, item in enumerate(response.results, 1):
            print(f"  [{i}] {item.title}")
            print(f"      URL: {item.url}")
            print(f"      Snippet: {item.content[:100]}...")
        print("==================================================")
        return True
    except TavilySearchError as e:
        print(f"[ERROR] Real Tavily search failed: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected failure: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(run_single_tavily_verification())
