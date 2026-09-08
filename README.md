# Voice AI Assistant with Interruption & Recovery
*DataForge 2026 Rime Hackathon Submission*

## 1. Project Overview & Name
**Project Name:** Voice AI Assistant with Interruption & Recovery  
**Primary TTS Provider:** Rime Labs (Ultra-low latency, expressive conversational voice output)

---

## 2. Target User
Users engaging in high-velocity, real-time spoken interactions (e.g., dispatch operators, interactive customer assistance, hands-free field specialists, and voice-first personal productivity workflows) where pauses, corrections, mid-sentence topic shifts, and interruptions are natural and frequent.

---

## 3. The Problem
Conventional voice assistants suffer from high turn rigidity and "barge-in" failure modes:
- **Speech Pipeline Lag:** When a user interrupts an ongoing AI monologue, current systems often continue rendering or streaming stale TTS audio for hundreds of milliseconds.
- **Stale Computation / Race Conditions:** Stale LLM inferences and pending tool calls from invalidated turns continue in the background and pollute subsequent context or trigger outdated responses.
- **Cognitive Friction:** Users are forced to listen to irrelevant answers or explicitly wait for completion before correcting their prompt.

---

## 4. Why Voice is Necessary
Voice communication is intrinsically bidirectional, continuous, and dynamic. Unlike text chat where turns are atomic and discrete, human conversation relies on real-time feedback cues, fast barge-ins, and conversational repairs. A natural voice assistant must support fluid turn invalidation with millisecond-level responsiveness.

---

## 5. Core Technical Claim
> **"When a user interrupts an ongoing voice response and changes their request, the system promptly stops obsolete Rime speech, invalidates/cancels obsolete work, prevents stale results from being spoken, and responds only to the latest request."**

---

## 6. Architecture & Concurrency Model *(Detailed in [docs/architecture.md](file:///c:/INTERNSHIP/rime-interruption-recovery/docs/architecture.md))*

```
Microphone Stream ──▶ Audio Input / VAD ──▶ STT Service ──▶ Turn Manager (Active Turn ID: N)
                                                                │
                                                                ▼
Client Playback ◀── Rime TTS API ◀── Stale Guard Buffer ◀── LLM & Async Tools
```

### Key Concurrency Principles:
1. **Monotonic Turn Isolation:** Every session maintains a strictly increasing `active_turn_id`. All asynchronous tasks, LLM tokens, tool responses, and Rime TTS chunks carry an immutable `turn_id`.
2. **Four-Tier Cancellation:** 
   - *Tier 1 (Client):* Instant audio hardware buffer flush upon barge-in.
   - *Tier 2 (Generation):* `asyncio.Task` cancellation on LLM streams.
   - *Tier 3 (Tools):* In-flight async tool call abort.
   - *Tier 4 (Logical):* Immediate invalidation of superseded turn state.
3. **Core Architectural Axiom:**
   > **"Cancellation is best-effort; stale-result rejection is the correctness guarantee."**  
   Even if an obsolete worker completes late, the Stale Result Guard rejects any payload where `worker.turn_id != active_turn_id`.
4. **Primary Rime TTS Spoken Output:** Expressive, ultra-low latency voice rendering managed through strict lifecycle states (`GENERATING` $\rightarrow$ `READY` $\rightarrow$ `PLAYING` $\rightarrow$ `COMPLETED` / `CANCELLED` / `STOPPED`).

---

## 7. Current Development Status
- [x] **Phase 1: Problem Definition, Project Audit & Safe Foundation** *(Completed)*
- [x] **Phase 2: Acceptance Test, Success Metrics & Evaluation Specification** *(Completed)*
- [x] **Phase 3: System Architecture & Concurrency Design** *(Completed)*
- [x] **Phase 4: FastAPI Backend Foundation** *(Completed)*
- [x] **Phase 5: Real Rime TTS Integration** *(Completed)*
- [x] **Phase 6: Rime Audio Delivery & Playback Pipeline** *(Completed)*
- [x] **Phase 7: Speech-to-Text Integration** *(Completed)*
  - Server-side `GroqSTTService` integrating Groq Whisper (`whisper-large-v3`) via multipart audio upload.
  - Backend `POST /api/voice/transcribe` endpoint with session and turn invariant enforcement.
  - Client-side `MicrophoneRecorder` service capturing microphone input with `MediaRecorder` / `getUserMedia`.
  - Push-to-Talk (PTT) interactive UI button with real-time state feedback and prompt pre-fill.
  - 100% automated test pass rate across backend (39 tests) and frontend (10 tests).
