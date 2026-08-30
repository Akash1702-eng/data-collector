import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Sparkles,
  AlertTriangle,
  UploadCloud,
  Mic,
  Zap,
  Volume2,
  RefreshCw,
  Dices,
} from 'lucide-react';
import AudioRecorder from '../components/AudioRecorder';
import { useSpeechRecognition } from '../utils/useSpeechRecognition';

export default function StudioView({
  flatPrompts = [],
  recordings = {},
  onSaveRecording,
  onRedoRecording,
  onFinishStudio,
  onBackToProfile,
  onRegeneratePrompt,
}) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [stopTrigger, setStopTrigger] = useState(false);
  const [autoAdvanceCountdown, setAutoAdvanceCountdown] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);

  const countdownTimerRef = useRef(null);

  const totalPrompts = flatPrompts.length || 9;
  const currentPrompt = flatPrompts[currentIndex] || {
    id: `p_${currentIndex + 1}`,
    language: 'english_indian',
    language_display: 'English',
    native_text: 'Loading prompt text...',
    romanized_text: 'Loading prompt text...',
    type: 'general',
    note: 'Read naturally at a comfortable pace.',
  };

  const currentRecording = recordings[currentPrompt.id];
  const completedCount = Object.keys(recordings).length;
  const isCurrentAccepted = Boolean(currentRecording);

  // Original native script text (Devanagari for Hindi/Marathi, English for English)
  const promptDisplayText = currentPrompt.native_text || currentPrompt.text || currentPrompt.romanized_text || '';
  const words = promptDisplayText.trim().split(/\s+/).filter(Boolean);

  const isAiPrompt =
    currentPrompt.is_ai_generated ||
    currentPrompt.type === 'ai_generated' ||
    currentPrompt.type === 'open_ended' ||
    currentPrompt.id?.includes('_open_');

  // Strict Speech Recognition hook
  const {
    isSupported,
    isListening,
    readWordIndex,
    recognizedTranscript,
    isCompleted,
    startListening,
    stopListening,
    reset: resetSpeech,
  } = useSpeechRecognition({
    promptText: promptDisplayText,
    romanizedText: currentPrompt.romanized_text || '',
    language: currentPrompt.language,
    isOpenEnded: isAiPrompt || currentPrompt.type === 'open_ended',
    autoComplete: autoAdvance,
    onAllWordsRead: () => {
      // Trigger recording stop
      setStopTrigger(true);
      setTimeout(() => setStopTrigger(false), 200);

      // Auto advance to next sentence if enabled
      if (autoAdvance) {
        setAutoAdvanceCountdown(1);
        countdownTimerRef.current = setTimeout(() => {
          setAutoAdvanceCountdown(null);
          handleNext();
        }, 1200);
      }
    },
  });

  // Reset speech recognition & stop trigger on prompt change
  useEffect(() => {
    resetSpeech();
    setStopTrigger(false);
    setAutoAdvanceCountdown(null);
    if (countdownTimerRef.current) {
      clearTimeout(countdownTimerRef.current);
    }
  }, [currentIndex]);

  const handleNext = () => {
    if (countdownTimerRef.current) clearTimeout(countdownTimerRef.current);
    setAutoAdvanceCountdown(null);

    if (currentIndex < totalPrompts - 1) {
      setCurrentIndex((prev) => prev + 1);
    } else {
      // Finished all prompts
      if (isSubmitting) return;
      setIsSubmitting(true);
      onFinishStudio();
    }
  };

  const handlePrev = () => {
    if (countdownTimerRef.current) clearTimeout(countdownTimerRef.current);
    setAutoAdvanceCountdown(null);

    if (currentIndex > 0) {
      setCurrentIndex((prev) => prev - 1);
    }
  };

  // Language badge color helper
  const getLangBadgeClass = (lang) => {
    if (lang === 'english_indian') return 'badge-cyan';
    if (lang === 'hindi') return 'badge-purple';
    if (lang === 'marathi') return 'badge-amber';
    return 'badge-indigo';
  };

  const handleRegenerateClick = async () => {
    if (isRegenerating || !onRegeneratePrompt) return;
    setIsRegenerating(true);
    resetSpeech();
    try {
      await onRegeneratePrompt(currentPrompt.id, currentPrompt.language);
    } catch (err) {
      console.error('Regeneration error:', err);
    } finally {
      setIsRegenerating(false);
    }
  };

  return (
    <div style={{ maxWidth: '780px', margin: '0 auto', width: '100%' }}>
      {/* Stepper & Progress */}
      <div className="stepper-container">
        <div className="stepper-header" style={{ marginBottom: '0.4rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span className="stepper-step-count">
              Prompt {currentIndex + 1} of {totalPrompts}
            </span>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              ({completedCount}/{totalPrompts} recorded)
            </span>
          </div>
        </div>

        <div className="progress-bar-bg">
          <div
            className="progress-bar-fill"
            style={{ width: `${((currentIndex + 1) / totalPrompts) * 100}%` }}
          />
        </div>
      </div>

      {/* Main Prompt Card with Word Highlighting */}
      <div className="prompt-card" style={{ position: 'relative' }}>
        {/* Top Badges & Action Bar */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexWrap: 'wrap',
          gap: '0.5rem',
          marginBottom: '1.25rem',
          position: 'relative',
        }}>
          <span className={`badge ${getLangBadgeClass(currentPrompt.language)}`}>
            🌐 {currentPrompt.language_display?.toUpperCase() || currentPrompt.language?.toUpperCase()}
          </span>

          {isAiPrompt ? (
            <span className="badge" style={{ background: 'linear-gradient(135deg, #8b5cf6, #c026d3)', color: '#ffffff', fontWeight: '700' }}>
              ✨ GEMINI AI STORY
            </span>
          ) : (
            <span className="badge badge-indigo">
              🏷️ {currentPrompt.type?.toUpperCase() || 'STANDARD'}
            </span>
          )}

          {currentPrompt.topic && (
            <span className="badge badge-cyan" title={`Topic: ${currentPrompt.topic}`}>
              🎯 {currentPrompt.topic.toUpperCase()}
            </span>
          )}

          {isSupported && (
            <span className="badge badge-emerald" title="Live speech tracking active">
              🎙️ LIVE SPEECH TRACKING
            </span>
          )}

          {isAiPrompt && onRegeneratePrompt && (
            <button
              type="button"
              onClick={handleRegenerateClick}
              disabled={isListening || isRegenerating}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                fontSize: '0.78rem',
                fontWeight: '600',
                padding: '0.3rem 0.85rem',
                borderRadius: '9999px',
                border: '1px solid #d8b4fe',
                background: '#faf5ff',
                color: '#7e22ce',
                cursor: isRegenerating || isListening ? 'not-allowed' : 'pointer',
                transition: 'all 0.15s ease',
                boxShadow: '0 1px 2px rgba(126, 34, 206, 0.08)',
                whiteSpace: 'nowrap',
              }}
              title="Generate a fresh random reading text with Gemini AI"
            >
              <RefreshCw size={13} className={isRegenerating ? 'spin' : ''} />
              <span>{isRegenerating ? 'Generating...' : '🎲 New AI Passage'}</span>
            </button>
          )}
        </div>

        {/* Word-by-Word Teleprompter Rendering */}
        <div className="prompt-romanized-text">
          {words.map((word, wIdx) => {
            let status = 'pending';
            if (wIdx <= readWordIndex) {
              status = 'read';
            } else if (isListening && wIdx === readWordIndex + 1) {
              status = 'current';
            }

            return (
              <span
                key={wIdx}
                className={`word-token ${status}`}
              >
                {word}
              </span>
            );
          })}
        </div>

        {/* Romanized Transliteration Guide for Hindi/Marathi */}
        {currentPrompt.romanized_text && currentPrompt.romanized_text !== promptDisplayText && (
          <div style={{
            marginTop: '0.85rem',
            padding: '0.55rem 0.9rem',
            background: 'rgba(99, 102, 241, 0.04)',
            border: '1px dashed rgba(99, 102, 241, 0.25)',
            borderRadius: 'var(--radius-md)',
            fontSize: '0.92rem',
            color: '#4338ca',
            fontStyle: 'italic',
            textAlign: 'center',
            lineHeight: '1.4',
          }}>
            <span style={{
              fontSize: '0.72rem',
              fontStyle: 'normal',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: '#6366f1',
              fontWeight: 700,
              display: 'block',
              marginBottom: '0.2rem',
            }}>
              🔤 Romanized Pronunciation:
            </span>
            "{currentPrompt.romanized_text}"
          </div>
        )}

        {/* Live speech feedback & completion badge */}
        {isCompleted ? (
          <div style={{ marginTop: '1rem' }}>
            <div className="sentence-completed-badge">
              <CheckCircle2 size={18} />
              <span>
                {autoAdvanceCountdown !== null
                  ? `All Words Read! Auto-advancing to next sentence...`
                  : `All Words Read! Sentence Complete`}
              </span>
            </div>
          </div>
        ) : isListening && readWordIndex >= 0 ? (
          <div className="karaoke-status-bar">
            <span className="speech-live-badge">
              <Mic size={14} className="spin" />
              <span>
                Words Read: {Math.min(readWordIndex + 1, words.length)} / {words.length} ({Math.round(((readWordIndex + 1) / words.length) * 100)}%)
              </span>
            </span>
          </div>
        ) : isListening ? (
          <div className="karaoke-status-bar" style={{ background: '#f8fafc', borderColor: '#e2e8f0' }}>
            <span className="speech-live-badge" style={{ color: 'var(--text-secondary)' }}>
              <Mic size={14} />
              <span>Listening... Speak the words displayed on screen</span>
            </span>
          </div>
        ) : null}

        <div className="prompt-instruction">
          <span>💡</span>
          <span>
            {isAiPrompt
              ? 'Read this AI-generated passage naturally at your normal speaking pace.'
              : (currentPrompt.note || 'Read naturally at a comfortable pace.')}
          </span>
        </div>
      </div>

      {/* Auto-Advance Setting Switch */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        padding: '0.55rem 0.9rem',
        marginBottom: '1.25rem',
        fontSize: '0.82rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)' }}>
          <Zap size={15} color={autoAdvance ? '#d97706' : '#9ca3af'} />
          <span>Auto-advance to next sentence when speech finishes</span>
        </div>

        <button
          type="button"
          className={`btn ${autoAdvance ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setAutoAdvance(!autoAdvance)}
          style={{ fontSize: '0.72rem', padding: '0.25rem 0.7rem' }}
        >
          {autoAdvance ? 'Enabled' : 'Disabled'}
        </button>
      </div>

      {/* Audio Recorder Component */}
      <AudioRecorder
        key={currentPrompt.id}
        promptId={currentPrompt.id}
        existingRecording={currentRecording}
        minSeconds={1.0}
        maxSeconds={15.0}
        stopTrigger={stopTrigger}
        onStart={() => {
          resetSpeech();
          startListening();
        }}
        onStop={() => {
          stopListening();
        }}
        onRecordingComplete={({ promptId, blob, url, duration }) => {
          onSaveRecording(promptId, { blob, url, duration, prompt: currentPrompt });
        }}
        onRedo={(promptId) => {
          resetSpeech();
          onRedoRecording(promptId);
        }}
      />

      {/* Studio Navigation Controls */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginTop: '2rem',
        padding: '0 0.5rem',
      }}>
        <button
          type="button"
          className="btn btn-outline"
          onClick={currentIndex === 0 ? onBackToProfile : handlePrev}
        >
          <ArrowLeft size={18} />
          <span>{currentIndex === 0 ? 'Back to Profile' : 'Previous Prompt'}</span>
        </button>

        {currentIndex < totalPrompts - 1 ? (
          <button
            type="button"
            className="btn btn-primary"
            disabled={!isCurrentAccepted}
            onClick={handleNext}
          >
            <span>Next Prompt</span>
            <ArrowRight size={18} />
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-emerald"
            disabled={completedCount < totalPrompts || isSubmitting}
            onClick={() => {
              if (isSubmitting) return;
              setIsSubmitting(true);
              onFinishStudio();
            }}
          >
            <UploadCloud size={20} />
            <span>{isSubmitting ? 'Saving...' : `Finish & Submit All ${totalPrompts} Clips`}</span>
          </button>
        )}
      </div>
    </div>
  );
}
