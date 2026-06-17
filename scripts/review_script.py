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

USED_SCRIPTS_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "used_scripts.json")

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
    # "you were X" pattern — massively overused, banned across all styles
    "you were not",
    "you were never",
    "you weren't",
    "you were just",
    "you were always",
    "you were cherished",
    "you were loved for",
    "you were too",
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
# ORDER MATTERS for _central_image (first match wins): specific lived-anchor
# objects FIRST (they ARE the story — a repeat anchor = a repeat story even
# with new words), generic poetry words after.
TRACKED_METAPHORS = [
    # Lived anchors (specific → checked first)
    "porch", "mug", "cup", "coffee", "tea", "bed", "pillow", "blanket",
    "phone", "text", "voicemail", "ringtone", "contact", "chair", "table",
    "couch", "hoodie", "jacket", "sweater", "perfume", "photo", "picture",
    "song", "playlist", "radio", "ceiling", "kitchen", "hallway", "stairs",
    "keys", "ring", "note", "diary", "wallet", "glass", "plate",
    # Generic poetry imagery
    "candle", "storm", "umbrella", "roots", "tide", "shore", "ocean", "waves",
    "shadow", "light", "rain", "fire", "wind", "bridge", "door", "window",
    "mirror", "path", "road", "wall", "garden", "flower", "seed", "tree",
    "star", "moon", "sun", "dark", "dawn", "silence", "noise", "echo",
    "mask", "armor", "sword", "anchor", "compass", "map", "letter",
]


def _extract_metaphors(script_text):
    """Extract which tracked metaphors/anchors appear in this script."""
    normalized = _normalize(script_text)
    return set(m for m in TRACKED_METAPHORS if m in normalized)


def _opener_stem(script_text, n_words=2):
    """First N normalized words of line 1 — the opener fingerprint.
    Two words catches the formula family: 'You're sitting alone.' /
    'You're sitting with me.' / 'You're sitting by the stove.' all share
    'youre sitting'. Within the recent window the same first-two-words IS
    a repeated opening formula, even when the rest differs."""
    first = script_text.strip().split("\n")[0]
    return " ".join(_normalize(first).split()[:n_words])


def _central_image(script_text):
    """The anchor the script is BUILT on: the first tracked metaphor/object
    appearing in the first 3 lines (the hook). Two scripts with the same
    central image are the same story regardless of wording (porch-light bug)."""
    lines = [l for l in script_text.split("\n") if l.strip()][:3]
    head = _normalize(" ".join(lines))
    for m in TRACKED_METAPHORS:
        if m in head:
            return m
    return None


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


def get_recently_used_context(n=15):
    """Return recently used metaphors and themes for the generation prompt.
    Used to tell the AI what to AVOID so it doesn't repeat itself."""
    scripts = load_used_scripts()[-n:]
    all_metaphors = set()
    all_themes = set()
    for s in scripts:
        # Recompute from text (stored 'metaphors' predate the expanded
        # anchor list, so most are stale-empty).
        all_metaphors.update(_extract_metaphors(s.get("script", "")))
        all_themes.update(s.get("themes", []))
    return list(all_metaphors), list(all_themes)


def get_recent_openers_and_images(n=15):
    """Recent opening lines + central images — injected into the generation
    prompt so the AI avoids repeating a formula instead of burning attempts."""
    scripts = load_used_scripts()[-n:]
    openers, images = [], set()
    for s in scripts:
        first = s.get("script", "").strip().split("\n")[0].strip()
        if first:
            openers.append(first)
        img = _central_image(s.get("script", ""))
        if img:
            images.add(img)
    return openers, sorted(images)


def check_banned_opener(script_text):
    first_line = _normalize(script_text.split("\n")[0])
    for banned in BANNED_OPENERS:
        # Only check if the line STARTS with the banned phrase — not mid-line matches.
        # Mid-line matching was rejecting valid lines like "And you were not ready."
        if first_line.startswith(banned):
            return False, f"Banned opener detected: '{banned}'"
    return True, "OK"


