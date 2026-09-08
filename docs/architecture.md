# System Architecture & Concurrency Design

**Project:** Voice AI Assistant with Interruption & Recovery  
**Hackathon:** DataForge 2026 Rime Hackathon  
**Phase:** Phase 16 — Tavily Web Search & Speech Input Diagnostics Fix  
**Status:** COMPLETE (Tavily Search Service -> Turn-Aware Search Tooling -> Stale Search Rejection -> Audio Capture Stream Sharing -> 177 Backend Tests & 56 Frontend Tests Passing)

---

## 1. Architecture Overview

The system is designed as a low-latency, full-duplex conversational voice assistant with **first-class turn invalidation and race-condition immunity**. Interruption in this system is not treated merely as a client-side UI pause; it is an orchestrated state transition propagated across the entire asynchronous pipeline.

### End-to-End Conceptual Flow:
```
Microphone Stream ──▶ Audio Input / VAD ──▶ STT Service ──▶ Turn Manager
                                                                │
                                                                ▼
Client Audio Playback ◀── Rime TTS API ◀── Response Stream ◀── LLM & Tools
```

### Full Concurrency & Interruption Architecture Diagram:
```mermaid
flowchart TD
    subgraph Client ["Client / Browser Context"]
        MIC["Microphone Audio Stream"]
        SPK["Audio Playback Queue / AudioContext"]
        VAD["Client VAD / Barge-In Detector"]
        WS_C["WebSocket Client"]
    end

    subgraph Server_Boundary ["FastAPI Real-Time Gateway"]
        WS_S["WebSocket Endpoint (/ws/voice)"]
        AUTH["Session & Auth Authenticator"]
    end

    subgraph Core_Engine ["Orchestration & State Engine"]
        SM["Session Manager"]
        TM["Turn Manager (Active Turn ID: N)"]
        CM["Cancellation Manager (Task Abort Hub)"]
        SRG["Stale Result Guard (Turn ID Gate)"]
        EVT["Event Logger & Latency Auditor"]
    end

    subgraph Async_Workers ["Asynchronous Worker Pipelines"]
        STT["Streaming STT (Groq/Whisper)"]
        LLM["LLM Stream (Groq / Gemini)"]
        TOOL["Async Tool Execution Layer"]
        RIME["Rime TTS Streaming API"]
    end

    %% Audio and Interruption Flow
    MIC -->|Audio Frames| WS_C
    VAD -->|Barge-In Signal| WS_C
    WS_C <-->|Bi-directional WebSocket| WS_S
    WS_S --> AUTH --> SM

    %% Normal Turn Ingestion
    SM -->|Audio Payload| STT
    STT -->|Transcribed Text| TM
    TM -->|Increment to Turn N| SM
    TM -->|Dispatch Turn N| LLM
    LLM -->|Tool Calls (Turn N)| TOOL
    TOOL -->|Tool Result (Turn N)| SRG
    LLM -->|Text Tokens (Turn N)| SRG

    %% TTS Dispatch
    SRG -->|Validated Text Stream| RIME
    RIME -->|Audio Chunks (Turn N)| WS_S
    WS_S -->|Stream Audio Payload| SPK

    %% Interruption Action
    VAD -.->|1. Interruption Event (Turn N+1)| TM
    TM -.->|2. Invalidate Turn N| CM
    CM -.->|3. Signal Abort (Best-Effort)| LLM
    CM -.->|4. Signal Abort (Best-Effort)| TOOL
    CM -.->|5. Signal Abort (Best-Effort)| RIME
    CM -.->|6. Stop Playback Cmd| WS_S
    WS_S -.->|7. Clear Buffer Instantly| SPK
    SRG -.->|8. Drop Any Residual Turn N Payload| EVT
```

---

## 2. Component Responsibilities

