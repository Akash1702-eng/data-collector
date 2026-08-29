import React, { useState, useRef, useEffect } from 'react';
import { Mic, Square, RotateCcw, Check, AlertCircle } from 'lucide-react';
import AudioVisualizer from './AudioVisualizer';

export default function AudioRecorder({
  promptId,
  existingRecording,
  minSeconds = 1.0,
  maxSeconds = 15.0,
  stopTrigger = false,
  onStart,
  onStop,
  onRecordingComplete,
  onRedo,
  onAudioEnergy,
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [errorMessage, setErrorMessage] = useState(null);
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
  const energyIntervalRef = useRef(null);

  // External stop trigger (e.g. speech recognition detected all words read)
  useEffect(() => {
    if (stopTrigger && isRecording) {
      const elapsed = (Date.now() - startTimeRef.current) / 1000;
      if (elapsed >= minSeconds) {
        stopRecording();
      }
    }
  }, [stopTrigger, isRecording, minSeconds]);

  // Sync with existing recording if prompt changes
  useEffect(() => {
    if (existingRecording) {
      setRecordedBlob(existingRecording.blob);
      setPreviewUrl(existingRecording.url);
    } else {
      setRecordedBlob(null);
      setPreviewUrl(null);
    }
    setErrorMessage(null);
    setIsRecording(false);
    setElapsedSeconds(0);
  }, [promptId, existingRecording]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      cleanupAudioStream();
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      if (energyIntervalRef.current) clearInterval(energyIntervalRef.current);
    };
  }, []);

  const cleanupAudioStream = () => {
    if (energyIntervalRef.current) {
      clearInterval(energyIntervalRef.current);
      energyIntervalRef.current = null;
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
      sourceRef.current = source; // Keep ref to prevent Chrome GC bug

      // Store in state so AudioVisualizer re-renders and gets active analyser
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
        setRecordedBlob(blob);
        setPreviewUrl(url);
        cleanupAudioStream();

        if (finalDuration < minSeconds) {
          setErrorMessage(`Recording too short (${finalDuration.toFixed(1)}s). Minimum is ${minSeconds}s.`);
        } else {
          onRecordingComplete({
            promptId,
            blob,
            url,
            duration: finalDuration,
          });
        }
      };

      mediaRecorder.start(100);
      setIsRecording(true);
      startTimeRef.current = Date.now();
      setElapsedSeconds(0);

      // Inform parent that recording has started
      if (onStart) onStart({ analyser });

      // Live voice energy polling (for visualizer + speech tracking)
      const dataArr = new Uint8Array(analyser.frequencyBinCount);
      energyIntervalRef.current = setInterval(() => {
        if (analyser) {
          analyser.getByteFrequencyData(dataArr);
          let sum = 0;
          for (let i = 0; i < dataArr.length; i++) {
            sum += dataArr[i];
          }
          const avg = sum / dataArr.length;
          if (onAudioEnergy) {
            onAudioEnergy(avg);
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
    if (energyIntervalRef.current) {
      clearInterval(energyIntervalRef.current);
      energyIntervalRef.current = null;
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
    setElapsedSeconds(0);
    if (onRedo) onRedo(promptId);
  };

  return (
    <div className="recorder-box">
      {errorMessage && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          color: 'var(--accent-rose)',
          background: '#fef2f2',
          border: '1px solid #fecaca',
          padding: '0.7rem 1.15rem',
          borderRadius: 'var(--radius-md)',
          width: '100%',
          maxWidth: '480px',
          fontSize: '0.88rem',
        }}>
          <AlertCircle size={17} />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Audio Visualizer */}
      <AudioVisualizer
        analyser={analyserNode}
        isRecording={isRecording}
      />

      {/* Timer & Limits */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        fontSize: '1.05rem',
        fontWeight: 600,
        fontFamily: 'var(--font-heading)',
        color: isRecording ? 'var(--accent-rose)' : 'var(--text-secondary)',
      }}>
        <span>
          {isRecording ? `${elapsedSeconds.toFixed(1)}s` : recordedBlob ? `${(existingRecording?.duration || elapsedSeconds).toFixed(1)}s` : '0.0s'}
        </span>
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          / {maxSeconds}s max
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
            gap: '0.4rem',
            padding: '0.22rem 0.7rem',
            borderRadius: '999px',
            background: isRecording ? '#fef2f2' : '#ecfdf5',
            border: `1px solid ${isRecording ? '#fecaca' : '#a7f3d0'}`,
            fontSize: '0.76rem',
            color: isRecording ? 'var(--accent-rose)' : 'var(--accent-emerald)',
            fontWeight: 500,
          }}>
            <span style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: isRecording ? 'var(--accent-rose)' : 'var(--accent-emerald)',
              boxShadow: isRecording ? '0 0 6px var(--accent-rose)' : '0 0 6px var(--accent-emerald)',
            }} />
            <span>
              {isRecording
                ? 'Microphone live — speak the words on screen'
                : 'Microphone permission granted & ready'}
            </span>
          </div>
        </div>
      ) : (
        <div className="playback-preview-box">
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            color: 'var(--accent-emerald)',
            fontWeight: 600,
            fontSize: '0.92rem',
          }}>
            <Check size={18} />
            <span>Recording Accepted</span>
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
        fontSize: '0.85rem',
        color: 'var(--text-muted)',
        textAlign: 'center',
      }}>
        {isRecording
          ? 'Speak clearly into your microphone... As you read, words will highlight green and advance automatically!'
          : recordedBlob
          ? 'Listen to your clip above or click Re-record if you want to try again.'
          : 'Click the microphone button to start recording.'}
      </p>
    </div>
  );
}
