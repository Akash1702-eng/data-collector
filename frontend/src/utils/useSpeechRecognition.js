/**
 * High-Speed Multilingual Speech Recognition & Voice-Tracking Engine
 *
 * Designed to handle both slow and fast speech seamlessly across Desktop & Mobile.
 *
 * Features:
 * 1. Global Forward Alignment: Matches spoken words even during rapid bursts,
 *    slurred syllables, contractions, or omitted filler words across the entire prompt.
 * 2. Compound Word & Number Decomposition: Decomposes numbers (e.g. "472" <-> "four seven two" <-> "चार सात दोन")
 *    and joined compound phrases.
 * 3. Instant Zero-Lag Voice Activity Tracking: On mobile/restricted environments,
 *    live voice energy (threshold >= 20) tracks speech at an adaptive fast pace (220-270ms/word),
 *    freezing immediately on silence.
 * 4. Dual-Mode Synchronization: STT matches take precedence and keep energy tracking in sync.
 */

import { useState, useRef, useEffect, useCallback } from 'react';

/* ── Multilingual Number & Digit Dictionary ───────────────────────────── */
const NUMBER_GROUPS = [
  ['0', 'zero', 'oh', 'o', 'शून्य', '०', 'shunya', 'shoonya', 'null'],
  ['1', 'one', 'एक', '१', 'ek', 'ik'],
  ['2', 'two', 'दो', 'दोन', '२', 'do', 'don', 'to', 'too'],
  ['3', 'three', 'तीन', '३', 'teen', 'tin', 'tri'],
  ['4', 'four', 'चार', '४', 'chaar', 'char', 'for'],
  ['5', 'five', 'पाँच', 'पांच', 'पाच', '५', 'paanch', 'paach', 'panch'],
  ['6', 'six', 'छह', 'सहा', '६', 'chhah', 'saha', 'che', 'chha'],
  ['7', 'seven', 'सात', '७', 'saat', 'sat'],
  ['8', 'eight', 'आठ', '८', 'aath', 'ath', 'ate'],
  ['9', 'nine', 'नौ', 'नऊ', '९', 'nau', 'nav', 'nou'],
  ['10', 'ten', 'दस', 'दहा', '१०', 'das', 'daha'],
  ['11', 'eleven', 'ग्यारह', 'अकरा', '११', 'gyarah', 'akara'],
  ['12', 'twelve', 'बारह', 'बारा', '१२', 'barah', 'bara'],
  ['13', 'thirteen', 'तेरह', 'तेरा', '१३', 'terah', 'tera'],
  ['14', 'fourteen', 'चौदह', 'चौदा', '१४', 'chaudah', 'chauda'],
  ['15', 'fifteen', 'पंद्रह', 'पंधरा', '१५', 'pandrah', 'pandhara'],
  ['16', 'sixteen', 'सोलह', 'सोळा', '१६', 'solah', 'sola'],
  ['17', 'seventeen', 'सत्रह', 'सतरा', '१७', 'satrah', 'satra'],
  ['18', 'eighteen', 'अठारह', 'अठरा', '१८', 'atharah', 'athara'],
  ['19', 'nineteen', 'उन्नीस', 'एकोणीस', '१९', 'unnees', 'ekonis'],
  ['20', 'twenty', 'बीस', 'वीस', '२०', 'bees', 'vis'],
  ['30', 'thirty', 'तीस', 'तीस', '३०', 'tees'],
  ['40', 'forty', 'चालीस', 'चाळीस', '४०', 'chalis'],
  ['50', 'fifty', 'पचास', 'पन्नास', '५०', 'pachas', 'pannas'],
  ['100', 'hundred', 'सौ', 'शंभर', '१००', 'sau', 'shambhar'],
  ['1000', 'thousand', 'हज़ार', 'हजार', '१०००', 'hazaar', 'hazar'],
];

const DEVA_DIGIT_MAP = {
  '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
  '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'
};

