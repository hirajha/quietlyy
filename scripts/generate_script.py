"""
Quietlyy — Script Generator
Generates nostalgic POETRY in the exact Quietlyy voice.
2-layer fallback: Gemini (primary) -> Groq (fallback)
"""

import os
import json
import random
import requests

from review_script import review_script, save_used_script, get_recently_used_context

TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "scripts.json")


def load_templates():
    with open(TEMPLATES_PATH, "r") as f:
        return json.load(f)


# Regular rotation styles (love/emotional 2-day cycle).
# Every 3rd regular video is automatically replaced by a wisdom/famous-poetry video.
# Use --style= flag or workflow input to force any style (poetic, wisdom, etc.)
STYLES = ["love", "emotional"]

# After this many regular videos, insert one wisdom/famous-poetry video
WISDOM_INTERVAL = 3

_STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "used_topics.json")


def _load_state():
    if os.path.exists(_STATE_PATH):
        with open(_STATE_PATH) as f:
            try:
                return json.load(f)
            except Exception:
                pass
    return {}


def _save_state(state):
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _extract_wisdom_quote(script_text):
    """Return lines 2-3 of a wisdom script joined as the quote fingerprint."""
    lines = [l.strip() for l in script_text.strip().splitlines() if l.strip()]
    if len(lines) >= 3:
        return " ".join(lines[1:3])
    return ""


def save_wisdom_quote(script_text):
    """Persist the quote from a wisdom script so it is never repeated."""
    quote = _extract_wisdom_quote(script_text)
    if not quote:
        return
    state = _load_state()
    used = state.get("used_wisdom_quotes", [])
    used.append(quote)
    state["used_wisdom_quotes"] = used[-50:]  # keep last 50
    _save_state(state)
    print(f"[script] Saved wisdom quote fingerprint ({len(used)} total)")


def pick_style_and_topic(templates, theme_hints=None):
    """Rotate between love/emotional, inserting a wisdom video every 3rd run.

    Sequence: love → emotional → love → WISDOM → emotional → love → emotional → WISDOM → …
    """
    state_path = os.path.join(os.path.dirname(__file__), "..", "assets", "used_topics.json")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)

    state = {
        "used_nostalgic": [], "used_emotional": [], "used_poetic": [],
        "used_love": [], "used_wisdom": [],
        "last_style": "love",
        "last_regular_style": "love",
        "videos_since_wisdom": 0,
    }
    if os.path.exists(state_path):
        with open(state_path) as f:
            try:
                loaded = json.load(f)
                state.update(loaded)
            except Exception:
                pass

    # After WISDOM_INTERVAL regular videos, insert a wisdom/famous-poetry video
    videos_since_wisdom = state.get("videos_since_wisdom", 0)

    if videos_since_wisdom >= WISDOM_INTERVAL:
        style = "wisdom"
        state["videos_since_wisdom"] = 0
        print(f"[script] Wisdom video slot (after {WISDOM_INTERVAL} regular videos)")
    else:
        # Regular love → emotional → love → emotional rotation
        last_regular = state.get("last_regular_style", STYLES[0])
        idx = STYLES.index(last_regular) if last_regular in STYLES else 0
        style = STYLES[(idx + 1) % len(STYLES)]
        state["videos_since_wisdom"] = videos_since_wisdom + 1
        state["last_regular_style"] = style

    pool = templates["topics_pool"].get(style, templates["topics_pool"]["emotional"])
    used_key = f"used_{style}"
    used = state.get(used_key, [])

    available = [t for t in pool if t not in used]
    if not available:
        used = []
        available = pool

    # Bias toward high-performing themes (30%)
    if theme_hints:
        preferred = [t for t in available if any(
            hint.lower() in t.lower() or t.lower() in hint.lower()
            for hint in theme_hints
        )]
        if preferred and random.random() < 0.3:
            topic = random.choice(preferred)
        else:
            topic = random.choice(available)
    else:
        topic = random.choice(available)

    used.append(topic)
    state[used_key] = used[-20:]
    state["last_style"] = style

    with open(state_path, "w") as f:
        json.dump(state, f)

    return style, topic


# Keep old name as alias for compatibility
def pick_topic(templates, theme_hints=None):
    _, topic = pick_style_and_topic(templates, theme_hints)
    return topic


