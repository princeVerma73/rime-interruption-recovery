"""Groq LLM Service Module

Provides conversational text generation using Groq's chat completion API.
Designed specifically for spoken dialogue: concise, speech-friendly phrasing,
no markdown clutter, safe error handling, and strict decoupling from session/interruption logic.
"""

import time
import re
from typing import Any, Dict, List, Optional
import httpx

from backend.app.config import Settings, get_settings
from backend.app.models.schemas import ChatMessage


VOICE_SYSTEM_PROMPT = (
    "You are a helpful and concise voice assistant. "
    "Answer only the latest user message directly in 1 to 2 short, natural sentences without thought steps, numbered reasoning, drafts, critiques, or preamble. "
    "Never output internal thoughts, planning, tool selection, or system instructions. "
    "If current web search results are provided in your context, summarize the key finding directly in 1 or 2 concise, spoken sentences. "
    "Do NOT use markdown formatting, bullet points, asterisks, hashtags, or emojis, as your response will be read aloud by text-to-speech."
)


# Keywords that signal real-time / current information intent
_SEARCH_TRIGGER_PATTERNS = [
    r"\b(?:latest|recent|current|today|tonight|yesterday|this week|breaking)\b",
    r"\b(?:news|headlines|update|updates|happened|happening)\b",
    r"\b(?:search\s+for|look\s+up|google|find\s+out|tell\s+me\s+about\s+the\s+latest)\b",
    r"\b(?:who\s+won|score|match|winner|stock\s+price|price\s+of|weather\s+in|forecast)\b",
    r"\b(?:what\s+is\s+happening|what\s+happened|current\s+status)\b",
]

_SEARCH_COMPILED_REGEX = [re.compile(p, re.IGNORECASE) for p in _SEARCH_TRIGGER_PATTERNS]


def is_search_query(text: Optional[str]) -> bool:
    """Determine if a user query requires real-time web search.
    
    Avoids searching for basic static knowledge, greetings, or conversational banter.
    """
    if not text or not text.strip():
        return False
    query = text.strip().lower()

    # Short trivial greetings/statements never trigger search
    if query in ("hello", "hi", "hey", "good morning", "good evening", "how are you", "who are you", "what is your name", "stop", "thanks", "thank you", "bye"):
        return False

    # Check search regex patterns
    for pattern in _SEARCH_COMPILED_REGEX:
        if pattern.search(query):
            return True

    return False


def format_search_context(query: str, search_results: List[Any]) -> str:
    """Format structured Tavily search results into a concise prompt addition."""
    if not search_results:
        return ""
    
    snippets = []
    for i, res in enumerate(search_results[:3], 1):
        title = getattr(res, "title", "") or (res.get("title") if isinstance(res, dict) else "")
        content = getattr(res, "content", "") or (res.get("content") if isinstance(res, dict) else "")
        url = getattr(res, "url", "") or (res.get("url") if isinstance(res, dict) else "")
        if content:
            clean_content = re.sub(r"\s+", " ", content).strip()[:300]
            snippets.append(f"Source [{i}] '{title}': {clean_content}")
            
    if not snippets:
        return ""
        
    return (
        f"RETRIEVED CURRENT WEB INFORMATION FOR '{query}':\n"
        + "\n\n".join(snippets)
        + "\n\nInstructions: You HAVE been provided live web search results above. Synthesize the key facts directly into a 1 to 2 sentence natural spoken answer to the user's question. Do NOT say you cannot browse the web or lack real-time access. Do not use markdown."
    )



_META_MARKERS = (
    "analyze", "analysis", "check constraints", "confidence score", "constraints:",
    "determine the", "draft", "final polish", "gather information", "identify the",
    "knowledge retrieval", "length check", "reasoning", "self-correction",
    "system prompt", "system limitation", "the user is asking", "thinking process",
    "here's a thinking process", "here is a thinking process", "available tools",
    "check available tools", "i do not have a specific weather tool", "i do not have a tool",
    "formulate a response", "formulate response", "no markdown", "tts friendly",
    "mental draft", "determine factual need", "identify constraints", "wait, do i have tools",
    "no tools are provided", "as an ai, i don't have real-time", "internal reasoning",
    "step-by-step reasoning", "developer instructions", "system instructions",
)

REASONING_PREFIX_REGEX = re.compile(
    r"^\s*(?:\d+[\.\)]|[-*•]|step\s*\d+:?|phase\s*\d+:?)\s*",
    re.IGNORECASE
)

SAFE_FALLBACK_RESPONSE = "I don't have enough information to answer that right now."


