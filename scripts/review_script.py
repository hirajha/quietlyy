"""
Quietlyy — Script Quality Agent
Reviews generated scripts for:
  1. No banned openers ("There was a time", "In a world", etc.)
  2. No near-duplicate of previously used scripts (fuzzy hash check)
  3. Emotional quality score — must feel connected, unique, human
  4. Matches the Quietlyy vibe (hook + human pain + lesson)

Returns: {"approved": bool, "reason": str, "score": int}
Integrated into generate_script.py — only approved scripts proceed to video.
"""

import os
import json
import re
import hashlib
import requests

USED_SCRIPTS_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "used_scripts.json")

# Openers that are overused / banned
BANNED_OPENERS = [
    "there was a time",
    "in a world",
    "once upon a time",
    "we live in a world",
    "in today's world",
    "have you ever",
    "life is",
    "we all have",
    "sometimes in life",
    "not everyone",
    "some people",
]

# Tighter threshold — catch concept-level near-duplicates, not just word overlap
SIMILARITY_THRESHOLD = 0.45


def _normalize(text):
    return re.sub(r"[^a-z0-9\s]", "", text.lower().strip())


def _line_hashes(script_text):
    lines = [_normalize(l) for l in script_text.split("\n") if l.strip()]
    return set(hashlib.md5(l.encode()).hexdigest() for l in lines if len(l) > 8)


def _similarity(script_a, script_b):
    """Jaccard similarity on line-level hashes."""
    hashes_a = _line_hashes(script_a)
    hashes_b = _line_hashes(script_b)
    if not hashes_a or not hashes_b:
        return 0.0
    return len(hashes_a & hashes_b) / len(hashes_a | hashes_b)


