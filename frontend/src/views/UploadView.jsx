import React, { useEffect, useState, useRef } from 'react';
import { UploadCloud, CheckCircle2, AlertTriangle, ArrowLeft, ShieldAlert, Sparkles } from 'lucide-react';
import { submitContributionSession } from '../api/client';

export default function UploadView({
  metadata,
  recordings,
  onUploadSuccess,
  onBackToStudio,
}) {
  const [status, setStatus] = useState('uploading'); // 'uploading' | 'success' | 'error'
  const [progressPercent, setProgressPercent] = useState(10);
  const [stageMessage, setStageMessage] = useState('Packaging and standardizing audio clips...');
  const [errorDetails, setErrorDetails] = useState(null);
  const uploadStartedRef = useRef(false);

  // Prevent accidental page closing/refreshing while upload is in progress
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (status === 'uploading') {
        e.preventDefault();
        e.returnValue = 'Please do not exit this page until recordings are submitted successfully.';
        return e.returnValue;
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [status]);

  useEffect(() => {
    if (uploadStartedRef.current) return;
    uploadStartedRef.current = true;

    let isMounted = true;
    const clipCount = Object.keys(recordings || {}).length;

    // Simulated stepped progress animation while server processes and synthesizes audio
    const progressInterval = setInterval(() => {
      setProgressPercent((prev) => {
        if (prev < 30) {
          setStageMessage('Packaging audio clips to 16kHz WAV format...');
          return prev + 6;
        } else if (prev < 60) {
          setStageMessage(`Uploading ${clipCount} recordings to dataset...`);
          return prev + 4;
        } else if (prev < 85) {
          setStageMessage('Generating paired AI text-to-speech samples...');
          return prev + 3;
        } else if (prev < 95) {
          setStageMessage('Finalizing dataset contribution session...');
          return prev + 1;
        }
        return prev;
      });
    }, 450);

    async function doUpload() {
      try {
        const recordingsMap = {};
        for (const [pId, rec] of Object.entries(recordings)) {
          recordingsMap[pId] = rec.blob;
        }

        const res = await submitContributionSession(metadata, recordingsMap);
        if (!isMounted) return;

        clearInterval(progressInterval);
        setProgressPercent(100);
        setStatus('success');
        setStageMessage(res.message || `Successfully submitted ${clipCount} recordings!`);

        setTimeout(() => {
          if (isMounted) {
            onUploadSuccess(res);
          }
        }, 1200);

      } catch (err) {
        if (!isMounted) return;
        clearInterval(progressInterval);
        console.error('Upload failed:', err);
        setStatus('error');
        setStageMessage('Upload encountered an issue.');
        setErrorDetails(err.message || 'Network or server error during upload.');
      }
    }

    doUpload();

    return () => {
      isMounted = false;
      clearInterval(progressInterval);
    };
  }, []);

  // SVG Circular Progress Calculations
  const radius = 54;
  const strokeWidth = 8;
  const normalizedRadius = radius - strokeWidth / 2;
  const circumference = normalizedRadius * 2 * Math.PI;
  const strokeDashoffset = circumference - (progressPercent / 100) * circumference;

  return (
    <div style={{ maxWidth: '580px', margin: '2rem auto 0', width: '100%', textAlign: 'center' }}>
      <div className="glass-card" style={{ padding: '2.5rem 2rem', position: 'relative' }}>
        {/* Important User Notice Banner */}
        {status === 'uploading' && (
          <div className="upload-warning-banner">
            <ShieldAlert size={22} className="warning-icon-pulse" />
            <div style={{ textAlign: 'left' }}>
              <div className="warning-title">
                Please DO NOT exit or refresh this page!
              </div>
              <div className="warning-desc">
                Stay on this page until all your voice recordings are submitted successfully.
              </div>
            </div>
          </div>
        )}

        {/* ── Submitting State with Circular Progress Bar ── */}
        {status === 'uploading' && (
          <div style={{ marginTop: '1.25rem' }}>
            {/* SVG Circular Progress Bar */}
            <div className="circular-progress-wrapper">
              <svg
                height={radius * 2}
                width={radius * 2}
                className="circular-progress-svg"
              >
                <defs>
                  <linearGradient id="progressGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#6366f1" />
                    <stop offset="50%" stopColor="#8b5cf6" />
                    <stop offset="100%" stopColor="#06b6d4" />
                  </linearGradient>
                </defs>

                {/* Background Track */}
                <circle
                  stroke="#e2e8f0"
                  fill="transparent"
                  strokeWidth={strokeWidth}
                  r={normalizedRadius}
                  cx={radius}
                  cy={radius}
                />

                {/* Animated Progress Circle */}
                <circle
                  stroke="url(#progressGradient)"
                  fill="transparent"
                  strokeWidth={strokeWidth}
                  strokeDasharray={`${circumference} ${circumference}`}
                  style={{ strokeDashoffset }}
                  strokeLinecap="round"
                  r={normalizedRadius}
                  cx={radius}
                  cy={radius}
                  className="circular-progress-circle"
                />
              </svg>

              {/* Centered Percentage Inside Circle */}
              <div className="circular-progress-text">
                <span className="progress-number">{progressPercent}%</span>
              </div>
            </div>

            <h2 style={{ fontSize: '1.55rem', marginBottom: '0.6rem', color: 'var(--text-primary)' }}>
              Submitting Your Recordings
            </h2>

            <p style={{ color: 'var(--accent-primary)', fontWeight: 600, fontSize: '0.95rem', minHeight: '1.5rem' }}>
              {stageMessage}
            </p>

            <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: '0.85rem' }}>
              Standardizing audio to 16kHz & generating paired AI voice samples...
            </p>
          </div>
        )}

        {/* ── Success State ── */}
        {status === 'success' && (
          <div>
            <div style={{
              width: '76px',
              height: '76px',
              borderRadius: '50%',
              background: '#ecfdf5',
              border: '2px solid #a7f3d0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1.5rem',
              color: 'var(--accent-emerald)',
              boxShadow: '0 0 20px rgba(5, 150, 105, 0.2)',
            }}>
              <CheckCircle2 size={44} />
            </div>

            <h2 style={{ fontSize: '1.65rem', marginBottom: '0.75rem', color: 'var(--accent-emerald)' }}>
              Recordings Submitted Successfully!
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>
              {stageMessage}
            </p>
          </div>
        )}

        {/* ── Error State ── */}
        {status === 'error' && (
          <div>
            <div style={{
              width: '76px',
              height: '76px',
              borderRadius: '50%',
              background: '#fef2f2',
              border: '2px solid #fecaca',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1.5rem',
              color: 'var(--accent-rose)',
            }}>
              <AlertTriangle size={40} />
            </div>

            <h2 style={{ fontSize: '1.6rem', marginBottom: '0.75rem', color: 'var(--accent-rose)' }}>
              Upload Issue
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem', marginBottom: '1rem' }}>
              {errorDetails || stageMessage}
            </p>

            <div style={{
              fontSize: '0.82rem',
              color: '#92400e',
              background: '#fffbeb',
              border: '1px solid #fde68a',
              padding: '0.85rem',
              borderRadius: 'var(--radius-md)',
              marginBottom: '1.5rem',
              textAlign: 'left',
            }}>
              Don't worry — if Hugging Face is unreachable, your recordings are safely stored in the local fallback directory on the server.
            </div>

            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.85rem' }}>
              <button
                type="button"
                className="btn btn-outline"
                onClick={onBackToStudio}
              >
                <ArrowLeft size={15} />
                <span>Return to Studio</span>
              </button>

              <button
                type="button"
                className="btn btn-primary"
                onClick={() => onUploadSuccess({ message: 'Saved with local fallback' })}
              >
                <span>Continue Anyway</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
