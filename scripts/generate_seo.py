"""
Quietlyy — SEO & Metadata Optimizer
2026 algorithm-optimised: DM shares > saves > watch time > likes.
Hashtags secondary to caption keywords for discovery.

Key insight from research:
  - DM shares (#1 signal): "send this to someone" CTA drives distribution
  - Watch time: first 3 seconds decide reach (5-10x difference)
  - Caption keywords: now more important than hashtags for discovery
  - Hashtag mix: niche (10K-500K) + mid (1M-5M), NOT just giant tags
  - Trending audio: +67% views (handled separately)
"""

import os
import json
import random
import requests

BRAND = "Quietlyy"
YT_HANDLE = "@SayQuietlyy"

FB_AI_DISCLOSURE = "AI assistance was used in the making of this video."
YT_AI_DISCLOSURE = "AI assistance was used in the making of this video."

# ── Tiered hashtag pools — niche tags outperform giant ones for new pages ──
# Tier 1: Niche (10K–500K posts) — easiest to rank, most targeted audience
TAGS_NICHE_EMOTIONAL = [
    "emotionalhealing", "deepwordsdeepfeelings", "wordsthatheal",
    "feelingsquotes", "soulfulwords", "wordsthatmatter", "quietmoments",
    "innerpeacequotes", "selfreflectionquotes", "silentfeelings",
    "poetryofinstagram", "wordsthatfit", "emotionalpoetry", "deepemotions",
    "poetrysoul", "sadpoetry", "poetryrise", "brokenbutbeautiful",
]
TAGS_NICHE_NOSTALGIC = [
    "nostalgiavibes", "childhoodmemories", "throwbackfeeling", "missthosdays",
    "olddaysmemories", "rememberingthepast", "nostalgiahit", "memorylane",
    "pastmemories", "throwbackemotion", "nostalgiapoetry", "missingyou",
]
TAGS_NICHE_LOVE = [
    "lovepoetry", "romanticpoetry", "lovewords", "couplesquotes",
    "loveletters", "soulmatequotes", "tagsomeone", "sendthem",
    "lovequotes2026", "relationshippoetry", "heartfeltemotions",
]
TAGS_NICHE_POETIC = [
    "poetrycommunity", "poetsofinstagram", "poetrylovers", "writersofinstagram",
    "instapoets", "poetryisnotdead", "micropoetry", "spilledink",
    "wordsofwisdom", "deepthoughtsquotes", "soulfulpoetry",
]
TAGS_NICHE_MOTIVATIONAL = [
    "lifelessons", "wisdomquotes", "growthmindsetquotes", "selfgrowthquotes",
    "lifewisdom", "dailywisdom", "quotestoliveby", "mindsetshift",
    "lifeadvice", "purposequotes", "selfdiscovery",
]

# Tier 2: Mid (1M–5M) — good reach, moderate competition
TAGS_MID = [
    "quotes", "poetry", "deepthoughts", "lifequotes", "emotionalquotes",
    "reflection", "selfhealing", "mentalhealth", "relatable", "feelings",
    "motivation", "inspiration", "mindfulness", "healing", "love",
]

# Tier 3: Discovery/Reels — algorithm surface tags
TAGS_REELS = [
    "reels", "reelsofinstagram", "reelsviral", "explorepage",
    "foryoupage", "fyp", "viralreels", "trending",
]

# Geo — low impact but harmless, keep a few
GEO_TAGS = ["india", "usa", "uk", "uae"]

# ── Style-specific tag pools ──────────────────────────────────────────────
STYLE_TAGS = {
    "emotional":    TAGS_NICHE_EMOTIONAL,
    "nostalgic":    TAGS_NICHE_NOSTALGIC + TAGS_NICHE_EMOTIONAL[:5],
    "poetic":       TAGS_NICHE_POETIC + TAGS_NICHE_EMOTIONAL[:5],
    "love":         TAGS_NICHE_LOVE + TAGS_NICHE_EMOTIONAL[:4],
    "motivational": TAGS_NICHE_MOTIVATIONAL + TAGS_NICHE_EMOTIONAL[:4],
}

# ── CTAs — DM share is #1 distribution signal, per 2026 algorithm research ─
CTA_SHARE_BLOCKS = {
    "emotional": (
        "📩 Send this to someone who needs to hear it.\n"
        "💾 Save it for when you forget your worth.\n"
    ),
    "nostalgic": (
        "📩 Send this to someone you grew up with.\n"
        "💾 Save this — some memories deserve to stay close.\n"
    ),
    "poetic": (
        "📩 Send this to someone who feels things deeply.\n"
        "💾 Save it for a quiet night.\n"
    ),
    "love": (
        "❤️ Send this to the person you thought of.\n"
        "📩 Tag them. They need to know.\n"
    ),
    "motivational": (
        "📩 Send this to someone who needs a reminder today.\n"
        "💾 Save it — you'll need this again.\n"
    ),
}

