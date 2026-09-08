/**
 * Browser Microphone Recorder Service
 * 
 * Captures user speech audio using native MediaRecorder & getUserMedia APIs.
 * Supports push-to-talk recording with deterministic state transitions.
 * 
 * DataForge 2026 Rime Hackathon - Phase 7
 */

export const RecorderState = {
  IDLE: 'IDLE',
  RECORDING: 'RECORDING',
  PROCESSING: 'PROCESSING',
  TRANSCRIBED: 'TRANSCRIBED',
  ERROR: 'ERROR',
};

export class MicrophoneRecorder {
  constructor() {
    this.state = RecorderState.IDLE;
    this.mediaRecorder = null;
    this.mediaStream = null;
    this.audioChunks = [];
    this.startTime = null;
    this._stateListeners = new Set();
    this._levelListeners = new Set();

    this.audioContext = null;
    this.analyser = null;
    this.sourceNode = null;
    this._levelInterval = null;
    this.maxEnergy = 0;
    this.totalEnergy = 0;
    this.energySamplesCount = 0;
  }

  /**
   * Check if microphone capture is supported in the current environment.
   */
  isSupported() {
    return (
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices &&
      !!navigator.mediaDevices.getUserMedia &&
      typeof MediaRecorder !== 'undefined'
    );
  }

