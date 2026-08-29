import React from 'react';
import { Mic, Users } from 'lucide-react';

export default function Navbar({ onNavigate, contributorCount = 0 }) {
  return (
    <header className="navbar">
      <div className="nav-brand" onClick={() => onNavigate('consent')}>
        <div className="nav-brand-icon">
          <Mic size={20} color="white" />
        </div>
        <div>
          <span>Voice Authenticity</span>
          <span style={{ color: 'var(--accent-primary)', marginLeft: '6px', fontSize: '0.9rem' }}>Studio</span>
        </div>
      </div>

      <div className="nav-actions">
        <div
          title="Total number of contributors who submitted voice samples to this dataset"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-subtle)',
            padding: '0.42rem 0.95rem',
            borderRadius: '999px',
            fontSize: '0.84rem',
            fontWeight: 500,
            color: 'var(--text-primary)',
            boxShadow: 'var(--shadow-sm)',
            userSelect: 'none',
          }}
        >
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: 'var(--accent-emerald)',
            boxShadow: '0 0 8px rgba(5, 150, 105, 0.5)',
          }} />
          <Users size={15} color="var(--accent-primary)" />
          <span>
            <strong style={{ color: 'var(--accent-primary)', fontWeight: 700 }}>
              {contributorCount ?? 0}
            </strong>{' '}
            {contributorCount === 1 ? 'Person Contributed' : 'People Contributed'}
          </span>
        </div>
      </div>
    </header>
  );
}
