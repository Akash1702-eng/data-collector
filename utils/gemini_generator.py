"""
Gemini AI Prompt Generator for Voice Authenticity Dataset Collector.

Dynamically generates natural, realistic conversational passages (15-20 words, ~10-15s reading time)
in English (Indian), Hindi (Devanagari + Romanized), and Marathi (Devanagari + Romanized)
for the final open-ended prompt slot of each language.

Includes:
- Direct Gemini API generation via google.generativeai with multi-model fallback.
- Multi-topic randomization (morning routine, commute, food, weather, hobbies, books, nature, etc.).
- Rich pre-populated multilingual fallback pools (20+ curated authentic stories per language)
  for instantaneous offline/fallback execution.
"""

import json
import random
import logging
from typing import Optional
from pathlib import Path

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# ── Multilingual Fallback Curated Pools ─────────────────────────────────────
FALLBACK_POOLS = {
    "english_indian": [
        {
            "native_text": "I woke up early this morning, made a hot cup of ginger tea, and went for a refreshing walk in the park.",
            "romanized_text": "I woke up early this morning, made a hot cup of ginger tea, and went for a refreshing walk in the park.",
            "topic": "Morning routine",
        },
        {
            "native_text": "On weekends, I love visiting the local farmers market to pick up fresh vegetables and handmade snacks.",
            "romanized_text": "On weekends, I love visiting the local farmers market to pick up fresh vegetables and handmade snacks.",
            "topic": "Weekend market",
        },
        {
            "native_text": "The monsoon rains started suddenly today, making the whole city cool down with the sweet smell of wet earth.",
            "romanized_text": "The monsoon rains started suddenly today, making the whole city cool down with the sweet smell of wet earth.",
            "topic": "Monsoon rain",
        },
        {
            "native_text": "I spent the afternoon reading an exciting mystery novel while listening to soft instrumental music in my room.",
            "romanized_text": "I spent the afternoon reading an exciting mystery novel while listening to soft instrumental music in my room.",
            "topic": "Reading books",
        },
        {
            "native_text": "Yesterday evening, my family gathered together to cook a delicious traditional meal and share funny childhood stories.",
            "romanized_text": "Yesterday evening, my family gathered together to cook a delicious traditional meal and share funny childhood stories.",
            "topic": "Family dinner",
        },
        {
            "native_text": "The train was bustling with people this morning, all heading towards their offices and chatting about daily news.",
            "romanized_text": "The train was bustling with people this morning, all heading towards their offices and chatting about daily news.",
            "topic": "Daily commute",
        },
        {
            "native_text": "I love watering my balcony plants every evening and watching the tiny green leaves grow under the sunlight.",
            "romanized_text": "I love watering my balcony plants every evening and watching the tiny green leaves grow under the sunlight.",
            "topic": "Gardening",
        },
        {
            "native_text": "We went on a short road trip to the hills and enjoyed the breathtaking mountain views during sunset.",
            "romanized_text": "We went on a short road trip to the hills and enjoyed the breathtaking mountain views during sunset.",
            "topic": "Travel & Nature",
        },
        {
            "native_text": "Nothing beats a plate of hot crispy samosas and spicy mint chutney on a cloudy breezy afternoon.",
            "romanized_text": "Nothing beats a plate of hot crispy samosas and spicy mint chutney on a cloudy breezy afternoon.",
            "topic": "Favorite snack",
        },
        {
            "native_text": "I learned how to make fresh mango ice cream at home, and everyone in my family loved the taste.",
            "romanized_text": "I learned how to make fresh mango ice cream at home, and everyone in my family loved the taste.",
            "topic": "Home cooking",
        },
    ],
    "hindi": [
        {
            "native_text": "आज सुबह मैंने गरम चाय पी और थोड़ी देर बालकनी में बैठकर ताज़ी हवा का आनंद लिया।",
            "romanized_text": "Aaj subah maine garam chai pi aur thodi der balcony mein baithkar taazi hawa ka aanand liya.",
            "topic": "Morning tea",
        },
        {
            "native_text": "शाम के समय पास के पार्क में बच्चों को खेलते देखना मन को बहुत शांति देता है।",
            "romanized_text": "Shaam ke samay paas ke park mein bachhon ko khelte dekhna man ko bahut shaanti deta hai.",
            "topic": "Evening park",
        },
        {
            "native_text": "बारिश की पहली बूँदें गिरते ही मिट्टी की सौंधी खुशबू पूरे मोहल्ले में फैल गई।",
            "romanized_text": "Baarish ki pehli boondein girte hi mitti ki sondhi khushboo poore mohalle mein phail gayi.",
            "topic": "First rain",
        },
        {
            "native_text": "कल रात हमने परिवार के साथ बैठकर एक पुरानी हिंदी फिल्म देखी और बहुत हँसी-मज़ाक किया।",
            "romanized_text": "Kal raat humne parivaar ke saath baithkar ek puraani hindi film dekhi aur bahut hansi-mazaak kiya.",
            "topic": "Family movie night",
        },
        {
            "native_text": "बाज़ार में आज ताज़े फल और सब्ज़ियाँ देखकर मैंने अपनी मनपसंद मिठाई भी खरीदी।",
            "romanized_text": "Baazaar mein aaj taaze phal aur sabziyaan dekhkar maine apni manpasand mithai bhi khareedi.",
            "topic": "Market shopping",
        },
        {
            "native_text": "सुबह की ठंडी हवा में टहलने से पूरा दिन ऊर्जा और ताजगी से भरा रहता है।",
            "romanized_text": "Subah ki thandi hawa mein tehelne se poora din oorja aur taazgi se bhara rehta hai.",
            "topic": "Morning walk",
        },
        {
            "native_text": "त्योहार के आते ही पूरे घर में दीपकों की रोशनी और मिठाइयों की खुशबू छा जाती है।",
            "romanized_text": "Tyohaar ke aate hi poore ghar mein deepakon ki roshni aur mithaiyon ki khushboo chhaa jaati hai.",
            "topic": "Festivals",
        },
        {
            "native_text": "मैंने अपने दोस्त के साथ कॉलेज के पुराने दिनों की यादें ताज़ा कीं और खूब बातें कीं।",
            "romanized_text": "Maine apne dost ke saath college ke puraane dino ki yaadein taaza keen aur khoob baatein keen.",
            "topic": "Catching up with a friend",
        },
    ],
    "marathi": [
        {
            "native_text": "आज सकाळी मी लवकर उठलो, वाफाळलेला चहा घेतला आणि बागेत थोडा वेळ फिरून आलो.",
            "romanized_text": "Aaj sakaali mee lavkar uthalo, vaaphaalelaa chaha ghetla aani baaget thoda vel firoon aalo.",
            "topic": "Morning walk",
        },
        {
            "native_text": "पावसाळ्यात गरमागरम कांदा भजी आणि आले घातलेला चहा पिण्याची मजा काही वेगळीच असते.",
            "romanized_text": "Paavsaalyaat garamaagaram kaandaa bhaji aani aale ghaatlelyaa chaha pinyaachi majaa kaahi vegaleech asate.",
            "topic": "Monsoon snacks",
        },
        {
            "native_text": "संध्याकाळी समुद्रकिनाऱ्यावर बसून सूर्यास्त पाहणे हा माझा सर्वात आवडता छंद आहे.",
            "romanized_text": "Sandhyaakaali samudrakinaaryavar basoon sooryaasta paahane ha maazaa sarvaat aavadtaa chhand aahe.",
            "topic": "Beach sunset",
        },
        {
            "native_text": "रविवारी सकाळी संपूर्ण कुटुंब एकत्र येऊन छान नाश्ता करतो आणि गप्पा मारतो.",
            "romanized_text": "Ravivaari sakaali sampoorna kutumba ekatra yeoon chhaan naashtaa karto aani gappaa maarto.",
            "topic": "Sunday family time",
        },
        {
            "native_text": "बागेतल्या झाडांना पाणी घालताना मन अगदी प्रसन्न आणि ताजेतवाने होते.",
            "romanized_text": "Baagetlyaa zaadaanna paani ghaaltaanaa man agadee prasanna aani taajetaavaane hote.",
            "topic": "Gardening joy",
        },
        {
            "native_text": "गावी जाऊन निसर्गाच्या सान्निध्यात शांतपणे दोन दिवस घालवणे मला खूप आवडते.",
            "romanized_text": "Gaavee jaaoon nisargaachyaa saannidhyaat shaantapane don divas ghaalavane malaa khoop aavadte.",
            "topic": "Village trip",
        },
        {
            "native_text": "सणासुदीच्या दिवसांत घरासमोर सुंदर रांगोळी काढताना संपूर्ण वातावरणात आनंद भरून राहतो.",
            "romanized_text": "Sanaasudeechya divsaant gharaasamor sundar raangoli kaadhtaanaa sampoorna vaataavaranaat aanand bharoon raahato.",
            "topic": "Rangoli festival",
        },
    ],
}