def check_duplicate(script_text):
    used = load_used_scripts()
    new_metaphors = _extract_metaphors(script_text)
    new_themes = _extract_core_theme(script_text)
    new_opener = _opener_stem(script_text)
    new_image = _central_image(script_text)

    # Opener formula: same first words as ANY recent script = same template
    # ("You're sitting..." appeared 3x in 10 videos). Computed from stored
    # script text, so it covers the whole history without a backfill.
    for prev in used[-25:]:
        if new_opener and new_opener == _opener_stem(prev["script"]):
            return False, (f"Same opener formula as '{prev['topic']}' "
                           f"('{new_opener}...') — needs a different opening")

    # Central image: the anchor IS the story. Two porch-light scripts in a row
    # slipped through word-overlap — block a repeat anchor within the last 25
    # (~6 days at 4/day; the 60-entry history cap bounds it).
    if new_image:
        for prev in used[-25:]:
            if new_image == _central_image(prev["script"]):
                return False, (f"Same central image as '{prev['topic']}' "
                               f"('{new_image}') — same story in new words")

    for prev in used[-20:]:  # check last 20
        # Word/line level similarity
        sim = max(
            _similarity(script_text, prev["script"]),
            _word_overlap(script_text, prev["script"]) * 0.8,
        )
        if sim >= SIMILARITY_THRESHOLD:
            return False, f"Too similar to '{prev['topic']}' (word overlap: {sim:.0%})"

        # Concept-level duplicate detection
        prev_themes = set(prev.get("themes", []))
        prev_metaphors = set(prev.get("metaphors", []))
        theme_overlap = new_themes & prev_themes
        metaphor_overlap = new_metaphors & prev_metaphors

        # Same emotional territory = same story even with different words → reject
        if len(theme_overlap) >= 2:
            return False, (
                f"Same emotional story as '{prev['topic']}' — "
                f"same themes: {', '.join(list(theme_overlap)[:3])}. Need a completely different angle."
            )
        # Same imagery + same theme = reject
        if len(theme_overlap) >= 1 and len(metaphor_overlap) >= 2:
            return False, (
                f"Conceptual duplicate of '{prev['topic']}' — "
                f"same theme ({', '.join(list(theme_overlap))}) "
                f"with same imagery ({', '.join(list(metaphor_overlap)[:3])})"
            )

    return True, "OK"


def check_quality_with_ai(script_text, topic, style, examples):
    """Ask AI to score the script on Quietlyy's emotional quality criteria."""
    examples_text = "\n\n".join(
        f"EXAMPLE ({e['style']}):\n{e['script']}" for e in examples[:4]
    )

    prompt = f"""You are a script quality reviewer for "Quietlyy" — an emotional quote video channel targeting adults 35-65 who share content about life, love, and human connection.

Your job: Review this script and score it on emotional quality.

SCRIPT TO REVIEW (topic: {topic}, style: {style}):
{script_text}

QUIETLYY QUALITY STANDARDS (study these examples):
{examples_text}

Score this script on these criteria:
1. HOOK (0-10): Does the first line stop a scrolling finger? Is it specific and unexpected — not a generic opener?
2. EMOTION (0-10): Does it feel genuinely human? Would someone feel it in their chest and want to share it?
3. FRESHNESS (0-10): Is the ANGLE or EXECUTION fresh — even if the topic (love, loss, nostalgia) is familiar?
4. FLOW (0-10): Do the lines build toward something — a turn, a realisation, or a moment of truth?
5. REALNESS (0-10): THE MOST IMPORTANT ONE. Would the viewer think "this is MY exact
   life — how do they know?" That comes from CONCRETE, SPECIFIC, lived detail (a saved
   contact, an empty side of the bed, a 2am phone screen, a half-typed text). Abstract
   nature-poetry ("the river bends", "love is a storm") scores LOW here — it's pretty
   but says nothing about the viewer's actual life.

IMPORTANT CONTEXT: Emotional content about love, loneliness, nostalgia, and heartbreak IS the genre.
A script about missing someone or letting go is NOT automatically rejected just because those topics are common.
What matters is whether THIS script has a specific, honest, CONCRETE moment that feels earned.

STYLE EXCEPTION — if style is "lesson" or "wisdom": this is a DIRECT, QUOTABLE TRUTH
(a viral "truth quote"), NOT a concrete scene. Judge it on how TRUE, PUNCHY, and
SHAREABLE the lesson is — abstract is EXPECTED and CORRECT here. Do NOT penalise
REALNESS for lacking physical objects; score realness on whether it names a real,
recognised truth. A great lesson screenshot-worthy line should score 8-10.

Reject outright (set approved=false) if:
- First line is a cliché opener: "There was a time", "In a world", "We all have", "Life is", "Some people", "Not everyone"
- It's abstract from start to finish — generic nature/weather metaphors with NO concrete human moment or object the viewer would recognise from their own life (REALNESS <= 4)
- The script says nothing specific — just vague platitudes end to end
- Lines are copy-paste of each other with no variation or build
- No ending — it just stops without a resonant final line, OR it literally writes a meta-word like "Period"/"Done"/"End" as the closing text

Return ONLY valid JSON:
{{"score": <overall 0-10>, "hook": <0-10>, "emotion": <0-10>, "freshness": <0-10>, "realness": <0-10>, "approved": <true/false>, "reason": "<one sentence why>"}}

Weight REALNESS heavily in the overall score. A beautifully-written but abstract poem that
doesn't describe the viewer's real life should NOT pass.
Scoring guide: 8-10 = exceptional, specific, shareable. 6-7 = solid and concrete, approved. 4-5 = generic/abstract or flat, reject. 0-3 = cliché or empty.
A script passes ONLY if overall score >= 6 AND realness >= 6."""

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


