/**
 * Backend Voice API Client (JavaScript)
 * 
 * Communicates exclusively with the server-side FastAPI backend.
 * Zero credentials or API keys are required or exposed in the client.
 */

const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

const safeDecodeHeader = (val) => {
  if (!val) return '';
  try {
    return decodeURIComponent(val);
  } catch (e) {
    return val;
  }
};

export class VoiceApiClient {
  constructor(baseUrl = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  /**
   * Create or retrieve an isolated voice session.
   * @param {string} [sessionId]
   * @returns {Promise<{ session_id: string, active_turn_id: number, is_active: boolean, turn_count: number }>}
   */
  async createSession(sessionId = null) {
    const payload = sessionId ? { session_id: sessionId } : {};
    const res = await fetch(`${this.baseUrl}/voice/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(errData.error || `Failed to create session (${res.status})`);
    }
    return res.json();
  }

  /**
   * Advance the session to the next monotonic turn ID.
   * @param {string} sessionId 
   * @param {string} [prompt] 
   * @returns {Promise<{ session_id: string, active_turn_id: number, is_active: boolean, turn_count: number }>}
   */
  async createTurn(sessionId, prompt = null) {
    const payload = prompt ? { prompt } : {};
    const res = await fetch(`${this.baseUrl}/voice/session/${encodeURIComponent(sessionId)}/turn`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(errData.error || `Failed to create turn (${res.status})`);
    }
    return res.json();
  }

  /**
   * Request genuine Rime TTS synthesis from the backend for the given turn.
   * @param {Object} params
   * @returns {Promise<{ blob: Blob, headers: Object }>}
   */
  async synthesizeSpeech({ sessionId, turnId, text, modelId, speaker, audioFormat, lang }) {
    const payload = {
      session_id: sessionId,
      turn_id: turnId,
      text,
      model_id: modelId,
      speaker: speaker,
      audio_format: audioFormat,
      lang: lang,
    };

    const res = await fetch(`${this.baseUrl}/voice/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: res.statusText }));
      const error = new Error(errData.error || `TTS synthesis failed with status ${res.status}`);
      error.status = res.status;
      throw error;
    }

    const blob = await res.blob();
    const headers = {
      sessionId: res.headers.get('X-Session-ID'),
      turnId: parseInt(res.headers.get('X-Turn-ID') || String(turnId), 10),
      provider: res.headers.get('X-Provider'),
      modelId: res.headers.get('X-Model-ID'),
      speaker: res.headers.get('X-Speaker'),
      audioFormat: res.headers.get('X-Audio-Format'),
      audioBytesLength: parseInt(res.headers.get('X-Audio-Bytes-Length') || String(blob.size), 10),
    };

    return { blob, headers };
  }

  /**
   * Send speech audio to backend for Groq Whisper transcription.
   * @param {Object} params
   * @returns {Promise<{ session_id: string, turn_id: number, text: string, provider: string, model: string, status: string }>}
   */
  async transcribeAudio({ audioBlob, sessionId = null, turnId = null, language = 'en', model = null }) {
    const formData = new FormData();
    const filename = audioBlob.type.includes('mp4') ? 'recording.mp4' : audioBlob.type.includes('ogg') ? 'recording.ogg' : 'recording.webm';
    formData.append('file', audioBlob, filename);

    if (sessionId) formData.append('session_id', sessionId);
    if (turnId !== null && turnId !== undefined) formData.append('turn_id', String(turnId));
    if (language) formData.append('language', language);
    if (model) formData.append('model', model);

    const res = await fetch(`${this.baseUrl}/voice/transcribe`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: res.statusText }));
      const error = new Error(errData.error || `Audio transcription failed (${res.status})`);
      error.status = res.status;
      throw error;
    }

    return res.json();
  }

  /**
   * Execute full End-to-End Voice Agent pipeline with microphone speech audio.
   * STT -> Session -> LLM -> Rime TTS -> Spoken Audio
   * @param {Object} params
   * @param {Blob} params.audioBlob
   * @param {string} [params.sessionId]
   * @param {number} [params.turnId]
   * @param {string} [params.language]
   * @param {string} [params.systemPrompt]
   * @param {string} [params.speaker]
   * @param {string} [params.modelId]
   * @param {string} [params.audioFormat]
   * @returns {Promise<{ blob: Blob, headers: Object }>}
   */
  async processAgentAudio({
    audioBlob,
    sessionId = null,
    turnId = null,
    language = 'en',
    systemPrompt = null,
    speaker = null,
    modelId = null,
    audioFormat = 'mp3',
  }) {
    const formData = new FormData();
    const filename = audioBlob.type.includes('mp4') ? 'recording.mp4' : audioBlob.type.includes('ogg') ? 'recording.ogg' : 'recording.webm';
    formData.append('file', audioBlob, filename);

    if (sessionId) formData.append('session_id', sessionId);
    if (turnId !== null && turnId !== undefined) formData.append('turn_id', String(turnId));
    if (language) formData.append('language', language);
    if (systemPrompt) formData.append('system_prompt', systemPrompt);
    if (speaker) formData.append('speaker', speaker);
    if (modelId) formData.append('model_id', modelId);
    if (audioFormat) formData.append('audio_format', audioFormat);

    const res = await fetch(`${this.baseUrl}/voice/agent/process-audio`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: res.statusText }));
      const error = new Error(errData.detail || errData.error || `Voice agent processing failed (${res.status})`);
      error.status = res.status;
      throw error;
    }

    const blob = await res.blob();
    const headers = {
      sessionId: res.headers.get('X-Session-ID'),
      turnId: parseInt(res.headers.get('X-Turn-ID') || String(turnId || 1), 10),
      userTranscript: safeDecodeHeader(res.headers.get('X-User-Transcript')),
      assistantResponse: safeDecodeHeader(res.headers.get('X-Assistant-Response')),
      finalResponse: safeDecodeHeader(res.headers.get('X-Final-Response')) || safeDecodeHeader(res.headers.get('X-Assistant-Response')) || '',
      llmProvider: res.headers.get('X-LLM-Provider'),
      llmModel: res.headers.get('X-LLM-Model'),
      provider: res.headers.get('X-Provider'),
      modelId: res.headers.get('X-Model-ID'),
      speaker: res.headers.get('X-Speaker'),
      audioFormat: res.headers.get('X-Audio-Format') || 'mp3',
      audioBytesLength: parseInt(res.headers.get('X-Audio-Bytes-Length') || String(blob.size), 10),
      latencyMs: parseFloat(res.headers.get('X-Pipeline-Latency-Ms') || '0'),
      searchUsed: res.headers.get('X-Search-Used') === 'true',
      searchSources: safeDecodeHeader(res.headers.get('X-Search-Sources')) ? safeDecodeHeader(res.headers.get('X-Search-Sources')).split(', ').filter(Boolean) : [],
    };

    return { blob, headers };
  }

  /**
   * Execute full End-to-End Voice Agent pipeline from text prompt.
   * @param {Object} params
   * @returns {Promise<{ blob: Blob, headers: Object }>}
   */
  async processAgentText({
    text,
    sessionId = null,
    turnId = null,
    systemPrompt = null,
    speaker = null,
    modelId = null,
    audioFormat = 'mp3',
  }) {
    const payload = {
      text,
      session_id: sessionId,
      turn_id: turnId,
      system_prompt: systemPrompt,
      speaker,
      model_id: modelId,
      audio_format: audioFormat,
    };

    const res = await fetch(`${this.baseUrl}/voice/agent/process-text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: res.statusText }));
      const error = new Error(errData.detail || errData.error || `Voice agent text processing failed (${res.status})`);
      error.status = res.status;
      throw error;
    }

    const blob = await res.blob();
    const headers = {
      sessionId: res.headers.get('X-Session-ID'),
      turnId: parseInt(res.headers.get('X-Turn-ID') || String(turnId || 1), 10),
      userTranscript: safeDecodeHeader(res.headers.get('X-User-Transcript')) || text,
      assistantResponse: safeDecodeHeader(res.headers.get('X-Assistant-Response')),
      finalResponse: safeDecodeHeader(res.headers.get('X-Final-Response')) || safeDecodeHeader(res.headers.get('X-Assistant-Response')) || '',
      llmProvider: res.headers.get('X-LLM-Provider'),
      llmModel: res.headers.get('X-LLM-Model'),
      provider: res.headers.get('X-Provider'),
      modelId: res.headers.get('X-Model-ID'),
      speaker: res.headers.get('X-Speaker'),
      audioFormat: res.headers.get('X-Audio-Format') || 'mp3',
      audioBytesLength: parseInt(res.headers.get('X-Audio-Bytes-Length') || String(blob.size), 10),
      latencyMs: parseFloat(res.headers.get('X-Pipeline-Latency-Ms') || '0'),
      searchUsed: res.headers.get('X-Search-Used') === 'true',
      searchSources: safeDecodeHeader(res.headers.get('X-Search-Sources')) ? safeDecodeHeader(res.headers.get('X-Search-Sources')).split(', ').filter(Boolean) : [],
    };

    return { blob, headers };
  }

  /**
   * Signal a real-time interruption / barge-in event to the backend.
   * Atomically marks the previous turn as interrupted and advances to next active turn.
   * @param {Object} params
   * @param {string} params.sessionId
   * @param {number} [params.turnId]
   * @param {string} [params.reason]
   * @param {string} [params.detectionSource]
   * @param {boolean} [params.advanceTurn]
   * @param {string} [params.assistantState]
   * @returns {Promise<{ session_id: string, previous_turn_id: number, new_turn_id: number, status: string, timestamp_ms: number, reason: string, detection_source: string, assistant_state: string }>}
   */
  async interruptSession({
    sessionId,
    turnId = null,
    reason = 'barge_in',
    detectionSource = 'vad',
    advanceTurn = true,
    assistantState = null,
  }) {
    const payload = {
      turn_id: turnId,
      reason,
      detection_source: detectionSource,
      advance_turn: advanceTurn,
      assistant_state: assistantState,
    };

    const res = await fetch(`${this.baseUrl}/voice/session/${encodeURIComponent(sessionId)}/interrupt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: res.statusText }));
      const error = new Error(errData.error || `Interruption request failed (${res.status})`);
      error.status = res.status;
      throw error;
    }

    return res.json();
  }
}

export const defaultApiClient = new VoiceApiClient();