TOPIC_IDEAS = [
    "morning routine & tea",
    "monsoon rain & cool breeze",
    "visiting a lively local market",
    "relaxing walk in the green garden",
    "reading a captivating storybook",
    "family cooking a delicious traditional dinner",
    "watching the colorful evening sunset",
    "catching up with a childhood friend",
    "enjoying hot crispy snacks on a rainy day",
    "a memorable road trip into the hills",
    "balcony gardening and fresh green plants",
    "celebrating a vibrant cultural festival",
]


def _get_fallback_prompt(language: str) -> dict:
    """Returns a random curated fallback item from the pool."""
    pool = FALLBACK_POOLS.get(language, FALLBACK_POOLS["english_indian"])
    return random.choice(pool)


def generate_with_gemini(language: str, topic: Optional[str] = None) -> Optional[dict]:
    """
    Calls Google Gemini API using google.generativeai to generate a random, natural sentence
    suitable for speech recording.

    Returns dict with {native_text, romanized_text, topic} or None if failed.
    """
    if not GEMINI_API_KEY:
        logger.debug("GEMINI_API_KEY not configured in environment/.env, using fallback pool.")
        return None

    if not topic:
        topic = random.choice(TOPIC_IDEAS)

        import urllib.request
        import urllib.error

        # 1. Try Direct Google Gemini REST API (no deprecation warnings, lightweight & fast)
        for model_name in unique_models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                payload = {
                    "contents": [{
                        "parts": [{"text": prompt_instruction}]
                    }],
                    "generationConfig": {
                        "temperature": 0.85,
                        "topP": 0.95,
                    }
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=12) as response:
                    res_body = json.loads(response.read().decode("utf-8"))
                    candidates = res_body.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            text = parts[0]["text"].strip()
                            if text.startswith("```"):
                                lines = text.split("\n")
                                if lines[0].startswith("```"):
                                    lines = lines[1:]
                                if lines and lines[-1].startswith("```"):
                                    lines = lines[:-1]
                                text = "\n".join(lines).strip()
                            data = json.loads(text)
                            if data.get("native_text") and data.get("romanized_text"):
                                logger.info(f"Generated prompt with Gemini ({model_name}) for {language}: {data['topic']}")
                                return {
                                    "native_text": data["native_text"].strip(),
                                    "romanized_text": data["romanized_text"].strip(),
                                    "topic": data.get("topic", topic),
                                }
            except urllib.error.HTTPError as http_err:
                logger.debug(f"Gemini REST model {model_name} HTTP {http_err.code}: {http_err.reason}")
                continue
            except Exception as e:
                logger.debug(f"Gemini REST model {model_name} error: {e}")
                continue

        # 2. Fallback to google.generativeai / google.genai if installed
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            for model_name in unique_models:
                try:
                    model = genai.GenerativeModel(model_name)
                    res = model.generate_content(
                        prompt_instruction,
                        generation_config={"temperature": 0.85, "top_p": 0.95}
                    )
                    text = res.text.strip()
                    if text.startswith("```"):
                        lines = text.split("\n")
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].startswith("```"):
                            lines = lines[:-1]
                        text = "\n".join(lines).strip()
                    data = json.loads(text)
                    if data.get("native_text") and data.get("romanized_text"):
                        return {
                            "native_text": data["native_text"].strip(),
                            "romanized_text": data["romanized_text"].strip(),
                            "topic": data.get("topic", topic),
                        }
                except Exception:
                    continue
        except Exception:
            pass

        logger.info("Using curated multilingual fallback prompt pool for this session.")
        return None

    except Exception as e:
        logger.debug(f"Gemini generation fallback: {e}")
        return None


