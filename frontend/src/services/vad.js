/**
 * Voice Activity Detection (VAD) & Real-Time Interruption Detector Service
 * 
 * Provides browser-native audio energy analysis, sustained speech onset detection,
 * debounce against acoustic transients (clicks, keystrokes), and assistant-aware
 * barge-in / interruption triggering.
 * 
 * DataForge 2026 Rime Hackathon - Phase 11
 */

export const VADState = {
  INACTIVE: 'INACTIVE',
  LISTENING_SILENCE: 'LISTENING_SILENCE',
  SPEECH_DETECTED: 'SPEECH_DETECTED',
  INTERRUPTED: 'INTERRUPTED',
  ERROR: 'ERROR',
};

export const VADEventType = {
  VAD_STARTED: 'VAD_STARTED',
  VAD_STOPPED: 'VAD_STOPPED',
  SPEECH_STARTED: 'SPEECH_STARTED',
  SPEECH_ENDED: 'SPEECH_ENDED',
  INTERRUPTION_DETECTED: 'INTERRUPTION_DETECTED',
  ENERGY_UPDATED: 'ENERGY_UPDATED',
};

export const DEFAULT_VAD_CONFIG = {
  // RMS energy threshold for speech onset (0.0 to 1.0)
  // 0.01 is ~ -40 dBFS, responsive for clear voice detection across desktop/laptop mics
  energyThreshold: 0.01,

  // Minimum duration of continuous speech above threshold before triggering speech onset (ms)
  minSpeechDurationMs: 100,

  // Duration of continuous silence below threshold before declaring speech ended (ms)
  silenceDurationMs: 550,

  // Minimum interval between successive interruption events to prevent event spam (ms)
  debounceMs: 400,

  // Analysis frame interval for polling/processing in milliseconds
  analysisIntervalMs: 25,
};

export class VoiceActivityDetector {
  /**
   * @param {Object} [options]
   * @param {Object} [options.config] - Custom VAD configuration overrides
   * @param {Function} [options.getAssistantState] - Callback returning current assistant state ('PLAYING', 'THINKING', 'SYNTHESIZING', 'IDLE')
   * @param {Function} [options.getSessionContext] - Callback returning { sessionId, activeTurnId }
   */
  constructor(options = {}) {
    this.config = { ...DEFAULT_VAD_CONFIG, ...(options.config || {}) };
    this.getAssistantState = options.getAssistantState || (() => 'IDLE');
    this.getSessionContext = options.getSessionContext || (() => ({ sessionId: 'default', activeTurnId: 0 }));

    this.state = VADState.INACTIVE;
    this.isSpeaking = false;
    this.speechStartTime = null;
    this.silenceStartTime = null;
    this.lastInterruptionTime = null;
    this.currentEnergy = 0.0;

    this.audioContext = null;
    this.mediaStream = null;
    this.analyser = null;
    this.sourceNode = null;
    this._intervalId = null;

    this._eventListeners = new Set();
    this._stateListeners = new Set();
  }

  /**
   * Compute Root Mean Square (RMS) energy from audio sample buffer.
   * @param {Float32Array|Array<number>} samples 
   * @returns {number} RMS energy value (0.0 to 1.0)
   */
  calculateRMS(samples) {
    if (!samples || samples.length === 0) return 0.0;
    let sumSquares = 0.0;
    for (let i = 0; i < samples.length; i++) {
      const val = samples[i];
      sumSquares += val * val;
    }
    return Math.sqrt(sumSquares / samples.length);
  }

  /**
   * Process a discrete frame of audio samples or pre-calculated RMS energy.
   * Deterministic core method used by both live Web Audio loop and unit test suites.
   * 
   * @param {Float32Array|Array<number>|number} input - Audio samples or direct RMS energy value
   * @param {number} [currentTimeMs] - Optional explicit timestamp for deterministic testing
   * @returns {Object} Frame processing result
   */
  processFrame(input, currentTimeMs = Date.now()) {
    if (this.state === VADState.INACTIVE) {
      return { energy: 0.0, isSpeaking: false, interruptionTriggered: false };
    }

    const energy = typeof input === 'number' ? input : this.calculateRMS(input);
    this.currentEnergy = energy;

    this._emitEvent(VADEventType.ENERGY_UPDATED, {
      energy,
      timestamp: currentTimeMs,
    });

    const isAboveThreshold = energy >= this.config.energyThreshold;
    let interruptionTriggered = false;

    if (isAboveThreshold) {
      // Audio energy is above threshold
      this.silenceStartTime = null;

      if (!this.isSpeaking) {
        if (this.speechStartTime === null) {
          this.speechStartTime = currentTimeMs;
        } else {
          const speechDuration = currentTimeMs - this.speechStartTime;
          if (speechDuration >= this.config.minSpeechDurationMs) {
            // Sustained speech confirmed!
            this.isSpeaking = true;
            this._transitionTo(VADState.SPEECH_DETECTED);

            const assistantState = this.getAssistantState();
            const sessionCtx = this.getSessionContext();

            const isAssistantActive = ['PLAYING', 'THINKING', 'SYNTHESIZING'].includes(assistantState);
            const isDebounced = this.lastInterruptionTime &&
              (currentTimeMs - this.lastInterruptionTime < this.config.debounceMs);

            if (isAssistantActive && !isDebounced) {
              // Trigger barge-in interruption!
              this.lastInterruptionTime = currentTimeMs;
              interruptionTriggered = true;
              this._transitionTo(VADState.INTERRUPTED);

              this._emitEvent(VADEventType.INTERRUPTION_DETECTED, {
                sessionId: sessionCtx.sessionId,
                previousTurnId: sessionCtx.activeTurnId,
                newTurnId: (sessionCtx.activeTurnId || 0) + 1,
                timestamp: currentTimeMs,
                detectionSource: 'vad_speech_start',
                assistantState: assistantState,
                energy: energy,
                speechDurationMs: speechDuration,
              });
            } else {
              // Normal speech start
              this._emitEvent(VADEventType.SPEECH_STARTED, {
                sessionId: sessionCtx.sessionId,
                turnId: sessionCtx.activeTurnId,
                timestamp: currentTimeMs,
                detectionSource: 'vad_speech_start',
                assistantState: assistantState,
                energy: energy,
              });
            }
          }
        }
      }
    } else {
      // Audio energy is below threshold
      this.speechStartTime = null;

      if (this.isSpeaking) {
        if (this.silenceStartTime === null) {
          this.silenceStartTime = currentTimeMs;
        } else {
          const silenceDuration = currentTimeMs - this.silenceStartTime;
          if (silenceDuration >= this.config.silenceDurationMs) {
            // Speech ended
            this.isSpeaking = false;
            this.silenceStartTime = null;
            this._transitionTo(VADState.LISTENING_SILENCE);

            const sessionCtx = this.getSessionContext();
            this._emitEvent(VADEventType.SPEECH_ENDED, {
              sessionId: sessionCtx.sessionId,
              turnId: sessionCtx.activeTurnId,
              timestamp: currentTimeMs,
              silenceDurationMs: silenceDuration,
            });
          }
        }
      }
    }

    return {
      energy,
      isSpeaking: this.isSpeaking,
      interruptionTriggered,
      state: this.state,
    };
  }

