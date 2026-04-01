"""
Quietlyy — Audience Intelligence & Market Research Agent
Goal: 5 Million followers in 6 months across FB, Instagram, YouTube Shorts.

Researches and caches (refreshed weekly):
  - Peak engagement windows by platform (IST-based)
  - Primary demographics and geo breakdown
  - High-performing topic themes and emotional triggers
  - Script tone/style hints for maximum relatability
  - A/B content strategy recommendations

Results cached in assets/market_research.json.
Consumed by: generate_script.py (tone hints), pipeline.py (topic weights).
"""

import os
import json
import requests
from datetime import datetime, timezone

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "market_research.json")
CACHE_TTL_DAYS = 7

RESEARCH_PROMPT = """You are a viral short-form content strategist specialising in emotional/nostalgic videos
targeting a global English-speaking audience (heavy South Asian diaspora + US + UK + Canada + Australia).

The channel "Quietlyy" posts 30-second nostalgic quote videos — soft music, AI voiceover, emotional imagery.
Current content style: deep, quiet pain, personal memories, human connection, relatable endings.

Goal: Grow from 0 to 5 MILLION followers across Facebook Reels, Instagram Reels and YouTube Shorts in 6 months.

Analyse this niche and return a research report as ONLY valid JSON:
{
  "target_demographics": {
    "primary_age": "...",
    "secondary_age": "...",
    "gender_split": "...",
    "top_geos": ["country1", "country2", "country3", "country4", "country5"]
  },
  "peak_posting_times_IST": {
    "facebook_reels": ["HH:MM", "HH:MM"],
    "instagram_reels": ["HH:MM", "HH:MM"],
    "youtube_shorts": ["HH:MM", "HH:MM"]
  },
  "high_performing_themes": ["theme1", "theme2", "theme3", "theme4", "theme5",
                              "theme6", "theme7", "theme8", "theme9", "theme10"],
  "script_tone_hints": [
    "...",
    "...",
    "..."
  ],
  "hook_strategies": [
    "...",
    "...",
    "..."
  ],
  "hashtag_strategy": {
    "facebook": ["tag1", "tag2", "tag3", "tag4", "tag5"],
    "instagram": ["tag1", "tag2", "tag3", "tag4", "tag5"],
    "youtube": ["tag1", "tag2", "tag3", "tag4", "tag5"]
  },
  "growth_tactics": [
    "...",
    "...",
    "..."
  ],
  "content_warnings": [
    "..."
  ]
}"""


def _call_gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 1500, "temperature": 0.3},
            },
            timeout=45,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        import re
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"[research] Gemini failed: {e}")
    return None


def _call_groq(prompt):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
            timeout=45,
        )
        resp.raise_for_status()
        return json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"[research] Groq failed: {e}")
    return None


def _baseline_research():
    """Evidence-based baseline for nostalgic emotional content niche."""
    return {
        "target_demographics": {
            "primary_age": "18-24",
            "secondary_age": "25-34",
            "gender_split": "55% female, 45% male",
            "top_geos": ["India", "United States", "United Kingdom", "Canada", "Australia"]
        },
        "peak_posting_times_IST": {
            "facebook_reels": ["11:00", "20:00"],
            "instagram_reels": ["11:00", "21:00"],
            "youtube_shorts": ["20:30", "22:00"]
        },
        "high_performing_themes": [
            "childhood friendships drifting apart",
            "old phone calls we never got",
            "parents growing older",
            "the last time we did something without knowing it",
            "how fast people change",
            "missing someone who is still alive",
            "school days we took for granted",
            "first love and what it felt like",
            "family dinners that stopped happening",
            "the version of yourself you lost along the way"
        ],
        "script_tone_hints": [
            "Use 'we' and 'you' to make it feel personal and universal",
            "Specific details (a song, a smell, a place) beat generic statements",
            "End with a quiet gut-punch realization, not a motivational line",
            "Keep sentences short — pause after every emotional beat",
            "Avoid explaining the feeling — make the reader feel it themselves"
        ],
        "hook_strategies": [
            "Open with a specific sensory memory the audience instantly recognizes",
            "Start with 'There was a time…' or 'Remember when…' to trigger nostalgia",
            "Name the exact thing that's gone — don't be vague"
        ],
        "hashtag_strategy": {
            "facebook": ["Reels", "nostalgia", "deepthoughts", "lifequotes", "viral"],
            "instagram": ["reels", "quotes", "nostalgia", "fyp", "emotional"],
            "youtube": ["Shorts", "nostalgia", "lifequotes", "viral", "emotional"]
        },
        "growth_tactics": [
            "Post twice daily: 11 AM IST (morning scroll) + 8 PM IST (evening wind-down)",
            "First 3 seconds must hook — start mid-thought, not with an intro",
            "Caption should stop at a cliffhanger before 'See more' to drive clicks",
            "Rotate between 10 proven emotional themes to prevent fatigue",
            "Consistent visual style (soft warm tones, same watermark) builds brand recall"
        ],
        "content_warnings": [
            "Avoid overly dark or hopeless endings — bittersweet is the sweet spot",
            "Do not use generic motivational closings — they kill the emotional landing"
        ],
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "_source": "baseline"
    }


def _is_cache_fresh():
    if not os.path.exists(CACHE_PATH):
        return False
    try:
        with open(CACHE_PATH) as f:
            data = json.load(f)
        generated_at = data.get("_generated_at")
        if not generated_at:
            return False
        from datetime import timedelta
        ts = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - ts
        return age.days < CACHE_TTL_DAYS
    except Exception:
        return False


def get_research():
    """
    Return market research data (cached or freshly generated).
    Always succeeds — falls back to baseline if AI unavailable.
    """
    if _is_cache_fresh():
        with open(CACHE_PATH) as f:
            data = json.load(f)
        print(f"[research] Using cached research (source: {data.get('_source', 'unknown')})")
        return data

    print("[research] Running market research...")
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)

    data = None
    for fn, name in [(_call_gemini, "Gemini"), (_call_groq, "Groq")]:
        data = fn(RESEARCH_PROMPT)
        if data and "high_performing_themes" in data:
            data["_generated_at"] = datetime.now(timezone.utc).isoformat()
            data["_source"] = name
            print(f"[research] Generated via {name}")
            break

    if not data:
        print("[research] Using baseline research")
        data = _baseline_research()

    with open(CACHE_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return data


def get_tone_hints(research):
    """Extract script tone hints as a formatted string for the prompt."""
    hints = research.get("script_tone_hints", [])
    hooks = research.get("hook_strategies", [])
    return "\n".join([f"- {h}" for h in hints + hooks])


def get_top_themes(research):
    """Return high-performing themes to bias topic selection."""
    return research.get("high_performing_themes", [])


if __name__ == "__main__":
    r = get_research()
    print(json.dumps(r, indent=2))