def _word_overlap(script_a, script_b):
    """Word-level overlap for near-duplicate detection."""
    words_a = set(_normalize(script_a).split())
    words_b = set(_normalize(script_b).split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def load_used_scripts():
    if os.path.exists(USED_SCRIPTS_PATH):
        with open(USED_SCRIPTS_PATH) as f:
            try:
                return json.load(f)
            except Exception:
                pass
    return []


# Common metaphors/images to track — if a script uses 2+ of these from recent scripts, reject
TRACKED_METAPHORS = [
    "candle", "storm", "umbrella", "roots", "tide", "shore", "ocean", "waves",
    "shadow", "light", "rain", "fire", "wind", "bridge", "door", "window",
    "mirror", "path", "road", "wall", "garden", "flower", "seed", "tree",
    "star", "moon", "sun", "dark", "dawn", "silence", "noise", "echo",
    "mask", "armor", "sword", "anchor", "compass", "map", "letter",
]


def _extract_metaphors(script_text):
    """Extract which tracked metaphors appear in this script."""
    normalized = _normalize(script_text)
    return set(m for m in TRACKED_METAPHORS if m in normalized)


def _extract_core_theme(script_text):
    """Extract a rough theme fingerprint: dominant emotional concepts."""
    normalized = _normalize(script_text)
    theme_words = {
        "loneliness": ["alone", "lonely", "solitude", "isolated", "left"],
        "being_used": ["used", "needed", "convenient", "purpose", "utility"],
        "heartbreak": ["heartbreak", "broke", "broken", "shattered", "hurt", "pain", "wound"],
        "friendship_loss": ["friend", "friendship", "drifted", "apart", "distance", "grew"],
        "self_worth": ["worth", "enough", "value", "deserve", "love yourself"],
        "nostalgia": ["remember", "childhood", "younger", "past", "ago", "used to"],
        "growth": ["grew", "grow", "stronger", "healed", "learned", "became"],
        "love": ["love", "loved", "loving", "lover", "heart", "together"],
        "grief_loss": ["lost", "gone", "miss", "grief", "death", "left behind"],
        "silence": ["quiet", "silence", "silent", "still", "unspoken"],
        "moving_on": ["moved on", "letting go", "release", "free", "forward"],
    }
    found = [theme for theme, words in theme_words.items()
             if any(w in normalized for w in words)]
    return set(found)


def save_used_script(script_text, topic, style):
    scripts = load_used_scripts()
    scripts.append({
        "topic": topic,
        "style": style,
        "script": script_text,
        "hash": hashlib.md5(_normalize(script_text).encode()).hexdigest(),
        "metaphors": list(_extract_metaphors(script_text)),
        "themes": list(_extract_core_theme(script_text)),
    })
    # Keep last 60 scripts in memory
    scripts = scripts[-60:]
    os.makedirs(os.path.dirname(USED_SCRIPTS_PATH), exist_ok=True)
    with open(USED_SCRIPTS_PATH, "w") as f:
        json.dump(scripts, f, indent=2)


def get_recently_used_context(n=8):
    """Return recently used metaphors and themes for the generation prompt.
    Used to tell the AI what to AVOID so it doesn't repeat itself."""
    scripts = load_used_scripts()[-n:]
    all_metaphors = set()
    all_themes = set()
    for s in scripts:
        all_metaphors.update(s.get("metaphors", []))
        all_themes.update(s.get("themes", []))
    return list(all_metaphors), list(all_themes)


def check_banned_opener(script_text):
    first_line = _normalize(script_text.split("\n")[0])
    for banned in BANNED_OPENERS:
        if first_line.startswith(banned) or banned in first_line[:40]:
            return False, f"Banned opener detected: '{banned}'"
    return True, "OK"


def check_duplicate(script_text):
    used = load_used_scripts()
    new_metaphors = _extract_metaphors(script_text)
    new_themes = _extract_core_theme(script_text)

    for prev in used[-20:]:  # check last 20
        # Word/line level similarity
        sim = max(
            _similarity(script_text, prev["script"]),
            _word_overlap(script_text, prev["script"]) * 0.8,
        )
        if sim >= SIMILARITY_THRESHOLD:
            return False, f"Too similar to '{prev['topic']}' (word overlap: {sim:.0%})"

        # Concept-level: same core themes AND same metaphors = reject
        prev_themes = set(prev.get("themes", []))
        prev_metaphors = set(prev.get("metaphors", []))
        theme_overlap = new_themes & prev_themes
        metaphor_overlap = new_metaphors & prev_metaphors

        # If it covers the same emotional territory with the same imagery — it's a duplicate in spirit
        if len(theme_overlap) >= 2 and len(metaphor_overlap) >= 2:
            return False, (
                f"Conceptual duplicate of '{prev['topic']}' — "
                f"same themes ({', '.join(list(theme_overlap)[:3])}) "
                f"and same metaphors ({', '.join(list(metaphor_overlap)[:3])})"
            )

    return True, "OK"


def check_quality_with_ai(script_text, topic, style, examples):
    """Ask AI to score the script on Quietlyy's emotional quality criteria."""
    examples_text = "\n\n".join(
        f"EXAMPLE ({e['style']}):\n{e['script']}" for e in examples[:4]
    )

    prompt = f"""You are a script quality reviewer for "Quietlyy" — an emotional quote video channel.

Your job: Review this script and score it on emotional quality.

SCRIPT TO REVIEW (topic: {topic}, style: {style}):
{script_text}

QUIETLYY QUALITY STANDARDS (study these examples):
{examples_text}

Score this script on these criteria (each 0-10):
1. HOOK: Does the first line immediately grab? Would someone stop scrolling?
2. EMOTION: Does it feel genuine? Would people feel it in their chest?
3. ORIGINALITY: Is it a TRULY UNIQUE perspective — not a repackaged common idea?
4. CONNECTION: Does it speak about real human pain — heartbreak, friendship, loss, growth?
5. LESSON: Does it end with something the viewer can carry with them?

Rules for REJECTION (score the whole script 0 if any apply):
- First line is generic ("There was a time", "In a world", "We all have", "Life is", "Some people", "Not everyone")
- Script is a variation of a common idea — the MESSAGE is not new, even if the words are slightly different
  Example of rejection: "You were used" = "They only needed you" = "You were their backup" — ALL THE SAME IDEA
- Script uses only overused metaphors: candle, storm, tide, roots, umbrella, shore — with no fresh angle
- Lines are all the same length / monotonous rhythm
- No emotional turn or lesson at the end
- Sounds like a motivational poster or something you've read 100 times on Instagram already
- The core insight could be summarized as a cliché: "people leave", "be yourself", "you deserve better"

ORIGINALITY TEST: Ask yourself — has this specific combination of idea + angle + imagery been said before in this exact way? If the answer is "kind of yes" — reject it.

Return ONLY valid JSON:
{{"score": <overall 0-10>, "hook": <0-10>, "emotion": <0-10>, "originality": <0-10>, "approved": <true/false>, "reason": "<one sentence why>"}}

A score of 7+ means approved. Be strict on originality — generic emotional content is everywhere. Only truly fresh scripts should pass."""

    # Try ChatGPT first, then Gemini
    for gen_fn, name in [(_call_openai, "ChatGPT"), (_call_gemini, "Gemini"), (_call_groq, "Groq")]:
        try:
            result = gen_fn(prompt)
            if result and "score" in result:
                print(f"[quality] Reviewed via {name} — score: {result.get('score')}/10")
                return result
        except Exception as e:
            print(f"[quality] {name} review failed: {e}")

    # Fallback: approve (don't block on AI failure)
    print("[quality] AI review unavailable — approving by default")
    return {"score": 7, "approved": True, "reason": "AI review unavailable"}


def _call_openai(prompt):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        },
        timeout=20,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


def _call_gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
        headers={"Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"maxOutputTokens": 300, "temperature": 0.3}},
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    match = re.search(r'\{[\s\S]*\}', text)
    return json.loads(match.group()) if match else None


def _call_groq(prompt):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        },
        timeout=20,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


def review_script(script_text, topic, style, examples):
    """
    Full quality review pipeline.
    Returns (approved: bool, reason: str, score: int)
    """
    print(f"[quality] Reviewing script: '{topic}' ({style})")

    # 1. Check banned openers
    ok, reason = check_banned_opener(script_text)
    if not ok:
        print(f"[quality] REJECTED — {reason}")
        return False, reason, 0

    # 2. Check duplicates
    ok, reason = check_duplicate(script_text)
    if not ok:
        print(f"[quality] REJECTED — {reason}")
        return False, reason, 0

    # 3. AI quality score
    ai_result = check_quality_with_ai(script_text, topic, style, examples)
    score = ai_result.get("score", 5)
    approved = ai_result.get("approved", score >= 6)
    reason = ai_result.get("reason", "")

    if not approved or score < 7:
        print(f"[quality] REJECTED (score {score}/10) — {reason}")
        return False, f"Score {score}/10: {reason}", score

    print(f"[quality] APPROVED (score {score}/10) — {reason}")
    return True, reason, score
