import React from 'react';
import QuickPrompts from './QuickPrompts.jsx';
import WaveformCanvas from './WaveformCanvas.jsx';
import { PlaybackState } from '../services/audio.js';
import { IconMic, IconStop, IconSend, IconRadio } from './Icons.jsx';

export default function ChatInput({
  text,
  setText,
  onSend,
  onToggleRecord,
  onStopAudio,
  onToggleVAD,
  isRecording,
  isProcessing,
  isLoading,
  isVADActive,
  playbackState,
  agentState,
  onSelectQuickPrompt,
}) {
  const isPlaying = playbackState === PlaybackState.PLAYING || agentState === 'PLAYING';
  const isListening = isRecording || isVADActive || agentState === 'LISTENING';

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (text.trim() && !isProcessing && !isLoading && !isRecording) {
        onSend();
      }
    }
  };

  return (
    <div className="chat-input-wrapper">
      {/* Interfacing Sine & Cosine Canvas Waveform (Appears dynamically when mic is listening or AI is speaking) */}
      <WaveformCanvas
        state={playbackState}
        agentState={agentState}
        isListening={isListening}
        isVADActive={isVADActive}
        isProcessing={isProcessing}
      />

      <QuickPrompts
        onSelectPrompt={onSelectQuickPrompt}
        disabled={isLoading || isProcessing || isRecording}
      />

      <div className="chat-input-bar">
        {/* PTT Recording Button */}
        <button
          type="button"
          id="btn-record-speech"
          className={`input-action-btn btn-mic ${isRecording ? 'recording' : ''}`}
          onClick={onToggleRecord}
          disabled={isLoading || isPlaying || isProcessing}
          title={isRecording ? 'Click to finish recording' : 'Hold or click to speak (Push-to-Talk)'}
        >
          {isRecording ? <IconStop size={18} color="#ef4444" /> : <IconMic size={18} color="#06b6d4" />}
        </button>

        {/* Stop Audio Button */}
        {isPlaying && (
          <button
            type="button"
            id="btn-stop-audio"
            className="input-action-btn btn-stop"
            onClick={onStopAudio}
            title="Immediately halt active Rime speech playback"
          >
            <IconStop size={18} color="#ffffff" />
          </button>
        )}

        {/* VAD Toggle Button */}
        <button
          type="button"
          id="btn-toggle-vad"
          className={`input-action-btn btn-vad ${isVADActive ? 'active' : ''}`}
          onClick={onToggleVAD}
          title={isVADActive ? 'VAD Active (Continuous Listening)' : 'Enable Continuous VAD Hands-Free Barge-In'}
        >
          <IconMic size={18} color={isVADActive ? '#10b981' : '#94a3b8'} />
        </button>

        {/* Text Input Field */}
        <input
          id="tts-text-input"
          type="text"
          className="chat-text-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isRecording ? 'Listening to your speech...' : 'Type a prompt or click mic to speak...'}
        />

        {/* Send Button */}
        <button
          type="button"
          id="btn-synthesize-play"
          className="input-send-btn"
          onClick={() => onSend()}
          disabled={isLoading || isProcessing || isRecording || !text.trim()}
          title="Send prompt to Voice AI"
        >
          <span>Send</span>
          <IconSend size={16} className="send-icon" />
        </button>
      </div>

      <div className="input-disclaimer">
        <span>Enable microphone access in Settings &bull; Powered by Rime Labs TTS</span>
      </div>
    </div>
  );
}

