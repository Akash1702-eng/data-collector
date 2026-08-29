"""
Config router - provides application settings, choices, prompt metadata, and contributor stats.
"""

import json
from pathlib import Path
from fastapi import APIRouter

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    LANGUAGES,
    AGE_RANGES,
    GENDERS,
    ENVIRONMENTS,
    PROMPTS_FILE,
    MAX_RECORDING_SECONDS,
    MIN_RECORDING_SECONDS,
    SAMPLE_RATE,
    GEMINI_API_KEY,
)
from utils.hf_upload import get_contributor_count
from utils.gemini_generator import generate_random_prompt

router = APIRouter(prefix="/api/config", tags=["config"])


def load_prompts():
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("")
async def get_config():
    prompts_data = load_prompts()
    language_order = ["english_indian", "hindi", "marathi"]

    # Flat ordered list of all prompts with dynamic Gemini text for the last question of each language
    flat_prompts = []
    dynamic_prompts_by_lang = {}

    for lang_key in language_order:
        lang_prompts = []
        raw_prompts = prompts_data.get(lang_key, [])
        for p in raw_prompts:
            is_last_open = p.get("type") == "open_ended" or "_open_" in p.get("id", "")
            if is_last_open:
                # Dynamically generate random text with Gemini
                ai_prompt = generate_random_prompt(lang_key, prompt_id=p.get("id"))
                prompt_obj = {
                    **p,
                    **ai_prompt,
                    "language": lang_key,
                    "language_display": LANGUAGES.get(lang_key, lang_key),
                }
            else:
                prompt_obj = {
                    **p,
                    "language": lang_key,
                    "language_display": LANGUAGES.get(lang_key, lang_key),
                }
            flat_prompts.append(prompt_obj)
            lang_prompts.append(prompt_obj)
        dynamic_prompts_by_lang[lang_key] = lang_prompts

    contributor_count = get_contributor_count()

    return {
        "languages": LANGUAGES,
        "language_order": language_order,
        "age_ranges": AGE_RANGES,
        "genders": GENDERS,
        "environments": ENVIRONMENTS,
        "prompts_by_language": dynamic_prompts_by_lang,
        "flat_prompts": flat_prompts,
        "total_prompts": len(flat_prompts),
        "contributor_count": contributor_count,
        "has_gemini_key": bool(GEMINI_API_KEY),
        "recording_limits": {
            "min_seconds": MIN_RECORDING_SECONDS,
            "max_seconds": MAX_RECORDING_SECONDS,
            "sample_rate": SAMPLE_RATE,
        }
    }


@router.post("/generate-prompt")
async def generate_prompt_route(payload: dict):
    """
    Dynamically generates a new random reading prompt for a given language using Gemini API.
    Payload: { "language": "english_indian", "prompt_id": "en_open_01", "topic": optional }
    """
    language = payload.get("language", "english_indian")
    prompt_id = payload.get("prompt_id")
    topic = payload.get("topic")

    ai_prompt = generate_random_prompt(language, prompt_id=prompt_id, topic=topic)
    return {
        **ai_prompt,
        "language": language,
        "language_display": LANGUAGES.get(language, language),
    }


@router.get("/generate-prompt")
async def generate_prompt_get_route(language: str = "english_indian", prompt_id: str = None, topic: str = None):
    """
    GET endpoint to dynamically generate a new random reading prompt for a given language.
    """
    ai_prompt = generate_random_prompt(language, prompt_id=prompt_id, topic=topic)
    return {
        **ai_prompt,
        "language": language,
        "language_display": LANGUAGES.get(language, language),
    }


@router.get("/stats")
async def get_stats():
    """Get live contributor count."""
    return {
        "contributor_count": get_contributor_count(),
    }
