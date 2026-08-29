import React, { useEffect, useRef } from 'react';

export default function AudioVisualizer({ analyser, isRecording }) {
  const canvasRef = useRef(null);
  const animationFrameRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    if (!isRecording || !analyser) {
      // Draw idle glowing line with soft center pulse
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.beginPath();
      ctx.moveTo(0, canvas.height / 2);
      ctx.lineTo(canvas.width, canvas.height / 2);
      ctx.strokeStyle = 'rgba(99, 102, 241, 0.3)';
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
      return;
    }

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      animationFrameRef.current = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(dataArray);

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const numBars = 48;
      const barWidth = canvas.width / numBars;
      const halfHeight = canvas.height / 2;

      // Draw mirrored frequency equalizer bars
      for (let i = 0; i < numBars; i++) {
        // Sample frequency bins across human vocal range (lower to mid-high frequencies)
        const binIndex = Math.min(
          Math.floor(Math.pow(i / numBars, 1.3) * (bufferLength * 0.7)),
          bufferLength - 1
        );
        const rawValue = dataArray[binIndex] || 0;
        const normalized = Math.min(1, rawValue / 200); // amplify sensitivity for normal speech
        const barHeight = Math.max(4, normalized * (canvas.height - 10));

        const x = i * barWidth;
        const y = halfHeight - barHeight / 2;

        // Dynamic gradient based on voice energy
        const gradient = ctx.createLinearGradient(0, y, 0, y + barHeight);
        if (normalized > 0.4) {
          gradient.addColorStop(0, '#34d399'); // Emerald glow when voice is clear
          gradient.addColorStop(0.5, '#6366f1');
          gradient.addColorStop(1, '#a855f7');
        } else {
          gradient.addColorStop(0, '#6366f1');
          gradient.addColorStop(0.5, '#a855f7');
          gradient.addColorStop(1, '#06b6d4');
        }

        ctx.fillStyle = gradient;
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(x + 1.5, y, Math.max(2, barWidth - 3), barHeight, 3);
        } else {
          ctx.rect(x + 1.5, y, Math.max(2, barWidth - 3), barHeight);
        }
        ctx.fill();
      }
    };

    draw();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [analyser, isRecording]);

  return (
    <canvas
      ref={canvasRef}
      className="canvas-visualizer"
      width={520}
      height={72}
    />
  );
}
