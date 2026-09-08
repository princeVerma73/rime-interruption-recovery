import React, { useEffect, useRef } from 'react';
import { PlaybackState } from '../services/audio.js';

export default function WaveformCanvas({ state, agentState, isListening, isProcessing, isVADActive }) {
  const canvasRef = useRef(null);

  const isPlaying = state === PlaybackState.PLAYING || agentState === 'PLAYING';
  const isActive = isListening || isVADActive || isPlaying || isProcessing || agentState === 'THINKING' || agentState === 'SYNTHESIZING' || agentState === 'INTERRUPTING';

  useEffect(() => {
    if (!isActive) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let animationFrameId;
    let phase = 0;

    const render = () => {
      const width = canvas.width;
      const height = canvas.height;
      const centerY = height / 2;

      ctx.clearRect(0, 0, width, height);

      // Determine colors based on active mode: Blue when Listening / VAD Active, Green when AI Speaking
      let strokeColor1, strokeColor2, glowColor;

      if (isPlaying) {
        // AI Speaking -> Green Wave
        strokeColor1 = '#10b981'; // Emerald Green
        strokeColor2 = '#34d399'; // Mint Green
        glowColor = 'rgba(16, 185, 129, 0.4)';
      } else if (isListening || isVADActive) {
        // User Speaking / Mic / VAD Active -> Blue Wave
        strokeColor1 = '#06b6d4'; // Cyan
        strokeColor2 = '#3b82f6'; // Royal Blue
        glowColor = 'rgba(6, 182, 212, 0.4)';
      } else {
        // Processing -> Purple/Blue Interfacing
        strokeColor1 = '#8b5cf6';
        strokeColor2 = '#06b6d4';
        glowColor = 'rgba(139, 92, 246, 0.4)';
      }

      // Draw Sine Wave
      ctx.save();
      ctx.shadowBlur = 12;
      ctx.shadowColor = glowColor;
      ctx.lineWidth = 2.5;

      // 1. Sine Wave Line
      ctx.beginPath();
      const grad1 = ctx.createLinearGradient(0, 0, width, 0);
      grad1.addColorStop(0, strokeColor1);
      grad1.addColorStop(1, strokeColor2);
      ctx.strokeStyle = grad1;

      const amplitude = isPlaying ? 22 : (isListening || isVADActive) ? 26 : 14;
      const frequency = 0.025;

      for (let x = 0; x < width; x++) {
        const y = centerY + Math.sin(x * frequency + phase) * amplitude * Math.sin((x / width) * Math.PI);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // 2. Cosine Interfacing Wave Line (opposite phase)
      ctx.beginPath();
      ctx.lineWidth = 1.8;
      const grad2 = ctx.createLinearGradient(0, 0, width, 0);
      grad2.addColorStop(0, strokeColor2);
      grad2.addColorStop(1, strokeColor1);
      ctx.strokeStyle = grad2;

      for (let x = 0; x < width; x++) {
        const y = centerY + Math.cos(x * frequency * 1.2 - phase * 1.3) * (amplitude * 0.75) * Math.sin((x / width) * Math.PI);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      ctx.restore();

      phase += isPlaying ? 0.08 : (isListening || isVADActive) ? 0.1 : 0.04;
      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [isActive, isPlaying, isListening, isVADActive, isProcessing, agentState]);

  if (!isActive) return null;

  return (
    <div className="waveform-canvas-container">
      <div className="canvas-header-info">
        <span className={`canvas-status-tag ${isPlaying ? 'status-speaking' : 'status-listening'}`}>
          {isPlaying ? 'AI Speaking' : isVADActive ? 'VAD Continuous Listening' : isListening ? 'Listening to Mic' : 'Processing'}
        </span>
      </div>
      <canvas ref={canvasRef} width={400} height={60} className="waveform-canvas" />
    </div>
  );
}
