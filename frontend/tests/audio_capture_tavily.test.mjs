import test from 'node:test';
import assert from 'node:assert/strict';
import { MicrophoneRecorder, RecorderState } from '../src/services/recorder.js';
import { VoiceActivityDetector, VADState, VADEventType } from '../src/services/vad.js';

test('1. MicrophoneRecorder initializes in IDLE state with support check', () => {
  const recorder = new MicrophoneRecorder();
  assert.equal(recorder.state, RecorderState.IDLE);
  assert.equal(typeof recorder.isSupported, 'function');
});

test('2. VoiceActivityDetector exposes getMediaStream method', () => {
  const vad = new VoiceActivityDetector();
  assert.equal(typeof vad.getMediaStream, 'function');
  assert.equal(vad.getMediaStream(), null);
});

test('3. VoiceActivityDetector processes audio frame and detects speech onset', () => {
  const vad = new VoiceActivityDetector({
    config: {
      energyThreshold: 0.015,
      minSpeechDurationMs: 100,
      silenceDurationMs: 500,
    },
  });

  vad.state = VADState.LISTENING_SILENCE;
  const highEnergyFrame = new Float32Array(512).fill(0.1); // Strong voice

  // Frame 1: Initial energy above threshold
  let res = vad.processFrame(highEnergyFrame, 1000);
  assert.equal(res.isSpeaking, false);

  // Frame 2: Sustained energy beyond minSpeechDurationMs -> Speech detected
  res = vad.processFrame(highEnergyFrame, 1150);
  assert.equal(res.isSpeaking, true);
  assert.equal(vad.state, VADState.SPEECH_DETECTED);
});

test('4. VAD barge-in triggers INTERRUPTION_DETECTED when assistant is PLAYING', () => {
  let emittedEvent = null;
  const vad = new VoiceActivityDetector({
    getAssistantState: () => 'PLAYING',
    getSessionContext: () => ({ sessionId: 'sess_test', activeTurnId: 2 }),
    config: {
      energyThreshold: 0.015,
      minSpeechDurationMs: 100,
      debounceMs: 200,
    },
  });

  vad.onEvent((evt) => {
    if (evt.eventType === VADEventType.INTERRUPTION_DETECTED) {
      emittedEvent = evt;
    }
  });

  vad.state = VADState.LISTENING_SILENCE;
  const voiceFrame = new Float32Array(512).fill(0.1);

  vad.processFrame(voiceFrame, 2000);
  vad.processFrame(voiceFrame, 2150);

  assert.ok(emittedEvent, 'Expected INTERRUPTION_DETECTED event');
  assert.equal(emittedEvent.previousTurnId, 2);
  assert.equal(emittedEvent.newTurnId, 3);
  assert.equal(emittedEvent.assistantState, 'PLAYING');
});

test('5. MicrophoneRecorder can cancel recording cleanly', () => {
  const recorder = new MicrophoneRecorder();
  recorder.state = RecorderState.RECORDING;
  recorder.audioChunks = [new Blob(['test audio bytes'])];
  recorder.cancelRecording();

  assert.equal(recorder.state, RecorderState.IDLE);
  assert.equal(recorder.audioChunks.length, 0);
});
