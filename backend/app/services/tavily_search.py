"""Tavily Web Search Service Module

Provides asynchronous integration with Tavily Search API (https://api.tavily.com/search).
Supplies real-time web search capabilities for current events, news, and live facts
with connection timeouts, structured result parsing, zero credential leakage, and turn-aware error handling.
"""

import time
import logging
from typing import Any, Dict, List, Optional
import httpx

from backend.app.config import Settings, get_settings
from backend.app.models.schemas import TavilySearchResult, TavilySearchResponse

logger = logging.getLogger(__name__)


class TavilySearchError(Exception):
    """Base exception for Tavily search failures with sanitized error messages."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class TavilySearchService:
    """Service client for Tavily Web Search API."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self._settings = settings or get_settings()
        self._client = client
        self._timeout = httpx.Timeout(timeout=8.0, connect=3.0)

    async def search(
        self,
        query: str,
        max_results: int = 3,
        search_depth: str = "basic",
        session_id: Optional[str] = None,
        turn_id: Optional[int] = None,
    ) -> TavilySearchResponse:
        """Execute web search query via Tavily API.

        Args:
            query: User search query string.
            max_results: Maximum number of web results to retrieve (default 3).
            search_depth: Search depth ('basic' or 'advanced').
            session_id: Associated session ID if applicable.
            turn_id: Associated turn ID if applicable.

        Returns:
            TavilySearchResponse containing ranked results and latency metadata.

        Raises:
            ValueError: If query is empty or TAVILY_API_KEY is not configured.
            TavilySearchError: If API request fails, times out, or returns an error.
        """
        clean_query = (query or "").strip()
        if not clean_query:
            raise ValueError("Search query cannot be empty.")

        api_key = self._settings.tavily_api_key
        if not api_key or not api_key.strip():
            raise ValueError(
                "TAVILY_API_KEY is not configured. Ensure credentials are set in environment."
            )

        api_url = self._settings.tavily_api_url
        payload = {
            "api_key": api_key.strip(),
            "query": clean_query,
            "search_depth": search_depth,
            "max_results": max(1, min(max_results, 5)),
            "include_answer": False,
            "include_raw_content": False,
        }

        created_client = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout)
            created_client = True

        start_time = time.perf_counter()

        try:
            response = await client.post(
                api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Handle non-2xx responses safely without leaking API key
            if response.status_code != 200:
                err_detail = "Unknown error"
                try:
                    err_json = response.json()
                    err_detail = (
                        err_json.get("error")
                        or err_json.get("detail")
                        or err_json.get("message")
                        or str(err_json)
                    )
                except Exception:
                    err_detail = response.text[:200] if response.text else "No response body"

                raise TavilySearchError(
                    f"Tavily API returned HTTP {response.status_code}: {err_detail}",
                    status_code=response.status_code,
                )

            res_json = response.json()
            raw_results = res_json.get("results", [])

            structured_results: List[TavilySearchResult] = []
            for item in raw_results:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "Untitled").strip()
                url = str(item.get("url") or "").strip()
                content = str(item.get("content") or "").strip()
                score = item.get("score")
                pub_date = item.get("published_date")

                if url and content:
                    structured_results.append(
                        TavilySearchResult(
                            title=title,
                            url=url,
                            content=content,
                            score=float(score) if score is not None else None,
                            published_date=str(pub_date) if pub_date else None,
                        )
                    )

            logger.info(
                f"[TAVILY] Search completed: query='{clean_query[:50]}' results={len(structured_results)} latency={latency_ms:.1f}ms"
            )

            return TavilySearchResponse(
                query=clean_query,
                results=structured_results,
                session_id=session_id,
                turn_id=turn_id,
                status="SUCCESS",
                latency_ms=round(latency_ms, 2),
            )

        except httpx.TimeoutException as exc:
            raise TavilySearchError(f"Tavily search request timed out: {type(exc).__name__}") from None
        except httpx.RequestError as exc:
            raise TavilySearchError(f"Tavily network connection error: {type(exc).__name__}") from None
        finally:
            if created_client:
                await client.aclose()


# Default service instance
default_tavily_service = TavilySearchService()