- [x] **Phase 8: Groq LLM Integration** *(Completed)*
  - Server-side `GroqLLMService` integrating Groq chat completions with active preview model `qwen/qwen3.6-27b` (Groq Preview model).
  - Voice-optimized system prompt generating concise, speech-ready sentences without markdown clutter.
  - Backend `POST /api/voice/respond` endpoint with session validation, pre-call turn gating, and critical post-completion stale turn rejection (HTTP 409 Conflict if barge-in advances the turn during generation).
  - 100% automated test pass rate across backend (53 tests with 0 live API calls) and frontend (10 tests).
  - Exactly ONE real Groq LLM integration verification call executed (`qwen/qwen3.6-27b`, single verification roundtrip latency: 1,269.66 ms; not a benchmark). Zero Gemini or Rime calls.
  - *Status:* **Phase 8 — Groq LLM integrated with turn validation; interruption detection and full duplex recovery pending.**
- [x] **Phase 9: Conversation / Session Manager** *(Completed)*
  - Robust in-memory `VoiceSession` and `SessionStore` with monotonic turn ID lifecycle (`CREATED` -> `ACTIVE` -> `COMPLETED` / `INTERRUPTED` / `CANCELLED` / `STALE` / `SUPERSEDED` / `FAILED`).
  - Strict turn validation invariant: `validate_turn(turn_id) == True` strictly if `turn_id == active_turn_id` and turn is active.
  - Authoritative conversation history management with deterministic stale-result rejection (stale/superseded worker writes are rejected and never enter conversation history).
  - High-level `ConversationManager` orchestrator service for turn creation, interruption, completion, and LLM context formatting.
  - Concurrency-safe thread synchronization preventing race conditions between worker completions and user interruptions.
- [x] **Phase 10: End-to-End Voice Agent Orchestration** *(Completed)*
  - Server-side `VoiceAgentOrchestrator` (`backend/app/services/voice_agent.py`) coordinating the full pipeline: Speech/Audio $\rightarrow$ Groq Whisper STT $\rightarrow$ Conversation State $\rightarrow$ Groq LLM $\rightarrow$ Turn Gating $\rightarrow$ Rime Labs TTS $\rightarrow$ Browser Playback.
  - Multi-phase monotonic turn invariants enforcing state validity and discarding stale intermediate outputs across STT, LLM, and TTS boundaries.
  - Backend orchestration endpoints: `POST /api/voice/agent/process-audio`, `POST /api/voice/agent/process-text`, and `POST /api/voice/agent/chat`.
  - Frontend voice interface supporting 7 distinct agent states: `IDLE`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `SYNTHESIZING`, `PLAYING`, and `ERROR`.
  - 100% automated test pass rate across backend (90 tests with 0 live API calls) and frontend (10 tests).
  - Exactly ONE genuine live end-to-end voice verification run successfully executed (STT $\rightarrow$ LLM $\rightarrow$ Rime TTS $\rightarrow$ `demo/live_agent_response.mp3`). Zero Gemini calls.