# ── Opening pattern rotation — ensures every video starts completely differently ──
# Injected randomly into each prompt so the AI can't default to "You still..." every time.
_OPENING_PATTERNS = [
    {
        "name": "first_person_confession",
        "instruction": (
            'Line 1 MUST be first-person: "I stopped..." / "I still..." / "I never told you..." '
            '/ "I carry it everywhere." — the narrator IS the viewer, confessing something private.'
        ),
    },
    {
        "name": "named_feeling",
        "instruction": (
            'Line 1 MUST name an unnamed feeling: "There\'s a kind of tired..." '
            '/ "There\'s a loneliness that..." / "There\'s a grief that has no name..." '
            '— give language to something they\'ve felt but never heard described.'
        ),
    },
    {
        "name": "time_and_scene",
        "instruction": (
            'Line 1 MUST open with a specific time + quiet scene: "3am. The house is quiet." '
            '/ "Sunday evening. The week hasn\'t started." / "It\'s raining. You\'re still awake." '
            '— drop the viewer into a moment, no explanation needed.'
        ),
    },
    {
        "name": "unanswerable_question",
        "instruction": (
            'Line 1 MUST be a question with no clean answer: "What do you call it when..." '
            '/ "When did it become easier to..." / "How do you explain to someone..." '
            '— not rhetorical, genuinely the question they\'ve been sitting with.'
        ),
    },
    {
        "name": "quiet_contradiction",
        "instruction": (
            'Line 1 MUST be a quiet contradiction or paradox: "You\'re not sad. Not exactly." '
            '/ "It doesn\'t hurt anymore. It just stays." / "You don\'t miss them. You miss who you were." '
            '— the kind of thing that\'s true but impossible to explain.'
        ),
    },
    {
        "name": "direct_observation",
        "instruction": (
            'Line 1 MUST be a direct honest observation — no "you", no "I" — just a truth stated simply: '
            '"Nobody talks about the grief of growing apart." / "People don\'t fall out of love all at once." '
            '/ "Healing is not a straight line." — factual, not poetic, but deeply felt.'
        ),
    },
    {
        "name": "small_specific_detail",
        "instruction": (
            'Line 1 MUST be one hyper-specific tiny detail that carries enormous emotional weight: '
            '"The coffee was already made for two." / "The ringtone was still theirs." '
            '/ "You still laugh at their jokes. Even now." — concrete, unexpected, immediately relatable.'
        ),
    },
    {
        "name": "second_person_present_moment",
        "instruction": (
            'Line 1 MUST be second-person present tense — catching them mid-moment: '
            '"You\'re reading this at 2am." / "You\'re fine. You keep saying you\'re fine." '
            '/ "You pick up your phone. Put it down. Pick it up again." '
            '— meets them exactly where they are right now.'
        ),
    },
]


