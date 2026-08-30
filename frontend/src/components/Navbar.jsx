import React from 'react';
import { Mic, Shield } from 'lucide-react';

export default function Navbar({ onNavigate }) {
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
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.35rem 0.85rem',
            borderRadius: '999px',
            background: '#eef2ff',
            border: '1px solid #c7d2fe',
            fontSize: '0.78rem',
            fontWeight: 600,
            color: 'var(--accent-primary)',
          }}
        >
          <Shield size={14} />
          <span>Anonymous Dataset</span>
        </div>
      </div>
    </header>
  );
}
