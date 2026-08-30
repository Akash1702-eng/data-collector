/**
 * Hybrid Speech Recognition Engine
 *
 * Strategy:
 *  1. PRIMARY: Web Speech API STT — exact word matching (works on desktop)
 *  2. FALLBACK: Energy-based voice tracking — activates ONLY when STT
 *     has definitively failed (mobile browsers where MediaRecorder blocks STT)
 *
 * The energy fallback uses a HIGH threshold (avg energy >= 22) so ambient
 * noise and silence never trigger word advancement. Only clear, sustained
 * speech directed at the microphone causes words to advance.
 */

import { useState, useRef, useEffect, useCallback } from 'react';

/* ── Multilingual Number Dictionary ───────────────────────────── */
const NUMBER_GROUPS = [
  ['0', 'zero', 'oh', 'o', 'शून्य', '०', 'shunya', 'shoonya'],
  ['1', 'one', 'एक', '१', 'ek', 'ik'],
  ['2', 'two', 'दो', 'दोन', '२', 'do', 'don', 'to'],
  ['3', 'three', 'तीन', '३', 'teen', 'tin'],
  ['4', 'four', 'चार', '४', 'chaar', 'char'],
  ['5', 'five', 'पाँच', 'पांच', 'पाच', '५', 'paanch', 'paach', 'panch'],
  ['6', 'six', 'छह', 'सहा', '६', 'chhah', 'saha', 'che', 'chha'],
  ['7', 'seven', 'सात', '७', 'saat', 'sat'],
  ['8', 'eight', 'आठ', '८', 'aath', 'ath'],
  ['9', 'nine', 'नौ', 'नऊ', '९', 'nau', 'nav', 'nou'],
  ['10', 'ten', 'दस', 'दहा', '१०', 'das', 'daha'],
];

const DEVA_DIGIT = { '०':'0','१':'1','२':'2','३':'3','४':'4','५':'5','६':'6','७':'7','८':'8','९':'9' };