def build_prompt(topic, examples, style="emotional", tone_hints="", idea_hints=""):
    """Build prompt for the given style: 'nostalgic' or 'emotional'."""
    style_examples = [e for e in examples if e.get("style") == style][:3]
    examples_text = "".join(f'\nTopic: {e["topic"]}\n{e["script"]}\n' for e in style_examples)

    audience_block = ""
    if tone_hints:
        audience_block += f"\nAudience intelligence:\n{tone_hints}\n"
    if idea_hints:
        audience_block += f"\n{idea_hints}\n"

    # Inject recently used metaphors/themes so AI explicitly avoids repeating them
    used_metaphors, used_themes = get_recently_used_context(n=8)
    avoid_block = ""
    if used_metaphors:
        avoid_block += f"\nDO NOT use these metaphors/images (already used recently): {', '.join(used_metaphors)}\n"
    if used_themes:
        avoid_block += f"DO NOT write about these emotional concepts (already covered recently): {', '.join(t.replace('_', ' ') for t in used_themes)}\n"
    avoid_block += "Write something COMPLETELY DIFFERENT — a fresh angle, fresh imagery, fresh emotional territory.\n"

    if style == "poetic":
        style_examples = [e for e in examples if e.get("style") == "poetic"][:2]
        examples_text = "".join(f'\nTopic: {e["topic"]}\n{e["script"]}\n' for e in style_examples)
        return f"""Generate a viral 20-25 second spoken-word poem for "Quietlyy" — lyrical, intimate, the kind that makes people feel seen in a feeling they've never heard named.{audience_block}{avoid_block}

Topic: {topic}
Tone: lyrical whisper — like a private thought made beautiful, spoken-word poetry that fits in a pocket

Rules:
- NEVER start with "You were...", "You weren't...", "You were never...", "You were cherished" — banned
- NEVER use the phrase "you call it / they call it" — banned cliché
- Open with one vivid, unexpected image that arrests attention immediately
- Build ONE central metaphor — not a list, ONE thread that the whole poem follows
- Short fragmented lines — 4-7 words, breathing room, reads like music
- Use "…" for pauses
- The turn must feel DISCOVERED through the image — not stated as a lesson
- End with one line that lands like an exhale — quiet, not a slogan
- 7-9 lines TOTAL — tight, no padding
- NO hashtags, NO emojis, NO stage directions

Structure:
Lines 1-2: Arresting image — pull them in before they know why
Lines 3-4: Deepen — the emotional weight underneath
Lines 5-6: The turn — a reframing discovered in the image itself
Lines 7-8: The quiet exhale — the truth that makes everything else land
Line 9 (optional): soft share nudge — "Save this for the quiet nights." or "Send this to someone you think about."

Also provide 4 visual keywords (symbolic, intimate scenes — not literal objects).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5\\nline6\\nline7", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}

EXAMPLES (notice: short, tight, paradox lives inside the image):
{examples_text}"""

    elif style == "love":
        style_examples = [e for e in examples if e.get("style") == "love"][:2]
        examples_text = "".join(f'\nTopic: {e["topic"]}\n{e["script"]}\n' for e in style_examples)
        # Pick a love-appropriate opening (exclude time/scene and observation openers)
        love_openings = [p for p in _OPENING_PATTERNS if p["name"] in (
            "first_person_confession", "quiet_contradiction",
            "small_specific_detail", "second_person_present_moment", "named_feeling"
        )]
        opening = random.choice(love_openings)
        return f"""Generate a viral 30-35 second love poem for "Quietlyy" — soft, intimate, the kind that makes someone put their phone down and immediately think of one specific person.{audience_block}{avoid_block}

Topic: {topic}
Tone: tender whisper — the feeling you have about someone but rarely say out loud. Inspired by Rupi Kaur and Atticus but completely original.

⚠️ OPENING REQUIREMENT (this video MUST open this way — give it a fresh start):
{opening["instruction"]}

Rules:
- Short fragmented lines — 5-9 words, reads like a quiet breath
- Use ONE sensory or specific detail that makes it feel real — not a list, ONE moment that carries everything
- The love should feel QUIET, SAFE, and UNSPOKEN — not dramatic or desperate
- Build the feeling slowly through images — they should feel it before they name it
- Use "…" for pauses
- End with a natural CTA: "Send this to them. They deserve to know." / "Tag the one who feels like home."
- 8-9 lines TOTAL including CTA — enough for 30 seconds, no filler
- NO clichés: no "my heart", no "soul mate", no "forever and always" — fresh language only

Also provide 4 visual keywords: quiet intimate moments, dark warm light, tender closeness.

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5\\nline6\\nline7\\nline8\\ncta_line", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}

EXAMPLES (notice: specific, quiet, builds slowly — not a list of compliments):
{examples_text}"""

    elif style == "nostalgic":
        return f"""Generate a viral 15-20 second script in "Quietlyy" nostalgic style — the kind that makes people stop scrolling because it names a feeling they've been carrying silently.{audience_block}{avoid_block}

Topic: {topic}
Tone: warm, aching, deeply human — a memory that still hurts in a beautiful way

CRITICAL RULES:
- The topic triggers a FEELING, not a description of an object
  WRONG: "Remember when we gathered around the television?" (about the object)
  RIGHT: "Remember when nobody wanted the night to end?" (about the connection)
- NEVER mention the physical object or technology directly
- NEVER start with "There was a time", "In a world", "Have you ever", "We live in", "Some people"
- Short punchy lines — 6-10 words max, reads like a quiet spoken memory
- Use "…" for emotional pauses
- 8-9 lines TOTAL — enough for 30 seconds, every line counts

Structure:
Line 1: HOOK — paint the warmth/belonging (not the object). Make them feel it immediately.
Lines 2-4: The specific feeling that made that time irreplaceable — expand it slowly
Lines 5-6: What quietly changed — honest but not bitter, just true
Lines 7-8: The ache — what's missing now, what they carry
Last line: Gentle share nudge — "Send this to someone you used to be closer to." / "Save this for the people who still matter."

Also provide 4 visual keywords (warm human scenes: family, togetherness, shared moments — NO objects).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5\\nline6\\nline7\\nline8\\nline9", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}

EXAMPLES:
{examples_text}"""

    elif style == "wisdom":
        # Build banned-quotes block from previously used wisdom quotes
        used_wisdom_quotes = _load_state().get("used_wisdom_quotes", [])
        banned_quotes_block = ""
        if used_wisdom_quotes:
            banned_quotes_block = (
                "\n⚠️ BANNED QUOTES (already used — you MUST use a completely different quote):\n"
                + "\n".join(f"- {q}" for q in used_wisdom_quotes[-20:])
                + "\nDo NOT reuse any of the above quotes or close paraphrases of them.\n"
            )

        return f"""Generate a viral 20-25 second life-lesson script for "Quietlyy" — a famous quote (or one written faithfully in the spirit of a great thinker) unpacked in 2-3 personal, honest lines.{audience_block}{avoid_block}{banned_quotes_block}

Topic: {topic}

FORMAT (follow exactly — 8 lines total):
Line 1: Attribution — e.g. "Rumi once wrote…" / "Marcus Aurelius kept this in his journal…" / "An old Japanese proverb says…" / "Kahlil Gibran once said…" / "Buddha taught…" / "Maya Angelou wrote…"
Lines 2-4: The quote itself — word-for-word as that thinker said it, or written so faithfully in their spirit it is indistinguishable. Split naturally across 3 lines. No filler added.
Lines 5-7: The reflection — 3 short lines that unpack what this means for real life. Specific, felt, honest. NOT a TED talk. NOT generic advice. Let it breathe.
Line 8: Soft share nudge — "Save this for the days you forget." / "Send this to someone carrying something heavy." / "Tag someone who needs to hear this today."

CRITICAL RULES:
- NEVER insert branded filler INSIDE or after the quote
- The quote ends cleanly — no bridge, no "And quietly…" commentary
- The reflection starts with the unpacking, not a transition phrase
- 8 lines TOTAL — enough for 30 seconds

WISDOM SOURCES (pick what fits the topic):
- Rumi — love, longing, transformation, the soul
- Marcus Aurelius — inner discipline, what we control, resilience
- Kahlil Gibran — love, grief, joy, parenting, freedom
- Buddha / Buddhist tradition — attachment, peace, impermanence
- Lao Tzu / Taoism — flow, nature, simplicity, non-resistance
- Japanese proverb — patience, resilience, impermanence, acceptance
- Maya Angelou — courage, self-worth, resilience, love
- Hafiz — joy, love, the divine, celebration of life
- Epictetus — freedom, what we control, inner peace
- Seneca — time, how we live, what matters

RULES:
- Quote can be real OR written in the authentic spirit of that tradition — must feel genuine
- Keep every line short — 6-12 words
- Use "…" for breath pauses
- End warm, not dramatic

Also provide 4 visual keywords: peaceful contemplative scenes — solitude, nature, quiet interiors.

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5\\nline6", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}"""

    else:  # emotional — grief, longing, unspoken pain, human truths
        opening = random.choice(_OPENING_PATTERNS)
        return f"""Generate a viral 30-35 second emotional script for "Quietlyy" — inspired by Whisprs, the page with 2M followers in 2 months. Their secret: they name feelings people whisper to themselves but never say out loud.

TARGET FEELING: The viewer thinks "who told them about my life?" — like the script read their private inner monologue. NOT generic motivation. NOT advice. A specific, unspoken human truth they have NEVER heard said so simply.

Topic: {topic}{audience_block}{avoid_block}
Tone: intimate whisper — grief, longing, the exhaustion of pretending, silent suffering, or the quiet weight of love — with surgical precision

⚠️ OPENING REQUIREMENT (this video MUST open this way — do not default to "You still..."):
{opening["instruction"]}

FEELINGS THAT GO VIRAL (pick the sharpest angle for this topic):
- Grief nobody validates (losing someone still alive, being the strong one who can't cry)
- The exhaustion of pretending to be okay when asked
- Loving someone who can't love back the right way
- The specific small moments that carry enormous silent weight
- Missing a version of yourself you used to be
- Being everyone's anchor while quietly drowning

Rules:
- NEVER start with "You were...", "You weren't...", "Some people", "There was a time", "In a world" — banned
- Short punchy lines — 5-10 words each, fast rhythm, each line is a quiet gut punch
- ONE central image that makes the feeling concrete and specific — not a list of metaphors
- MUST have a turn — one line that quietly reframes everything before it
- Build slowly — let the emotion breathe and deepen across lines
- End with something so honest they'll screenshot it
- Last line: organic share nudge — "Save this for the days you forget." / "Send this to someone carrying something heavy." / "Tag someone who needs to hear this."
- 8-9 lines TOTAL including CTA — enough to fill 30 seconds, every line earns its place
- NO hashtags, NO emojis, NO stage directions

Structure:
Line 1: HOOK using the opening requirement above — stop the scroll with something they've never heard phrased this way
Lines 2-3: Deepen — the quiet truth underneath, make it feel personal and unspoken
Lines 4-5: Expand — the second layer, the thing underneath the thing
Lines 6-7: The turn + honest exhale — the realization that makes them feel seen, not lectured
Line 8: Landing — something quietly powerful, screenshot-worthy
Line 9: CTA — "Save this for the heavy days." or "Send this to someone who needs it."

Also provide 4 visual keywords (solitary, intimate scenes — 3am moments, dark rooms, quiet figures).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5\\nline6\\nline7\\nline8\\nline9", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}

EXAMPLES (study the hook — how specific and quiet the first line is):
{examples_text}"""


