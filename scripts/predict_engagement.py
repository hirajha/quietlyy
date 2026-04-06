"""
Quietlyy — Engagement Predictor Agent
Predicts the likelihood a script/video will get likes, saves, and shares.
Runs AFTER the quality gate, BEFORE posting — no cost if it rejects.

Scores the script on viral emotional triggers used by top quote accounts.
Returns a prediction with specific improvement suggestions.
"""

import os
import re
import json
import requests

# Viral triggers that drive saves/shares on emotional content
VIRAL_TRIGGERS = {
    "universal_pain": ["miss", "lost", "alone", "left", "never said", "last time", "didn't know"],
    "identity": ["you are", "you were", "you're not", "you deserve", "you gave"],
    "specificity": ["3 am", "sunday", "old texts", "last message", "your name"],
    "shareability": ["send this", "someone who", "tag", "for the one", "for anyone"],
    "save_triggers": ["save this", "remember this", "write this down", "keep this"],
    "pattern_interrupt": ["but here's", "the truth is", "what they don't", "no one tells you"],
}


def _count_triggers(script_text):
    text_lower = script_text.lower()
    hits = {}
    total = 0
    for category, phrases in VIRAL_TRIGGERS.items():
        count = sum(1 for p in phrases if p in text_lower)
        hits[category] = count
        total += count
    return hits, total


def _predict_with_ai(script_text, topic, style, trigger_hits):
    """Ask AI to predict engagement and suggest one concrete improvement."""
    trigger_summary = ", ".join(
        f"{k}({v})" for k, v in trigger_hits.items() if v > 0
    ) or "none detected"

    prompt = f"""You are a viral content analyst for emotional quote videos (YouTube Shorts, Instagram Reels).

Analyze this script and predict its engagement potential:

TOPIC: {topic} ({style})
SCRIPT:
{script_text}

VIRAL TRIGGERS DETECTED: {trigger_summary}

Predict on these factors (each 0-10):
1. SAVE RATE: Will people save/bookmark this? (emotional resonance, relatability)
2. SHARE RATE: Will people send this to someone? (specific enough to tag someone)
3. COMMENT RATE: Will people comment? (does it ask a question or demand a response?)
4. HOOK STRENGTH: Does line 1 stop the scroll in 2 seconds?
5. REWATCH: Will people watch it again? (poetic rhythm, surprising lines)

Also give ONE specific suggestion to increase shares (max 15 words).

Return ONLY valid JSON:
{{"save": <0-10>, "share": <0-10>, "comment": <0-10>, "hook": <0-10>, "rewatch": <0-10>, "overall": <0-10>, "prediction": "low/medium/high/viral", "top_suggestion": "..."}}"""

    providers = [
        ("openai", os.environ.get("OPENAI_API_KEY")),
        ("gemini", os.environ.get("GEMINI_API_KEY")),
        ("groq", os.environ.get("GROQ_API_KEY")),
    ]

    for provider, key in providers:
        if not key:
            continue
        try:
            if provider == "openai":
                resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": 200, "temperature": 0.3,
                          "response_format": {"type": "json_object"}},
                    timeout=15,
                )
                resp.raise_for_status()
                return json.loads(resp.json()["choices"][0]["message"]["content"]), provider
            elif provider == "gemini":
                resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"maxOutputTokens": 300, "temperature": 0.3}},
                    timeout=20,
                )
                resp.raise_for_status()
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                match = re.search(r'\{[\s\S]*\}', text)
                if match:
                    return json.loads(match.group()), provider
            else:  # groq
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.3-70b-versatile",
                          "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": 200, "temperature": 0.3,
                          "response_format": {"type": "json_object"}},
                    timeout=15,
                )
                resp.raise_for_status()
                return json.loads(resp.json()["choices"][0]["message"]["content"]), provider
        except Exception as e:
            print(f"[predict] {provider} failed: {e}")

    return None, None


def predict_engagement(script_text, topic, style):
    """
    Predict engagement potential of a script.
    Returns dict with scores, prediction level, and improvement suggestion.
    Never blocks the pipeline — logs only.
    """
    print(f"[predict] Analyzing engagement potential...")

    trigger_hits, trigger_total = _count_triggers(script_text)

    result, provider = _predict_with_ai(script_text, topic, style, trigger_hits)

    if not result:
        print(f"[predict] AI unavailable — skipping prediction")
        return {"prediction": "unknown", "overall": 5}

    overall = result.get("overall", 5)
    prediction = result.get("prediction", "medium")
    suggestion = result.get("top_suggestion", "")

    # Color-coded log
    icons = {"low": "🔴", "medium": "🟡", "high": "🟢", "viral": "🚀"}
    icon = icons.get(prediction, "⚪")

    print(f"[predict] {icon} Engagement: {prediction.upper()} (score {overall}/10) via {provider}")
    print(f"[predict]   Save:{result.get('save',0)} Share:{result.get('share',0)} "
          f"Comment:{result.get('comment',0)} Hook:{result.get('hook',0)} Rewatch:{result.get('rewatch',0)}")
    print(f"[predict]   Viral triggers: {trigger_total} hits — {trigger_hits}")
    if suggestion:
        print(f"[predict]   💡 Tip: {suggestion}")

    result["triggers"] = trigger_hits
    result["trigger_total"] = trigger_total
    return result
