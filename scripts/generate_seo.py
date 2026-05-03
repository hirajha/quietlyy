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
import requests

BRAND = "Quietlyy"
YT_HANDLE = "@SayQuietlyy"

FB_AI_DISCLOSURE = "AI assistance was used in the making of this video."
YT_AI_DISCLOSURE = "AI assistance was used in the making of this video."

# ── Niche hashtags per style — research-backed: niche tags outperform broad ones ──
# Broad tags (#love #motivation) = buried in millions of posts.
# Niche tags (#grief #unspokenwords) = seen by exact audience that shares emotional content.
STYLE_HASHTAGS = {
    "emotional":    ["grief", "emotionalhealing", "unspokenwords", "heartbreak", "longing", "innerhealing", "quietlyy"],
    "nostalgic":    ["nostalgia", "childhoodmemories", "missthosedays", "simplelife", "familylove", "thenandnow", "quietlyy"],
    "poetic":       ["poetrylovers", "spokenword", "soulquotes", "deepfeelings", "wordsthatmatter", "unspokenwords", "quietlyy"],
    "love":         ["missingyou", "lovestory", "heartache", "unspokenlove", "lovequotes", "deepfeelings", "quietlyy"],
    "wisdom":       ["lifewisdom", "soulquotes", "innerpeace", "lifetruth", "deepthoughts", "mentalpeace", "quietlyy"],
    "motivational": ["keepgoing", "innerstrength", "healingjourney", "selfworth", "mentalhealth", "quietstrength", "quietlyy"],
}

# ── CTAs — research-backed: "Save this" and "Share with" outperform tag-baiting ──
# Facebook algorithm PENALIZES "tag 3 friends" / "comment YES" — suppresses reach.
# "Save this" and "Share with someone who needs this" are safe and drive DM shares.
CTA_SHARE_BLOCKS = {
    "emotional": (
        "Save this if it found you at the right time.\n"
        "Share it with someone who needs to feel less alone today."
    ),
    "nostalgic": (
        "Save this for the people you still miss.\n"
        "Share it with someone who grew up with you."
    ),
    "poetic": (
        "Save this for a quiet night when you need it.\n"
        "Share it with someone who feels things deeply."
    ),
    "love": (
        "Save this. Some feelings deserve to be kept.\n"
        "Send this to the person you thought of while reading."
    ),
    "wisdom": (
        "Save this for the days you forget.\n"
        "Share it with someone carrying something heavy right now."
    ),
    "motivational": (
        "Save this for when you need a reminder.\n"
        "Share it with someone who is quietly struggling."
    ),
}

SEO_PROMPT = """You are a YouTube SEO expert for short emotional video content.

Topic: {topic}
Style: {style}
Script opening line: {theme}

Return ONLY valid JSON:
{{
  "youtube_title": "...",
  "youtube_tags": ["tag1", "tag2"],
  "best_post_times": {{
    "facebook_instagram": ["HH:MM IST", "HH:MM IST"],
    "youtube": ["HH:MM IST", "HH:MM IST"],
    "reasoning": "1 sentence why"
  }}
}}

Rules:
- youtube_title: under 60 chars, emotionally compelling, includes main keyword
- youtube_tags: exactly 10 tags, mix of specific and broad, no # symbol
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
    first_line = [l.strip() for l in script_text.split("\n") if l.strip()][0]
    topic_tag = topic.replace(" ", "").lower()
    yt_tags = ["shorts", "poetry", "love", "memories", "healing",
               "lifequotes", "relatable", topic_tag, "emotional", "quietlyy"]
    return {
        "youtube_title": first_line[:57] + ("..." if len(first_line) > 57 else ""),
        "youtube_tags": yt_tags,
        "best_post_times": {
            "facebook_instagram": ["11:00", "22:00"],
            "youtube": ["20:30", "22:00"],
            "reasoning": "11AM IST morning scroll peak + 10PM late-night emotional scroll.",
        },
    }


# ── Public API ──────────────────────────────────────────────────────────────

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
        theme=theme,
    )

    ai_data = None
    for fn, name in [(_generate_with_gemini, "Gemini"), (_generate_with_openai, "OpenAI"), (_generate_with_groq, "Groq")]:
        ai_data = fn(prompt)
        if ai_data and "youtube_title" in ai_data:
            print(f"[seo] Generated via {name}")
            break

    if not ai_data:
        print("[seo] Using template fallback")
        ai_data = _template_fallback(topic, script_text)

    # ── 3-part caption formula (research-backed for viral emotional pages) ──
    # Part 1: Hook — first script line (emotionally charged, appears before "See more")
    hook_line = lines[0] if lines else topic

    # Part 2: Quote reprint — next 2-3 lines (full quote for accessibility + discovery)
    quote_lines = lines[1:4]
    quote_text = "\n".join(quote_lines) if quote_lines else ""

    # Part 3: CTA — "Save this" / "Share with" (no tag-baiting — Facebook penalizes it)
    cta_block = CTA_SHARE_BLOCKS.get(style, CTA_SHARE_BLOCKS["emotional"])

    # ── Hashtags: niche-specific (~7 tags) ───────────────────────────────
    hashtag_list = STYLE_HASHTAGS.get(style, STYLE_HASHTAGS["emotional"])
    hashtag_str = " ".join(f"#{t}" for t in hashtag_list)

    caption_text = hook_line  # used in YouTube desc too

    # ── Facebook / Instagram description — 3-part formula ────────────────
    fb_description = (
        f"{hook_line}\n\n"
        f"{quote_text}\n\n"
        f"{cta_block}\n\n"
        f"{hashtag_str}"
    ).strip()

    # ── YouTube description ───────────────────────────────────────────────
    yt_tags = ai_data.get("youtube_tags", [])
    yt_tags_clean = [t.lstrip("#").lower().replace(" ", "") for t in yt_tags][:10]

    yt_description = (
        f"{caption_text}\n\n"
        f"💾 Save this for when you need it.\n"
        f"🔔 Subscribe → {YT_HANDLE}\n\n"
        f"{hashtag_str}\n\n"
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
            "hashtags": hashtag_list,
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
