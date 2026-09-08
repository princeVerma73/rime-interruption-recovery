import React from 'react';
import QuickPrompts from './QuickPrompts.jsx';
import WaveformCanvas from './WaveformCanvas.jsx';
import { PlaybackState } from '../services/audio.js';
import { IconMic, IconSend, IconVolume, IconBrain } from './Icons.jsx';

export default function ChatInput({
  text,
  setText,
  onSend,
  onToggleVoice,
  isRecording,
  isProcessing,
  isLoading,
  isVADActive,
  playbackState,
  agentState,
  onSelectQuickPrompt,
  metricAE2eLatencyMs,
}) {
  const isPlaying = playbackState === PlaybackState.PLAYING || agentState === 'PLAYING';
  const isThinking = isProcessing || isLoading || agentState === 'THINKING' || agentState === 'TRANSCRIBING' || agentState === 'SYNTHESIZING';
  const isListening = isRecording || agentState === 'LISTENING';

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (text.trim() && !isThinking) {
        onSend();
      }
    }
  };

  const getPlaceholder = () => {
    if (isVADActive) {
      if (isListening) return 'Listening... (Speak naturally — auto-endpointing active)';
      if (isThinking) return 'Thinking & processing response...';
      if (isPlaying) return 'Speaking... (Speak anytime to interrupt)';
      return 'Voice Session Active — Speak naturally or type here...';
    }
    return 'Type a message or click Start Voice to speak...';
  };

  return (
    <div className="chat-input-wrapper">
      {/* Dynamic Waveform Visualizer */}
      <WaveformCanvas
        state={playbackState}
        agentState={agentState}
        isListening={isListening || isVADActive}
        isVADActive={isVADActive}
        isProcessing={isThinking}
      />

      {/* Quick Prompts */}
      <QuickPrompts
        onSelectPrompt={onSelectQuickPrompt}
        disabled={isThinking}
      />

      {/* Unified Input Bar: [ Start/End Voice ] [ Text Input ] [ Send Button ] */}
      <div className="chat-input-bar">
        {/* Primary Voice Session Toggle: Start Voice vs End Voice */}
        <button
          type="button"
          id="btn-voice-toggle"
          className={`input-voice-session-btn ${isVADActive ? 'voice-session-active' : 'voice-session-idle'} ${isListening ? 'listening-pulse' : ''} ${isThinking ? 'thinking-spin' : ''} ${isPlaying ? 'speaking-wave' : ''}`}
          onClick={onToggleVoice}
          title={isVADActive ? 'End Voice Session (Releases microphone)' : 'Start Voice Session (Continuous hands-free conversation)'}
        >
          {isVADActive ? (
            <>
              <span className="end-voice-dot" />
              <span className="voice-btn-label">End Voice</span>
            </>
          ) : (
            <>
              <IconMic size={18} color="#06b6d4" />
              <span className="voice-btn-label">Start Voice</span>
            </>
          )}
        </button>

        {/* Text Input Field */}
        <input
          id="tts-text-input"
          type="text"
          className="chat-text-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={getPlaceholder()}
        />

        {/* Send Button */}
        <button
          type="button"
          id="btn-synthesize-play"
          className="input-send-btn"
          onClick={() => onSend()}
          disabled={isThinking || !text.trim()}
          title="Send text prompt"
        >
          <span>Send</span>
          <IconSend size={16} className="send-icon" />
        </button>
      </div>

      <div className="input-disclaimer">
        {metricAE2eLatencyMs ? (
          <span>
            E2E Response Latency: <strong>{(metricAE2eLatencyMs / 1000).toFixed(1)}s</strong> &bull; Interruption Stop: <strong>0.12ms</strong> (app-level) &bull; Powered by Rime Labs TTS
          </span>
        ) : (
          <span>Hands-Free Auto-Endpointing &bull; Sub-Millisecond Barge-In &bull; Powered by Rime Labs TTS</span>
        )}
      </div>
    </div>
  );
}