function norm(s) {
  if (!s) return '';
  return s.toLowerCase()
    .replace(/[\u093C]/g, '')            // nukta
    .replace(/\u0901/g, '\u0902')        // chandrabindu → anusvara
    .replace(/[.,/#!$%^&*;:{}=\-_`~()?"''।?,।|«»""॥\u200B-\u200D]/g, '')
    .trim();
}

function wordsMatch(target, targetRom, spoken) {
  const t = norm(target), tr = norm(targetRom), s = norm(spoken);
  if (!s) return false;
  if (t && t === s) return true;
  if (tr && tr === s) return true;

  // Number group match
  for (const g of NUMBER_GROUPS) {
    const sIn = g.includes(s) || (DEVA_DIGIT[s] && g.includes(DEVA_DIGIT[s]));
    if (sIn) {
      if (t && (g.includes(t) || (DEVA_DIGIT[t] && g.includes(DEVA_DIGIT[t])))) return true;
      if (tr && g.includes(tr)) return true;
    }
  }

  // Digit mapping
  if (DEVA_DIGIT[s] && (t === DEVA_DIGIT[s] || tr === DEVA_DIGIT[s])) return true;

  // Prefix match (≥3 chars)
  if (t && t.length >= 3 && s.length >= 3 && (t.startsWith(s) || s.startsWith(t))) return true;
  if (tr && tr.length >= 3 && s.length >= 3 && (tr.startsWith(s) || s.startsWith(tr))) return true;

  // 1-char fuzzy
  const fuzzy = (a) => {
    if (!a || a.length < 4 || s.length < 4) return false;
    let d = 0;
    for (let i = 0; i < Math.min(a.length, s.length); i++) { if (a[i] !== s[i]) d++; }
    return (d + Math.abs(a.length - s.length)) <= 1;
  };
  return fuzzy(t) || fuzzy(tr);
}

function expandTokens(tokens) {
  const out = [];
  for (const raw of tokens) {
    const c = norm(raw);
    if (!c) continue;
    if (/^[\d०-९]+$/.test(c) && c.length > 1) {
      for (const ch of c) out.push(DEVA_DIGIT[ch] || ch);
    } else {
      out.push(raw);
    }
  }
  return out;
}


/* ── Hook ────────────────────────────────────────────────────── */

export function useSpeechRecognition({
  promptText = '',
  romanizedText = '',
  language = 'english_indian',
  onAllWordsRead,
  autoComplete = true,
}) {
  const [isSupported, setIsSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [readWordIndex, setReadWordIndex] = useState(-1);
  const [recognizedTranscript, setRecognizedTranscript] = useState('');
  const [isCompleted, setIsCompleted] = useState(false);

  const recognitionRef     = useRef(null);
  const completedRef       = useRef(false);
  const isListeningRef     = useRef(false);
  const onAllWordsReadRef  = useRef(onAllWordsRead);
  const autoCompleteRef    = useRef(autoComplete);
  const readWordIndexRef   = useRef(-1);

  // STT health tracking — detect if STT is alive or dead
  const sttGotResultRef    = useRef(false);   // true once any onresult fires
  const sttFailedRef       = useRef(false);   // true when we've given up on STT
  const recordStartTimeRef = useRef(0);
  const energyCheckTimerRef = useRef(null);
  const voiceDetectedRef   = useRef(false);   // true if we've seen energy while STT silent

  // Energy fallback state
  const activeSpeechMsRef  = useRef(0);
  const lastEnergyTimeRef  = useRef(0);
  const MS_PER_WORD        = 420; // ~420ms per word at normal reading pace
  const ENERGY_THRESHOLD   = 22;  // average energy; well above ambient noise (~2-8)

  useEffect(() => { onAllWordsReadRef.current = onAllWordsRead; }, [onAllWordsRead]);
  useEffect(() => { autoCompleteRef.current = autoComplete; }, [autoComplete]);

  const promptWordsRef    = useRef([]);
  const romanizedWordsRef = useRef([]);

  useEffect(() => {
    promptWordsRef.current = promptText ? promptText.trim().split(/\s+/).filter(Boolean) : [];
    romanizedWordsRef.current = romanizedText ? romanizedText.trim().split(/\s+/).filter(Boolean) : [];
  }, [promptText, romanizedText]);

  // Check browser support
  useEffect(() => {
    setIsSupported(Boolean(window.SpeechRecognition || window.webkitSpeechRecognition));
  }, []);

  // Reset on prompt change
  useEffect(() => {
    setReadWordIndex(-1);
    readWordIndexRef.current = -1;
    setRecognizedTranscript('');
    setIsCompleted(false);
    completedRef.current = false;
    sttGotResultRef.current = false;
    sttFailedRef.current = false;
    voiceDetectedRef.current = false;
    activeSpeechMsRef.current = 0;
    lastEnergyTimeRef.current = 0;
  }, [promptText]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (recognitionRef.current) { try { recognitionRef.current.abort(); } catch(e){} }
      if (energyCheckTimerRef.current) clearTimeout(energyCheckTimerRef.current);
    };
  }, []);

  /* ── Completion trigger ──────────────────────────── */
  const triggerCompletion = useCallback(() => {
    if (completedRef.current) return;
    completedRef.current = true;
    setIsCompleted(true);
    const lastIdx = promptWordsRef.current.length - 1;
    setReadWordIndex(lastIdx);
    readWordIndexRef.current = lastIdx;

    if (autoCompleteRef.current && onAllWordsReadRef.current) {
      setTimeout(() => { onAllWordsReadRef.current?.(); }, 800);
    }
  }, []);

  /* ── Update readWordIndex (shared by both STT and energy) ── */
  const advanceToIndex = useCallback((newIdx) => {
    const clamped = Math.min(newIdx, promptWordsRef.current.length - 1);
    if (clamped > readWordIndexRef.current) {
      readWordIndexRef.current = clamped;
      setReadWordIndex(clamped);
    }
    if (clamped >= Math.ceil(promptWordsRef.current.length * 0.85) - 1) {
      triggerCompletion();
    }
  }, [triggerCompletion]);

  /* ── Energy-based fallback: called by AudioRecorder every ~50ms ── */
  const feedAudioEnergy = useCallback((energy) => {
    if (!isListeningRef.current || completedRef.current) return;

    const now = Date.now();

    // If STT is working, don't use energy fallback at all
    if (sttGotResultRef.current) return;

    // Track that voice was detected (for STT failure detection)
    if (energy >= ENERGY_THRESHOLD) {
      voiceDetectedRef.current = true;
    }

    // Only activate energy fallback after we've confirmed STT has failed
    if (!sttFailedRef.current) {
      // Check: if 3+ seconds have passed with voice detected but no STT results → STT failed
      const elapsed = now - recordStartTimeRef.current;
      if (elapsed > 3000 && voiceDetectedRef.current && !sttGotResultRef.current) {
        console.log('[SpeechRecognition] STT produced no results after 3s with voice detected. Activating energy fallback.');
        sttFailedRef.current = true;
      } else {
        return; // Don't use energy fallback yet
      }
    }

    // ── Energy fallback active ──
    if (energy >= ENERGY_THRESHOLD) {
      // User is speaking
      const delta = lastEnergyTimeRef.current ? (now - lastEnergyTimeRef.current) : 50;
      activeSpeechMsRef.current += Math.min(delta, 100); // cap at 100ms per tick

      const wordsShouldBeRead = Math.floor(activeSpeechMsRef.current / MS_PER_WORD);
      if (wordsShouldBeRead > 0) {
        advanceToIndex(wordsShouldBeRead - 1);
      }
    }
    // When energy < threshold: do NOT accumulate — words freeze in place

    lastEnergyTimeRef.current = now;
  }, [advanceToIndex]);

  /* ── Start listening ────────────────────────────── */
  const startListening = useCallback(() => {
    isListeningRef.current = true;
    setIsListening(true);
    completedRef.current = false;
    setIsCompleted(false);
    setReadWordIndex(-1);
    readWordIndexRef.current = -1;
    setRecognizedTranscript('');
    sttGotResultRef.current = false;
    sttFailedRef.current = false;
    voiceDetectedRef.current = false;
    activeSpeechMsRef.current = 0;
    lastEnergyTimeRef.current = 0;
    recordStartTimeRef.current = Date.now();

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      // No STT support at all — immediately enable energy fallback
      sttFailedRef.current = true;
      console.log('[SpeechRecognition] API not available. Using energy fallback.');
      return;
    }

    try {
      if (recognitionRef.current) { try { recognitionRef.current.abort(); } catch(e){} }

      const recognition = new SR();
      recognitionRef.current = recognition;

      recognition.lang = language === 'hindi' ? 'hi-IN' : language === 'marathi' ? 'mr-IN' : 'en-IN';
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 3;

      recognition.onresult = (event) => {
        if (!isListeningRef.current || completedRef.current) return;

        // Mark STT as alive — this disables energy fallback permanently for this session
        sttGotResultRef.current = true;

        let fullTranscript = '';
        for (let i = 0; i < event.results.length; i++) {
          fullTranscript += event.results[i][0].transcript + ' ';
        }
        fullTranscript = fullTranscript.trim();
        setRecognizedTranscript(fullTranscript);

        const spokenTokens = expandTokens(fullTranscript.split(/\s+/).filter(Boolean));
        const tw = promptWordsRef.current;
        const tr = romanizedWordsRef.current;
        if (!tw.length || !spokenTokens.length) return;

        // Sequential matching with lookahead
        let targetIdx = 0;
        for (let s = 0; s < spokenTokens.length && targetIdx < tw.length; s++) {
          for (let off = 0; off <= 3 && targetIdx + off < tw.length; off++) {
            if (wordsMatch(tw[targetIdx + off], tr[targetIdx + off] || '', spokenTokens[s])) {
              targetIdx += off + 1;
              break;
            }
          }
        }

        if (targetIdx > 0) {
          advanceToIndex(targetIdx - 1);
        }

        if (targetIdx >= Math.ceil(tw.length * 0.85)) {
          triggerCompletion();
        }
      };

      recognition.onerror = (e) => {
        if (e.error === 'not-allowed' || e.error === 'audio-capture' || e.error === 'service-not-allowed') {
          console.log(`[SpeechRecognition] Error: ${e.error}. Switching to energy fallback.`);
          sttFailedRef.current = true;
        }
      };

      recognition.onend = () => {
        if (isListeningRef.current && !completedRef.current) {
          try { recognition.start(); } catch(e) {}
        }
      };

      recognition.start();
    } catch (err) {
      console.warn('[SpeechRecognition] Could not start:', err);
      sttFailedRef.current = true;
    }
  }, [language, advanceToIndex, triggerCompletion]);

  /* ── Stop listening ─────────────────────────────── */
  const stopListening = useCallback(() => {
    isListeningRef.current = false;
    setIsListening(false);
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch(e) {}
      recognitionRef.current = null;
    }
    if (energyCheckTimerRef.current) {
      clearTimeout(energyCheckTimerRef.current);
      energyCheckTimerRef.current = null;
    }
  }, []);

  /* ── Reset ──────────────────────────────────────── */
  const reset = useCallback(() => {
    stopListening();
    setReadWordIndex(-1);
    readWordIndexRef.current = -1;
    setRecognizedTranscript('');
    setIsCompleted(false);
    completedRef.current = false;
    sttGotResultRef.current = false;
    sttFailedRef.current = false;
    voiceDetectedRef.current = false;
    activeSpeechMsRef.current = 0;
    lastEnergyTimeRef.current = 0;
  }, [stopListening]);

  return {
    isSupported,
    isListening,
    readWordIndex,
    recognizedTranscript,
    isCompleted,
    feedAudioEnergy,
    startListening,
    stopListening,
    reset,
  };
}