SEO_PROMPT = """You are an Instagram SEO expert for short-form emotional content (2026 algorithm).

Key facts about 2026 Instagram algorithm:
- DM shares are the #1 distribution signal (more than likes or saves)
- Caption KEYWORDS drive discovery (more than hashtags now)
- First 3 seconds of video decide reach — hook must be in caption too
- Niche hashtags (10K-500K posts) outperform giant hashtags for new pages

Topic: {topic}
Style: {style}
Visual keywords: {keywords}
Script opening line: {theme}

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
- short_caption: 2-3 emotionally compelling sentences. Include the topic keyword naturally (for discovery). NO hashtags. Should make someone stop scrolling. Reference the emotional theme directly.
- instagram_hashtags: exactly 20 tags, NO # symbol, all lowercase. Mix: 8 niche (under 500K posts), 7 mid-size (1M-5M posts), 5 broad discovery. Topic-specific tags preferred over generic ones.
- youtube_title: under 60 chars, emotionally compelling, includes main keyword
- youtube_tags: exactly 15 tags, mix of specific and broad
- youtube_seo_line: 1 sentence, 120 chars max, keyword-rich for search
- best_post_times: 2 optimal IST times targeting India peak + global overlap"""


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

    ig_tags = [topic_tag, "quotes", "emotional", "poetry", "deepthoughts",
               "emotionalquotes", "reels", "poetrycommunity", "feelings",
               "relatable"] + GEO_TAGS
    ig_tags = list(dict.fromkeys(ig_tags))[:25]

    yt_tags = ["Shorts", "nostalgia", "deepthoughts", "lifequotes",
               "emotionalquotes", "relatable", "viral", "youtubeshorts",
               "poetry", "feelings", topic_tag, "emotional", "trending"]
    yt_tags = list(dict.fromkeys(yt_tags))[:15]

    return {
        "short_caption": caption,
        "instagram_hashtags": ig_tags,
        "youtube_title": first_line[:57] + ("..." if len(first_line) > 57 else ""),
        "youtube_tags": yt_tags,
        "youtube_seo_line": f"A quiet reflection on {topic} — words that hit different.",
        "best_post_times": {
            "facebook_instagram": ["11:00", "22:00"],
            "youtube": ["20:30", "22:00"],
            "reasoning": "11AM IST morning scroll peak + 10PM late-night emotional scroll.",
        },
    }


# ── Public API ──────────────────────────────────────────────────────────────

def _build_hashtag_set(ai_tags, style):
    """Build a tiered hashtag set: AI suggestions + niche pool + mid + reels + geo.
    25 total. Niche tags (easier to rank) weighted highest for new page growth."""
    clean = [t.lstrip("#").lower().replace(" ", "") for t in (ai_tags or [])]

    # Pull from style-specific niche pool
    niche_pool = STYLE_TAGS.get(style, TAGS_NICHE_EMOTIONAL)
    niche_sample = random.sample(niche_pool, min(6, len(niche_pool)))

    # Mid-size tags
    mid_sample = random.sample(TAGS_MID, min(5, len(TAGS_MID)))

    # Reels/discovery
    reels_sample = random.sample(TAGS_REELS, min(4, len(TAGS_REELS)))

    # Combine: AI first (most topic-specific), then niche, mid, reels, geo
    combined = clean + niche_sample + mid_sample + reels_sample + GEO_TAGS
    # Deduplicate preserving order
    seen = set()
    result = []
    for t in combined:
        if t not in seen and t:
            seen.add(t)
            result.append(t)

    return result[:25]


def generate_seo(topic, script_text, visual_keywords, style="emotional"):
    """
    Returns platform-specific SEO metadata dict:
    {
        "facebook": { "description": str, "hashtags": list },
        "youtube":  { "title": str, "description": str, "tags": list },
        "best_post_times": { "facebook_instagram": [...], "youtube": [...], "reasoning": str }
    }
    """
    lines = [l.strip() for l in script_text.split("\n") if l.strip()]
    theme = lines[0] if lines else topic

    prompt = SEO_PROMPT.format(
        topic=topic,
        style=style,
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

    # ── Hashtags — tiered system: niche > mid > reels > geo ──────────────
    ig_tags_clean = _build_hashtag_set(ai_data.get("instagram_hashtags", []), style)
    hashtag_str = " ".join(f"#{t}" for t in ig_tags_clean)

    # ── CTA — DM share is #1 distribution signal per 2026 research ───────
    short_caption = ai_data.get("short_caption", theme)
    cta_block = CTA_SHARE_BLOCKS.get(style, CTA_SHARE_BLOCKS["emotional"])

    fb_description = (
        f"{short_caption}\n\n"
        f"{cta_block}\n"
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