| Component | Primary Inputs | Primary Outputs | Core Responsibilities | What It MUST NOT Do |
| :--- | :--- | :--- | :--- | :--- |
| **1. Audio Input** | Raw user PCM mic stream | Binary audio frames / VAD events | Streams audio frames, performs client-side voice activity detection. | Must NOT buffer indefinitely or block on network. |
| **2. STT Service** | Binary audio stream chunks | Transcribed text & finalized phrases | Real-time speech transcription. | Must NOT mutate session conversation history. |
| **3. Session Manager** | WebSocket connection, turn events | Active session context | Coordinates session lifecycle, connections, and persistent history. | Must NOT dispatch unvalidated audio to playback. |
| **4. Turn Manager** | Finalized STT prompts / barge-in cues | Monotonic `turn_id`, active turn state | Creates and tracks `active_turn_id`. Declares superseded turns obsolete. | Must NOT allow older turn IDs to become active. |
| **5. LLM Service** | Prompt context with `turn_id` | Token stream with tagged `turn_id` | Streaming token generation, tool call emission. Supports task abort signals. | Must NOT write directly to client WebSocket. |
| **6. Tool Execution** | Tool call arguments with `turn_id` | Structured tool outputs with `turn_id` | Asynchronous external execution (APIs, searches, computations). | Must NOT bypass the Stale Result Guard. |
| **7. Rime TTS Service** | Text phrases with `turn_id` | Streaming PCM/WAV audio chunks | Generates ultra-low latency expressive speech using Rime Labs API. | Must NOT stream audio for superseded turns. |
| **8. Playback Manager** | Audio chunks from server | Audio hardware output buffer | Manages browser audio buffer queue; instantly clears buffers on abort. | Must NOT play out-of-order or invalidated chunks. |
| **9. Cancellation Manager** | Turn invalidation trigger | `asyncio.Task` abort signals | Best-effort cancellation of running LLM, tool, and TTS tasks. | Must NOT be solely relied on for system correctness. |
| **10. Stale Result Guard** | Any worker result with `turn_id` | Validated result OR discard signal | Verifies `worker.turn_id == session.active_turn_id`. Discards stale items. | Must NOT allow stale items to modify conversation state. |
| **11. Event Logger** | System events, timestamps, errors | Structured JSON observability logs | Instruments latency, logs turn transitions and metrics for audit. | Must NOT log secrets or API keys. |

---

## 3. Request / Turn Lifecycle

Every interaction turn adheres to a strict monotonic progression:

1. **Turn Generation ($N$):** When user speech begins, Turn Manager assigns $N = \text{active\_turn\_id} + 1$.
2. **Context Binding:** All subsequent asynchronous tasks (STT, LLM inference, Tool calls, TTS requests) receive an immutable `TurnContext(session_id, turn_id=N)`.
3. **Execution Pipeline:** Asynchronous workers process turn $N$ concurrently.
4. **Validation Gate:** As each chunk/result resolves, it passes through the **Stale Result Guard**.
5. **Turn Completion:** When turn $N$ finishes speaking without interruption, it transitions to `COMPLETED` and is appended to conversation history.

---

## 4. Interruption Lifecycle & Race Scenarios

### Scenario A: Normal Mid-Speech Interruption
```
User speaks T1 ──▶ Assistant speaks T1 via Rime ──▶ User speaks T2 (Barge-In)
                                                          │
   ┌──────────────────────────────────────────────────────┴──────────────────────────────────┐
   ▼                                                      ▼                                  ▼
[Turn Manager]                                   [Cancellation Hub]                 [Client Playback]
active_turn_id := 2                              Abort Task(T1)                     Clear AudioBuffer
T1 is OBSOLETE                                   Best-effort cancel                 Audio stops <250ms
   │
   ▼
[Process T2 Cleanly] ──▶ [Synthesize T2 via Rime] ──▶ [Play T2 Audio Stream]
```

### Scenario B: Hard Race Condition (Late-Returning Tool Execution)
```
Turn 1: Ingests "Search flight NY to Tokyo" (Starts slow async tool, latency = 3000ms)
  │
  ├─▶ [t = 1200ms] User Interrupts: "Change to London" (Turn 2 created: active_turn_id := 2)
  │     │
  │     ├─▶ Cancellation Manager attempts to cancel Turn 1 Tool task.
  │     └─▶ Turn 2 starts processing London query cleanly.
  │
  ├─▶ [t = 2800ms] Turn 1 Tool FINISHES LATE and returns: {flights: ["Tokyo 10:00AM"]}
  │     │
  │     ▼
  │   [Stale Result Guard Gate]
  │   Check: worker.turn_id (1) == session.active_turn_id (2)
  │   Verdict: FALSE (Mismatch)
  │   Action: DISCARD RESULT IMMEDIATELY & LOG STALE_RESULT_DISCARDED
  │   Effect: Tokyo flight details NEVER reach LLM, NEVER reach Rime TTS, NEVER spoken.
  │
  └─▶ [t = 3100ms] Turn 2 completes London query -> Rime speaks London flight details.
```

---

## 5. Cancellation Strategy

The system implements a **4-tier cancellation model**:

