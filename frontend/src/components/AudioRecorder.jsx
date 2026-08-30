import React, { useState, useRef, useEffect } from 'react';
import { Mic, Square, RotateCcw, Check, AlertTriangle, AlertCircle, Sparkles, Activity } from 'lucide-react';
import AudioVisualizer from './AudioVisualizer';

/**
 * Validates whether the audio contains genuine human speech with frequency/pitch dynamics
 * rather than flat silence, constant monotone noise, or background hum.
 */
function validateVoiceFrequencyDynamics(snapshots, durationSeconds, minSeconds) {
  if (durationSeconds < minSeconds) {
    return {
      isValid: false,
      reason: 'too_short',
      message: `Recording too short (${durationSeconds.toFixed(1)}s). Please read the prompt completely within 10 to 15 seconds.`,
    };
  }

  // Extract voiced frames where frequency energy in speech band (bins 1-45) is above noise floor
  const voicedFrames = snapshots.filter((s) => s.energy >= 13);

  // Must have at least ~0.8s of active speech (16 snapshots at 50ms interval)
  if (voicedFrames.length < 16) {
    return {
      isValid: false,
      reason: 'no_speech',
      message: 'No clear voice detected. Please read the prompt aloud clearly into your microphone and re-record.',
    };
  }

  // Extract spectral centroids and dominant peak bins
  const centroids = voicedFrames.map((f) => f.centroid);
  const peakBins = voicedFrames.map((f) => f.peakBin);

  // Calculate mean and standard deviation of spectral centroids
  const meanCentroid = centroids.reduce((sum, val) => sum + val, 0) / centroids.length;
  const variance =
    centroids.reduce((sum, val) => sum + Math.pow(val - meanCentroid, 2), 0) / centroids.length;
  const stdDevCentroid = Math.sqrt(variance);

  // Count distinct dominant peak frequency bins
  const uniquePeakBins = new Set(peakBins).size;

  // Count frequency shifts (pitch transitions over time)
  let pitchTransitions = 0;
  for (let i = 1; i < peakBins.length; i++) {
    if (Math.abs(peakBins[i] - peakBins[i - 1]) >= 1) {
      pitchTransitions++;
    }
  }

  // Genuine human voice has dynamic formant/pitch movement (stdDev >= 2.0 and distinct frequency shifts)
  const hasFrequencyVariation =
    stdDevCentroid >= 2.0 && (uniquePeakBins >= 3 || pitchTransitions >= 3);

  if (!hasFrequencyVariation) {
    return {
      isValid: false,
      reason: 'monotone_or_noise',
      message:
        'Voice pitch & frequency changes not detected (monotone or background noise). Please speak the prompt aloud with natural voice intonation and re-record.',
    };
  }

  return {
    isValid: true,
    message: 'Voice frequency & pitch variation verified!',
    stats: {
      stdDevCentroid: stdDevCentroid.toFixed(2),
      uniquePeaks: uniquePeakBins,
      transitions: pitchTransitions,
      speechDuration: (voicedFrames.length * 0.05).toFixed(1),
    },
  };
}

