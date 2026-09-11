# Rime Voice Evidence & Real Acceptance Benchmark

**Project:** Voice AI Assistant with Interruption & Recovery  
**Hackathon:** DataForge 2026 Rime Hackathon  
**Primary TTS Provider:** Rime Labs (Ultra-Low Latency Conversational Voice Output)   
**Benchmark Artifact:** [demo/benchmark_results_phase15.json](demo/benchmark_results_phase15.json)  
**Recorded:** 2026-09-07 (UTC)  

---

## 1. Hard Voice Problem
**Interruption & Recovery in Conversational Voice AI**

When a user interrupts an ongoing AI voice response and changes their request, conventional voice assistants suffer from:
1. **Audio Bleed / Monologue Lag:** Obsolete speech continues playing for hundreds of milliseconds after the user begins speaking.
2. **Context Corruption / State Desynchronization:** Outdated background inferences and tool executions from interrupted turns complete late, pollute conversational context, and overwrite subsequent user intents.
3. **Double Spoken Output:** Late results from superseded turns are synthesized and spoken out of order.

Solving this requires millisecond-level client-side audio stopping, thread-safe asynchronous task cancellation, and strict turn-isolated stale-result rejection.

---

## 2. Core Technical Claim
> **“When a user interrupts an active voice response and changes their request, obsolete Rime speech stops promptly, obsolete work/results are not spoken, and the final response corresponds only to the latest request.”**

---

## 3. Real Acceptance Benchmark (20 Trials)

To rigorously validate this claim without fabrication or estimation, a standalone 20-trial acceptance benchmark suite was executed using live Rime TTS and live Groq LLM services.

### Benchmark Structure:
- **10 Normal Interruption Trials:** Realistic queries where user barge-in interrupts active Rime speech/generation and redirects the request (e.g. *“What is the weather like in Delhi?”* $\rightarrow$ *“Actually, tell me about Mumbai instead.”*).
- **10 Stress Interruption Trials:** Realistic queries with a controlled local test fixture delay (0.35s artificial sleep in local async test worker) giving $T_1$ a realistic opportunity to finish late after $T_2$ has already become authoritative (e.g. *“Search for a flight from New York to Tokyo.”* $\rightarrow$ *“Actually, make that London.”*).

---

## 4. Measured Benchmark Results

| Metric | Benchmark Result | Specification Target | Status |
| :--- | :---: | :---: | :---: |
| **Total Trials Executed** | **20 / 20** | 20 | **100% Complete** |
| **Recovery Success Rate** | **100.0%** (20/20) | $\ge 95\%$ | **PASSED** |
| **Latest-Turn Correctness Rate** | **100.0%** (20/20) | $100\%$ | **PASSED** |
| **Stale Responses Spoken** | **0** | 0 | **PASSED (Zero Leaks)** |
| **Stale Audio Events to Playback** | **0** | 0 | **PASSED (Zero Leaks)** |
| **Post-Interruption Usability** | **100.0%** | $100\%$ | **PASSED** |

### Application-Level Interruption-to-Playback-Stop Latency:
- **Minimum:** `0.068 ms`
- **Maximum:** `0.196 ms`
- **Arithmetic Mean:** `0.116 ms`
- **Median ($P_{50}$):** `0.113 ms`
- **95th Percentile ($P_{95}$):** `0.181 ms`

> [!NOTE]
> Latency was recorded using high-resolution monotonic local clock timestamps (`time.perf_counter()`) at the application layer:
> $$\text{INTERRUPTION\_DETECTED} \longrightarrow \text{stopCurrentAudio()} \longrightarrow \text{AUDIO\_STOPPED}$$
> This reflects deterministic in-memory execution and state-machine transitions (buffer purge, source detachment, queue clearing), not acoustic transducer latency.

---

## 5. Complete 20-Trial Results Table

