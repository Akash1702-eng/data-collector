import React from 'react';
import { Mic, ShieldCheck, Languages, Sparkles, ArrowRight, Activity, CheckCircle2 } from 'lucide-react';

export default function LandingView({ onStart }) {
  return (
    <div>
      <section className="hero">
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.35rem 0.85rem',
          background: '#eef2ff',
          border: '1px solid #c7d2fe',
          borderRadius: 'var(--radius-full)',
          fontSize: '0.82rem',
          fontWeight: 600,
          color: 'var(--accent-primary)',
          marginBottom: '1.5rem',
        }}>
          <Sparkles size={14} />
          <span>AI Voice Fraud Detection Research</span>
        </div>

        <h1 className="hero-title">
          Contribute Your Voice to <br />
          <span className="gradient-text">Detect AI Voice Fraud</span>
        </h1>

        <p className="hero-subtitle">
          Help build an open dataset distinguishing genuine human voices from AI voice clones.
          Record 9 short sentences in English, Hindi, and Marathi.
        </p>

        <button
          type="button"
          className="btn btn-primary btn-large"
          onClick={onStart}
        >
          <Mic size={20} />
          <span>Start Voice Contribution</span>
          <ArrowRight size={18} />
        </button>

        <p style={{
          fontSize: '0.82rem',
          color: 'var(--text-muted)',
          marginTop: '1rem',
        }}>
          Takes about 3–5 minutes · No account required · Works on desktop & mobile
        </p>
      </section>

      {/* Feature Grid */}
      <div className="hero-features-grid">
        <div className="feature-card">
          <div className="feature-icon-wrapper" style={{ background: '#eef2ff', color: 'var(--accent-primary)' }}>
            <Activity size={22} />
          </div>
          <h3 style={{ fontSize: '1.05rem', marginBottom: '0.4rem' }}>🔬 Research Purpose</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            Deepfake voice scams are rising. Your recordings train detectors to catch subtle audio artifacts produced by neural TTS engines.
          </p>
        </div>

        <div className="feature-card">
          <div className="feature-icon-wrapper" style={{ background: '#ecfdf5', color: 'var(--accent-emerald)' }}>
            <ShieldCheck size={22} />
          </div>
          <h3 style={{ fontSize: '1.05rem', marginBottom: '0.4rem' }}>🔒 100% Anonymous</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            No names, emails, phone numbers, or IP addresses are collected. Sessions are tied only to a random anonymous ID.
          </p>
        </div>

        <div className="feature-card">
          <div className="feature-icon-wrapper" style={{ background: '#ecfeff', color: 'var(--accent-cyan)' }}>
            <Languages size={22} />
          </div>
          <h3 style={{ fontSize: '1.05rem', marginBottom: '0.4rem' }}>🌐 3 Languages (Romanized)</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            Read 3 short sentences each in English, Hindi, and Marathi. All prompts are written in romanized Latin script so anyone can read them.
          </p>
        </div>
      </div>

      {/* Process Flow */}
      <div className="glass-card" style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '1.15rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span>📋</span>
          <span>How It Works</span>
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          <div>
            <div style={{ fontWeight: 700, color: 'var(--accent-primary)', marginBottom: '0.2rem', fontSize: '0.9rem' }}>1. Consent</div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Confirm you are 18+ and agree to project terms.
            </p>
          </div>
          <div>
            <div style={{ fontWeight: 700, color: 'var(--accent-primary)', marginBottom: '0.2rem', fontSize: '0.9rem' }}>2. Profile</div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Select your age range, gender, region, and background noise level.
            </p>
          </div>
          <div>
            <div style={{ fontWeight: 700, color: 'var(--accent-primary)', marginBottom: '0.2rem', fontSize: '0.9rem' }}>3. Studio Record</div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Read 9 short prompt cards into your browser microphone.
            </p>
          </div>
          <div>
            <div style={{ fontWeight: 700, color: 'var(--accent-primary)', marginBottom: '0.2rem', fontSize: '0.9rem' }}>4. Upload</div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Clips are converted to 16 kHz WAV and stored securely on Hugging Face.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