export default function AudioRecorder({
  promptId,
  existingRecording,
  minSeconds = 1.0,
  maxSeconds = 15.0,
  onStart,
  onStop,
  onRecordingComplete,
  onRedo,
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [speechState, setSpeechState] = useState('idle'); // 'idle' | 'waiting_speech' | 'speaking' | 'finishing'
  const [errorMessage, setErrorMessage] = useState(null);
  const [validationSuccess, setValidationSuccess] = useState(null);
  const [recordedBlob, setRecordedBlob] = useState(existingRecording?.blob || null);
  const [previewUrl, setPreviewUrl] = useState(existingRecording?.url || null);
  const [analyserNode, setAnalyserNode] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioContextRef = useRef(null);
  const sourceRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerIntervalRef = useRef(null);
  const startTimeRef = useRef(0);
  const sampleIntervalRef = useRef(null);
  const frequencySnapshotsRef = useRef([]);

  // End-of-speech silence detection refs
  const lastVoiceTimeRef = useRef(0);
  const voicedFramesCountRef = useRef(0);
  const autoStopTriggeredRef = useRef(false);

  // Sync with existing recording if prompt changes
  useEffect(() => {
    if (existingRecording) {
      setRecordedBlob(existingRecording.blob);
      setPreviewUrl(existingRecording.url);
      setValidationSuccess(true);
    } else {
      setRecordedBlob(null);
      setPreviewUrl(null);
      setValidationSuccess(null);
    }
    setErrorMessage(null);
    setIsRecording(false);
    setSpeechState('idle');
    setElapsedSeconds(0);
    frequencySnapshotsRef.current = [];
    autoStopTriggeredRef.current = false;
    voicedFramesCountRef.current = 0;
  }, [promptId, existingRecording]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      cleanupAudioStream();
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      if (sampleIntervalRef.current) clearInterval(sampleIntervalRef.current);
    };
  }, []);

  const cleanupAudioStream = () => {
    if (sampleIntervalRef.current) {
      clearInterval(sampleIntervalRef.current);
      sampleIntervalRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    setAnalyserNode(null);
  };

  const startRecording = async () => {
    setErrorMessage(null);
    setValidationSuccess(null);
    setSpeechState('waiting_speech');
    frequencySnapshotsRef.current = [];
    lastVoiceTimeRef.current = 0;
    voicedFramesCountRef.current = 0;
    autoStopTriggeredRef.current = false;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      streamRef.current = stream;

      // Setup Web Audio Analyser
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioCtx();
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }
      audioContextRef.current = audioCtx;

      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.7;

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);
      sourceRef.current = source;

      setAnalyserNode(analyser);

      // Setup MediaRecorder
      let options = {};
      if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
        options = { mimeType: 'audio/webm;codecs=opus' };
      } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
        options = { mimeType: 'audio/mp4' };
      }

      const mediaRecorder = new MediaRecorder(stream, options);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = () => {
        const finalDuration = (Date.now() - startTimeRef.current) / 1000;
        const blob = new Blob(chunksRef.current, { type: mediaRecorder.mimeType || 'audio/webm' });
        const url = URL.createObjectURL(blob);
        cleanupAudioStream();
        setSpeechState('idle');

        // Perform Voice Frequency & Pitch Dynamics Validation
        const validation = validateVoiceFrequencyDynamics(
          frequencySnapshotsRef.current,
          finalDuration,
          minSeconds
        );

        if (!validation.isValid) {
          // Voice frequency variation missing or recording invalid -> prompt to re-record
          setRecordedBlob(null);
          setPreviewUrl(null);
          setValidationSuccess(false);
          setErrorMessage(validation.message);
          return;
        }

        // Voice frequency variation confirmed -> Accept recording
        setRecordedBlob(blob);
        setPreviewUrl(url);
        setErrorMessage(null);
        setValidationSuccess(true);

        onRecordingComplete({
          promptId,
          blob,
          url,
          duration: finalDuration,
          voiceValidated: true,
          stats: validation.stats,
        });
      };

      mediaRecorder.start(100);
      setIsRecording(true);
      startTimeRef.current = Date.now();
      setElapsedSeconds(0);

      if (onStart) onStart();

      // Sample frequency spectrum every 50ms to measure voice frequency & pitch variation
      const binCount = analyser.frequencyBinCount;
      const freqData = new Uint8Array(binCount);

      sampleIntervalRef.current = setInterval(() => {
        if (!analyser) return;

        analyser.getByteFrequencyData(freqData);

        // Vocal spectrum analysis across speech range (bins 1 to 45 = ~150Hz to 4000Hz)
        let totalEnergy = 0;
        let weightedSum = 0;
        let peakVal = 0;
        let peakBin = 1;

        const startBin = 1;
        const endBin = Math.min(45, binCount);

        for (let i = startBin; i < endBin; i++) {
          const val = freqData[i];
          totalEnergy += val;
          weightedSum += i * val;
          if (val > peakVal) {
            peakVal = val;
            peakBin = i;
          }
        }

        const avgEnergy = totalEnergy / (endBin - startBin);
        const centroid = totalEnergy > 0 ? weightedSum / totalEnergy : 0;
        const now = Date.now();

        frequencySnapshotsRef.current.push({
          timeMs: now - startTimeRef.current,
          energy: avgEnergy,
          centroid: centroid,
          peakBin: peakBin,
          peakVal: peakVal,
        });

        // ── Automatic End-of-Speech Detection ─────────────────────────────────
        // When user is speaking near device:
        if (avgEnergy >= 13) {
          lastVoiceTimeRef.current = now;
          voicedFramesCountRef.current += 1;
          setSpeechState('speaking');
        } else {
          // When user stops speaking (silence after at least ~1.0s of active speech):
          if (voicedFramesCountRef.current >= 18 && lastVoiceTimeRef.current > 0) {
            const silenceMs = now - lastVoiceTimeRef.current;

            if (silenceMs >= 600) {
              setSpeechState('finishing');
            }

            // User has stopped speaking for ~1.2 seconds -> automatically finish and validate!
            if (silenceMs >= 1200 && !autoStopTriggeredRef.current) {
              autoStopTriggeredRef.current = true;
              stopRecording();
            }
          }
        }
      }, 50);

      // Duration counter
      timerIntervalRef.current = setInterval(() => {
        const seconds = (Date.now() - startTimeRef.current) / 1000;
        setElapsedSeconds(seconds);

        if (seconds >= maxSeconds) {
          stopRecording();
        }
      }, 100);

    } catch (err) {
      console.error('Microphone access error:', err);
      setErrorMessage('Microphone access denied or unavailable. Please check browser permissions.');
      if (onStop) onStop();
    }
  };

  const stopRecording = () => {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    if (sampleIntervalRef.current) {
      clearInterval(sampleIntervalRef.current);
      sampleIntervalRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    if (onStop) onStop();
  };

  const handleRedo = () => {
    setRecordedBlob(null);
    setPreviewUrl(null);
    setErrorMessage(null);
    setValidationSuccess(null);
    setSpeechState('idle');
    setElapsedSeconds(0);
    frequencySnapshotsRef.current = [];
    autoStopTriggeredRef.current = false;
    voicedFramesCountRef.current = 0;
    if (onRedo) onRedo(promptId);
  };

  // Helper for dynamic pill badge based on speech state
  const getSpeechPillContent = () => {
    if (!isRecording) {
      return {
        bg: '#ecfdf5',
        border: '#a7f3d0',
        color: 'var(--accent-emerald)',
        dotColor: 'var(--accent-emerald)',
        text: 'Click microphone to record',
      };
    }
    if (speechState === 'finishing') {
      return {
        bg: '#f0fdf4',
        border: '#86efac',
        color: '#15803d',
        dotColor: '#16a34a',
        text: '🤫 Speech finished — validating & moving to next prompt...',
      };
    }
    if (speechState === 'speaking') {
      return {
        bg: '#ecfdf5',
        border: '#6ee7b7',
        color: '#047857',
        dotColor: '#059669',
        text: '🗣️ Voice detected — keep reading...',
      };
    }
    return {
      bg: '#fef2f2',
      border: '#fecaca',
      color: 'var(--accent-rose)',
      dotColor: 'var(--accent-rose)',
      text: '🎙️ Speak prompt near your microphone...',
    };
  };

  const pill = getSpeechPillContent();

  return (
    <div className="recorder-box">
      {/* Error & Re-record Warning Banner */}
      {errorMessage && (
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.65rem',
          color: '#991b1b',
          background: '#fef2f2',
          border: '1.5px solid #fecaca',
          padding: '0.85rem 1.15rem',
          borderRadius: 'var(--radius-md)',
          width: '100%',
          maxWidth: '560px',
          fontSize: '0.9rem',
          lineHeight: '1.45',
          boxShadow: '0 2px 8px rgba(239, 68, 68, 0.08)',
        }}>
          <AlertCircle size={20} color="#dc2626" style={{ flexShrink: 0, marginTop: '2px' }} />
          <div>
            <strong style={{ display: 'block', color: '#b91c1c', marginBottom: '0.2rem' }}>
              Recording Not Accepted
            </strong>
            <span>{errorMessage}</span>
          </div>
        </div>
      )}

      {/* Audio Waveform Visualizer */}
      <AudioVisualizer
        analyser={analyserNode}
        isRecording={isRecording}
      />

      {/* Timer & Window Limits */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        fontSize: '1.1rem',
        fontWeight: 700,
        fontFamily: 'var(--font-heading)',
        color: isRecording ? 'var(--accent-rose)' : 'var(--text-secondary)',
      }}>
        <span>
          {isRecording ? `${elapsedSeconds.toFixed(1)}s` : recordedBlob ? `${(existingRecording?.duration || elapsedSeconds).toFixed(1)}s` : '0.0s'}
        </span>
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 500 }}>
          / {maxSeconds}s max (10–15s recommended)
        </span>
      </div>

      {/* Main Recording Action Controls */}
      {!recordedBlob ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem' }}>
          <div className="record-btn-wrapper">
            {isRecording && <div className="record-pulse-ring" />}
            <button
              type="button"
              className={`record-main-btn ${isRecording ? 'recording' : 'idle'}`}
              onClick={isRecording ? stopRecording : startRecording}
              title={isRecording ? 'Stop Recording' : 'Start Recording'}
            >
              {isRecording ? <Square size={28} /> : <Mic size={32} />}
            </button>
          </div>

          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.45rem',
            padding: '0.28rem 0.9rem',
            borderRadius: '999px',
            background: pill.bg,
            border: `1px solid ${pill.border}`,
            fontSize: '0.8rem',
            color: pill.color,
            fontWeight: 600,
            transition: 'all 0.2s ease',
          }}>
            <span style={{
              width: '7px',
              height: '7px',
              borderRadius: '50%',
              background: pill.dotColor,
              boxShadow: `0 0 6px ${pill.dotColor}`,
            }} />
            <span>{pill.text}</span>
          </div>
        </div>
      ) : (
        <div className="playback-preview-box">
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            color: 'var(--accent-emerald)',
            fontWeight: 700,
            fontSize: '0.95rem',
          }}>
            <Check size={19} />
            <span>Voice Frequency & Pitch Verified ✓</span>
          </div>

          {previewUrl && (
            <audio
              controls
              src={previewUrl}
              className="audio-element"
            />
          )}

          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleRedo}
            >
              <RotateCcw size={16} />
              <span>Re-record</span>
            </button>
          </div>
        </div>
      )}

      <p style={{
        fontSize: '0.86rem',
        color: 'var(--text-muted)',
        textAlign: 'center',
        maxWidth: '480px',
      }}>
        {isRecording
          ? 'Read the prompt aloud near your device. When you stop speaking, it will automatically validate and advance!'
          : recordedBlob
          ? 'Recording verified and saved! Listen above or re-record if needed.'
          : 'Read the displayed prompt within 10 to 15 seconds.'}
      </p>
    </div>
  );
}
