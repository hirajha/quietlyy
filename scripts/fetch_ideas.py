"""
Quietlyy — Fresh Ideas Agent
Searches the web for trending emotional topics, poetry themes, and unique
human stories to feed into the script generator.

Uses Gemini's Google Search grounding to find:
- What people are emotionally resonating with right now
- Fresh angles on heartbreak, friendship, loss, healing
- Trending poem/quote themes across Instagram, Reddit, Pinterest

Returns: list of FreshIdea dicts with topic, angle, and emotional hook
Falls back gracefully if web search is unavailable.
"""

import os
import json
import re
import requests
from datetime import datetime


def _search_with_gemini(query):
    """Use Gemini with Google Search grounding to find real web content."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": query}]}],
                "tools": [{"google_search": {}}],
                "generationConfig": {
                    "maxOutputTokens": 1500,
                    "temperature": 0.7,
                },
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        if "candidates" in data and data["candidates"]:
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[ideas] Gemini search failed: {e}")
    return None


def _extract_ideas_with_ai(raw_research, existing_topics):
    """Parse raw web research into structured FreshIdea list."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not key:
        return []

    existing_str = ", ".join(existing_topics[:20]) if existing_topics else "none"

    prompt = f"""You are a creative director for "Quietlyy" — an emotional quote video channel.

Based on this web research about trending emotional content:
---
{raw_research[:2000]}
---

Extract 6 fresh, specific ideas for emotional video scripts.

Rules:
- Each idea must be about HUMAN EMOTIONS — heartbreak, friendship, missing someone, growing up, letting go, healing
- Must feel CURRENT and SPECIFIC — not generic "love hurts" advice
- Should inspire a 25-second spoken-word poem that makes people feel something deep
- AVOID these already used topics: {existing_str}
- Think: what are people ACTUALLY going through right now? What shared pain is trending?

Return ONLY valid JSON array:
[
  {{
    "topic": "Short topic name (3-5 words)",
    "angle": "The specific emotional angle (1 sentence) — what makes this unique",
    "hook": "A possible first line that would stop someone scrolling (1 line)",
    "style": "nostalgic OR emotional"
  }}
]"""

    providers = [
        ("gemini", os.environ.get("GEMINI_API_KEY")),
        ("openai", os.environ.get("OPENAI_API_KEY")),
        ("groq", os.environ.get("GROQ_API_KEY")),
    ]

    for provider, api_key in providers:
        if not api_key:
            continue
        try:
            if provider == "gemini":
                resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.8}},
                    timeout=30,
                )
                resp.raise_for_status()
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            elif provider == "openai":
                resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini",
                          "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": 800, "temperature": 0.8,
                          "response_format": {"type": "json_object"}},
                    timeout=20,
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]
            else:  # groq
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.3-70b-versatile",
                          "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": 800, "temperature": 0.8,
                          "response_format": {"type": "json_object"}},
                    timeout=20,
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]

            # Extract JSON array
            match = re.search(r'\[[\s\S]*\]', text)
            if match:
                ideas = json.loads(match.group())
                if ideas and isinstance(ideas, list):
                    print(f"[ideas] Extracted {len(ideas)} fresh ideas via {provider}")
                    return ideas
        except Exception as e:
            print(f"[ideas] {provider} extraction failed: {e}")

    return []


def fetch_fresh_ideas(existing_topics=None):
    """
    Main entry: search web for trending emotional content and return fresh ideas.
    Returns list of idea dicts, or empty list if unavailable (never blocks pipeline).
    """
    print("[ideas] Searching web for trending emotional content...")

    existing_topics = existing_topics or []
    month = datetime.now().strftime("%B %Y")

    # Search query targeting emotional content that's trending
    search_query = f"""Search for trending emotional content in {month}:
1. What emotional topics are people posting about on Instagram Reels and YouTube Shorts right now?
2. What heartbreak, friendship, loss, or healing themes are going viral in short-form videos?
3. What are people searching for on Reddit r/relationships, r/BreakUps, r/offmychest about emotions?
4. What poetry and quote themes are getting millions of saves on Pinterest and Instagram in {month}?
5. Any specific emotional experiences (like social media ghosting, growing apart from friends, realizing you love the wrong person) that are trending?

Focus on: unique human experiences, not generic advice. What specific situations are making people feel deeply right now?"""

    raw_research = _search_with_gemini(search_query)

    if not raw_research:
        print("[ideas] Web search unavailable — using fallback ideas")
        return _fallback_ideas()

    print(f"[ideas] Got {len(raw_research)} chars of web research")
    ideas = _extract_ideas_with_ai(raw_research, existing_topics)

    if not ideas:
        print("[ideas] Extraction failed — using fallback ideas")
        return _fallback_ideas()

    for idea in ideas:
        print(f"  • [{idea.get('style','?')}] {idea.get('topic')} — {idea.get('angle','')[:60]}")

    return ideas


def _fallback_ideas():
    """Static fallback ideas when web search is unavailable."""
    return [
        {"topic": "The Last Good Day", "angle": "The day before everything changed — you didn't know it was goodbye", "hook": "You don't always know it's the last time.", "style": "emotional"},
        {"topic": "Reading Old Texts", "angle": "Scrolling back through conversations with someone you've lost", "hook": "I still have all your messages saved.", "style": "emotional"},
        {"topic": "Growing Up Too Fast", "angle": "The moment childhood ended and no one warned you", "hook": "Nobody told me adulthood would feel this lonely.", "style": "nostalgic"},
        {"topic": "The Friend You Became", "angle": "Realizing you've become the person who always checks in first", "hook": "I'm always the one who texts first.", "style": "emotional"},
        {"topic": "Silence After Noise", "angle": "The emptiness after a relationship ends — the missing sounds", "hook": "It's not the fights I miss. It's the quiet mornings.", "style": "emotional"},
        {"topic": "Unfinished Conversations", "angle": "Things left unsaid to people who are no longer there to hear them", "hook": "I still write things I'll never send.", "style": "emotional"},
    ]


def ideas_to_theme_hints(ideas):
    """Convert ideas list to theme hints string for script generator."""
    if not ideas:
        return ""
    hints = []
    for idea in ideas[:4]:
        hints.append(f"- {idea['topic']}: {idea.get('angle', '')} (hook: \"{idea.get('hook', '')}\")")
    return "Fresh trending ideas from web research:\n" + "\n".join(hints)
