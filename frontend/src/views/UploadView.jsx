import React, { useEffect, useState, useRef } from 'react';
import { UploadCloud, CheckCircle2, AlertTriangle, ArrowLeft } from 'lucide-react';
import { submitContributionSession } from '../api/client';

export default function UploadView({
  metadata,
  recordings,
  onUploadSuccess,
  onBackToStudio,
}) {
  const [status, setStatus] = useState('uploading');
  const [message, setMessage] = useState('Processing and standardizing audio clips...');
  const [errorDetails, setErrorDetails] = useState(null);
  const uploadStartedRef = useRef(false);

  useEffect(() => {
    if (uploadStartedRef.current) return;
    uploadStartedRef.current = true;

    let isMounted = true;
    const clipCount = Object.keys(recordings || {}).length;

    async function doUpload() {
      try {
        setStatus('uploading');
        setMessage(`Uploading ${clipCount} recordings to Hugging Face Hub dataset...`);

        const recordingsMap = {};
        for (const [pId, rec] of Object.entries(recordings)) {
          recordingsMap[pId] = rec.blob;
        }

        const res = await submitContributionSession(metadata, recordingsMap);
        if (!isMounted) return;

        setStatus('success');
        setMessage(res.message || `Successfully uploaded ${clipCount} clips to the dataset!`);
        setTimeout(() => {
          onUploadSuccess(res);
        }, 1200);

      } catch (err) {
        if (!isMounted) return;
        console.error('Upload failed:', err);
        setStatus('error');
        setMessage('Upload encountered an issue.');
        setErrorDetails(err.message || 'Network or server error during upload.');
      }
    }

    doUpload();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div style={{ maxWidth: '560px', margin: '2.5rem auto 0', width: '100%', textAlign: 'center' }}>
      <div className="glass-card" style={{ padding: '2.5rem 2rem' }}>
        {status === 'uploading' && (
          <div>
            <div style={{
              width: '72px',
              height: '72px',
              borderRadius: '50%',
              background: '#eef2ff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1.5rem',
              color: 'var(--accent-primary)',
              animation: 'pulse-ring 2s infinite',
            }}>
              <UploadCloud size={36} />
            </div>

            <h2 style={{ fontSize: '1.6rem', marginBottom: '0.75rem' }}>Submitting Your Session</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem' }}>
              {message}
            </p>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: '0.75rem' }}>
              AI voice will also be generated automatically for each recording...
            </p>
          </div>
        )}

        {status === 'success' && (
          <div>
            <div style={{
              width: '72px',
              height: '72px',
              borderRadius: '50%',
              background: '#ecfdf5',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1.5rem',
              color: 'var(--accent-emerald)',
            }}>
              <CheckCircle2 size={40} />
            </div>

            <h2 style={{ fontSize: '1.6rem', marginBottom: '0.75rem', color: 'var(--accent-emerald)' }}>
              Upload Completed!
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem' }}>
              {message}
            </p>
          </div>
        )}

        {status === 'error' && (
          <div>
            <div style={{
              width: '72px',
              height: '72px',
              borderRadius: '50%',
              background: '#fef2f2',
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
              {errorDetails || message}
            </p>
            <div style={{
              fontSize: '0.82rem',
              color: '#92400e',
              background: '#fffbeb',
              border: '1px solid #fde68a',
              padding: '0.7rem',
              borderRadius: 'var(--radius-md)',
              marginBottom: '1.5rem',
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
