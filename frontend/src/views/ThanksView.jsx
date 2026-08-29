import React, { useEffect } from 'react';
import { RotateCcw, Home, CheckCircle2 } from 'lucide-react';
import confetti from 'canvas-confetti';

export default function ThanksView({ contributorId, onReset, onHome }) {
  useEffect(() => {
    try {
      confetti({
        particleCount: 80,
        spread: 70,
        origin: { y: 0.6 },
        colors: ['#6366f1', '#8b5cf6', '#0891b2', '#059669', '#e11d48'],
      });
    } catch (e) {
      // Confetti fallback
    }
  }, []);

  return (
    <div style={{ maxWidth: '600px', margin: '2rem auto 0', width: '100%', textAlign: 'center' }}>
      <div className="glass-card" style={{
        background: '#ecfdf5',
        border: '1px solid #a7f3d0',
      }}>
        <div style={{
          width: '68px',
          height: '68px',
          borderRadius: '50%',
          background: 'var(--accent-emerald)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          margin: '0 auto 1.25rem',
          color: 'white',
          boxShadow: '0 4px 16px rgba(5, 150, 105, 0.25)',
        }}>
          <CheckCircle2 size={36} />
        </div>

        <h1 style={{
          fontFamily: 'var(--font-heading)',
          fontSize: '2.25rem',
          fontWeight: 800,
          color: '#065f46',
          marginBottom: '0.75rem',
        }}>
          Thank You for Contributing!
        </h1>

        <p style={{
          fontSize: '1.05rem',
          color: '#047857',
          marginBottom: '1.5rem',
          lineHeight: 1.55,
        }}>
          Your voice recordings have been successfully received.
          AI-generated voice pairs have also been created automatically for the fixed prompts.
          Your contribution plays a vital role in training open-source detectors to prevent AI deepfake voice scams.
        </p>

        {/* Anonymous ID Badge */}
        <div style={{
          background: 'white',
          border: '1px solid #a7f3d0',
          borderRadius: 'var(--radius-md)',
          padding: '0.85rem',
          marginBottom: '1.75rem',
          display: 'inline-block',
        }}>
          <div style={{ fontSize: '0.72rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Anonymous Contributor ID
          </div>
          <code style={{ fontSize: '0.95rem', color: 'var(--text-primary)', fontWeight: 600 }}>
            {contributorId || 'uuid-anonymous-session'}
          </code>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.85rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onReset}
          >
            <RotateCcw size={16} />
            <span>Record Another Session</span>
          </button>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={onHome}
          >
            <Home size={16} />
            <span>Return Home</span>
          </button>
        </div>
      </div>
    </div>
  );
}
