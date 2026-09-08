import React from 'react';
import { PlaybackState } from '../services/audio.js';
import { IconBot, IconMic, IconBrain, IconVolume, IconStop, IconZap, IconAlert } from './Icons.jsx';

export default function SpeakingIndicator({ state, agentState, currentAudio, interruptionInfo, errorMessage, micLevel = 0 }) {
  const isPlaying = state === PlaybackState.PLAYING || agentState === 'PLAYING';
  const isLoading = state === PlaybackState.LOADING || agentState === 'SYNTHESIZING';
  const isThinking = agentState === 'THINKING';
  const isTranscribing = agentState === 'TRANSCRIBING';
  const isListening = agentState === 'LISTENING';
  const isInterrupting = agentState === 'INTERRUPTING';
  const isStopped = state === PlaybackState.STOPPED;

  const dynamicScale = Math.min(1.0, Math.max(0.18, (micLevel || 0) * 10));

  const getOrbIcon = () => {
    if (isInterrupting) return <IconZap size={20} color="#f59e0b" />;
    if (isListening) return <IconMic size={20} color="#06b6d4" />;
    if (isTranscribing || isThinking || isLoading) return <IconBrain size={20} color="#8b5cf6" />;
    if (isPlaying) return <IconVolume size={20} color="#10b981" />;
    if (isStopped) return <IconStop size={20} color="#ef4444" />;
    if (agentState === 'ERROR' || state === PlaybackState.ERROR) return <IconAlert size={20} color="#ef4444" />;
    return <IconBot size={20} color="#94a3b8" />;
  };

  const getStatusLabel = () => {
    if (isInterrupting) {
      return {
        text: `Barge-In Interruption Detected! Turn #${interruptionInfo?.previousTurnId || ''} speech halted promptly (${interruptionInfo?.stopLatencyMs?.toFixed(2) || '< 0.2'} ms).`,
        cls: 'interrupting',
      };
    }
    if (isListening) {
      const isVoiceActive = micLevel > 0.015;
      return {
        text: isVoiceActive
          ? 'Listening... (Voice detected, speak freely)'
          : 'Listening... (Speak into your microphone)',
        cls: 'recording',
      };
    }
    if (isTranscribing) return { text: 'Transcribing speech via Groq Whisper (whisper-large-v3)...', cls: 'loading' };
    if (isThinking) return { text: 'Generating response via Groq LLM (qwen/qwen3.6-27b)...', cls: 'thinking' };
    if (isLoading) return { text: 'Synthesizing conversational voice via Rime Labs (coda / celeste)...', cls: 'loading' };
    if (isPlaying) {
      return {
        text: `Speaking Turn #${currentAudio?.turnId || ''} via Rime Labs (${currentAudio?.metadata?.speaker || 'celeste'})`,
        cls: 'playing',
      };
    }
    if (isStopped) return { text: 'Audio Playback Stopped (Buffer Purged)', cls: 'stopped' };
    if (agentState === 'ERROR' || state === PlaybackState.ERROR) {
      return { text: errorMessage || 'Pipeline Error encountered', cls: 'error' };
    }
    return { text: 'Voice Assistant Ready — Speak or click Talk to begin', cls: 'idle' };
  };

  const statusInfo = getStatusLabel();
  const isActive = isPlaying || isListening || isLoading || isThinking || isTranscribing || isInterrupting;

  return (
    <div
      className={`speaking-visualizer ${isPlaying ? 'active' : ''} ${isLoading || isThinking || isTranscribing ? 'loading' : ''} ${isListening ? 'listening' : ''} ${isInterrupting ? 'interrupting' : ''}`}
    >
      <div className="visualizer-orb">
        <div className="orb-core">
          <span className={`orb-icon ${isLoading || isThinking ? 'spin' : isPlaying ? 'pulse' : isInterrupting ? 'flash' : ''}`}>
            {getOrbIcon()}
          </span>
        </div>
      </div>

      <div className="speaking-status-text">
        <span className={`status-label ${statusInfo.cls}`}>
          {statusInfo.text}
        </span>
      </div>
    </div>
  );
}

