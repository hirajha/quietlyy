"""
Quietlyy — SEO & Metadata Optimizer
Generates AI-powered, platform-specific SEO metadata for every video.

Produces:
  - Facebook/Instagram: short caption + 25 hashtags (with geo tags), AI disclosure
  - YouTube Shorts: compelling title, short description, 15 tags, AI disclosure
  - Posting time recommendations for international audience

Uses same AI providers as generate_script.py (Gemini → OpenAI → Groq → fallback).
"""

import os
import json
import requests

BRAND = "Quietlyy"
YT_HANDLE = "@SayQuietlyy"

# AI disclosure — platform-policy compliant, minimal
FB_AI_DISCLOSURE  = "AI assistance was used in the making of this video."
YT_AI_DISCLOSURE  = "AI assistance was used in the making of this video."

# ── Geo hashtags — always included to capture global audience ─────────────
GEO_TAGS = ["usa", "uk", "india", "canada", "australia", "uae", "viral"]

# ── Fallback hashtag sets ─────────────────────────────────────────────────
BASE_FB_TAGS = [
    "nostalgia", "deepthoughts", "lifequotes", "reflection", "memories",
    "emotionalquotes", "reels", "viralreels", "quotesoftheday", "relatable",
    "feelingsdeep", "mindfulness", "poetrylovers", "wordsthatmatter",
]

BASE_YT_TAGS = [
    "Shorts", "nostalgia", "deepthoughts", "lifequotes", "reflection",
    "emotionalquotes", "relatable", "viral", "youtubeshorts",
    "motivationalquotes", "feelings", "trending", "poetry",
]

SEO_PROMPT = """You are an expert social media SEO specialist for short-form emotional content targeting a global audience (India, USA, UK, Canada, Australia, UAE).

Topic: {topic}
Visual keywords: {keywords}
Script theme: {theme}

Generate optimized metadata. Return ONLY valid JSON:
{{
  "short_caption": "...",
  "instagram_hashtags": ["tag1", "tag2"],
  "youtube_title": "...",
  "youtube_tags": ["tag1", "tag2"],
  "youtube_seo_line": "...",
  "best_post_times": {{
    "facebook_instagram": ["HH:MM IST", "HH:MM IST"],
    "youtube": ["HH:MM IST", "HH:MM IST"],
    "reasoning": "1 sentence why"
  }}
}}

Rules:
- short_caption: 1-2 punchy sentences max (NOT the full script). Emotionally compelling. No hashtags.
- instagram_hashtags: exactly 25 tags, NO # symbol, NO spaces, all lowercase.
  Must include: 5 broad emotional (nostalgia, quotes, viral), 8 topic-specific,
  5 geo-audience (usa, uk, india, canada, australia), 7 engagement (foryou, reels, trending, explore)
- youtube_title: under 60 chars, emotionally compelling, NO hashtags
- youtube_tags: exactly 15 tags, NO AI-related tags
- youtube_seo_line: 1 sentence under 120 chars for search discovery
- best_post_times: optimal times in IST for THIS specific content to reach global audience"""


def _call_openai_compatible(url, key, model, prompt):
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 600,
            "temperature": 0.5,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


def _repair_json(text):
    import re
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None


def _generate_with_gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 700, "temperature": 0.5},
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _repair_json(text)
    except Exception as e:
        print(f"[seo] Gemini failed: {e}")
        return None


def _generate_with_openai(prompt):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        return _call_openai_compatible(
            "https://api.openai.com/v1/chat/completions",
            key, "gpt-4o-mini", prompt,
        )
    except Exception as e:
        print(f"[seo] OpenAI failed: {e}")
        return None


def _generate_with_groq(prompt):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    try:
        return _call_openai_compatible(
            "https://api.groq.com/openai/v1/chat/completions",
            key, "llama-3.3-70b-versatile", prompt,
        )
    except Exception as e:
        print(f"[seo] Groq failed: {e}")
        return None


def _template_fallback(topic, script_text):
    topic_tag = topic.replace(" ", "").lower()
    first_line = [l.strip() for l in script_text.split("\n") if l.strip()][0]
    caption = first_line[:100]

    ig_tags = BASE_FB_TAGS + GEO_TAGS + [topic_tag, "quotes", "emotional", "poetry"]
    ig_tags = list(dict.fromkeys(ig_tags))[:25]

    yt_tags = BASE_YT_TAGS + [topic_tag, "emotional", "poetry"]
    yt_tags = list(dict.fromkeys(yt_tags))[:15]

    return {
        "short_caption": caption,
        "instagram_hashtags": ig_tags,
        "youtube_title": first_line[:57] + ("..." if len(first_line) > 57 else ""),
        "youtube_tags": yt_tags,
        "youtube_seo_line": f"A quiet reflection on {topic} — words that hit different.",
        "best_post_times": {
            "facebook_instagram": ["11:00", "20:00"],
            "youtube": ["20:30", "22:00"],
            "reasoning": "Peak scroll times for India + evening overlap with USA/UK mornings.",
        },
    }


