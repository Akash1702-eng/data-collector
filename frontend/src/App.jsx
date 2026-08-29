import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import LandingView from './views/LandingView';
import ConsentView from './views/ConsentView';
import ProfileView from './views/ProfileView';
import StudioView from './views/StudioView';
import UploadView from './views/UploadView';
import ThanksView from './views/ThanksView';
import { getConfig, getContributorStats, generatePrompt } from './api/client';

function generateUUID() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export default function App() {
  const [currentView, setCurrentView] = useState('consent');
  const [config, setConfig] = useState(null);
  const [contributorCount, setContributorCount] = useState(0);
  const [contributorId, setContributorId] = useState(generateUUID());
  const [profile, setProfile] = useState(null);
  const [recordings, setRecordings] = useState({});
  const [uploadResult, setUploadResult] = useState(null);

  const refreshStats = async () => {
    try {
      const stats = await getContributorStats();
      if (stats && typeof stats.contributor_count === 'number') {
        setContributorCount(stats.contributor_count);
      }
    } catch (err) {
      console.debug('Could not refresh contributor stats:', err);
    }
  };

  // Load app config & prompts & stats
  useEffect(() => {
    async function init() {
      try {
        const data = await getConfig();
        setConfig(data);
        if (data && typeof data.contributor_count === 'number') {
          setContributorCount(data.contributor_count);
        }
      } catch (err) {
        console.error('Config fetch failed, using defaults:', err);
      }
    }
    init();
  }, []);

  const handleStart = () => {
    setCurrentView('consent');
  };

  const handleConsentComplete = () => {
    setCurrentView('profile');
  };

  const handleProfileComplete = (profileData) => {
    setProfile(profileData);
    setCurrentView('studio');
  };

  const handleSaveRecording = (promptId, recordingData) => {
    setRecordings((prev) => ({
      ...prev,
      [promptId]: recordingData,
    }));
  };

  const handleRedoRecording = (promptId) => {
    setRecordings((prev) => {
      const next = { ...prev };
      delete next[promptId];
      return next;
    });
  };

  const handleRegeneratePrompt = async (promptId, language) => {
    try {
      const updatedPrompt = await generatePrompt(language, promptId);
      if (updatedPrompt && config?.flat_prompts) {
        setConfig((prev) => {
          if (!prev) return prev;
          const nextFlat = prev.flat_prompts.map((p) =>
            p.id === promptId ? { ...p, ...updatedPrompt } : p
          );
          return {
            ...prev,
            flat_prompts: nextFlat,
          };
        });
        handleRedoRecording(promptId);
        return updatedPrompt;
      }
    } catch (err) {
      console.error('Failed to regenerate prompt:', err);
    }
    return null;
  };

  const handleFinishStudio = () => {
    setCurrentView('upload');
  };

  const handleUploadSuccess = (result) => {
    setUploadResult(result);
    setContributorCount((prev) => prev + 1);
    refreshStats();
    setCurrentView('thanks');
  };

  const handleResetSession = () => {
    setContributorId(generateUUID());
    setProfile(null);
    setRecordings({});
    setUploadResult(null);
    refreshStats();
    setCurrentView('consent');
  };

  const handleHome = () => {
    setContributorId(generateUUID());
    setProfile(null);
    setRecordings({});
    setUploadResult(null);
    refreshStats();
    setCurrentView('consent');
  };

  // Build custom prompts map for metadata
  const customPromptsMap = {};
  if (config?.flat_prompts) {
    for (const p of config.flat_prompts) {
      if (p.is_ai_generated || p.type === 'ai_generated' || p.id?.includes('_open_')) {
        customPromptsMap[p.id] = {
          native_text: p.native_text,
          romanized_text: p.romanized_text,
          topic: p.topic,
          type: p.type,
        };
      }
    }
  }

  return (
    <div className="app-container">
      <Navbar
        onNavigate={(view) => setCurrentView(view)}
        contributorCount={contributorCount}
      />

      <main style={{ flex: 1 }}>
        {currentView === 'landing' && (
          <LandingView onStart={handleStart} />
        )}

        {currentView === 'consent' && (
          <ConsentView
            onConsentComplete={handleConsentComplete}
            onBack={() => setCurrentView('landing')}
          />
        )}

        {currentView === 'profile' && (
          <ProfileView
            config={config}
            initialProfile={profile}
            onProfileComplete={handleProfileComplete}
            onBack={() => setCurrentView('consent')}
          />
        )}

        {currentView === 'studio' && (
          <StudioView
            flatPrompts={config?.flat_prompts || []}
            recordings={recordings}
            onSaveRecording={handleSaveRecording}
            onRedoRecording={handleRedoRecording}
            onFinishStudio={handleFinishStudio}
            onBackToProfile={() => setCurrentView('profile')}
            onRegeneratePrompt={handleRegeneratePrompt}
          />
        )}

        {currentView === 'upload' && (
          <UploadView
            metadata={{
              contribution_id: contributorId,
              ...profile,
              custom_prompts: customPromptsMap,
            }}
            recordings={recordings}
            onUploadSuccess={handleUploadSuccess}
            onBackToStudio={() => setCurrentView('studio')}
          />
        )}

        {currentView === 'thanks' && (
          <ThanksView
            contributorId={contributorId}
            onReset={handleResetSession}
            onHome={handleHome}
          />
        )}
      </main>

      <footer style={{
        marginTop: '2.5rem',
        paddingTop: '1.25rem',
        borderTop: '1px solid var(--border-subtle)',
        textAlign: 'center',
        fontSize: '0.82rem',
        color: 'var(--text-muted)',
      }}>
        <div>
          🎙️ <strong style={{ color: 'var(--text-secondary)' }}>Voice Authenticity Dataset Collector</strong> · Open Research Initiative
        </div>
        <div style={{ marginTop: '0.2rem', fontSize: '0.72rem' }}>
          Powered by React, FastAPI, Hugging Face Hub & Edge-TTS
        </div>
      </footer>
    </div>
  );
}