def generate_random_prompt(language: str, prompt_id: Optional[str] = None, topic: Optional[str] = None) -> dict:
    """
    Generates a full prompt object for the open-ended/final prompt slot.
    Uses Gemini API if available, falling back gracefully to the rich curated pool.

    Args:
        language: "english_indian", "hindi", or "marathi"
        prompt_id: e.g. "en_open_01", "hi_open_01", "mr_open_01"
        topic: optional topic override

    Returns:
        Structured prompt dict compatible with studio and speech recognition.
    """
    if not prompt_id:
        if language == "hindi":
            prompt_id = "hi_open_01"
        elif language == "marathi":
            prompt_id = "mr_open_01"
        else:
            prompt_id = "en_open_01"

    # Try Gemini generation
    gemini_result = generate_with_gemini(language, topic)
    if gemini_result:
        native_text = gemini_result["native_text"]
        romanized_text = gemini_result["romanized_text"]
        generated_topic = gemini_result.get("topic", "Daily life")
        is_live_gemini = True
    else:
        fallback = _get_fallback_prompt(language)
        native_text = fallback["native_text"]
        romanized_text = fallback["romanized_text"]
        generated_topic = fallback.get("topic", "Daily life")
        is_live_gemini = False

    return {
        "id": prompt_id,
        "native_text": native_text,
        "romanized_text": romanized_text,
        "type": "ai_generated",
        "note": "Read this AI-generated passage naturally at your normal speaking pace.",
        "topic": generated_topic,
        "is_ai_generated": True,
        "generator": "gemini" if is_live_gemini else "curated_pool",
    }
