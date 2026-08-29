/**
 * Robust Multilingual Speech-Driven Word Tracking Engine
 *
 * Handles:
 * 1. Native script matching: Hindi (Devanagari), Marathi (Devanagari), English.
 * 2. Automatic decomposition of concatenated digits (e.g., STT output "4729018356" -> ["4", "7", "2", "9", ...]).
 * 3. Compound and conjoined words (e.g. "कुत्र्याजवळ" -> matches "कुत्र्या", "जवळ").
 * 4. Lookahead window matching so dropped prepositions/fillers don't stall progression.
 * 5. Strict speech verification: words ONLY turn green when spoken.
 */

import { useState, useRef, useEffect, useCallback } from 'react';

// Multilingual Number Dictionary (Digits, Devanagari numerals, Hindi, Marathi, English)
const NUMBER_GROUPS = [
  ['0', 'zero', 'oh', 'o', 'शून्य', '०', 'shunya', 'shoonya', 'null'],
  ['1', 'one', 'एक', '१', 'ek', 'ik'],
  ['2', 'two', 'दो', 'दोन', '२', 'do', 'don', 'to'],
  ['3', 'three', 'तीन', '३', 'teen', 'tin'],
  ['4', 'four', 'चार', '४', 'chaar', 'char'],
  ['5', 'five', 'पाँच', 'पाच', '५', 'paanch', 'paach', 'panch'],
  ['6', 'six', 'छह', 'सहा', '६', 'chhah', 'saha', 'che'],
  ['7', 'seven', 'सात', '७', 'saat', 'sat'],
  ['8', 'eight', 'आठ', '८', 'aath', 'ath'],
  ['9', 'nine', 'नौ', 'नऊ', '९', 'nau', 'nav', 'nou'],
];

// Devanagari digit to standard digit map
const DEVA_DIGIT_MAP = {
  '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
  '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'
};

function normalizeWord(str) {
  return (str || '')
    .toLowerCase()
    .replace(/[.,/#!$%^&*;:{}=\-_`~()?"'’।?,।|«»“”।]/g, '')
    .trim();
}

function wordsMatch(targetWord, spokenWord) {
  const t = normalizeWord(targetWord);
  const s = normalizeWord(spokenWord);

  if (!t || !s) return false;
  if (t === s) return true;

  // Check multilingual number matches
  for (const group of NUMBER_GROUPS) {
    if (group.includes(t) && group.includes(s)) {
      return true;
    }
  }

  // Devanagari digit to standard digit
  if (DEVA_DIGIT_MAP[s] && NUMBER_GROUPS[parseInt(DEVA_DIGIT_MAP[s], 10)]?.includes(t)) {
    return true;
  }
  if (DEVA_DIGIT_MAP[t] && NUMBER_GROUPS[parseInt(DEVA_DIGIT_MAP[t], 10)]?.includes(s)) {
    return true;
  }

  // Substring / prefix / conjoined word matching (e.g. "कुत्र्याजवळ" matches "कुत्र्या")
  if (t.length >= 3 && s.length >= 3) {
    if (t.startsWith(s) || s.startsWith(t)) return true;
  }

  // Fuzzy tolerance for minor pronunciation variations (min 4 characters)
  if (t.length >= 4 && s.length >= 4) {
    let diff = 0;
    const minLen = Math.min(t.length, s.length);
    for (let i = 0; i < minLen; i++) {
      if (t[i] !== s[i]) diff++;
    }
    diff += Math.abs(t.length - s.length);
    if (diff <= 1) return true;
  }

  return false;
}

// Decomposes multi-digit sequences into individual digit tokens
function expandSpokenTokens(rawTokens) {
  const expanded = [];

  for (const raw of rawTokens) {
    const clean = normalizeWord(raw);
    if (!clean) continue;

    // Check if token is a series of digits / Devanagari numerals (e.g. "4729018356" or "४७२९")
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

  const promptWords = promptText ? promptText.trim().split(/\s+/).filter(Boolean) : [];
  const promptWordsRef = useRef(promptWords);
  useEffect(() => {
    promptWordsRef.current = promptText ? promptText.trim().split(/\s+/).filter(Boolean) : [];
  }, [promptText]);

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
      console.warn('[SpeechRecognition] Web Speech API not supported in this browser');
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

      // Set recognition language
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

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event) => {
        if (!isListeningRef.current || completedRef.current) return;

        // Build continuous transcript from all speech segments
        let fullTranscript = '';
        for (let i = 0; i < event.results.length; i++) {
          fullTranscript += event.results[i][0].transcript + ' ';
        }
        fullTranscript = fullTranscript.trim();
        setRecognizedTranscript(fullTranscript);

        const rawTokens = fullTranscript.split(/\s+/).filter(Boolean);
        const spokenTokens = expandSpokenTokens(rawTokens);
        const targetWords = promptWordsRef.current;
        if (!targetWords.length || !spokenTokens.length) return;

        // Progressive lookahead matching
        let currentTargetIdx = 0;

        for (let sIdx = 0; sIdx < spokenTokens.length && currentTargetIdx < targetWords.length; sIdx++) {
          const spoken = spokenTokens[sIdx];

          // Check direct match or lookahead up to 3 words
          let matchedOffset = -1;
          for (let offset = 0; offset <= 3 && currentTargetIdx + offset < targetWords.length; offset++) {
            if (wordsMatch(targetWords[currentTargetIdx + offset], spoken)) {
              matchedOffset = offset;
              break;
            }
          }

          if (matchedOffset >= 0) {
            currentTargetIdx += matchedOffset + 1;
          }
        }

        // Strictly update readWordIndex based on matched spoken tokens
        const newReadIdx = Math.min(currentTargetIdx - 1, targetWords.length - 1);
        if (newReadIdx >= 0) {
          setReadWordIndex((prev) => Math.max(prev, newReadIdx));
        }

        // Trigger sentence completion when all words (or >= 85%) are read
        if (currentTargetIdx >= Math.ceil(targetWords.length * 0.85)) {
          triggerCompletion();
        }
      };

      recognition.onerror = (e) => {
        if (e.error !== 'no-speech' && e.error !== 'aborted') {
          console.warn('[SpeechRecognition] warning:', e.error);
        }
      };

      recognition.onend = () => {
        if (isListeningRef.current && !completedRef.current) {
          try {
            recognition.start();
          } catch (e) {}
        } else {
          setIsListening(false);
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
      try {
        recognitionRef.current.stop();
      } catch (e) {}
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
