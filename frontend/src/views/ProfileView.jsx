import React, { useState } from 'react';
import { User, ArrowRight, ArrowLeft, Info } from 'lucide-react';

export default function ProfileView({
  config,
  initialProfile,
  onProfileComplete,
  onBack,
}) {
  const ageRanges = config?.age_ranges || ["18-24", "25-34", "35-44", "45-54", "55+"];
  const genders = config?.genders || ["Male", "Female", "Non-binary", "Prefer not to say"];
  const environments = config?.environments || ["Quiet room", "Some background noise", "Noisy environment"];


  const [ageRange, setAgeRange] = useState(initialProfile?.age_range || '');
  const [gender, setGender] = useState(initialProfile?.gender || '');
  const [environment, setEnvironment] = useState(initialProfile?.environment || '');

  // All three fields are required
  const isValid = Boolean(ageRange && gender && environment);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!isValid) return;
    onProfileComplete({
      age_range: ageRange,
      gender,
      environment,
    });
  };

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
            <User size={22} />
          </div>
          <div>
            <h2 style={{ fontSize: '1.4rem', color: 'var(--text-primary)' }}>Contributor Profile</h2>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Step 2 of 3 · Anonymous demographic data
            </p>
          </div>
        </div>

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.6rem',
          background: '#eef2ff',
          border: '1px solid #c7d2fe',
          borderRadius: 'var(--radius-md)',
          padding: '0.75rem 1rem',
          marginBottom: '1.5rem',
          fontSize: '0.82rem',
          color: '#4338ca',
        }}>
          <Info size={16} style={{ flexShrink: 0 }} />
          <span>
            You'll record <strong>12 prompts total</strong> — 4 in English, 4 in Hindi, 4 in Marathi (3 fixed sentences + 1 short free-speech prompt each).
          </span>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Age Range */}
          <div className="form-group">
            <label className="form-label">
              <span>📅 Age Range</span>
              <span style={{ color: '#e11d48', fontSize: '0.9rem' }}>*</span>
            </label>
            <select
              className="form-select"
              value={ageRange}
              onChange={(e) => setAgeRange(e.target.value)}
              required
            >
              <option value="">Select your age range...</option>
              {ageRanges.map((range) => (
                <option key={range} value={range}>
                  {range}
                </option>
              ))}
            </select>
          </div>

          {/* Gender — REQUIRED */}
          <div className="form-group">
            <label className="form-label">
              <span>⚧ Gender</span>
              <span style={{ color: '#e11d48', fontSize: '0.9rem' }}>*</span>
            </label>
            <select
              className="form-select"
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              required
            >
              <option value="">Select your gender...</option>
              {genders.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </div>

          {/* Environment */}
          <div className="form-group">
            <label className="form-label">
              <span>🔊 Recording Environment</span>
              <span style={{ color: '#e11d48', fontSize: '0.9rem' }}>*</span>
            </label>
            <select
              className="form-select"
              value={environment}
              onChange={(e) => setEnvironment(e.target.value)}
              required
            >
              <option value="">Select your current environment...</option>
              {environments.map((env) => (
                <option key={env} value={env}>
                  {env}
                </option>
              ))}
            </select>
          </div>

          {/* Required fields notice */}
          <p style={{
            fontSize: '0.78rem',
            color: 'var(--text-muted)',
            marginBottom: '1.25rem',
          }}>
            <span style={{ color: '#e11d48' }}>*</span> All fields are required
          </p>

          {/* Buttons */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <button
              type="button"
              className="btn btn-outline"
              onClick={onBack}
            >
              <ArrowLeft size={16} />
              <span>Back</span>
            </button>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={!isValid}
            >
              <span>Enter Recording Studio</span>
              <ArrowRight size={16} />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