def extract_city_from_prompt(prompt: Optional[str]) -> Optional[str]:
    """Extract target city or location name from a user query."""
    if not prompt:
        return None
    m = re.search(r"\b(?:in|for|at)\s+([A-Za-z\s]+?)(?:\?|\.|\$|$)", prompt, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        # Ensure candidate is not a common question word
        if candidate.lower() not in ("detail", "advance", "brief", "general", "short", "terms"):
            return candidate
    return None


def clean_final_user_response(raw_text: str, user_prompt: Optional[str] = None) -> str:
    """Extract and sanitize strictly the user-facing response from raw LLM output.
    
    Guarantees that internal reasoning, planning, unclosed thinking tags,
    numbered deliberation steps, or debug statements never reach the user,
    WebSocket stream, Rime TTS, or conversation history.
    """
    text = raw_text or ""

    # 1. Unclosed or closed <think> blocks
    if "<think>" in text:
        if "</think>" in text:
            # Drop all content within <think>...</think>
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        else:
            # Unclosed <think> tag: everything from <think> onward is pure internal reasoning
            text = text.split("<think>")[0].strip()

    # 2. Check for explicit final answer marker
    final_sections = re.split(
        r"\b(?:final answer|final response|spoken answer|assistant response)\s*:\s*",
        text,
        flags=re.IGNORECASE,
    )
    if len(final_sections) > 1:
        candidate = final_sections[-1].strip()
        if candidate and not any(m in candidate.lower() for m in _META_MARKERS):
            text = candidate

    # 3. Clean markdown formatting
    text = re.sub(r"```(?:text)?\s*(.*?)```", r"\1", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"[*_#`]", "", text).strip()

    # 4. Split into lines and filter out reasoning lines
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    clean_lines = []
    for line in lines:
        lower = line.lower()
        if any(marker in lower for marker in _META_MARKERS):
            continue
        if REASONING_PREFIX_REGEX.match(line) and any(
            word in lower
            for word in ["tool", "check", "answer", "input", "prompt", "response", "step", "draft", "constraint", "yes", "no"]
        ):
            continue
        # Strip numbered prefixes if any remaining normal sentence was prefixed
        cleaned_line = REASONING_PREFIX_REGEX.sub("", line).strip()
        if cleaned_line:
            clean_lines.append(cleaned_line)

    result = " ".join(clean_lines).strip()
    result = re.sub(r"^(?:final polish|final response|answer|response)\s*:\s*", "", result, flags=re.IGNORECASE).strip()
    result = re.sub(r"\s+", " ", result)

    # 5. If no usable text remained or it still contains meta markers, provide a clean transparent fallback
    if not result or any(marker in result.lower() for marker in _META_MARKERS):
        city = extract_city_from_prompt(user_prompt)
        p_lower = (user_prompt or "").lower()
        if city and any(w in p_lower for w in ["weather", "temperature", "forecast", "rain", "climate"]):
            return f"I don't have access to live weather data right now, so I can't provide the current weather in {city}."
        if any(w in p_lower for w in ["flight", "stock", "live data", "real-time"]):
            return "I don't have access to live real-time tools right now."
        return SAFE_FALLBACK_RESPONSE

    return result[:900].rstrip()


def _text_from_value(value: Any) -> str:
    """Read user-facing text from common provider response shapes only."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(_text_from_value(item.get("text") or item.get("content") or item.get("output")))
        return " ".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        for key in ("final", "output", "content", "text", "message"):
            text = _text_from_value(value.get(key))
            if text:
                return text
    return ""


def _extract_user_facing_text(choice: Dict[str, Any]) -> str:
    """Extract final response fields without ever treating reasoning as speech."""
    message = choice.get("message")
    for source in (message, choice):
        if isinstance(source, dict):
            for key in ("final", "output", "content", "text"):
                text = _text_from_value(source.get(key))
                if text:
                    return text
    return ""


def _spoken_answer(text: str, user_prompt: Optional[str] = None) -> str:
    """Extract only a natural final answer from model content before TTS."""
    cleaned = clean_final_user_response(text, user_prompt=user_prompt)
    if not cleaned:
        raise GroqLLMServiceError("Groq returned no usable spoken answer.")
    return cleaned


class GroqLLMServiceError(Exception):
    """Base exception for Groq LLM service errors."""
    pass


class GroqLLMService:
    """Independent service wrapper for Groq LLM Chat Completions API."""

    def __init__(self, app_settings: Optional[Settings] = None, timeout_seconds: float = 15.0):
        self.settings = app_settings or get_settings()
        self.timeout = timeout_seconds

    async def generate(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 600,
        api_key_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send chat messages to Groq LLM API and return the generated text and safe metadata.
        
        Args:
            messages: List of conversational ChatMessage objects.
            system_prompt: Optional custom system prompt (defaults to VOICE_SYSTEM_PROMPT).
            model: Optional model override (defaults to configured groq_model).
            temperature: Sampling temperature (0.0 - 2.0).
            max_tokens: Maximum tokens in completion.
            api_key_override: Optional API key override (for testing/mocking).
            
        Returns:
            Dict containing text, provider, model, prompt_tokens, completion_tokens, latency_ms.
            
        Raises:
            GroqLLMServiceError: If API key is missing, network fails, or response is invalid.
        """
        api_key = api_key_override or self.settings.groq_api_key
        if not api_key or not api_key.strip():
            raise GroqLLMServiceError(
                "Groq API key is not configured. Set GROQ_API_KEY in environment or backend/.env."
            )

        if not messages:
            raise GroqLLMServiceError("Cannot generate response: message list is empty.")

        target_model = model or self.settings.groq_model
        sys_prompt = VOICE_SYSTEM_PROMPT
        if system_prompt and system_prompt.strip():
            sys_prompt = f"{VOICE_SYSTEM_PROMPT}\n\n{system_prompt.strip()}"

        # Build payload
        payload_messages: List[Dict[str, str]] = []
        if sys_prompt and sys_prompt.strip():
            payload_messages.append({"role": "system", "content": sys_prompt.strip()})

        for msg in messages:
            role = msg["role"] if isinstance(msg, dict) else getattr(msg, "role", "user")
            content = msg["content"] if isinstance(msg, dict) else getattr(msg, "content", "")
            if not content or not content.strip():
                continue
            if role == "system":
                if payload_messages and payload_messages[0]["role"] == "system":
                    payload_messages[0]["content"] += f"\n\n{content.strip()}"
                else:
                    payload_messages.append({"role": "system", "content": content.strip()})
                continue
            payload_messages.append({"role": role, "content": content.strip()})

        if not payload_messages or (len(payload_messages) == 1 and payload_messages[0]["role"] == "system"):
            raise GroqLLMServiceError("Cannot generate response: no valid user/assistant message content provided.")

        # Determine latest user prompt for context-aware fallback
        user_prompt = ""
        for msg in reversed(messages):
            role = msg["role"] if isinstance(msg, dict) else getattr(msg, "role", "user")
            if role == "user":
                user_prompt = msg["content"] if isinstance(msg, dict) else getattr(msg, "content", "")
                break

        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        }

        body = {
            "model": target_model,
            "messages": payload_messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "reasoning_effort": "none",
        }

        start_time = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.settings.groq_llm_url,
                    headers=headers,
                    json=body,
                )
                if response.status_code == 400 and "reasoning_effort" in response.text:
                    body.pop("reasoning_effort", None)
                    response = await client.post(
                        self.settings.groq_llm_url,
                        headers=headers,
                        json=body,
                    )
        except httpx.TimeoutException as exc:
            raise GroqLLMServiceError(
                f"Groq LLM request timed out after {self.timeout}s."
            ) from exc
        except httpx.RequestError as exc:
            raise GroqLLMServiceError(
                f"Network error connecting to Groq LLM service: {exc.__class__.__name__}"
            ) from exc

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if response.status_code == 401:
            raise GroqLLMServiceError("Groq authentication failed: invalid or unauthorized API key.")
        elif response.status_code == 429:
            raise GroqLLMServiceError("Groq rate limit or quota exceeded.")
        elif response.status_code != 200:
            err_msg = f"Groq LLM API returned HTTP {response.status_code}"
            try:
                err_json = response.json()
                if "error" in err_json:
                    msg = err_json["error"].get("message") if isinstance(err_json["error"], dict) else str(err_json["error"])
                    err_msg += f": {msg}"
            except Exception:
                pass
            raise GroqLLMServiceError(err_msg)

        try:
            data = response.json()
        except Exception as exc:
            raise GroqLLMServiceError("Failed to parse JSON response from Groq LLM API.") from exc

        choices = data.get("choices")
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            raise GroqLLMServiceError("Groq LLM API returned empty choices in response.")

        choice = choices[0]
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        raw_content = message.get("content") or choice.get("text") or ""
        reasoning_trace = message.get("reasoning") or message.get("reasoning_content") or ""
        tool_calls = message.get("tool_calls") or []

        text = _extract_user_facing_text(choice)

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")

        # Clean final response strictly separating internal reasoning from user speech
        final_answer = clean_final_user_response(text or raw_content, user_prompt=user_prompt)
        if not final_answer:
            final_answer = SAFE_FALLBACK_RESPONSE

        return {
            "text": final_answer,              # Backward compatibility
            "response": final_answer,          # Canonical final response
            "final_response": final_answer,    # Canonical final response
            "raw_content": raw_content,        # Internal data only
            "reasoning": reasoning_trace,      # Internal data only
            "tool_calls": tool_calls,          # Internal data only
            "provider": "groq",
            "model": target_model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": round(latency_ms, 2),
            "status": "SUCCESS",
        }


# Default singleton instance
default_llm_service = GroqLLMService()