# ── Public API ──────────────────────────────────────────────────────────────

def generate_seo(topic, script_text, visual_keywords):
    """
    Returns platform-specific SEO metadata dict:
    {
        "facebook": { "description": str, "hashtags": list },
        "youtube":  { "title": str, "description": str, "tags": list },
        "best_post_times": { "facebook_instagram": [...], "youtube": [...], "reasoning": str }
    }
    """
    lines = [l.strip() for l in script_text.split("\n") if l.strip()]
    theme = lines[0] if lines else topic  # first line as theme hint for AI

    prompt = SEO_PROMPT.format(
        topic=topic,
        keywords=", ".join(visual_keywords),
        theme=theme,
    )

    ai_data = None
    for fn, name in [(_generate_with_gemini, "Gemini"), (_generate_with_openai, "OpenAI"), (_generate_with_groq, "Groq")]:
        ai_data = fn(prompt)
        if ai_data and "instagram_hashtags" in ai_data:
            print(f"[seo] Generated via {name}")
            break

    if not ai_data:
        print("[seo] Using template fallback")
        ai_data = _template_fallback(topic, script_text)

    # ── Hashtags — always inject geo tags ─────────────────────────────────
    ig_tags = ai_data.get("instagram_hashtags", BASE_FB_TAGS)
    # Ensure geo tags are present (AI may omit them)
    ig_tags_clean = [t.lstrip("#").lower().replace(" ", "") for t in ig_tags]
    for geo in GEO_TAGS:
        if geo not in ig_tags_clean:
            ig_tags_clean.append(geo)
    ig_tags_clean = list(dict.fromkeys(ig_tags_clean))[:25]  # dedupe, cap 25
    hashtag_str = " ".join(f"#{t}" for t in ig_tags_clean)

    # ── Facebook / Instagram — SHORT caption, no script ───────────────────
    short_caption = ai_data.get("short_caption", theme)
    fb_description = (
        f"{short_caption}\n\n"
        f"💾 Save this for when you need it.\n"
        f"❤️ Like if this hit different.\n"
        f"👇 Tag someone who needs to hear this.\n\n"
        f"— {BRAND}\n\n"
        f"{hashtag_str}\n\n"
        f"{FB_AI_DISCLOSURE}"
    )

    # ── YouTube — hashtags first, short description, no script ────────────
    yt_tags = ai_data.get("youtube_tags", BASE_YT_TAGS)
    yt_tags_clean = [t.lstrip("#").lower().replace(" ", "") for t in yt_tags][:15]
    yt_tag_str = " ".join(f"#{t}" for t in yt_tags_clean)

    seo_line = ai_data.get("youtube_seo_line", f"A quiet reflection on {topic}.")

    # Hashtags at TOP so YouTube shows first 3 above the title as clickable links
    yt_description = (
        f"{yt_tag_str}\n\n"
        f"{short_caption}\n\n"
        f"💾 Save this for when you need it.\n"
        f"❤️ Like if this hit different.\n"
        f"🔔 Subscribe for a new one every day → {YT_HANDLE}\n\n"
        f"— {BRAND}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{seo_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{YT_AI_DISCLOSURE}"
    )

    raw_title = ai_data.get("youtube_title", topic)
    yt_title = f"{raw_title[:90]} #Shorts"

    # ── Posting time advice ───────────────────────────────────────────────
    post_times = ai_data.get("best_post_times", {
        "facebook_instagram": ["11:00", "20:00"],
        "youtube": ["20:30", "22:00"],
        "reasoning": "Peak scroll times for India + overlap with global evening.",
    })
    print(f"[seo] Best FB/IG times: {post_times.get('facebook_instagram')} IST")
    print(f"[seo] Best YT times:    {post_times.get('youtube')} IST")
    print(f"[seo] Reason: {post_times.get('reasoning', '')}")

    return {
        "facebook": {
            "description": fb_description,
            "hashtags": ig_tags_clean,
        },
        "youtube": {
            "title": yt_title[:100],
            "description": yt_description,
            "tags": yt_tags_clean,
        },
        "best_post_times": post_times,
    }


if __name__ == "__main__":
    sample = generate_seo(
        "People Who Use You",
        "You were never too much.\nJust too real for people who only needed you in storms.\nThey held you close when the rain came.\nAnd forgot you the moment the sky cleared.\nThe cruelest part — they knew you'd stay anyway.",
        ["umbrella", "storm", "loneliness", "walking alone"],
    )
    print(json.dumps(sample, indent=2))
