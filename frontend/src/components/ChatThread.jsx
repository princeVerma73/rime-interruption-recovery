import React, { useEffect, useRef } from 'react';
import { IconUser, IconBot, IconZap, IconSparkles } from './Icons.jsx';

export default function ChatThread({
  conversationTurns = [],
  currentTranscript = '',
  isListening,
  isProcessing,
  agentState,
  activeTurnId,
}) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [conversationTurns, currentTranscript, isListening, isProcessing, agentState]);

  const hasTurns = conversationTurns && conversationTurns.length > 0;
  const isPendingTurn = (isListening || isProcessing) && Boolean(currentTranscript.trim());

  return (
    <div className="chat-thread-container" ref={scrollRef}>
      {!hasTurns && !isPendingTurn ? (
        <div className="empty-thread-welcome">
          <div className="welcome-icon-box">
            <IconBot size={48} color="#06b6d4" />
          </div>
          <h2>Voice AI Assistant</h2>
          <p>Ultra-Low Latency Conversational Voice powered by Rime Labs TTS.</p>
          <p className="welcome-hint">Click the Microphone or type a message below to start.</p>
        </div>
      ) : (
        <div className="chat-messages-list">
          {conversationTurns.map((turn, idx) => {
            const isInterrupted = turn.status === 'INTERRUPTED' || turn.status === 'CANCELLED';
            return (
              <div key={turn.turnId || idx} className="chat-turn-group">
                {/* User Message */}
                {turn.userPrompt && (
                  <div className="chat-msg user-msg">
                    <div className="msg-avatar user-avatar">
                      <IconUser size={18} />
                    </div>
                    <div className="msg-bubble user-bubble-content">
                      <div className="msg-header">
                        <span className="msg-author">You</span>
                        <span className="msg-turn-tag">Turn #{turn.turnId}</span>
                      </div>
                      <div className="msg-text">{turn.userPrompt}</div>
                    </div>
                  </div>
                )}

                {/* Assistant Message */}
                <div className={`chat-msg assistant-msg ${isInterrupted ? 'msg-interrupted' : ''}`}>
                  <div className="msg-avatar assistant-avatar">
                    <IconBot size={18} />
                  </div>
                  <div className="msg-bubble assistant-bubble-content">
                    <div className="msg-header">
                      <span className="msg-author">Voice Assistant</span>
                      <span className="msg-rime-tag">Rime &bull; {turn.speaker || 'celeste'}</span>
                      {turn.searchUsed && (
                        <span className="turn-status-tag tag-authoritative" title="Real-time web search results from Tavily were incorporated">
                          🔍 Web Search
                        </span>
                      )}
                      {isInterrupted ? (
                        <span className="turn-status-tag tag-interrupted">
                          <IconZap size={12} style={{ marginRight: 4 }} /> INTERRUPTED
                        </span>
                      ) : (
                        <span className="turn-status-tag tag-completed">COMPLETED</span>
                      )}
                    </div>
                    <div className="msg-text">
                      {turn.assistantResponse || (isInterrupted ? '[Speech Halted Promptly on Barge-In]' : '')}
                    </div>
                    {turn.searchSources && turn.searchSources.length > 0 && (
                      <div className="msg-sources" style={{ marginTop: '6px', fontSize: '11px', color: '#94a3b8' }}>
                        <span>Sources: </span>
                        {turn.searchSources.slice(0, 3).map((src, sIdx) => {
                          let hostname = src;
                          try { hostname = new URL(src).hostname.replace('www.', ''); } catch (e) {}
                          return (
                            <a
                              key={sIdx}
                              href={src}
                              target="_blank"
                              rel="noreferrer noopener"
                              style={{ color: '#06b6d4', marginRight: '8px', textDecoration: 'underline' }}
                            >
                              {hostname}
                            </a>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          {/* Pending In-Flight Turn */}
          {isPendingTurn && (
            <div className="chat-turn-group pending-turn-group">
              <div className="chat-msg user-msg">
                <div className="msg-avatar user-avatar">
                  <IconUser size={18} />
                </div>
                <div className="msg-bubble user-bubble-content">
                  <div className="msg-header">
                    <span className="msg-author">You</span>
                    <span className="msg-turn-tag">Turn #{activeTurnId}</span>
                  </div>
                  <div className="msg-text">{currentTranscript}</div>
                </div>
              </div>

              <div className="chat-msg assistant-msg">
                <div className="msg-avatar assistant-avatar pulse-orb">
                  <IconSparkles size={18} />
                </div>
                <div className="msg-bubble assistant-bubble-content">
                  <div className="msg-header">
                    <span className="msg-author">Voice Assistant</span>
                    <span className="turn-status-tag tag-authoritative">IN PROGRESS</span>
                  </div>
                  <div className="msg-text processing-text">
                    <span className="typing-dots">
                      {agentState === 'TRANSCRIBING'
                        ? 'Transcribing speech...'
                        : agentState === 'THINKING'
                        ? 'Generating response...'
                        : agentState === 'SYNTHESIZING'
                        ? 'Synthesizing voice via Rime TTS...'
                        : 'Processing...'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