# Meta-words an AI sometimes writes LITERALLY instead of using the punctuation
# (the prompt used to say "Period at the very end" → models wrote "Period").
# Match ONLY when the meta-word is a dangling token: the whole last line IS the
# word, or it's appended after a sentence ("...phone. Period"). This avoids
# false positives like "...how to stop." where 'stop' is real content.
_ARTIFACT_WHOLE = re.compile(r"^\s*(period|full stop|done|the end|end)\s*\.?\s*$", re.I)
_ARTIFACT_APPENDED = re.compile(r"[.,!?]\s+(period|full stop|done|the end)\s*\.?\s*$", re.I)
# Connectives that cannot end a thought → broken close if they're the last line.
_DANGLING_END = {"but", "and", "so", "or", "the", "a", "of", "to", "with", "just", "not"}
# Statistics / data — NEVER belong in an emotional poem ("75% of people...").
_STATS = re.compile(r"\b\d+\s*%|\b\d+\s+percent|\bpercent\b|\b\d+\s+(?:of\s+)?people\b", re.I)
# Cold/technical objects that make a poem feel like a help-desk ticket.
_COLD_TECH = re.compile(r"\b(keyboard|login|log\s?in|password|username|wi-?fi|"
                        r"router|browser|server|database|app icon|settings menu)\b", re.I)


def check_structure(script_text):
    """Deterministic structural rejects — catch broken output the AI scorer
    waves through (it scored 'in my phone. Period' a 7/10, and 'their old
    keyboard still has your login... 75% of people' a 7/10)."""
    lines = [l.strip() for l in script_text.split("\n") if l.strip()]
    if len(lines) < 6:
        return False, f"Too few lines ({len(lines)})"
    last = lines[-1]
    if _ARTIFACT_WHOLE.match(last) or _ARTIFACT_APPENDED.search(last):
        return False, f"Artifact ending (literal meta-word): '{last}'"
    if last.lower().rstrip(".,!?") in _DANGLING_END:
        return False, f"Final line is a dangling connective: '{last}'"
    if _STATS.search(script_text):
        return False, "Contains a statistic/number-as-data (banned in a poem)"
    if _COLD_TECH.search(script_text):
        m = _COLD_TECH.search(script_text)
        return False, f"Cold/technical object ('{m.group()}') — not emotional imagery"
    # Breath structure: enough lines must END a thought (punctuation) or the
    # voiceover reads it as one rushed run-on paragraph.
    punctuated = sum(1 for l in lines if l.rstrip()[-1:] in ".!?,;:—")
    if punctuated < max(2, int(len(lines) * 0.30)):
        return False, f"Run-on: only {punctuated}/{len(lines)} lines end with punctuation"
    return True, ""


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

    # 2b. Structural sanity (artifact endings, dangling filler, too short)
    ok, reason = check_structure(script_text)
    if not ok:
        print(f"[quality] REJECTED — {reason}")
        return False, reason, 0

    # 3. AI quality score
    ai_result = check_quality_with_ai(script_text, topic, style, examples)
    score = ai_result.get("score", 5)
    realness = ai_result.get("realness", score)  # default to overall if model omits it
    approved = ai_result.get("approved", score >= 6)
    reason = ai_result.get("reason", "")

    # Realness floor — 'wisdom' and 'lesson' are DIRECT-truth/quote styles that
    # are abstract BY DESIGN, so they're exempt. Everything else must feel like
    # the viewer's real life, not abstract poetry.
    if style not in ("wisdom", "lesson") and realness < 6:
        print(f"[quality] REJECTED (realness {realness}/10 — too abstract) — {reason}")
        return False, f"Realness {realness}/10 (too abstract): {reason}", score

    if not approved or score < 6:
        print(f"[quality] REJECTED (score {score}/10) — {reason}")
        return False, f"Score {score}/10: {reason}", score

    print(f"[quality] APPROVED (score {score}/10) — {reason}")
    return True, reason, score