- [x] **Phase 11: Real-Time Interruption & Barge-In Detection** *(Completed)*
  - Browser-native Voice Activity Detection (`VoiceActivityDetector` in `frontend/src/services/vad.js`) using Web Audio API / RMS energy analysis.
  - Configurable detection parameters: RMS energy threshold (`0.02`), sustained speech duration (`150ms` debounce against clicks/keystrokes), silence duration (`700ms`), and event debounce (`400ms`).
  - Browser microphone constraints enabled: `echoCancellation: true`, `noiseSuppression: true`, `autoGainControl: true`.
  - Assistant playback awareness: triggers `INTERRUPTION_DETECTED` when user speech begins while assistant is `PLAYING`, `THINKING`, or `SYNTHESIZING`; emits `SPEECH_STARTED` when assistant is `IDLE`.
  - Server-side atomic turn transition (`interrupt_and_advance` on `VoiceSession` and `POST /api/voice/session/{session_id}/interrupt` endpoint): marks previous turn as `INTERRUPTED` with metadata and immediately makes new monotonic turn `ACTIVE`.
  - Frontend UI state: added `INTERRUPTING` state, visual feedback in `SpeakingIndicator` and `Status`, manual barge-in button, and continuous VAD mode.
  - 100% automated test pass rate: 96 backend tests passing and 22 frontend tests passing (0 live API calls).
  - *Scope Note:* Speech detection and monotonic turn transition are implemented. Physical Rime audio stopping (Phase 12) and LLM/tool task cancellation (Phase 13) are deliberately scheduled for upcoming phases.
- [x] **Phase 12: Immediate Rime Audio Output Cancellation** *(Completed)*
  - Immediate audio hardware buffer cutoff (`this.audio.pause()`, `this.audio.currentTime = 0`, `removeAttribute('src')`, `audio.load()`) upon barge-in detection.
  - Turn-aware audio validation (`AudioPlaybackManager` in `frontend/src/services/audio.js`): discards stale audio where `turnId < activeTurnId`.
  - Playback queue purge: obsolete pending chunks from interrupted turns are discarded and associated Blob object URLs are revoked (`URL.revokeObjectURL`) to prevent memory leaks.
  - Race condition immunity: post-`playPromise` re-validation prevents late resolution or spurious `play` events from restarting superseded audio.
  - Deterministic UI transition: `PLAYING` $\rightarrow$ `INTERRUPTING` $\rightarrow$ `LISTENING` without stuck states or audio leakage.
  - 100% automated test pass rate: 96 backend tests passing and 31 frontend tests passing (0 live API calls).
- [x] **Phase 13: LLM & Background Task Cancellation Layer** *(Completed)*
  - Thread-safe `CancellationManager` (`backend/app/core/cancellation.py`) maintaining task ownership indexed by `(session_id, turn_id)`.
  - Automatic task registration for active turn pipelines (`agent_turn`, LLM inference, TTS synthesis).
  - Immediate `asyncio.Task.cancel()` dispatch on obsolete tasks upon user interruption ($T_N \rightarrow T_{N+1}$) or turn advance without blocking the event loop.
  - Clean `asyncio.CancelledError` propagation and resource teardown (releasing `httpx.AsyncClient` connections and unregistering tasks via auto `add_done_callback`).
  - Strict preservation of the foundational invariant: *"Cancellation is best-effort; stale-result rejection is the correctness guarantee."* Stale turn outputs cannot mutate state or history.
  - 100% automated test pass rate: 116 backend tests passing and 31 frontend tests passing (0 live API calls).
- [x] **Phase 14: Real-Time Full-Duplex WebSocket Layer** *(Completed)*
  - Real-time bidirectional WebSocket gateway (`/api/voice/ws/{session_id}` and `/api/voice/ws`) supporting streaming audio frames and structured JSON events.
  - Standardized event lifecycle (`CONNECT_ACK`, `SPEECH_STARTED`, `AUDIO_DATA`, `SPEECH_ENDED`, `INTERRUPTION_DETECTED`, `TURN_STARTED`, `TRANSCRIPT`, `THINKING`, `AUDIO_STARTED`, `AUDIO_STOP`, `TURN_INTERRUPTED`, `TURN_CANCELLED`, `TURN_COMPLETED`, `ERROR`, `DISCONNECT`).
  - Strict pre-send monotonic turn validation gate (`session.validate_turn(turn_id)`): prevents stale audio chunks and superseded turn events from transmitting over the WebSocket.
  - Instant barge-in signaling: forwards VAD interruption cues over the socket, emits `AUDIO_STOP` to client, atomically advances turn sequence, and cancels obsolete in-flight tasks.
  - Browser WebSocket client (`VoiceWebSocketClient` in `frontend/src/services/websocket.js`) routing realtime streaming events directly to UI state and `AudioPlaybackManager`.
  - 100% automated test pass rate: 136 backend tests passing and 37 frontend tests passing (0 live API calls).
