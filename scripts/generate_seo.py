"""
Quietlyy — SEO & Metadata Optimizer
Generates AI-powered, platform-specific SEO metadata for every video.

Produces:
  - Facebook/Instagram: optimized caption, 25 hashtags, AI disclosure
  - YouTube Shorts: compelling title, full description, 15 tags, AI disclosure

Uses same AI providers as generate_script.py (Gemini → Groq → template fallback).
"""

import os
import json
import requests

# ── AI disclosure text (platform-policy compliant, minimal/end-of-post) ───

# Facebook/Instagram: buried after all hashtags — visible only if expanded
FB_AI_DISCLOSURE = "Made with AI tools."

# YouTube: last line of description, after all tags
YT_AI_DISCLOSURE = "Made with AI tools."

# ── Fallback hashtag sets by category ──────────────────────────────────────

BASE_FB_TAGS = [
    "Quietlyy", "nostalgia", "deepthoughts", "lifequotes", "reflection",
    "memories", "lostmoments", "emotionalquotes", "reels", "viralreels",
    "quotesoftheday", "relatable", "feelingsdeep", "mindfulness", "innerpeace",
]

BASE_YT_TAGS = [
    "Shorts", "Quietlyy", "nostalgia", "deepthoughts", "lifequotes",
    "reflection", "emotionalquotes", "relatable", "viral", "shortsvideo",
    "youtubeshorts", "motivationalquotes", "sadquotes", "feelings", "trending",
]

SEO_PROMPT = """You are an expert social media SEO specialist for short-form emotional content.

Topic: {topic}
Script:
{script}
Visual keywords: {keywords}

Generate optimized metadata. Return ONLY valid JSON:
{{
  "instagram_hashtags": ["tag1", "tag2"],
  "youtube_title": "...",
  "youtube_tags": ["tag1", "tag2"],
  "youtube_seo_line": "..."
}}

Rules:
- instagram_hashtags: exactly 25 tags, NO # symbol, NO spaces, all lowercase
  Mix: 5 broad (nostalgia, quotes, viral), 10 topic-specific, 10 engagement (foryou, reels, trending)
- youtube_title: under 60 chars, emotionally compelling, NO hashtags, makes people stop scrolling
- youtube_tags: exactly 15 tags, mix broad + niche + topic-specific, include "AIgenerated"
- youtube_seo_line: 1 sentence (under 120 chars) describing the video for search discovery"""


def _call_openai_compatible(url, key, model, prompt):
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
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
                "generationConfig": {"maxOutputTokens": 600, "temperature": 0.5},
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _repair_json(text)
    except Exception as e:
        print(f"[seo] Gemini failed: {e}")
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
    """Generate decent metadata without AI."""
    topic_tag = topic.replace(" ", "").lower()
    first_line = [l.strip() for l in script_text.split("\n") if l.strip()][0]
    title = first_line[:57] + "..." if len(first_line) > 60 else first_line

    ig_tags = BASE_FB_TAGS + [topic_tag, "quotes", "viral", "emotional",
                               "poetry", "shortsvideo", "trending", "foryou",
                               "reelsvideo", "instareels"]
    ig_tags = list(dict.fromkeys(ig_tags))[:25]  # dedupe, cap at 25

    yt_tags = BASE_YT_TAGS + [topic_tag, "emotional", "poetry"]
    yt_tags = list(dict.fromkeys(yt_tags))[:15]

    return {
        "instagram_hashtags": ig_tags,
        "youtube_title": title,
        "youtube_tags": yt_tags,
        "youtube_seo_line": f"A quiet reflection on {topic} — words that hit different at 3 AM.",
    }


# ── Public API ──────────────────────────────────────────────────────────────

def generate_seo(topic, script_text, visual_keywords):
    """
    Returns platform-specific SEO metadata dict:
    {
        "facebook": { "description": str, "hashtags": list },
        "youtube":  { "title": str, "description": str, "tags": list }
    }
    """
    prompt = SEO_PROMPT.format(
        topic=topic,
        script=script_text,
        keywords=", ".join(visual_keywords),
    )

    ai_data = None
    for fn, name in [(_generate_with_gemini, "Gemini"), (_generate_with_groq, "Groq")]:
        ai_data = fn(prompt)
        if ai_data and "instagram_hashtags" in ai_data:
            print(f"[seo] Generated via {name}")
            break

    if not ai_data:
        print("[seo] Using template fallback")
        ai_data = _template_fallback(topic, script_text)

    # ── Facebook / Instagram description ───────────────────────────────────
    lines = [l.strip() for l in script_text.split("\n") if l.strip()]
    caption = "\n".join(lines)

    ig_tags = ai_data.get("instagram_hashtags", BASE_FB_TAGS)[:25]
    hashtag_str = " ".join(f"#{t.lstrip('#')}" for t in ig_tags)

    # Disclosure goes AFTER all hashtags — only visible if audience taps "more"
    fb_description = (
        f"{caption}\n\n"
        f"— Quietlyy\n\n"
        f"{hashtag_str}\n\n"
        f"{FB_AI_DISCLOSURE}"
    )

    # ── YouTube description ─────────────────────────────────────────────────
    seo_line = ai_data.get("youtube_seo_line", f"A quiet reflection on {topic}.")
    yt_tags = ai_data.get("youtube_tags", BASE_YT_TAGS)[:15]
    yt_tag_str = " ".join(f"#{t.lstrip('#')}" for t in yt_tags)

    yt_description = (
        f"{caption}\n\n"
        f"— Quietlyy\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{seo_line}\n\n"
        f"📌 Follow for daily reflections: @Quietlyy\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{yt_tag_str}\n\n"
        f"{YT_AI_DISCLOSURE}"
    )

    raw_title = ai_data.get("youtube_title", topic)
    # Ensure #Shorts is appended and total stays under 100 chars
    yt_title = f"{raw_title[:90]} #Shorts" if len(raw_title) <= 90 else f"{raw_title[:90]}... #Shorts"

    return {
        "facebook": {
            "description": fb_description,
            "hashtags": ig_tags,
        },
        "youtube": {
            "title": yt_title[:100],
            "description": yt_description,
            "tags": yt_tags,
        },
    }


if __name__ == "__main__":
    # Quick test
    sample = generate_seo(
        "Old Phone Calls",
        "There was a time we called just to hear a voice…\nNot to share news, not to make plans.\nJust to feel less alone in the dark.\nNow we text 'lol' and call it staying in touch.\nMaybe we were never really that busy… just slowly forgetting how to care.",
        ["phone", "connection", "loneliness"],
    )
    print(json.dumps(sample, indent=2))