function normalizeText(str) {
  if (!str) return '';
  return str
    .toLowerCase()
    .replace(/[\u093C]/g, '')            // remove Nukta
    .replace(/\u0901/g, '\u0902')        // Chandrabindu -> Anusvara
    .replace(/[.,/#!$%^&*;:{}=\-_`~()?"''।?,।|«»""॥\u200B-\u200D]/g, '')
    .trim();
}

/**
 * Check if two single words match phonetically, textually, or numerically
 */
function singleWordMatch(target, targetRom, spoken) {
  const t = normalizeText(target);
  const tr = normalizeText(targetRom);
  const s = normalizeText(spoken);

  if (!s) return false;
  if (t && t === s) return true;
  if (tr && tr === s) return true;

  // Number dictionary check
  for (const group of NUMBER_GROUPS) {
    const sIn = group.includes(s) || (DEVA_DIGIT_MAP[s] && group.includes(DEVA_DIGIT_MAP[s]));
    if (sIn) {
      if (t && (group.includes(t) || (DEVA_DIGIT_MAP[t] && group.includes(DEVA_DIGIT_MAP[t])))) return true;
      if (tr && group.includes(tr)) return true;
    }
  }

  // Direct digit check
  if (DEVA_DIGIT_MAP[s] && (t === DEVA_DIGIT_MAP[s] || tr === DEVA_DIGIT_MAP[s])) return true;

  // Prefix matching for words >= 3 chars
  if (t && t.length >= 3 && s.length >= 3 && (t.startsWith(s) || s.startsWith(t))) return true;
  if (tr && tr.length >= 3 && s.length >= 3 && (tr.startsWith(s) || s.startsWith(tr))) return true;

  // Levenshtein fuzzy matching (1 edit for len >= 4, 2 edits for len >= 7)
  const isFuzzy = (targetStr) => {
    if (!targetStr || targetStr.length < 4 || s.length < 4) return false;
    const maxDiff = targetStr.length >= 7 && s.length >= 7 ? 2 : 1;
    let diff = 0;
    const minLen = Math.min(targetStr.length, s.length);
    for (let i = 0; i < minLen; i++) {
      if (targetStr[i] !== s[i]) diff++;
    }
    diff += Math.abs(targetStr.length - s.length);
    return diff <= maxDiff;
  };

  return isFuzzy(t) || isFuzzy(tr);
}

/**
 * Expand digit sequences (e.g., "472" -> ["4", "7", "2"])
 */
function expandTokens(tokens) {
  const expanded = [];
  for (const raw of tokens) {
    const clean = normalizeText(raw);
    if (!clean) continue;
    if (/^[\d०-९]+$/.test(clean) && clean.length > 1) {
      for (const char of clean) {
        expanded.push(DEVA_DIGIT_MAP[char] || char);
      }
    } else {
      expanded.push(clean);
    }
  }
  return expanded;
}

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

  const recognitionRef = useRef(null);
  const completedRef = useRef(false);
  const isListeningRef = useRef(false);
  const onAllWordsReadRef = useRef(onAllWordsRead);
  const autoCompleteRef = useRef(autoComplete);
  const readWordIndexRef = useRef(-1);

  // STT detection tracking
  const sttActiveRef = useRef(false);

  // Fast-adaptive voice energy tracking
  const activeSpeechMsRef = useRef(0);
  const lastEnergyTimeRef = useRef(0);
  const ENERGY_THRESHOLD = 20; // Human vocal threshold (silence is 2-8)

  useEffect(() => { onAllWordsReadRef.current = onAllWordsRead; }, [onAllWordsRead]);
  useEffect(() => { autoCompleteRef.current = autoComplete; }, [autoComplete]);

  const promptWordsRef = useRef([]);
  const romanizedWordsRef = useRef([]);

  useEffect(() => {
    promptWordsRef.current = promptText ? promptText.trim().split(/\s+/).filter(Boolean) : [];
    romanizedWordsRef.current = romanizedText ? romanizedText.trim().split(/\s+/).filter(Boolean) : [];
  }, [promptText, romanizedText]);

  // Check browser support
  useEffect(() => {
    setIsSupported(Boolean(window.SpeechRecognition || window.webkitSpeechRecognition));
  }, []);

  // Reset state on prompt change
  useEffect(() => {
    setReadWordIndex(-1);
    readWordIndexRef.current = -1;
    setRecognizedTranscript('');
    setIsCompleted(false);
    completedRef.current = false;
    sttActiveRef.current = false;
    activeSpeechMsRef.current = 0;
    lastEnergyTimeRef.current = 0;
  }, [promptText]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch (e) {}
      }
    };
  }, []);

  const triggerCompletion = useCallback(() => {
    if (completedRef.current) return;
    completedRef.current = true;
    setIsCompleted(true);
    const lastIdx = promptWordsRef.current.length - 1;
    setReadWordIndex(lastIdx);
    readWordIndexRef.current = lastIdx;

    if (autoCompleteRef.current && onAllWordsReadRef.current) {
      setTimeout(() => {
        onAllWordsReadRef.current?.();
      }, 700);
    }
  }, []);

  const advanceToIndex = useCallback((newIdx) => {
    const totalWords = promptWordsRef.current.length;
    if (totalWords === 0) return;

    const clamped = Math.min(newIdx, totalWords - 1);
    if (clamped > readWordIndexRef.current) {
      readWordIndexRef.current = clamped;
      setReadWordIndex(clamped);

      // Keep energy accumulator in sync with current word position
      activeSpeechMsRef.current = Math.max(activeSpeechMsRef.current, (clamped + 1) * 260);
    }

    // Complete if >= 80% of words are read or reached last/second-to-last word
    if (clamped >= totalWords - 1 || clamped >= Math.ceil(totalWords * 0.8) - 1) {
      if (clamped >= totalWords - 2) {
        triggerCompletion();
      }
    }
  }, [triggerCompletion]);

  /**
   * Real-time audio energy handler (called every 50ms from AudioRecorder)
   */
  const feedAudioEnergy = useCallback((energy) => {
    if (!isListeningRef.current || completedRef.current) return;

    const now = Date.now();
    const totalWords = promptWordsRef.current.length;
    if (totalWords === 0) return;

    if (energy >= ENERGY_THRESHOLD) {
      // User is actively speaking into the microphone
      const delta = lastEnergyTimeRef.current ? Math.min(now - lastEnergyTimeRef.current, 100) : 50;
      
      // Dynamic speech speed: fast loud speech (~220ms/word) vs normal speech (~270ms/word)
      const speedFactor = energy > 38 ? 1.25 : energy > 28 ? 1.1 : 1.0;
      activeSpeechMsRef.current += delta * speedFactor;

      const msPerWord = 260; // Fast natural speech baseline (~230 WPM)
      const wordsCalculated = Math.floor(activeSpeechMsRef.current / msPerWord);

      if (wordsCalculated > 0) {
        advanceToIndex(wordsCalculated - 1);
      }
    }
    // When energy < ENERGY_THRESHOLD (silence/pause), accumulator is frozen

    lastEnergyTimeRef.current = now;
  }, [advanceToIndex]);

  /**
   * Global forward matching algorithm
   * Matches spoken words against prompt words across the entire remaining prompt
   */
  const processTranscript = useCallback((transcriptText) => {
    const rawTokens = transcriptText.split(/\s+/).filter(Boolean);
    const spoken = expandTokens(rawTokens);
    const target = promptWordsRef.current;
    const targetRom = romanizedWordsRef.current;

    if (!target.length || !spoken.length) return;

    let targetIdx = 0;
    let sIdx = 0;

    while (sIdx < spoken.length && targetIdx < target.length) {
      const sWord = spoken[sIdx];
      let foundTargetIdx = -1;
      let consumedSpokenCount = 1;

      // 1. Single word search across remaining prompt
      for (let t = targetIdx; t < target.length; t++) {
        if (singleWordMatch(target[t], targetRom[t] || '', sWord)) {
          foundTargetIdx = t;
          consumedSpokenCount = 1;
          break;
        }
      }

      // 2. Compound spoken check (e.g. spoken[i] + spoken[i+1] matches target[t])
      if (foundTargetIdx === -1 && sIdx + 1 < spoken.length) {
        const sCombined = sWord + spoken[sIdx + 1];
        for (let t = targetIdx; t < target.length; t++) {
          if (singleWordMatch(target[t], targetRom[t] || '', sCombined)) {
            foundTargetIdx = t;
            consumedSpokenCount = 2;
            break;
          }
        }
      }

      // 3. Compound target check (e.g. target[t] + target[t+1] matches spoken[i])
      if (foundTargetIdx === -1) {
        for (let t = targetIdx; t + 1 < target.length; t++) {
          const tCombined = target[t] + target[t + 1];
          const trCombined = (targetRom[t] || '') + (targetRom[t + 1] || '');
          if (singleWordMatch(tCombined, trCombined, sWord)) {
            foundTargetIdx = t + 1;
            consumedSpokenCount = 1;
            break;
          }
        }
      }

      if (foundTargetIdx !== -1) {
        targetIdx = foundTargetIdx + 1;
        sIdx += consumedSpokenCount;
      } else {
        sIdx += 1;
      }
    }

    if (targetIdx > 0) {
      advanceToIndex(targetIdx - 1);
    }
  }, [advanceToIndex]);

  const startListening = useCallback(() => {
    isListeningRef.current = true;
    setIsListening(true);
    completedRef.current = false;
    setIsCompleted(false);
    setReadWordIndex(-1);
    readWordIndexRef.current = -1;
    setRecognizedTranscript('');
    sttActiveRef.current = false;
    activeSpeechMsRef.current = 0;
    lastEnergyTimeRef.current = 0;

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    try {
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch (e) {}
      }

      const recognition = new SR();
      recognitionRef.current = recognition;

      recognition.lang = language === 'hindi' ? 'hi-IN' : language === 'marathi' ? 'mr-IN' : 'en-IN';
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 3;

      recognition.onresult = (event) => {
        if (!isListeningRef.current || completedRef.current) return;
        sttActiveRef.current = true;

        let fullTranscript = '';
        for (let i = 0; i < event.results.length; i++) {
          fullTranscript += event.results[i][0].transcript + ' ';
        }
        fullTranscript = fullTranscript.trim();
        setRecognizedTranscript(fullTranscript);

        processTranscript(fullTranscript);
      };

      recognition.onerror = (e) => {
        if (e.error !== 'no-speech' && e.error !== 'aborted') {
          console.debug('[SpeechRecognition]', e.error);
        }
      };

      recognition.onend = () => {
        if (isListeningRef.current && !completedRef.current) {
          try { recognition.start(); } catch (e) {}
        }
      };

      recognition.start();
    } catch (err) {
      console.warn('[SpeechRecognition] Could not start:', err);
    }
  }, [language, processTranscript]);

  const stopListening = useCallback(() => {
    isListeningRef.current = false;
    setIsListening(false);
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch (e) {}
      recognitionRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    stopListening();
    setReadWordIndex(-1);
    readWordIndexRef.current = -1;
    setRecognizedTranscript('');
    setIsCompleted(false);
    completedRef.current = false;
    sttActiveRef.current = false;
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
