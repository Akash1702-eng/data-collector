"""
🎤 Record — Human voice collection flow.
Every contributor records 3 prompts in EACH of 3 languages (Hindi, Marathi, English)
for a total of 9 recordings per session.

Flow: Consent → Profile → Record (9 prompts across 3 languages) → Upload → Thank you.
After upload, AI voice is automatically generated via Edge-TTS + gTTS for each recording
in a background thread (non-blocking — contributor sees thank-you immediately).
"""

import json
import uuid
import threading
import tempfile
import datetime
import logging
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Record Your Voice",
    page_icon="🎤",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Imports (after page config) ─────────────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    LANGUAGES, AGE_RANGES, GENDERS, ENVIRONMENTS,
    PROMPTS_FILE, MAX_RECORDING_SECONDS, MIN_RECORDING_SECONDS,
)
from utils.audio import process_recording, save_wav
from utils.hf_upload import upload_session
from utils.synthesis import run_all_synthetic_engines

# ── Load prompts ────────────────────────────────────────────────────────────
@st.cache_data
def load_prompts():
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

PROMPTS = load_prompts()

# ── Build the flat list of all 9 prompts (3 languages × 3 prompts) ──────────
# Order: all English prompts, then all Hindi, then all Marathi
LANGUAGE_ORDER = ["english_indian", "hindi", "marathi"]

ALL_PROMPTS = []
for lang_key in LANGUAGE_ORDER:
    lang_prompts = PROMPTS.get(lang_key, [])
    for p in lang_prompts:
        ALL_PROMPTS.append({**p, "language": lang_key})

TOTAL_PROMPTS = len(ALL_PROMPTS)  # should be 9


# ── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    #MainMenu, footer, header { visibility: hidden; }

    .prompt-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 2rem 1.5rem;
        margin: 1.5rem 0;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
    }
    .prompt-text {
        color: #111827;
        font-size: 1.5rem;
        font-weight: 600;
        line-height: 1.5;
        letter-spacing: 0.01em;
    }
    .prompt-note {
        color: #6b7280;
        font-size: 0.9rem;
        margin-top: 0.8rem;
        font-style: italic;
    }
    .prompt-type-badge {
        display: inline-block;
        background: #eef2ff;
        color: #4338ca;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 1rem;
    }
    .lang-badge {
        display: inline-block;
        background: #6366f1;
        color: white;
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    .progress-text {
        text-align: center;
        color: #6366f1;
        font-weight: 600;
        font-size: 1.1rem;
        margin-bottom: 0.5rem;
    }
    .consent-box {
        background: #fffbeb;
        border: 1px solid #fde68a;
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        color: #92400e;
    }
    .success-card {
        background: #ecfdf5;
        border: 1px solid #a7f3d0;
        border-radius: 16px;
        padding: 2rem;
        text-align: center;
        color: #065f46;
    }
    .success-card h2 { color: #059669; }

    @media (max-width: 768px) {
        .prompt-text { font-size: 1.2rem; }
        .prompt-card { padding: 1.5rem 1rem; }
    }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# Session state initialization
# ═══════════════════════════════════════════════════════════════════════════

def init_state():
    defaults = {
        "step": "consent",        # consent → profile → record → upload → thanks
        "contributor_id": str(uuid.uuid4()),
        "consent_age": False,
        "consent_recording": False,
        "age_range": None,
        "gender": "",
        "environment": "",
        "current_prompt_idx": 0,
        "recordings": {},         # prompt_id → {"bytes": ..., "path": ..., "duration": ..., "language": ...}
        "upload_done": False,
        "submitting": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Consent
# ═══════════════════════════════════════════════════════════════════════════

def render_consent():
    st.markdown("## 📝 Before We Begin")

    st.markdown(f"""
    <div class="consent-box">
        <strong>What you're agreeing to:</strong>
        <ul>
            <li>Your voice will be recorded reading prompts in <strong>3 languages</strong> (English, Hindi, Marathi)</li>
            <li>You'll record <strong>4 prompts per language</strong> — {TOTAL_PROMPTS} recordings total (3 fixed sentences + 1 free-speech prompt each)</li>
            <li>Recordings are stored anonymously (no name, email, or contact info)</li>
            <li>Your voice data may be used to train AI systems that detect voice cloning fraud</li>
            <li>After upload, the system automatically generates AI text-to-speech versions of the fixed sentences (not clones of your voice) and stores them alongside your recordings in the dataset</li>
            <li>The dataset is private and used only for this research</li>
            <li>You can stop at any time — incomplete sessions are discarded</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

    st.session_state.consent_age = st.checkbox(
        "✅ I confirm I am 18 years of age or older",
        value=st.session_state.consent_age,
    )
    st.session_state.consent_recording = st.checkbox(
        "✅ I consent to my voice being recorded and used for AI voice-fraud detection research",
        value=st.session_state.consent_recording,
    )

    both_checked = st.session_state.consent_age and st.session_state.consent_recording

    if not both_checked:
        st.info("Please check both boxes above to continue.")

    if st.button(
        "Continue →",
        disabled=not both_checked,
        use_container_width=True,
        type="primary",
    ):
        st.session_state.step = "profile"
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Profile — Gender and Region are REQUIRED
# ═══════════════════════════════════════════════════════════════════════════

def render_profile():
    st.markdown("## 👤 Quick Profile")
    st.caption("All fields are required. No names or contact info collected.")

    st.info(
        "📋 You'll record **9 prompts total** — "
        "3 in English, 3 in Hindi, and 3 in Marathi. "
        "All prompts are in romanized (Latin) script."
    )

    age_range = st.selectbox(
        "📅 Age range *",
        options=AGE_RANGES,
        index=None,
        placeholder="Select age range...",
    )

    gender = st.selectbox(
        "⚧ Gender *",
        options=GENDERS,
        index=None,
        placeholder="Select gender...",
    )

    environment = st.selectbox(
        "🔊 Your current recording environment *",
        options=ENVIRONMENTS,
        index=None,
        placeholder="Select environment...",
    )

    ready = age_range is not None and gender is not None and environment is not None

    if not ready:
        st.info("Please fill in all required fields to continue.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            st.session_state.step = "consent"
            st.rerun()
    with col2:
        if st.button(
            "Start Recording →",
            disabled=not ready,
            use_container_width=True,
            type="primary",
        ):
            st.session_state.age_range = age_range
            st.session_state.gender = gender
            st.session_state.environment = environment
            st.session_state.step = "record"
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Record (all 9 prompts — 3 languages × 3 each)
# ═══════════════════════════════════════════════════════════════════════════

def render_record():
    idx = st.session_state.current_prompt_idx

    if idx >= TOTAL_PROMPTS:
        st.session_state.step = "upload"
        st.rerun()
        return

    prompt = ALL_PROMPTS[idx]
    lang_key = prompt["language"]
    lang_display = LANGUAGES.get(lang_key, lang_key)
    prompt_id = prompt["id"]

    # Progress
    st.markdown(
        f'<p class="progress-text">Recording {idx + 1} of {TOTAL_PROMPTS}</p>',
        unsafe_allow_html=True,
    )
    st.progress(idx / TOTAL_PROMPTS)

    # Language + type badges + prompt card
    type_label = prompt.get("type", "").upper()
    st.markdown(f"""
    <div class="prompt-card">
        <div class="lang-badge">🌐 {lang_display}</div>
        <div class="prompt-type-badge">{type_label}</div>
        <div class="prompt-text">"{prompt['romanized_text']}"</div>
        <div class="prompt-note">💡 {prompt.get('note', 'Read naturally.')}</div>
    </div>
    """, unsafe_allow_html=True)

    # Check if this prompt already has a recording
    existing = st.session_state.recordings.get(prompt_id)

    if existing:
        st.success("✅ Recording accepted!")
        st.audio(existing["bytes"], format="audio/wav")
        st.caption(f"Duration: {existing['duration']:.1f}s")

        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button("🔄 Redo", use_container_width=True):
                del st.session_state.recordings[prompt_id]
                st.rerun()
        with col3:
            if idx < TOTAL_PROMPTS - 1:
                if st.button("Next →", use_container_width=True, type="primary"):
                    st.session_state.current_prompt_idx = idx + 1
                    st.rerun()
            else:
                is_submitting = st.session_state.get("submitting", False)
                if st.button(
                    "Saving & Uploading..." if is_submitting else "Finish & Upload →",
                    use_container_width=True,
                    type="primary",
                    disabled=is_submitting,
                ):
                    st.session_state.submitting = True
                    st.session_state.step = "upload"
                    st.rerun()
    else:
        # Recording widget
        st.markdown(f"**🎤 Tap the mic to record** (max {MAX_RECORDING_SECONDS}s)")

        audio_data = st.audio_input(
            f"Record prompt {idx + 1}",
            key=f"audio_{prompt_id}_{idx}",
        )

        if audio_data is not None:
            audio_bytes = audio_data.read()

            try:
                audio_array, duration = process_recording(audio_bytes)

                if duration < MIN_RECORDING_SECONDS:
                    st.warning(
                        f"Recording too short ({duration:.1f}s). "
                        f"Please record at least {MIN_RECORDING_SECONDS}s."
                    )
                elif duration > MAX_RECORDING_SECONDS + 2:
                    st.warning(
                        f"Recording too long ({duration:.1f}s). "
                        f"Please keep it under {MAX_RECORDING_SECONDS}s."
                    )
                else:
                    # Save to temp file
                    tmp_dir = Path(tempfile.gettempdir()) / "voice_collector" / st.session_state.contributor_id
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                    wav_path = tmp_dir / f"{prompt_id}.wav"
                    save_wav(audio_array, wav_path)

                    # Read back bytes for playback
                    with open(wav_path, "rb") as f:
                        wav_bytes = f.read()

                    st.session_state.recordings[prompt_id] = {
                        "bytes": wav_bytes,
                        "path": str(wav_path),
                        "duration": duration,
                        "language": lang_key,
                    }
                    st.rerun()

            except Exception as e:
                st.error(f"Error processing audio: {e}")
                st.info(
                    "Make sure your browser has microphone permissions enabled. "
                    "Try using Chrome or Edge for best compatibility."
                )

    # Back button (always visible)
    st.markdown("---")
    if st.button("← Back to profile"):
        st.session_state.step = "profile"
        st.session_state.current_prompt_idx = 0
        st.session_state.recordings = {}
        st.rerun()




# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Upload + Fire-and-Forget AI Voice Generation
# ═══════════════════════════════════════════════════════════════════════════

def render_upload():
    st.markdown("## 📤 Uploading Your Recordings")

    recordings = st.session_state.recordings

    if len(recordings) < TOTAL_PROMPTS:
        st.warning(f"You've recorded {len(recordings)}/{TOTAL_PROMPTS} prompts. Go back to finish.")
        if st.button("← Back to recording"):
            st.session_state.step = "record"
            st.rerun()
        return

    if st.session_state.upload_done:
        st.session_state.step = "thanks"
        st.rerun()
        return

    # Build clip list for upload
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    clips = []

    for prompt in ALL_PROMPTS:
        pid = prompt["id"]
        rec = recordings.get(pid)
        if rec:
            clips.append({
                "contribution_id": st.session_state.contributor_id,
                "source": "human",
                "language": prompt["language"],
                "prompt_id": pid,
                "prompt_text_romanized": prompt["romanized_text"],
                "age_range": st.session_state.age_range,
                "gender": st.session_state.gender,
                "region": "",
                "environment": st.session_state.environment,
                "tts_engine": "",
                "voice_id": "",
                "audio_path": rec["path"],
                "duration_seconds": rec["duration"],
                "submitted_at": now,
            })

    progress_bar = st.progress(0, text="Preparing upload...")

    # Step 1: Upload human recordings
    with st.spinner("Uploading human recordings to Hugging Face Hub..."):
        progress_bar.progress(40, text="Uploading human recordings...")
        success, message = upload_session(clips)
        progress_bar.progress(80, text="Human recordings uploaded!")

    if success:
        st.success(message)
    else:
        st.error(message)

    # Step 2: Fire-and-forget AI synthetic voice generation in background thread
    # Contributor does NOT wait for this to finish.
    contribution_id = st.session_state.contributor_id

    def _bg_synth():
        try:
            summaries = run_all_synthetic_engines(clips, contribution_id)
            total_gen = sum(s["generated"] for s in summaries)
            total_fail = sum(s["failed"] for s in summaries)
            logger.info(
                f"Background synthesis done for {contribution_id}: "
                f"{total_gen} generated, {total_fail} failed"
            )
        except Exception as e:
            logger.error(f"Background synthesis failed for {contribution_id}: {e}")

    synth_thread = threading.Thread(target=_bg_synth, daemon=True)
    synth_thread.start()
    logger.info(f"Started background synthesis thread for {contribution_id}")

    progress_bar.progress(100, text="Done! AI voice pairs generating in background...")
    st.info("🤖 AI voice pairs (Edge-TTS + gTTS) are being generated in the background for fixed sentences. You're done!")

    st.session_state.upload_done = True
    st.session_state.submitting = False
    st.session_state.step = "thanks"
    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Thank You
# ═══════════════════════════════════════════════════════════════════════════

def render_thanks():
    st.markdown(f"""
    <div class="success-card">
        <h2>🎉 Thank You!</h2>
        <p style="font-size: 1.1rem; margin: 1rem 0;">
            Your {TOTAL_PROMPTS} voice recordings have been submitted successfully.<br>
            AI-generated voice pairs (Edge-TTS + gTTS) are being created in the background.<br>
            You're helping make voice communication safer for everyone.
        </p>
        <p style="font-size: 0.9rem; opacity: 0.8;">
            Your anonymous contributor ID:<br>
            <code style="color: #059669;">{st.session_state.contributor_id}</code>
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("")
    st.markdown("")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Record Another Session", use_container_width=True, type="primary"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            init_state()
            st.session_state.contributor_id = str(uuid.uuid4())
            st.rerun()
    with col2:
        st.page_link("app.py", label="🏠 Home", use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# Router
# ═══════════════════════════════════════════════════════════════════════════

step = st.session_state.get("step", "consent")

if step == "consent":
    render_consent()
elif step == "profile":
    render_profile()
elif step == "record":
    render_record()
elif step == "upload":
    render_upload()
elif step == "thanks":
    render_thanks()
else:
    st.session_state.step = "consent"
    st.rerun()