  /**
   * Start live microphone capture and real-time VAD analysis.
   * @returns {Promise<void>}
   */
  async start() {
    if (this.state !== VADState.INACTIVE) {
      return;
    }

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      // Headless/test fallback mode
      this._transitionTo(VADState.LISTENING_SILENCE);
      this._emitEvent(VADEventType.VAD_STARTED, { timestamp: Date.now(), mode: 'simulated' });
      return;
    }

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.audioContext = new AudioCtx();
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 512;
      this.analyser.smoothingTimeConstant = 0.2;

      this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
      this.sourceNode.connect(this.analyser);

      const bufferLength = this.analyser.fftSize;
      const dataArray = new Float32Array(bufferLength);

      this._transitionTo(VADState.LISTENING_SILENCE);
      this._emitEvent(VADEventType.VAD_STARTED, { timestamp: Date.now(), mode: 'live' });

      // Run periodic analysis loop
      this._intervalId = setInterval(() => {
        if (this.state === VADState.INACTIVE || !this.analyser) return;
        this.analyser.getFloatTimeDomainData(dataArray);
        this.processFrame(dataArray, Date.now());
      }, this.config.analysisIntervalMs);

    } catch (err) {
      this.stop();
      this._transitionTo(VADState.ERROR);
      throw new Error(`Failed to initialize VAD: ${err.message}`);
    }
  }

  /**
   * Get the active media stream if VAD is running.
   * @returns {MediaStream|null}
   */
  getMediaStream() {
    return this.mediaStream;
  }

  /**
   * Stop VAD listening and clean up all audio streams and nodes.
   */
  stop() {
    if (this._intervalId) {
      clearInterval(this._intervalId);
      this._intervalId = null;
    }

    if (this.sourceNode) {
      try {
        this.sourceNode.disconnect();
      } catch (e) {
        // ignore
      }
      this.sourceNode = null;
    }

    if (this.audioContext) {
      try {
        this.audioContext.close();
      } catch (e) {
        // ignore
      }
      this.audioContext = null;
    }

    if (this.mediaStream) {
      try {
        this.mediaStream.getTracks().forEach((track) => track.stop());
      } catch (e) {
        // ignore
      }
      this.mediaStream = null;
    }

    this.analyser = null;
    this.isSpeaking = false;
    this.speechStartTime = null;
    this.silenceStartTime = null;
    this.currentEnergy = 0.0;

    const prevState = this.state;
    this._transitionTo(VADState.INACTIVE);
    if (prevState !== VADState.INACTIVE) {
      this._emitEvent(VADEventType.VAD_STOPPED, { timestamp: Date.now() });
    }
  }

  /**
   * Reset internal detection state (e.g. after turn transition).
   */
  resetState() {
    this.isSpeaking = false;
    this.speechStartTime = null;
    this.silenceStartTime = null;
    if (this.state !== VADState.INACTIVE && this.state !== VADState.ERROR) {
      this._transitionTo(VADState.LISTENING_SILENCE);
    }
  }

  _transitionTo(nextState) {
    if (this.state === nextState) return;
    const prevState = this.state;
    this.state = nextState;
    for (const listener of this._stateListeners) {
      try {
        listener(this.state, prevState);
      } catch (e) {
        console.error('VAD state listener error:', e);
      }
    }
  }

  _emitEvent(eventType, payload) {
    const event = {
      eventType,
      ...payload,
    };
    for (const listener of this._eventListeners) {
      try {
        listener(event);
      } catch (e) {
        console.error('VAD event listener error:', e);
      }
    }
  }

  onEvent(callback) {
    this._eventListeners.add(callback);
    return () => this._eventListeners.delete(callback);
  }

  onStateChange(callback) {
    this._stateListeners.add(callback);
    return () => this._stateListeners.delete(callback);
  }
}

export const defaultVAD = new VoiceActivityDetector();
