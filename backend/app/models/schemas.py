"""Typed Pydantic Data Models & Schemas

Defines structured models for session management, turn tracking,
event logging, conversation context, STT, LLM, TTS, and end-to-end voice agent orchestration payloads.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TurnStatus(str, Enum):
    """Lifecycle states for a conversational turn."""
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    STALE = "stale"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class HealthResponse(BaseModel):
    """Deterministic health check response model."""
    status: str = Field(default="ok", description="Service health status")


class RootStatusResponse(BaseModel):
    """Root service status response model."""
    service: str = "Rime Voice AI Assistant"
    status: str = "online"
    phase: int = 11
    rime_configured: bool = False


class ChatMessage(BaseModel):
    """Conversational message representation with optional turn attribution."""
    role: str = Field(..., description="Message author role (system, user, assistant)")
    content: str = Field(..., description="Message text content")
    turn_id: Optional[int] = Field(default=None, description="Associated turn ID when created")
    timestamp_ms: Optional[int] = Field(default=None, description="Timestamp in milliseconds")
    status: Optional[str] = Field(default="active", description="Message status (active, stale, discarded)")


class LLMRequest(BaseModel):
    """Payload for LLM response generation."""
    session_id: Optional[str] = Field(default=None, description="Optional target session ID for turn gating")
    turn_id: Optional[int] = Field(default=None, description="Optional associated turn ID")
    messages: List[ChatMessage] = Field(..., min_length=1, description="List of conversational messages")
    system_prompt: Optional[str] = Field(default=None, description="Optional custom system instruction")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=256, ge=1, le=4096, description="Max tokens to generate")


class LLMResponse(BaseModel):
    """Structured response model for LLM generation."""
    session_id: Optional[str] = Field(default=None, description="Associated session ID")
    turn_id: Optional[int] = Field(default=None, description="Associated turn ID")
    text: str = Field(..., description="Generated text response")
    response: Optional[str] = Field(default=None, description="Canonical final user-facing response")
    final_response: Optional[str] = Field(default=None, description="Canonical final user-facing response")
    provider: str = Field(default="groq", description="LLM Provider name")
    model: str = Field(..., description="LLM Model used")
    prompt_tokens: Optional[int] = Field(default=None, description="Prompt token count if provided")
    completion_tokens: Optional[int] = Field(default=None, description="Completion token count if provided")
    latency_ms: Optional[float] = Field(default=None, description="Generation latency in milliseconds")
    status: str = Field(default="SUCCESS", description="Outcome status")


class TranscriptionResponse(BaseModel):
    """Structured response model for Speech-to-Text transcription."""
    session_id: Optional[str] = Field(default=None, description="Associated session ID")
    turn_id: Optional[int] = Field(default=None, description="Associated turn ID")
    text: str = Field(..., description="Transcribed speech text")
    provider: str = Field(default="groq", description="STT Provider name")
    model: str = Field(..., description="STT Model used")
    status: str = Field(default="SUCCESS", description="Transcription status")


class RimeTTSRequest(BaseModel):
    """Payload for TTS generation request."""
    session_id: str = Field(..., description="Target session ID")
    turn_id: int = Field(..., ge=1, description="Associated turn ID")
    text: str = Field(..., min_length=1, description="Text string to synthesize into speech")
    model_id: Optional[str] = Field(default=None, description="Optional Rime model ID override (e.g. 'coda')")
    speaker: Optional[str] = Field(default=None, description="Optional speaker voice override (e.g. 'celeste')")
    audio_format: Optional[str] = Field(default=None, description="Audio format (e.g. 'mp3', 'wav')")
    lang: Optional[str] = Field(default=None, description="Language code (e.g. 'en')")


class RimeTTSMetadata(BaseModel):
    """Structured metadata describing synthesized speech."""
    session_id: str = Field(..., description="Associated session ID")
    turn_id: int = Field(..., description="Associated turn ID")
    provider: str = Field(default="rime", description="TTS Provider name")
    model_id: str = Field(..., description="Rime model ID used")
    speaker: str = Field(..., description="Rime speaker voice used")
    audio_format: str = Field(..., description="Audio format (mp3, wav)")
    audio_bytes_length: int = Field(..., ge=0, description="Length of synthesized audio binary in bytes")
    status: str = Field(default="SUCCESS", description="Synthesis outcome status")


class TurnContext(BaseModel):
    """Immutable context tagging every asynchronous task with session and turn identity."""
    session_id: str = Field(..., description="Unique identifier for the active conversation session")
    turn_id: int = Field(..., ge=1, description="Monotonically increasing turn sequence identifier")


class VoiceTurn(BaseModel):
    """Represents a single conversational turn within a session."""
    turn_id: int = Field(..., ge=1, description="Monotonic turn ID")
    prompt: Optional[str] = Field(default=None, description="Transcribed user prompt for this turn")
    status: str = Field(default="active", description="Turn status: created, active, completed, interrupted, cancelled, stale, superseded, or failed")
    created_at_ms: int = Field(..., description="Turn start timestamp in epoch milliseconds")
    completed_at_ms: Optional[int] = Field(default=None, description="Turn completion timestamp in epoch milliseconds")
    interrupted_at_ms: Optional[int] = Field(default=None, description="Turn interruption timestamp in epoch milliseconds")
    assistant_response: Optional[str] = Field(default=None, description="Committed assistant response text")
    error: Optional[str] = Field(default=None, description="Error message if turn failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata for turn tracking")


class VoiceSessionInfo(BaseModel):
    """Session summary model exposed via API."""
    session_id: str = Field(..., description="Unique session identifier")
    active_turn_id: int = Field(..., ge=0, description="Currently active turn ID (0 if uninitiated)")
    is_active: bool = Field(default=True, description="Whether the session is active and accepting turns")
    turn_count: int = Field(default=0, description="Total turns initiated in this session")
    message_count: int = Field(default=0, description="Total messages in session history")
    status: str = Field(default="active", description="Lifecycle state of the session")
    created_at_ms: Optional[int] = Field(default=None, description="Session creation timestamp in epoch milliseconds")
    updated_at_ms: Optional[int] = Field(default=None, description="Session last updated timestamp in epoch milliseconds")


class ConversationContextResponse(BaseModel):
    """Structured response containing conversational history formatted for LLM context."""
    session_id: str = Field(..., description="Associated session ID")
    active_turn_id: int = Field(..., description="Currently active turn ID")
    is_active: bool = Field(default=True, description="Session active state")
    messages: List[ChatMessage] = Field(default_factory=list, description="Authoritative message history")


class VoiceAgentTextRequest(BaseModel):
    """Payload to trigger end-to-end voice agent processing from text."""
    session_id: Optional[str] = Field(default=None, description="Target session ID (auto-created if omitted)")
    turn_id: Optional[int] = Field(default=None, description="Optional turn ID (advances monotonic turn if omitted)")
    text: str = Field(..., min_length=1, description="User prompt text")
    system_prompt: Optional[str] = Field(default=None, description="Optional custom system instruction")
    speaker: Optional[str] = Field(default=None, description="Optional Rime speaker override")
    model_id: Optional[str] = Field(default=None, description="Optional Rime model ID override")
    audio_format: Optional[str] = Field(default="mp3", description="Desired audio output format")


class VoiceAgentResponse(BaseModel):
    """Structured response metadata from end-to-end voice agent orchestration."""
    session_id: str = Field(..., description="Associated session ID")
    turn_id: int = Field(..., description="Associated monotonic turn ID")
    user_prompt: str = Field(..., description="Transcribed or submitted user prompt")
    assistant_text: str = Field(..., description="Generated assistant response text")
    response: Optional[str] = Field(default=None, description="Canonical final user-facing response")
    final_response: Optional[str] = Field(default=None, description="Canonical final user-facing response")
    llm_provider: str = Field(default="groq", description="LLM provider name")
    llm_model: str = Field(..., description="LLM model identifier")
    tts_provider: str = Field(default="rime", description="TTS provider name")
    tts_model: str = Field(..., description="Rime TTS model used")
    tts_speaker: str = Field(..., description="Rime TTS speaker voice used")
    audio_format: str = Field(default="mp3", description="Audio binary format")
    audio_bytes_length: int = Field(..., ge=0, description="Size of synthesized audio in bytes")
    latency_ms: Optional[float] = Field(default=None, description="Total pipeline latency in milliseconds")
    status: str = Field(default="SUCCESS", description="Outcome status: SUCCESS, STALE_DISCARDED, or FAILED")


class EventPayload(BaseModel):
    """Structured observability and event logging schema."""
    timestamp_ms: int = Field(..., description="Timestamp in milliseconds")
    session_id: str = Field(..., description="Associated session ID")
    turn_id: int = Field(..., description="Associated turn ID")
    event_type: str = Field(..., description="Event type matching architectural schema")
    component: str = Field(..., description="Component emitting the event")
    status: str = Field(default="SUCCESS", description="Execution status: SUCCESS, FAILED, or DISCARDED")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional context or timing metadata")


class InterruptionEventRequest(BaseModel):
    """Payload to signal a real-time speech interruption / barge-in event."""
    turn_id: Optional[int] = Field(default=None, description="Optional specific turn ID to interrupt (defaults to active)")
    reason: Optional[str] = Field(default="barge_in", description="Reason for interruption: barge_in, manual, speech_detected")
    detection_source: Optional[str] = Field(default="vad", description="Source of detection: vad, client_vad, manual")
    advance_turn: Optional[bool] = Field(default=True, description="Whether to automatically advance to the next active turn")
    new_prompt: Optional[str] = Field(default=None, description="Optional user speech prompt starting the new turn")
    assistant_state: Optional[str] = Field(default=None, description="State of the assistant when interruption occurred (PLAYING, SYNTHESIZING, THINKING)")


class InterruptionEventResponse(BaseModel):
    """Structured response returned when an interruption is registered and turn transitioned."""
    session_id: str = Field(..., description="Associated session ID")
    previous_turn_id: int = Field(..., description="The superseded/interrupted turn ID")
    new_turn_id: int = Field(..., description="The newly active monotonic turn ID")
    status: str = Field(default="interrupted", description="Interruption status")
    timestamp_ms: int = Field(..., description="Epoch timestamp of interruption detection in milliseconds")
    reason: str = Field(default="barge_in", description="Reason for interruption")
    detection_source: str = Field(default="vad", description="Detection source")
    assistant_state: Optional[str] = Field(default=None, description="Assistant state at moment of detection")


class TavilySearchResult(BaseModel):
    """Structured search result item returned from Tavily API."""
    title: str = Field(..., description="Title of the web page / article")
    url: str = Field(..., description="Canonical source URL")
    content: str = Field(..., description="Relevant content snippet")
    score: Optional[float] = Field(default=None, description="Relevance ranking score")
    published_date: Optional[str] = Field(default=None, description="Publication timestamp if available")


class TavilySearchResponse(BaseModel):
    """Structured search response containing validated results."""
    query: str = Field(..., description="Cleaned search query string")
    results: List[TavilySearchResult] = Field(default_factory=list, description="Ranked list of search results")
    session_id: Optional[str] = Field(default=None, description="Associated session ID")
    turn_id: Optional[int] = Field(default=None, description="Associated turn ID")
    status: str = Field(default="SUCCESS", description="Execution outcome: SUCCESS, ERROR, or STALE_DISCARDED")
    latency_ms: Optional[float] = Field(default=None, description="Search round-trip duration in milliseconds")