### Tier 1: Client Audio Cutoff (Immediate)
- Upon user barge-in detection, the client immediately pauses audio playback and flushes its `AudioContext` queue.
- WebSocket sends an `INTERRUPT` control packet to the server.

### Tier 2: Generation Cancellation (Async Best-Effort)
- The server `CancellationManager` maintains a registry of active `asyncio.Task` instances for the current turn.
- Calling `cancel()` on the LLM token generator stops ongoing token consumption from Groq/Gemini.

### Tier 3: Tool Execution Cancellation (Async Best-Effort)
- Long-running async tool executions (HTTP queries, retrievals) are cancelled via standard Python asyncio task cancellation.

### Tier 4: Logical Invalidation (Correctness Guarantee)
- Physical cancellation cannot always stop an in-flight network packet or external API invocation immediately.
- **Fundamental Architectural Axiom:**  
  > **"Cancellation is best-effort; stale-result rejection is the correctness guarantee."**  
  Even if an obsolete task runs to completion, its output is strictly suppressed by the Stale Result Guard.

---

## 6. Turn / Version Strategy

1. **State Location:** `active_turn_id` is maintained in `SessionState` on the server.
2. **Monotonic Progression:** `active_turn_id` is strictly integer-incremented ($1, 2, 3, \dots$).
3. **Propagation:** Every `Task`, token, tool call, audio packet, and WebSocket payload encapsulates `turn_id`.
4. **Validation Invariant:**  
   $$\text{Output Allowed} \iff \text{payload.turn\_id} = \text{session.active\_turn\_id}$$
5. **Late Worker Handling:** If `worker.turn_id < session.active_turn_id`, the payload is silently dropped and audited.

---

## 7. Stale Result Protection

The **Stale Result Guard** acts as an mandatory gate before four critical boundaries:
1. **State Mutation Boundary:** Stale tool or LLM completions cannot append messages to session context.
2. **LLM Input Boundary:** Stale tool results cannot trigger secondary LLM reasoning loops.
3. **Rime TTS Dispatch Boundary:** Stale text sentences cannot be sent to the Rime API for voice generation.
4. **WebSocket Streaming Boundary:** Stale audio binary chunks cannot be transmitted to the client playback buffer.

---

## 8. Rime Audio Lifecycle & Playback Pipeline

Rime is the **primary spoken-output provider**. In Phase 5 & 6, the system implements a unified audio generation and browser playback pipeline:

### End-to-End Pipeline Dataflow:
```
Backend Execution Flow:
Text Payload
   │
   ▼
[Pre-Synthesis Turn Validation: session.validate_turn(turn_id)]
   │
   ▼
RimeTTSService (Async HTTP POST to https://users.rime.ai/v1/rime-tts)
   │
   ▼
[Post-Synthesis Turn Invariant Check: session.validate_turn(turn_id)]
   ├── If active ──▶ Binary Audio Response (HTTP 200 with X-Turn-ID, X-Session-ID headers)
   └── If stale  ──▶ Audio Discarded Immediately (HTTP 409 Conflict)

Frontend Playback Flow:
Binary Audio Response
   │
   ▼
AudioPlaybackManager (frontend/src/services/audio.js)
   │ [Pre-Play Turn Validation: item.turnId === activeTurnId]
   ▼
HTML5 / Web Audio Element
   │
   ▼
Speaker Output to User
```

### Playback Finite State Machine:
```
                  ┌───────────────┐
                  │     IDLE      │
                  └───────┬───────┘
                          │ (playAudio / enqueueAudio)
                          ▼
                  ┌───────────────┐
                  │    LOADING    │
                  └───────┬───────┘
                          │ (Turn invalidated during prep) ──▶ DISCARDED ──▶ IDLE
                          ▼
                  ┌───────────────┐
                  │     READY     │
                  └───────┬───────┘
                          │ (audio.play())
                          ▼
                  ┌───────────────┐
                  │    PLAYING    │
                  └───────┬───────┘
                          │
            ┌─────────────┴─────────────┐
            │ (Audio finished)          │ (Interruption / stopCurrentAudio)
            ▼                           ▼
      ┌───────────┐               ┌───────────┐
      │ COMPLETED │               │ STOPPING  │
      └─────┬─────┘               └─────┬─────┘
            │                           │
            │                           ▼
            │                     ┌───────────┐
            │                     │  STOPPED  │
            │                     └─────┬─────┘
            │                           │
            └─────────────┬─────────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │     IDLE      │
                  └───────────────┘
```

