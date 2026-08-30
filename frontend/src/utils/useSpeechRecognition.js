/**
 * Strict Speech-to-Text Word Matching Engine
 *
 * CORE RULE: Words ONLY change color when the Web Speech API recognizes
 * that the user has spoken those specific words from the prompt.
 * NO energy-based, time-based, or cadence-based auto-advancing.
 *
 * If the browser does not support Web Speech API, words will not
 * change color (the recording still works, just without live highlighting).
 */

import { useState, useRef, useEffect, useCallback } from 'react';

// Multilingual Number Dictionary
const NUMBER_GROUPS = [
  ['0', 'zero', 'oh', 'o', 'शून्य', '०', 'shunya', 'shoonya', 'null'],
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
  ['15', 'fifteen', 'पंद्रह', 'पंधरा', '१५', 'pandrah', 'pandhara'],
  ['1000', 'thousand', 'हज़ार', 'हजार', 'hazaar', 'hazar'],
];

const DEVA_DIGIT_MAP = {
  '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
  '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'
};

function normalizeText(str) {
  if (!str) return '';
  return str
    .toLowerCase()
    .replace(/[\u093C]/g, '')
    .replace(/\u0901/g, '\u0902')
    .replace(/[.,/#!$%^&*;:{}=\-_`~()?"''।?,।|«»""॥\u200B-\u200D]/g, '')
    .trim();
}

function wordsMatch(targetWord, targetRomanizedWord, spokenWord) {
  const t = normalizeText(targetWord);
  const tr = normalizeText(targetRomanizedWord);
  const s = normalizeText(spokenWord);

  if (!s) return false;
  if (t && t === s) return true;
  if (tr && tr === s) return true;

  for (const group of NUMBER_GROUPS) {
    const sInGroup = group.includes(s) || (DEVA_DIGIT_MAP[s] && group.includes(DEVA_DIGIT_MAP[s]));
    if (sInGroup) {
      if (t && (group.includes(t) || (DEVA_DIGIT_MAP[t] && group.includes(DEVA_DIGIT_MAP[t])))) return true;
      if (tr && group.includes(tr)) return true;
    }
  }

  if (DEVA_DIGIT_MAP[s]) {
    const digitStr = DEVA_DIGIT_MAP[s];
    if (t === digitStr || tr === digitStr) return true;
  }

  if (t && t.length >= 3 && s.length >= 3) {
    if (t.startsWith(s) || s.startsWith(t)) return true;
  }
  if (tr && tr.length >= 3 && s.length >= 3) {
    if (tr.startsWith(s) || s.startsWith(tr)) return true;
  }

  const isFuzzyMatch = (str) => {
    if (!str || str.length < 4 || s.length < 4) return false;
    let diff = 0;
    const minLen = Math.min(str.length, s.length);
    for (let i = 0; i < minLen; i++) {
      if (str[i] !== s[i]) diff++;
    }
    diff += Math.abs(str.length - s.length);
    return diff <= 1;
  };

  if (isFuzzyMatch(t) || isFuzzyMatch(tr)) return true;

  return false;
}

function expandSpokenTokens(rawTokens) {
  const expanded = [];
  for (const raw of rawTokens) {
    const clean = normalizeText(raw);
    if (!clean) continue;
    if (/^[\d०-९]+$/.test(clean) && clean.length > 1) {
      for (const char of clean) {
        expanded.push(DEVA_DIGIT_MAP[char] || char);
      }
    } else {
      expanded.push(raw);
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

  useEffect(() => { onAllWordsReadRef.current = onAllWordsRead; }, [onAllWordsRead]);
  useEffect(() => { autoCompleteRef.current = autoComplete; }, [autoComplete]);

  const promptWordsRef = useRef([]);
  const romanizedWordsRef = useRef([]);

  useEffect(() => {
    promptWordsRef.current = promptText ? promptText.trim().split(/\s+/).filter(Boolean) : [];
    romanizedWordsRef.current = romanizedText ? romanizedText.trim().split(/\s+/).filter(Boolean) : [];
  }, [promptText, romanizedText]);

  // Check browser SpeechRecognition support
  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    setIsSupported(Boolean(SR));
  }, []);

  // Reset state when prompt changes
  useEffect(() => {
    setReadWordIndex(-1);
    setRecognizedTranscript('');
    setIsCompleted(false);
    completedRef.current = false;
  }, [promptText]);

  // Clean up on unmount
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
    setReadWordIndex(promptWordsRef.current.length - 1);

    if (autoCompleteRef.current && onAllWordsReadRef.current) {
      setTimeout(() => {
        if (onAllWordsReadRef.current) {
          onAllWordsReadRef.current();
        }
      }, 800);
    }
  }, []);

  const startListening = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('[SpeechRecognition] Not supported in this browser.');
      return;
    }

    isListeningRef.current = true;
    setIsListening(true);
    completedRef.current = false;
    setIsCompleted(false);
    setReadWordIndex(-1);
    setRecognizedTranscript('');

    try {
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch (e) {}
      }

      const recognition = new SpeechRecognition();
      recognitionRef.current = recognition;

      if (language === 'hindi') {
        recognition.lang = 'hi-IN';
      } else if (language === 'marathi') {
        recognition.lang = 'mr-IN';
      } else {
        recognition.lang = 'en-IN';
      }

      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 3;

      recognition.onresult = (event) => {
        if (!isListeningRef.current || completedRef.current) return;

        // Build full transcript from all result segments
        let fullTranscript = '';
        for (let i = 0; i < event.results.length; i++) {
          fullTranscript += event.results[i][0].transcript + ' ';
        }
        fullTranscript = fullTranscript.trim();
        setRecognizedTranscript(fullTranscript);

        const rawTokens = fullTranscript.split(/\s+/).filter(Boolean);
        const spokenTokens = expandSpokenTokens(rawTokens);
        const targetWords = promptWordsRef.current;
        const targetRomanized = romanizedWordsRef.current;

        if (!targetWords.length || !spokenTokens.length) return;

        // Match spoken tokens against prompt words sequentially
        let currentTargetIdx = 0;
        for (let sIdx = 0; sIdx < spokenTokens.length && currentTargetIdx < targetWords.length; sIdx++) {
          const spoken = spokenTokens[sIdx];

          // Lookahead up to 3 words to handle skipped filler words
          let matchedOffset = -1;
          for (let offset = 0; offset <= 3 && currentTargetIdx + offset < targetWords.length; offset++) {
            const tw = targetWords[currentTargetIdx + offset];
            const tr = targetRomanized[currentTargetIdx + offset] || '';
            if (wordsMatch(tw, tr, spoken)) {
              matchedOffset = offset;
              break;
            }
          }

          if (matchedOffset >= 0) {
            currentTargetIdx += matchedOffset + 1;
          }
        }

        // Only update readWordIndex based on confirmed spoken word matches
        const newReadIdx = Math.min(currentTargetIdx - 1, targetWords.length - 1);
        if (newReadIdx >= 0) {
          setReadWordIndex((prev) => Math.max(prev, newReadIdx));
        }

        // Complete when >= 85% of words are matched
        if (currentTargetIdx >= Math.ceil(targetWords.length * 0.85)) {
          triggerCompletion();
        }
      };

      recognition.onerror = (e) => {
        if (e.error !== 'no-speech' && e.error !== 'aborted') {
          console.debug('[SpeechRecognition]', e.error);
        }
      };

      recognition.onend = () => {
        // Auto-restart while still recording
        if (isListeningRef.current && !completedRef.current) {
          try { recognition.start(); } catch (e) {}
        }
      };

      recognition.start();
    } catch (err) {
      console.warn('[SpeechRecognition] Could not start:', err);
    }
  }, [language, triggerCompletion]);

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
    setRecognizedTranscript('');
    setIsCompleted(false);
    completedRef.current = false;
  }, [stopListening]);

  return {
    isSupported,
    isListening,
    readWordIndex,
    recognizedTranscript,
    isCompleted,
    startListening,
    stopListening,
    reset,
  };
}