- [x] **Phase 15: Real Acceptance Benchmark & Evidence** *(Completed)*
  - Standalone 20-trial repeatable acceptance benchmark suite (`scripts/run_real_benchmark.py`) executed against genuine Rime Labs TTS (`coda` / `celeste` / `mp3`) and Groq LLM (`qwen/qwen3.6-27b`).
  - Executed 10 Normal Interruption Trials and 10 Stress Interruption Trials (with controlled local asynchronous delay fixtures).
  - **100.0% Recovery Success Rate** (20/20 trials recovered seamlessly).
  - **100.0% Latest-Turn Correctness Rate** (20/20 trials responded strictly to the latest revision).
  - **0 Stale Responses Spoken** and **0 Stale Audio Events Reaching Playback**.
  - **Application-Level Interruption-to-Playback-Stop Latency:** Mean `0.116 ms`, Median `0.113 ms`, P95 `0.181 ms` (Min `0.068 ms`, Max `0.196 ms`).
  - [x] **Phase 16: Tavily Web Search & Speech Input Diagnostics Fix** *(Completed)*
  - **Tavily Web Search Integration:** Server-side `TavilySearchService` (`backend/app/services/tavily_search.py`) providing real-time factual web search for current events, news, sports scores, and live data.
  - **Search Intent Detection:** Heuristic query classifier (`is_search_query` in `backend/app/services/llm.py`) selectively triggering web search only when current/latest information is needed, avoiding search overhead for static knowledge.
  - **Search Interruption & Stale-Result Protection:** Tavily operations are bound to `(session_id, turn_id)` with two-phase turn validation (`session.validate_turn`). If an interruption occurs mid-search, the search results are discarded immediately and never reach the LLM or Rime TTS.
  - **Speech Input Capture & STT Diagnostic Fix:** Diagnosed and resolved the root cause of speech capture failure (microphone stream contention and `getUserMedia` re-negotiation latency clipping the first 300-600ms of speech upon VAD onset). Harmonized audio constraints (`echoCancellation: true`, `noiseSuppression: true`, `autoGainControl: true`) and enabled direct stream sharing from VAD to `MicrophoneRecorder` with zero-latency speech capture.
  - **Full Test Suite & Build Verification:** 177 backend automated tests passing (100%), 56 frontend automated tests passing (100%), clean Vite production build.

---

## 8. Getting Started & Running Locally

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm
- Valid API keys (`RIME_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `TAVILY_API_KEY`)

### Backend Setup & Run
1. Configure environment template:
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env with your API credentials (kept server-side & git-ignored)
   ```
2. Install Python dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Run automated backend test suite (0 external API calls):
   ```bash
   python -m pytest tests/ -v
   ```
4. Start FastAPI server locally:
   ```bash
   uvicorn backend.app.main:app --reload --port 8000
   ```
5. Check health probe:
   ```bash
   curl http://127.0.0.1:8000/health
   # Returns: {"status": "ok"}
   ```

### Frontend Setup & Run
1. Install dependencies & run frontend tests:
   ```bash
   cd frontend
   npm install
   npm test
   ```
2. Start Vite development server:
   ```bash
   npm run dev
   ```
3. Open browser at `http://localhost:5173`.
4. Interact with the voice assistant:
   - **Record Voice (Mic PTT):** Click the Push-to-Talk button, grant microphone permission, speak your prompt, and click to finish recording. Audio is sent to `/api/voice/transcribe` and the transcript is populated directly into the input field.
   - **Advance Turn:** Atomically advances monotonic turn $N \rightarrow N+1$.
   - **Synthesize & Play Rime Audio:** Fetches genuine Rime audio from `/api/voice/tts` and streams via `AudioPlaybackManager`.
   - **Stop / Interrupt Speech:** Immediately halts active audio output, detaches media stream, and logs the interruption event.