### Interruption & Immediate Flush Mechanism:
When user barge-in occurs in subsequent phases:
1. Client-side speech/VAD detector immediately triggers `stopCurrentAudio('barge_in')`.
2. Active audio element is instantly paused, `src` is detached, and audio queue is flushed.
3. Turn sequence is advanced to $N+1$, permanently rendering any late-arriving audio for Turn $N$ stale and unplayable.
4. Structured event `AUDIO_STOP_REQUESTED` and `AUDIO_STOPPED` are emitted for latency auditing.

---

## 9. Error and Failure Handling

- **STT Transcription Error:** Emits non-blocking error event; prompts user for clarification without crashing session.
- **LLM Provider Timeout / Rate Limit:** Falls back gracefully or emits speech-synthesized error message for the *active turn*.
- **Rime TTS Service Degradation:** Logs error event and maintains session state.
- **Obsolete Turn Failure:** If an obsolete task ($T_1$) throws an exception or network error after $T_2$ has started, the exception is intercepted and discarded without propagating to $T_2$.
- **Network WebSocket Drop:** Session state is retained in memory for reconnect window; all in-flight tasks paused.

---

## 10. Observability & Structured Event Logging

All lifecycle transitions emit structured JSON events to the latency auditor:

```json
{
  "timestamp_ms": 1725667200150,
  "session_id": "sess_8f3a12",
  "turn_id": 2,
  "event_type": "INTERRUPTION_DETECTED",
  "component": "TurnManager",
  "status": "SUCCESS",
  "details": {
    "interrupted_turn_id": 1,
    "interruption_reason": "client_barge_in"
  }
}
```

### 17 Core Observability Events:
`TURN_CREATED`, `INTERRUPTION_DETECTED`, `TURN_INVALIDATED`, `AUDIO_STOP_REQUESTED`, `AUDIO_STOPPED`, `LLM_STARTED`, `LLM_CANCELLED`, `TOOL_STARTED`, `TOOL_CANCELLED`, `TOOL_RESULT_DISCARDED`, `RIME_TTS_STARTED`, `RIME_TTS_READY`, `RIME_AUDIO_STARTED`, `RIME_AUDIO_STOPPED`, `STALE_RESULT_DISCARDED`, `TURN_COMPLETED`, `ERROR`.

---

## 11. Security Boundaries

- **Zero Client Credential Exposure:** Frontend client never receives `RIME_API_KEY`, `GROQ_API_KEY`, or `GEMINI_API_KEY`.
- **Environment Isolation:** Backend `.env` remains strictly git-ignored; settings are loaded through safe Pydantic configuration.
- **Log Sanitization:** Event logger masks all token strings, authorization headers, and personal identifiers.

---

## 12. Planned Implementation Mapping

| Repository Path | Architectural Role | Phase Mapping |
| :--- | :--- | :--- |
| `backend/app/config.py` | Configuration & safe credential loading | Phase 1 & 8 (Complete) |
| `backend/app/models/schemas.py` | Pydantic event, turn, interruption, STT, LLM, TTS, agent & conversation schemas | Phase 4, 5, 7, 8, 9, 10 & 11 (Complete) |
| `backend/app/core/session.py` | `VoiceSession` & `SessionStore` state manager | Phase 4, 9 & 11 (Complete) |
| `backend/app/services/rime_tts.py` | Rime Labs genuine TTS integration | Phase 5 (Complete) |
| `backend/app/api/voice.py` | Voice session, STT, LLM, TTS, Agent, Interruption & Cancellation REST endpoints | Phase 4, 5, 7, 8, 9, 10, 11, 12 & 13 (Complete) |
| `backend/app/services/stt.py` | Speech-to-text service provider (Groq/Whisper) | Phase 7 (Complete) |
| `backend/app/services/llm.py` | LLM text generation provider (Groq) | Phase 8 (Complete) |
| `backend/app/services/conversation.py` | `ConversationManager` orchestrator service | Phase 9, 11 & 13 (Complete) |
| `backend/app/services/voice_agent.py` | `VoiceAgentOrchestrator` E2E pipeline service with task registration & cancellation | Phase 10 & 13 (Complete) |
| `backend/app/api/websocket.py` | Real-time full-duplex Voice WebSocket gateway & `VoiceWebSocketManager` | Phase 14 (Complete) |
| `frontend/src/services/websocket.js` | Browser `VoiceWebSocketClient` streaming manager | Phase 14 (Complete) |
| `frontend/src/services/vad.js` | Browser-native Voice Activity Detection & Interruption Detector | Phase 11 (Complete) |
| `frontend/src/services/recorder.js` | Push-to-talk microphone audio recording service | Phase 7 (Complete) |
| `frontend/src/components/VoiceButton.jsx` | Push-to-talk microphone, Barge-in trigger & VAD UI controls | Phase 7, 10 & 11 (Complete) |
| `frontend/src/` | Full Voice Assistant Client (Web Audio API, VAD & Playback Manager) | Phase 6, 7, 10, 11, 12 & 14 (Complete) |
| `backend/app/core/cancellation.py` | `CancellationManager` & Task Abort Hub indexed by `(session_id, turn_id)` | Phase 13 (Complete) |
| `tests/` | Unit, integration, interruption, cancellation, and WebSocket test suite | Phase 14 Complete: 136 backend tests, 37 frontend tests |

