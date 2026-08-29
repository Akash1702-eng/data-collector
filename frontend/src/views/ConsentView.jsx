import React, { useState } from 'react';
import { Check, ShieldCheck, ArrowRight, AlertCircle } from 'lucide-react';

export default function ConsentView({ onConsentComplete, onBack }) {
  const [consentAge, setConsentAge] = useState(false);
  const [consentTerms, setConsentTerms] = useState(false);

  const canProceed = consentAge && consentTerms;

  return (
    <div style={{ maxWidth: '640px', margin: '0 auto', width: '100%' }}>
      <div className="glass-card">
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          marginBottom: '1.25rem',
        }}>
          <div style={{
            width: '42px',
            height: '42px',
            borderRadius: 'var(--radius-md)',
            background: '#eef2ff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent-primary)',
          }}>
            <ShieldCheck size={22} />
          </div>
          <div>
            <h2 style={{ fontSize: '1.4rem', color: 'var(--text-primary)' }}>Participant Consent</h2>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Step 1 of 3 · Terms & Research Usage
            </p>
          </div>
        </div>

        <div style={{
          background: '#fffbeb',
          border: '1px solid #fde68a',
          borderRadius: 'var(--radius-md)',
          padding: '1.15rem',
          marginBottom: '1.5rem',
          fontSize: '0.88rem',
          color: '#92400e',
        }}>
          <strong style={{ display: 'block', marginBottom: '0.4rem', color: '#b45309' }}>
            What you are agreeing to:
          </strong>
          <ul style={{ paddingLeft: '1.15rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
            <li>You will record 12 prompts across 3 languages (English, Hindi, Marathi — 3 fixed sentences + 1 short free-speech prompt each).</li>
            <li>Recordings are stored anonymously without names, emails, or IP addresses.</li>
            <li>Voice data is used solely for research in detecting voice-cloning telephone fraud.</li>
            <li>After upload, the system automatically generates AI text-to-speech versions of the fixed sentences (not clones of your voice) and stores them alongside your recordings in the dataset.</li>
            <li>You can stop at any time before uploading without saving partial recordings.</li>
          </ul>
        </div>

        {/* Checkbox 1 */}
        <div
          className={`checkbox-card ${consentAge ? 'checked' : ''}`}
          onClick={() => setConsentAge(!consentAge)}
        >
          <div className="custom-checkbox">
            {consentAge && <Check size={14} />}
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>
              Age Verification
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              I confirm that I am 18 years of age or older.
            </div>
          </div>
        </div>

        {/* Checkbox 2 */}
        <div
          className={`checkbox-card ${consentTerms ? 'checked' : ''}`}
          onClick={() => setConsentTerms(!consentTerms)}
        >
          <div className="custom-checkbox">
            {consentTerms && <Check size={14} />}
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>
              Research & Voice Usage Consent
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              I consent to my voice recordings being used anonymously for voice fraud detection research and paired evaluation.
            </div>
          </div>
        </div>

        {/* Navigation buttons */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', marginTop: '1.5rem' }}>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canProceed}
            onClick={onConsentComplete}
          >
            <span>Proceed to Profile</span>
            <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