| Trial # | Type | $T_1$ Prompt | $T_2$ Revision | Stop Latency (ms) | $T_1$ Cancelled | Stale Detected | Recovered |
| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **01** | NORMAL | What is the weather like in Delhi? | Actually, tell me about Mumbai instead. | 0.196 ms | YES | NO (0) | **PASS** |
| **02** | NORMAL | What is the population of Tokyo? | Wait, tell me the population of Paris instead. | 0.068 ms | YES | NO (0) | **PASS** |
| **03** | NORMAL | How far is the moon from Earth? | Hold on, how far is Mars from Earth? | 0.099 ms | YES | NO (0) | **PASS** |
| **04** | NORMAL | Who wrote the play Hamlet? | Actually, who wrote Macbeth? | 0.102 ms | YES | NO (0) | **PASS** |
| **05** | NORMAL | What is the speed of light? | Wait, what is the speed of sound? | 0.078 ms | YES | NO (0) | **PASS** |
| **06** | NORMAL | What is the tallest mountain in the world? | Actually, what is the second tallest mountain? | 0.095 ms | YES | NO (0) | **PASS** |
| **07** | NORMAL | What is the currency of Japan? | Sorry, what is the currency of South Korea? | 0.089 ms | YES | NO (0) | **PASS** |
| **08** | NORMAL | Who painted the Mona Lisa? | Actually, who painted Starry Night? | 0.095 ms | YES | NO (0) | **PASS** |
| **09** | NORMAL | What is the capital of Australia? | Wait, what is the capital of Canada? | 0.109 ms | YES | NO (0) | **PASS** |
| **10** | NORMAL | What is the freezing point of water in Fahrenheit? | Actually, in Celsius? | 0.134 ms | YES | NO (0) | **PASS** |
| **11** | STRESS | Search for a flight from New York to Tokyo. | Actually, make that London. | 0.125 ms | YES | NO (0) | **PASS** |
| **12** | STRESS | Calculate compound interest for $10k over 5 yrs. | Actually, calculate it for three years. | 0.137 ms | YES | NO (0) | **PASS** |
| **13** | STRESS | Summarize the plot of Pride and Prejudice. | Wait, summarize Sense and Sensibility instead. | 0.127 ms | YES | NO (0) | **PASS** |
| **14** | STRESS | Find Italian restaurants in downtown SF. | Actually, find Japanese restaurants in Seattle. | 0.133 ms | YES | NO (0) | **PASS** |
| **15** | STRESS | Translate hello my friend into German. | Wait, translate it into Spanish instead. | 0.139 ms | YES | NO (0) | **PASS** |
| **16** | STRESS | Give me the top three tourist spots in Rome. | Actually, give me the top three in Florence. | 0.181 ms | YES | NO (0) | **PASS** |
| **17** | STRESS | Explain quantum computing in simple terms. | Wait, explain cloud computing instead. | 0.070 ms | YES | NO (0) | **PASS** |
| **18** | STRESS | List ingredients for making pasta carbonara. | Actually, make it pasta arrabbiata. | 0.126 ms | YES | NO (0) | **PASS** |
| **19** | STRESS | What are the rules of chess? | Wait, what are the rules of checkers? | 0.099 ms | YES | NO (0) | **PASS** |
| **20** | STRESS | Recommend a good science fiction book. | Actually, recommend a classic mystery novel. | 0.116 ms | YES | NO (0) | **PASS** |

---

## 6. Exact Runtime Configuration

- **Rime API Endpoint:** `https://users.rime.ai/v1/rime-tts`
- **Rime Model ID:** `coda` (Flagship ultra-expressive conversational model)
- **Rime Speaker / Voice:** `celeste`
- **Rime Language:** `en`
- **Rime Audio Format:** `mp3` (`audio/mpeg`)
- **Rime Transport:** REST HTTP/1.1 POST; the application also exposes a full-duplex WebSocket gateway
- **Groq STT Model:** `whisper-large-v3` (`https://api.groq.com/openai/v1/audio/transcriptions`)
- **Groq LLM Model:** `qwen/qwen3.6-27b` (`https://api.groq.com/openai/v1/chat/completions`)
- **Google Gemini:** `0 calls` (Enforced & Audited)

---

## 7. Provider Call Audit

| Provider | Service | Total Benchmark Calls |
| :--- | :--- | :---: |
| **Rime Labs** | Text-to-Speech (`/v1/rime-tts`) | **20** |
| **Groq** | Chat Completions (`qwen/qwen3.6-27b`) | **52** *(includes rate-limit backoff attempts)* |
| **Groq** | Whisper STT (`whisper-large-v3`) | **0** |
| **Google Gemini** | LLM Inferences | **0** |

---

## 8. Correctness Guarantee & Invariant Enforcement

Our architecture enforces the fundamental axiom:
> **“Cancellation is best-effort; stale-result rejection is the correctness guarantee.”**

1. **Two-Phase Turn Validation Gate:** Every asynchronous worker verifies `session.validate_turn(turn_id)` before initiating synthesis/generation and immediately prior to committing results to history or playback.
2. **Deterministic Playback Queue Flush:** When barge-in occurs, `stopCurrentAudio()` synchronously invalidates the active audio buffer, flushes all pending audio chunks, and revokes active Blob URLs.
3. **Session Isolation:** Interruption and turn advancement on one session cannot affect concurrent independent sessions.

---

## 9. Reproducibility Instructions

To reproduce the exact 20-trial benchmark independently:

1. Ensure valid credentials in `backend/.env`:
   ```bash
   RIME_API_KEY=your_rime_api_key
   GROQ_API_KEY=your_groq_api_key
   ```
2. Run the automated benchmark script:
   ```bash
   python scripts/run_real_benchmark.py
   ```
3. Inspect output summary on stdout and the generated machine-readable artifact:
   ```bash
   Get-Content demo/benchmark_results_phase15.json
   ```

---

## 10. Limitations & Scope Notes

- **Acoustic vs. Application Latency:** The measured stop latency (0.068 ms – 0.196 ms) represents the application-level execution time of stopping the playback state machine, flushing audio queues, and clearing media buffers. Hardware speaker acoustic output latency is governed by physical OS audio drivers.
- **Controlled Test Fixtures:** The artificial 0.35s delay in stress trials is strictly a local test fixture to simulate asynchronous delay and verify race-condition immunity. It does not represent provider API latency.
- **Cancellation Semantics:** No provider-side cancellation is claimed; all cancellation and stale-result rejections are enforced authoritatively by the application's Turn and Cancellation Managers.
- **Provider/model drift:** The benchmark records the provider configuration used on 2026-09-07. Defaults or upstream availability may change; inspect `backend/app/config.py` and the generated JSON artifact before comparing a future run.
