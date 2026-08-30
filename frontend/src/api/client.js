/**
 * API Client for Voice Authenticity Dataset Collector Backend
 */

const API_BASE = '/api';

export async function getConfig() {
  const res = await fetch(`${API_BASE}/config`);
  if (!res.ok) {
    throw new Error(`Failed to load config: ${res.statusText}`);
  }
  return res.json();
}

export async function getContributorStats() {
  const res = await fetch(`${API_BASE}/config/stats`);
  if (!res.ok) {
    throw new Error(`Failed to load stats: ${res.statusText}`);
  }
  return res.json();
}

export async function submitContributionSession(metadata, recordingsMap) {
  const formData = new FormData();
  formData.append('metadata', JSON.stringify(metadata));

  for (const [promptId, audioBlob] of Object.entries(recordingsMap)) {
    formData.append(`file_${promptId}`, audioBlob, `${promptId}.webm`);
  }

  let res;
  try {
    res = await fetch(`${API_BASE}/contributions/submit`, {
      method: 'POST',
      body: formData,
    });
  } catch (networkErr) {
    throw new Error('Network error: Could not reach the server. Please check your connection and try again.');
  }

  let data;
  const rawText = await res.text();
  try {
    data = rawText ? JSON.parse(rawText) : {};
  } catch (parseErr) {
    if (!res.ok) {
      throw new Error(`Server returned HTTP ${res.status} (${res.statusText || 'Upload Error'})`);
    }
    throw new Error('Server returned an unreadable response format.');
  }

  if (!res.ok) {
    throw new Error(data.detail || data.message || `Upload failed with status ${res.status}`);
  }
  return data;
}


export async function generatePrompt(language, promptId, topic) {
  const res = await fetch(`${API_BASE}/config/generate-prompt`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      language,
      prompt_id: promptId,
      topic,
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to generate prompt: ${res.statusText}`);
  }
  return res.json();
}