---

## 13. Phase 13: Background Task Cancellation Mechanics

### Core Invariant:
> **"Cancellation is best-effort; stale-result rejection is the correctness guarantee."**

### Task Ownership:
Every asynchronous, turn-bound operation is registered with `CancellationManager` under ownership tuple:
```python
(session_id: str, turn_id: int) -> TrackedTask(task_id, task_type, task, created_at_ms, is_cancelled)
```

### Lifecycle & Cancellation Progression:
1. **Task Registration:** When an async turn worker begins (`agent_turn`, `llm`, `tts`), it registers `asyncio.current_task()` with `cancellation_manager.register_task(...)`.
2. **Interruption Trigger:** When a user barge-in occurs or a new turn is created ($T_N \rightarrow T_{N+1}$), `interrupt_and_advance_turn()` executes `cancellation_manager.cancel_obsolete_tasks(session_id, active_turn_id=N+1)`.
3. **Asyncio Cancellation Propagation:** In-flight tasks belonging to $T_N$ receive `task.cancel()`, causing pending `await httpx.AsyncClient` calls to raise `asyncio.CancelledError`.
4. **Clean Resource Teardown:** Open HTTP client connections and temporary resources are immediately closed in `finally:` blocks without swallowing errors or corrupting session history.
5. **Stale Validation Fallback:** If a provider request finishes right as cancellation arrives, downstream state commit gates check `session.validate_turn(turn_id)`. Because $T_N$ is superseded, the stale result is dropped and $T_{N+1}$ remains authoritative.
6. **Task Unregistration:** Automatic `task.add_done_callback()` purges completed/cancelled tasks from memory, preventing memory leaks.

### Provider Cancellation Limitations:
- **Local Task Cancellation:** Closes the local client socket/HTTP stream immediately, saving local CPU and event loop resources.
- **Remote Provider Handling:** We do NOT claim that remote server-side generation (on Groq or Rime GPUs) is terminated after disconnect unless explicit provider protocol guarantees exist. The local client connection is safely severed.

---

## 14. Architectural Decisions & Known Limitations

### Recorded Architectural Decisions:
- **Decision 1 (Monotonic Turn ID):** Use a single integer `active_turn_id` per session to eliminate ambiguity.
- **Decision 2 (Turn Context Propagation):** Every async task and data chunk must carry `turn_id`.
- **Decision 3 (Best-Effort Cancellation):** Cancellation is best-effort to free server resources.
- **Decision 4 (Mandatory Stale Rejection):** Stale-result rejection is the absolute guarantee for user-visible correctness.
- **Decision 5 (Single Active Speaker):** Only the active turn may dispatch audio to client playback.
- **Decision 6 (Rime Primary TTS):** Rime Labs is the primary spoken output provider.
- **Decision 7 (Server-Side Isolation):** All credentials and AI provider SDKs remain backend-contained.
- **Decision 8 (Simplicity & Reproducibility):** Direct monolithic FastAPI backend with async primitives rather than complex distributed broker infrastructure.
- **Decision 9 (Asyncio Task Ownership):** Track in-flight tasks indexed by `(session_id, turn_id)` in `CancellationManager` with automatic cleanup callbacks.

### Known Limitations:
- Remote LLM/TTS provider servers may continue token generation internally after client disconnects; client-side disconnection and stale result rejection guarantee zero application state corruption.
- Rapid multi-barge-in (<100ms apart) will result in multiple rapid turn increments; handled safely by monotonic ordering and obsolete task cancellation.

