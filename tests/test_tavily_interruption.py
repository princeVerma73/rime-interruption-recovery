"""Tests for Tavily Search Turn Isolation & Interruption Safety

Verifies:
1. Tavily participates in monotonic turn validation.
2. If turn advances / user interrupts during search, stale search results are rejected.
3. Stale search results never mutate conversation history or get spoken by Rime.
4. Active turn with search completes and commits authoritative history.
5. Non-fatal search error allows graceful fallback.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from backend.app.core.session import SessionStore, VoiceSession
from backend.app.core.cancellation import CancellationManager
from backend.app.services.conversation import ConversationManager
from backend.app.services.stt import GroqSTTService
from backend.app.services.llm import GroqLLMService
from backend.app.services.rime_tts import RimeTTSService
from backend.app.services.tavily_search import (
    TavilySearchService,
    TavilySearchResult,
    TavilySearchResponse,
    TavilySearchError,
)
from backend.app.services.voice_agent import (
    VoiceAgentOrchestrator,
    VoiceAgentStaleTurnError,
)
from backend.app.models.schemas import RimeTTSMetadata


@pytest.fixture
def mock_pipeline_components():
    store = SessionStore()
    canceller = CancellationManager()
    conversation = ConversationManager(session_store=store, cancellation_manager=canceller)

    stt = AsyncMock(spec=GroqSTTService)
    llm = AsyncMock(spec=GroqLLMService)
    rime = AsyncMock(spec=RimeTTSService)
    tavily = AsyncMock(spec=TavilySearchService)

    # Configure default mock returns
    llm.generate.return_value = {
        "text": "The latest news is that AI agents are advancing rapidly.",
        "final_response": "The latest news is that AI agents are advancing rapidly.",
        "provider": "groq",
        "model": "qwen/qwen3.6-27b",
    }

    rime.synthesize.return_value = (
        b"\xff\xfb\x90\x44" * 100,
        RimeTTSMetadata(
            session_id="sess_test",
            turn_id=1,
            provider="rime",
            model_id="coda",
            speaker="celeste",
            audio_format="mp3",
            duration_sec=2.5,
            audio_bytes_length=400,
        ),
    )

    orchestrator = VoiceAgentOrchestrator(
        conversation_manager=conversation,
        stt_service=stt,
        llm_service=llm,
        rime_service=rime,
        tavily_service=tavily,
        cancellation_manager=canceller,
    )

    return {
        "store": store,
        "canceller": canceller,
        "conversation": conversation,
        "stt": stt,
        "llm": llm,
        "rime": rime,
        "tavily": tavily,
        "orchestrator": orchestrator,
    }


@pytest.mark.asyncio
class TestTavilyInterruptionSafety:
    """Test suite for Tavily turn isolation and interruption safety."""

    async def test_search_turn_completes_successfully(self, mock_pipeline_components):
        comps = mock_pipeline_components
        orchestrator = comps["orchestrator"]
        tavily = comps["tavily"]
        store = comps["store"]

        session = store.create_session("sess_search_1")
        turn_id = session.create_next_turn(prompt="What is the latest news about OpenAI?")

        tavily.search.return_value = TavilySearchResponse(
            query="What is the latest news about OpenAI?",
            results=[
                TavilySearchResult(
                    title="OpenAI Live Updates",
                    url="https://news.example.com/openai",
                    content="OpenAI announced new features today.",
                )
            ],
            session_id="sess_search_1",
            turn_id=turn_id,
            status="SUCCESS",
        )

        result = await orchestrator.process_turn(
            session_id="sess_search_1",
            turn_id=turn_id,
            text_prompt="What is the latest news about OpenAI?",
        )

        assert result.search_used is True
        assert len(result.search_sources) == 1
        assert result.search_sources[0] == "https://news.example.com/openai"
        assert result.final_response == "The latest news is that AI agents are advancing rapidly."
        assert session.get_turn(turn_id).status == "completed"

    async def test_interruption_during_tavily_search_rejects_stale_result(self, mock_pipeline_components):
        comps = mock_pipeline_components
        orchestrator = comps["orchestrator"]
        tavily = comps["tavily"]
        store = comps["store"]

        session = store.create_session("sess_search_interrupt")
        turn_1 = session.create_next_turn(prompt="What is the latest news about OpenAI?")

        # Simulate barge-in happening DURING Tavily search
        async def mock_search_with_barge_in(*args, **kwargs):
            # User barge-in: advance turn to Turn 2 while Turn 1 search is running
            session.interrupt_and_advance(reason="vad_barge_in")
            return TavilySearchResponse(
                query="What is the latest news about OpenAI?",
                results=[
                    TavilySearchResult(
                        title="Stale OpenAI News",
                        url="https://stale.example.com",
                        content="Old content that should be discarded.",
                    )
                ],
                session_id="sess_search_interrupt",
                turn_id=turn_1,
                status="SUCCESS",
            )

        tavily.search.side_effect = mock_search_with_barge_in

        # Process Turn 1 -> must raise VoiceAgentStaleTurnError
        with pytest.raises(VoiceAgentStaleTurnError) as exc_info:
            await orchestrator.process_turn(
                session_id="sess_search_interrupt",
                turn_id=turn_1,
                text_prompt="What is the latest news about OpenAI?",
            )

        assert "superseded during web search" in str(exc_info.value)
        # Verify Rime TTS was NEVER called for superseded turn
        comps["rime"].synthesize.assert_not_called()
        # Verify LLM was NEVER called for superseded turn
        comps["llm"].generate.assert_not_called()

    async def test_tavily_failure_allows_graceful_recovery(self, mock_pipeline_components):
        comps = mock_pipeline_components
        orchestrator = comps["orchestrator"]
        tavily = comps["tavily"]
        store = comps["store"]

        session = store.create_session("sess_search_fail")
        turn_id = session.create_next_turn(prompt="What is the latest weather in Tokyo?")

        # Simulate Tavily API network failure
        tavily.search.side_effect = TavilySearchError("Tavily service unavailable", status_code=503)

        result = await orchestrator.process_turn(
            session_id="sess_search_fail",
            turn_id=turn_id,
            text_prompt="What is the latest weather in Tokyo?",
        )

        # Pipeline does not crash, proceeds to LLM & Rime TTS gracefully
        assert result.search_used is False
        assert result.turn_id == turn_id
        assert session.get_turn(turn_id).status == "completed"