def _call_openai_compatible(url, key, model, prompt):
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.92,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def _repair_json(text):
    """Try to extract valid JSON from possibly malformed response."""
    import re
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find JSON object in text
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Fix common issues: unescaped newlines in strings
    fixed = text.replace('\n', '\\n')
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    return None


def generate_with_chatgpt(prompt):
    """Primary: ChatGPT (OpenAI) — best for creative Quietlyy Quotes."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        return _call_openai_compatible(
            "https://api.openai.com/v1/chat/completions",
            key, "gpt-4o-mini", prompt,
        )
    except Exception as e:
        print(f"[script] ChatGPT failed: {e}")
    return None


def generate_with_gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 2000,
                "temperature": 0.92,
            },
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if "candidates" not in data or not data["candidates"]:
        print(f"[script] Gemini no candidates: {str(data)[:200]}")
        return None
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    print(f"[script] Gemini raw: {text[:300]}")
    result = _repair_json(text)
    if result is None:
        print(f"[script] Gemini JSON repair failed")
    return result


def generate_with_groq(prompt):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    return _call_openai_compatible(
        "https://api.groq.com/openai/v1/chat/completions",
        key, "llama-3.3-70b-versatile", prompt,
    )


def generate_with_huggingface(prompt):
    """Free fallback via HF Serverless Inference — Mistral-7B-Instruct.
    Quality lower than GPT-4/Gemini but free. Used only when all other free
    options fail. Requires HF_TOKEN env var."""
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        return None
    model = "mistralai/Mistral-7B-Instruct-v0.3"
    try:
        resp = requests.post(
            f"https://api-inference.huggingface.co/models/{model}/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.9,
            },
            timeout=90,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _repair_json(content)
    except Exception as e:
        print(f"[script] HuggingFace failed: {e}")
    return None


def _generate_raw(prompt, style):
    """Try all providers — free first, paid last.
    Order: Gemini (free) → Groq (free) → HuggingFace (free) → ChatGPT (paid fallback).
    ChatGPT only runs when all 3 free options fail."""
    providers = [
        (generate_with_gemini,       "Gemini"),
        (generate_with_groq,         "Groq"),
        (generate_with_huggingface,  "HuggingFace"),
        (generate_with_chatgpt,      "ChatGPT"),
    ]
    for gen_fn, name in providers:
        try:
            result = gen_fn(prompt)
            if result and "script" in result:
                lines = [l.strip() for l in result["script"].split("\n") if l.strip()]
                min_lines = 4 if style == "nostalgic" else 5
                if len(lines) >= min_lines:
                    print(f"[script] Generated via {name}")
                    return result
                print(f"[script] {name} output wrong format, trying next...")
        except Exception as e:
            print(f"[script] {name} failed: {e}")
    return None


def generate_script(tone_hints="", theme_hints=None, idea_hints=""):
    templates = load_templates()
    examples = templates["example_scripts"]
    MAX_ATTEMPTS = 5

    for attempt in range(1, MAX_ATTEMPTS + 1):
        style, topic = pick_style_and_topic(templates, theme_hints=theme_hints)
        prompt = build_prompt(topic, examples, style=style, tone_hints=tone_hints, idea_hints=idea_hints)
        print(f"[script] Attempt {attempt}/{MAX_ATTEMPTS} — Style: {style} | Topic: {topic}")

        result = _generate_raw(prompt, style)
        if not result:
            print(f"[script] All providers failed on attempt {attempt}, retrying...")
            continue

        script_text = result["script"]

        # Quality gate — checks banned openers, duplicates, and AI vibe score
        approved, reason, score = review_script(script_text, topic, style, examples)
        if not approved:
            print(f"[script] Quality gate failed (attempt {attempt}): {reason} — retrying with new topic...")
            continue

        # Approved — save to used scripts history and return
        save_used_script(script_text, topic, style)
        if style == "wisdom":
            save_wisdom_quote(script_text)
        result["topic"] = topic
        result["style"] = style
        result["quality_score"] = score
        return result

    raise RuntimeError(f"Script quality gate failed after {MAX_ATTEMPTS} attempts. Cannot proceed.")


def generate_best_script(tone_hints="", theme_hints=None, idea_hints="", n_candidates=5, forced_topic=None, forced_style=None):
    """
    Generate up to n_candidates scripts that pass the quality gate,
    score each with the engagement predictor, and return the highest-scoring one.

    This is the recommended entry point for the main pipeline.
    Falls back to the first passing script if the predictor is unavailable.
    """
    try:
        from predict_engagement import predict_engagement
        predictor_available = True
    except ImportError:
        predictor_available = False

    templates = load_templates()
    examples = templates["example_scripts"]
    candidates = []
    MAX_TOTAL_ATTEMPTS = n_candidates * 3  # avoid infinite loops

    print(f"[script] Generating {n_candidates} candidate scripts for engagement scoring...")

    attempt = 0
    while len(candidates) < n_candidates and attempt < MAX_TOTAL_ATTEMPTS:
        attempt += 1
        style, topic = pick_style_and_topic(templates, theme_hints=theme_hints)
        if forced_style:
            style = forced_style
        if forced_topic:
            topic = forced_topic
        prompt = build_prompt(topic, examples, style=style, tone_hints=tone_hints, idea_hints=idea_hints)
        print(f"[script] Candidate {len(candidates)+1}/{n_candidates} (try {attempt}) — Style: {style} | Topic: {topic}")

        result = _generate_raw(prompt, style)
        if not result:
            continue

        approved, reason, score = review_script(result["script"], topic, style, examples)
        if not approved:
            print(f"[script]   Quality gate: {reason} — skipping")
            continue

        result["topic"] = topic
        result["style"] = style
        result["quality_score"] = score
        result["engagement_score"] = 0  # default

        if predictor_available:
            try:
                pred = predict_engagement(result["script"], topic, style)
                composite = (
                    pred.get("scores", {}).get("hook", 0) * 0.3 +
                    pred.get("scores", {}).get("save", 0) * 0.25 +
                    pred.get("scores", {}).get("share", 0) * 0.25 +
                    pred.get("scores", {}).get("rewatch", 0) * 0.2
                )
                result["engagement_score"] = round(composite, 2)
                result["engagement_prediction"] = pred.get("prediction", "unknown")
                print(f"[script]   Engagement score: {composite:.1f}/10 ({pred.get('prediction', '?')})")
            except Exception as e:
                print(f"[script]   Predictor failed ({e}) — using quality score only")

        candidates.append(result)

    if not candidates:
        raise RuntimeError(f"Script quality gate failed after {MAX_TOTAL_ATTEMPTS} attempts. Cannot proceed.")

    # Pick the highest engagement-scoring candidate
    best = max(candidates, key=lambda c: (c["engagement_score"], c["quality_score"]))
    print(f"\n[script] Selected best of {len(candidates)} candidates:")
    print(f"  Topic: {best['topic']} | Style: {best['style']}")
    print(f"  Quality: {best['quality_score']}/10 | Engagement: {best['engagement_score']}/10")
    print(f"  Prediction: {best.get('engagement_prediction', 'n/a')}")

    save_used_script(best["script"], best["topic"], best["style"])
    if best.get("style") == "wisdom":
        save_wisdom_quote(best["script"])
    return best


if __name__ == "__main__":
    script = generate_best_script()
    print(json.dumps(script, indent=2))
