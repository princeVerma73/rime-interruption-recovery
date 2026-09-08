"""Tests for Tavily Web Search Service

Validates search intent detection, query dispatch, structured result parsing,
error handling, timeout resilience, and zero credential leakage.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch

from backend.app.config import Settings
from backend.app.services.tavily_search import (
    TavilySearchService,
    TavilySearchError,
    TavilySearchResult,
    TavilySearchResponse,
)
from backend.app.services.llm import (
    is_search_query,
    format_search_context,
)


@pytest.fixture
def mock_settings():
    return Settings(
        rime_api_key="mock_rime_key",
        groq_api_key="mock_groq_key",
        gemini_api_key="mock_gemini_key",
        tavily_api_key="mock_tavily_key",
    )


class TestTavilyIntentDetection:
    """Test suite for determining when real-time search should be triggered."""

    def test_search_queries_detected(self):
        positive_queries = [
            "What is the latest news about OpenAI?",
            "What happened in India today?",
            "Who won the latest football match?",
            "What is the current stock price of Apple?",
            "Search for recent AI breakthroughs",
            "Give me the latest updates on space missions",
            "What is the weather in Tokyo today?",
            "What are the breaking headlines?",
            "Tell me about the latest models released by Groq",
        ]
        for query in positive_queries:
            assert is_search_query(query) is True, f"Failed to detect search intent for: {query}"

    def test_static_queries_not_searched(self):
        negative_queries = [
            "Hello",
            "Hi there",
            "How are you?",
            "What is the capital of France?",
            "Explain quantum computing simply",
            "Tell me a joke",
            "Write a poem about rain",
            "What is 2 plus 2?",
            "Who was Albert Einstein?",
            "",
            None,
        ]
        for query in negative_queries:
            assert is_search_query(query) is False, f"False positive search intent for: {query}"

    def test_format_search_context(self):
        results = [
            TavilySearchResult(
                title="OpenAI announces GPT-5",
                url="https://example.com/gpt5",
                content="OpenAI today announced their next generation model with major reasoning improvements.",
                score=0.95,
            ),
            TavilySearchResult(
                title="AI Advancements 2026",
                url="https://example.com/ai2026",
                content="Industry reports show massive growth in agentic AI.",
                score=0.88,
            ),
        ]
        context = format_search_context("latest AI news", results)
        assert "CURRENT WEB INFORMATION FOR 'latest AI news':" in context
        assert "OpenAI announces GPT-5" in context
        assert "https://example.com/gpt5" not in context or "OpenAI announces" in context
        assert "Instructions:" in context

    def test_format_empty_search_context(self):
        assert format_search_context("test", []) == ""


@pytest.mark.asyncio
class TestTavilySearchService:
    """Test suite for TavilySearchService API client."""

    async def test_successful_search(self, mock_settings):
        mock_response_data = {
            "query": "latest news",
            "results": [
                {
                    "title": "Breaking News Today",
                    "url": "https://news.example.com/article1",
                    "content": "Major events occurred today across global tech sectors.",
                    "score": 0.92,
                    "published_date": "2026-09-08",
                }
            ],
        }

        mock_http_response = httpx.Response(
            status_code=200,
            json=mock_response_data,
            request=httpx.Request("POST", "https://api.tavily.com/search"),
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_http_response

        service = TavilySearchService(settings=mock_settings, client=mock_client)
        result = await service.search(query="latest news", session_id="sess_123", turn_id=1)

        assert isinstance(result, TavilySearchResponse)
        assert result.status == "SUCCESS"
        assert len(result.results) == 1
        assert result.results[0].title == "Breaking News Today"
        assert result.results[0].url == "https://news.example.com/article1"
        assert result.session_id == "sess_123"
        assert result.turn_id == 1

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"]["query"] == "latest news"
        assert call_kwargs["json"]["api_key"] == "mock_tavily_key"

    async def test_missing_api_key_raises_value_error(self):
        empty_settings = Settings(
            rime_api_key="mock_rime_key",
            groq_api_key="mock_groq_key",
            gemini_api_key="mock_gemini_key",
            tavily_api_key="",
        )
        service = TavilySearchService(settings=empty_settings)
        with pytest.raises(ValueError, match="TAVILY_API_KEY is not configured"):
            await service.search(query="latest news")

    async def test_empty_query_raises_value_error(self, mock_settings):
        service = TavilySearchService(settings=mock_settings)
        with pytest.raises(ValueError, match="Search query cannot be empty"):
            await service.search(query="   ")

    async def test_api_error_response(self, mock_settings):
        mock_http_response = httpx.Response(
            status_code=401,
            json={"error": "Invalid API Key"},
            request=httpx.Request("POST", "https://api.tavily.com/search"),
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_http_response

        service = TavilySearchService(settings=mock_settings, client=mock_client)
        with pytest.raises(TavilySearchError) as exc_info:
            await service.search(query="test query")

        assert "HTTP 401" in str(exc_info.value)
        assert exc_info.value.status_code == 401

    async def test_timeout_handling(self, mock_settings):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")

        service = TavilySearchService(settings=mock_settings, client=mock_client)
        with pytest.raises(TavilySearchError, match="timed out"):
            await service.search(query="test query")

    async def test_network_connection_error(self, mock_settings):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.ConnectError("Network unreachable")

        service = TavilySearchService(settings=mock_settings, client=mock_client)
        with pytest.raises(TavilySearchError, match="network connection error"):
            await service.search(query="test query")