  /**
   * Enumerate available microphone devices in the browser.
   * @returns {Promise<Array<MediaDeviceInfo>>}
   */
  async getAudioDevices() {
    if (!this.isSupported()) return [];
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      return devices.filter((d) => d.kind === 'audioinput');
    } catch (e) {
      console.warn('Failed to enumerate audio devices:', e);
      return [];
    }
  }

  /**
   * Request microphone permission and begin recording audio.
   * @param {string} [deviceId] Optional device ID to select a specific microphone
   * @param {MediaStream} [existingStream] Optional active MediaStream to reuse without re-negotiating getUserMedia
   * @returns {Promise<void>}
   */
  async startRecording(deviceId = null, existingStream = null) {
    if (!this.isSupported()) {
      this._transitionTo(RecorderState.ERROR);
      throw new Error('Microphone recording is not supported in this browser environment.');
    }

    if (this.state === RecorderState.RECORDING) {
      return;
    }

    try {
      this._isSharedStream = Boolean(existingStream && existingStream.active);
      if (this._isSharedStream) {
        this.mediaStream = existingStream;
      } else {
        const audioConstraints = deviceId
          ? {
              deviceId: { exact: deviceId },
              echoCancellation: true,
              autoGainControl: true,
              noiseSuppression: true,
            }
          : {
              echoCancellation: true,
              autoGainControl: true,
              noiseSuppression: true,
            };

        this.mediaStream = await navigator.mediaDevices.getUserMedia({
          audio: audioConstraints,
        });
      }

      // Set up AudioContext for live volume metering and silence verification
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {
          this.audioContext = new AudioCtx();
          if (this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
          }
          this.analyser = this.audioContext.createAnalyser();
          this.analyser.fftSize = 512;
          this.analyser.smoothingTimeConstant = 0.3;

          this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
          this.sourceNode.connect(this.analyser);

          const bufferLength = this.analyser.fftSize;
          const dataArray = new Float32Array(bufferLength);
          this.maxEnergy = 0;
          this.totalEnergy = 0;
          this.energySamplesCount = 0;

          this._levelInterval = setInterval(() => {
            if (!this.analyser || this.state !== RecorderState.RECORDING) return;
            this.analyser.getFloatTimeDomainData(dataArray);
            let sumSquares = 0;
            for (let i = 0; i < dataArray.length; i++) {
              const val = dataArray[i];
              sumSquares += val * val;
            }
            const rms = Math.sqrt(sumSquares / dataArray.length);
            if (rms > this.maxEnergy) this.maxEnergy = rms;
            this.totalEnergy += rms;
            this.energySamplesCount++;
            this._emitLevel(rms);
          }, 40);
        }
      } catch (audioCtxErr) {
        console.warn('AudioContext volume metering could not be started:', audioCtxErr);
      }

      // Detect supported mime type
      let mimeType = 'audio/webm;codecs=opus';
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : MediaRecorder.isTypeSupported('audio/mp4')
          ? 'audio/mp4'
          : 'audio/ogg';
      }

      this.audioChunks = [];
      this.mediaRecorder = new MediaRecorder(this.mediaStream, { mimeType });

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      this.startTime = Date.now();
      this.mediaRecorder.start(100); // collect in 100ms slices
      this._transitionTo(RecorderState.RECORDING);

    } catch (err) {
      this._transitionTo(RecorderState.ERROR);
      this._cleanupStream();
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        throw new Error('Microphone permission was denied. Please allow microphone access in your browser.');
      }
      throw new Error(`Failed to access microphone: ${err.message}`);
    }
  }

  /**
   * Stop recording and return the recorded audio Blob with energy telemetry.
   * @returns {Promise<{ blob: Blob, mimeType: string, durationMs: number, maxEnergy: number, avgEnergy: number }>}
   */
  async stopRecording() {
    if (this.state !== RecorderState.RECORDING || !this.mediaRecorder) {
      return null;
    }

    this._transitionTo(RecorderState.PROCESSING);

    return new Promise((resolve, reject) => {
      this.mediaRecorder.onstop = () => {
        try {
          const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
          const blob = new Blob(this.audioChunks, { type: mimeType });
          const durationMs = this.startTime ? Date.now() - this.startTime : 0;
          const maxEnergy = this.maxEnergy || 0;
          const avgEnergy = this.energySamplesCount > 0 ? this.totalEnergy / this.energySamplesCount : 0;

          console.log(`[Recorder] Stopped: chunks=${this.audioChunks.length}, size=${blob.size}B, duration=${durationMs}ms, maxEnergy=${maxEnergy.toFixed(4)}, avgEnergy=${avgEnergy.toFixed(4)}`);

          this._cleanupStream();
          this._transitionTo(RecorderState.IDLE);
          this._emitLevel(0);

          resolve({ blob, mimeType, durationMs, maxEnergy, avgEnergy });
        } catch (err) {
          this._cleanupStream();
          this._transitionTo(RecorderState.ERROR);
          this._emitLevel(0);
          reject(err);
        }
      };

      this.mediaRecorder.onerror = (err) => {
        this._cleanupStream();
        this._transitionTo(RecorderState.ERROR);
        this._emitLevel(0);
        reject(err);
      };

      try {
        // Explicitly flush buffered timeslice audio before stopping
        if (this.mediaRecorder.state === 'recording') {
          this.mediaRecorder.requestData();
        }
        this.mediaRecorder.stop();
      } catch (err) {
        this._cleanupStream();
        this._transitionTo(RecorderState.ERROR);
        this._emitLevel(0);
        reject(err);
      }
    });
  }

  /**
   * Cancel recording immediately and discard audio data.
   */
  cancelRecording() {
    if (this.mediaRecorder && this.state === RecorderState.RECORDING) {
      try {
        this.mediaRecorder.stop();
      } catch (e) {
        // ignore on cancel
      }
    }
    this._cleanupStream();
    this.audioChunks = [];
    this._emitLevel(0);
    this._transitionTo(RecorderState.IDLE);
  }

  _cleanupStream() {
    if (this._levelInterval) {
      clearInterval(this._levelInterval);
      this._levelInterval = null;
    }
    if (this.sourceNode) {
      try {
        this.sourceNode.disconnect();
      } catch (e) {}
      this.sourceNode = null;
    }
    if (this.audioContext && !this._isSharedStream) {
      try {
        this.audioContext.close();
      } catch (e) {}
      this.audioContext = null;
    }
    if (this.mediaStream && !this._isSharedStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }
    this.mediaRecorder = null;
    this.analyser = null;
  }

  _transitionTo(nextState) {
    if (this.state === nextState) return;
    const prevState = this.state;
    this.state = nextState;
    for (const listener of this._stateListeners) {
      try {
        listener(this.state, prevState);
      } catch (e) {
        console.error('Recorder state listener error:', e);
      }
    }
  }

  _emitLevel(level) {
    for (const listener of this._levelListeners) {
      try {
        listener(level);
      } catch (e) {
        console.error('Recorder level listener error:', e);
      }
    }
  }

  onStateChange(callback) {
    this._stateListeners.add(callback);
    return () => this._stateListeners.delete(callback);
  }

  onLevelChange(callback) {
    this._levelListeners.add(callback);
    return () => this._levelListeners.delete(callback);
  }
}

export const defaultRecorder = new MicrophoneRecorder();
