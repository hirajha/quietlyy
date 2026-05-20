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
        return f"""Write a 25-30 second spoken-word poem for "Quietlyy" in the exact Whisprs style.{audience_block}{avoid_block}

Topic: {topic}

━━ THE WHISPRS RHYTHM — STUDY THE LINE LENGTHS ━━
Real Whisprs narrators VARY line length to break the metronomic feel:
  - Some lines are 2-3 words (tight, punchy)
  - Some are 4-6 words (medium breath)
  - Some are 7-10 words (a flowing thought)
NEVER use the SAME line length twice in a row. Mix them up.

Real Whisprs example — count the words:
I'm a leaver who never really left   (8 words — flowing)
I walked away                          (3 — punch)
but kept looking back                  (4)
not chasing                            (2 — tight)
just watching from a distance          (5)
but holding onto hope                  (4)
I won't make you stay                  (5)
quiet and steady                       (3 — punch)
not out of weakness                    (4)
but out of love                        (4)

Notice: 8 → 3 → 4 → 2 → 5 → 4 → 5 → 3 → 4 → 4 — RHYTHM VARIES.

Punctuation = breath markers (this controls our audio gap timing):
  - End line with period (.) when a complete thought lands → LONGER pause
  - End line with comma (,) or nothing → SHORTER pause, thought continues
  - This makes the narrator sound human, not robotic.

Rules:
- LINE LENGTH: vary between 2-10 words. NEVER same length twice in a row.
- TOTAL: 10-13 lines for 25-30 seconds
- Lines are enjambed — they flow grammatically into each other
- Continuation lines start lowercase: "but...", "and...", "just..."
- New emotional beats CAPITALIZE: "Some people...", "The hands that..."
- ONE central image/metaphor carried through the whole piece
- Use periods at major beat-endings (deep breath); commas for flowing within
- NEVER start with "You were..." — banned

Also provide 4 visual keywords (atmospheric, solitary scenes).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\n...line10-13", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}"""

    elif style == "love":
        style_examples = [e for e in examples if e.get("style") == "love"][:2]
        examples_text = "".join(f'\nTopic: {e["topic"]}\n{e["script"]}\n' for e in style_examples)
        love_openings = [p for p in _OPENING_PATTERNS if p["name"] in (
            "first_person_confession", "quiet_contradiction",
            "small_specific_detail", "second_person_present_moment", "named_feeling"
        )]
        opening = random.choice(love_openings)
        return f"""Write a 30-second love poem for "Quietlyy" in the exact Whisprs style.{audience_block}{avoid_block}

Topic: {topic}

━━ THE WHISPRS RHYTHM ━━
VARY line lengths to avoid sounding robotic:
  - Some 2-3 word punches
  - Some 4-6 word medium breaths
  - Some 7-10 word flowing thoughts
NEVER use the SAME line length twice in a row.

Real Whisprs example — count the words:
the umbrella feels too heavy to hold        (7 — flowing)
The same hands that reached for you in storms  (9 — long)
slowly forget the warmth you gave            (6)
but sunshine makes your presence fade        (6)
Some people don't love you                   (5)
they love the comfort you create.            (6, period = deep breath)

Punctuation = breath markers:
  - Period (.) at end → LONGER pause (complete thought lands)
  - Comma (,) or no punctuation → SHORT pause (thought continues)

⚠️ OPENING (must open this way):
{opening["instruction"]}

Rules:
- VARY line length 2-10 words. NEVER same length twice in a row.
- 10-13 lines for 30 seconds
- Continuation lowercase: "but...", "and...", "slowly..."
- New thoughts CAPITALIZE
- ONE central tender image/metaphor through the whole piece
- End with a quiet close — period or "send this to them." (final line)
- NO clichés: no "my heart", "soulmate", "forever and always"
- NEVER start with "You were..." — banned

Also provide 4 visual keywords: quiet intimate atmosphere.

Return ONLY valid JSON:
{{"script": "line1\\nline2\\n...line10-13", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}"""

    elif style == "nostalgic":
        return f"""Write a 30-second nostalgic poem for "Quietlyy" in the exact Whisprs style.{audience_block}{avoid_block}

Topic: {topic}

━━ THE WHISPRS RHYTHM ━━
VARY line lengths (2-3 punchy / 4-6 medium / 7-10 flowing).
NEVER same length twice in a row.

Example (topic: the people we used to be close to):
We never said goodbye                       (4)
we just                                     (2 — punch)
stopped calling                             (2 — punch)
stopped showing up                          (3)
stopped saving each other seats             (5)
and somewhere between then and now          (6 — flowing)
we became strangers                         (3)
who still smile                             (3)
when we pass.                               (3, period = deep breath)

Notice: 4 → 2 → 2 → 3 → 5 → 6 → 3 → 3 → 3 — varied with rhythm.

Punctuation = breath:
  - Period → LONGER pause (a beat lands)
  - Comma or none → SHORT pause (continues)

Rules:
- VARY length 2-10 words. NEVER same length twice in a row.
- 10-13 lines for 30 seconds
- The topic triggers a FEELING not a description of an object
- Continuation lowercase: "we just...", "still..."
- New thoughts CAPITALIZE
- End with a quiet ache
- NEVER start with "There was a time", "In a world", "Have you ever"

Also provide 4 visual keywords (warm, human, atmospheric scenes).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\n...line10-13", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}"""

    elif style == "wisdom":
        used_wisdom_quotes = _load_state().get("used_wisdom_quotes", [])
        banned_quotes_block = ""
        if used_wisdom_quotes:
            banned_quotes_block = (
                "\n⚠️ BANNED QUOTES (already used):\n"
                + "\n".join(f"- {q}" for q in used_wisdom_quotes[-20:])
                + "\nUse a completely different quote.\n"
            )

        return f"""Write a 30-second wisdom poem for "Quietlyy" in the exact Whisprs style.{audience_block}{avoid_block}{banned_quotes_block}

Topic: {topic}

━━ THE WHISPRS RHYTHM ━━
VARY line lengths (2-3 punchy / 4-6 medium / 7-10 flowing).
NEVER same length twice in a row.

Real Whisprs wisdom example (Rumi):
Rumi said                                   (2 — attribution punch)
you're with everyone                        (3)
you're with no one.                         (4, period = deep breath)

Structure for wisdom:
Line 1: Attribution (2-5 words): "Rumi once said…" / "Marcus Aurelius wrote…"
Lines 2-5: The quote in VARIED breath fragments
Lines 6-10: Reflection — unpack it in honest, VARIED fragments
Lines 11-12: Quiet close — a landing, not a lesson

Punctuation = breath:
  - Period → LONGER pause
  - Comma or none → SHORT pause

WISDOM SOURCES:
- Rumi — love, longing, the soul's search
- Marcus Aurelius — inner discipline, control, resilience
- Kahlil Gibran — grief, love, freedom, parenting
- Buddha — attachment, peace, impermanence
- Lao Tzu — flow, simplicity, nature
- Japanese proverb — patience, resilience
- Maya Angelou — courage, self-worth, love
- Hafiz — joy, the divine, life's abundance

Rules:
- VARY length 2-10 words. NEVER same twice in a row.
- 10-13 lines for 30 seconds
- Attribution on its own line
- Quote lines are lowercase fragments continuing naturally
- Reflection lowercase, personal, honest — NOT generic advice
- End with quiet open landing — no forced "Save this"

Also provide 4 visual keywords: contemplative solitary scenes, nature, quiet.

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5\\nline6\\nline7\\nline8\\nline9\\nline10\\nline11\\nline12", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}"""

    else:  # emotional — the core Quietlyy format, matched exactly to Whisprs
        opening = random.choice(_OPENING_PATTERNS)
        return f"""Write a 30-second emotional poem for "Quietlyy" in the EXACT Whisprs style.
Whisprs reached 2M followers with this format. Match it precisely.{audience_block}{avoid_block}

Topic: {topic}

━━ THE WHISPRS RHYTHM (CRITICAL) ━━
Real Whisprs narrators VARY line length so the rhythm sounds HUMAN, not robotic:
  - 2-3 word lines = punches (a tight beat)
  - 4-6 word lines = medium breaths
  - 7-10 word lines = flowing thoughts (a longer phrase)
NEVER use the SAME line length twice in a row. Mix them up.

Real Whisprs Video 1 (count the words per line):
I'm a leaver who never really left          (8 — flowing)
I walked away                                (3 — punch)
but kept looking back                        (4)
not chasing                                  (2 — tight)
just watching from a distance                (5)
but holding onto hope                        (4)
I won't make you stay                        (5)
quiet and steady                             (3 — punch)
not out of weakness                          (4)
but out of love.                             (4, period = breath)

Rhythm: 8 → 3 → 4 → 2 → 5 → 4 → 5 → 3 → 4 → 4. NEVER monotone.

Real Whisprs Video 2:
the umbrella feels too heavy to hold         (7 — flowing)
The same hands that reached for you in storms (9 — long)
slowly forget the warmth you gave            (6)
but sunshine makes your presence fade        (6)
Some people don't love you                   (5)
they love the comfort you create.            (6, period)

━━ PUNCTUATION = BREATH MARKERS (this controls voiceover timing) ━━
  - Period (.) at end → LONGER pause (~1.8s, deep breath, beat lands)
  - Comma (,) or no punctuation → SHORTER pause (~0.6s, flow continues)
  - Use this DELIBERATELY to control where the audio pauses

━━ YOUR POEM ━━
Topic: {topic}
⚠️ Opening style required: {opening["instruction"]}

Rules — follow exactly:
- VARY line length 2-10 words. NEVER same length twice in a row.
- 10-13 lines total (30 seconds with varied pauses)
- Continuation lines LOWERCASE: "but...", "and...", "just...", "slowly...", "not..."
- New emotional beats CAPITALIZE: "Some people...", "The hands that...", "I won't..."
- ONE central image or metaphor carried the whole way through
- The poem makes the viewer think: "who told them about my life?"
- End with a quiet, powerful close — 3-7 words. Period at the very end.
- Optionally: final line "send this to them." or "let them know." (if natural)
- NO "Save this", NO "Tag someone" — feel, don't sell
- NEVER start with "You were..." — banned

Also provide 4 visual keywords (solitary, atmospheric scenes).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\n...line10-13", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}"""


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


def generate_with_cerebras(prompt):
    """Cerebras Cloud — 1M tokens/day FREE on Llama 3.3 70B. OpenAI-compatible."""
    key = os.environ.get("CEREBRAS_API_KEY")
    if not key:
        return None
    try:
        return _call_openai_compatible(
            "https://api.cerebras.ai/v1/chat/completions",
            key, "llama-3.3-70b", prompt,
        )
    except Exception as e:
        print(f"[script] Cerebras failed: {e}")
    return None


def generate_with_sambanova(prompt):
    """SambaNova — 200K tokens/day FREE on Llama 3.1 405B (largest free model)."""
    key = os.environ.get("SAMBANOVA_API_KEY")
    if not key:
        return None
    try:
        return _call_openai_compatible(
            "https://api.sambanova.ai/v1/chat/completions",
            key, "Meta-Llama-3.3-70B-Instruct", prompt,
        )
    except Exception as e:
        print(f"[script] SambaNova failed: {e}")
    return None


def generate_with_mistral(prompt):
    """Mistral La Plateforme — 1B tokens/month FREE on Mistral Large."""
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        return None
    try:
        return _call_openai_compatible(
            "https://api.mistral.ai/v1/chat/completions",
            key, "mistral-large-latest", prompt,
        )
    except Exception as e:
        print(f"[script] Mistral failed: {e}")
    return None


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
    """Try all providers in order — free-first by daily quota, paid last.

    Order rationale:
      1. Gemini       — 250 req/day free, fast, strong creative
      2. Cerebras     — 1M tokens/day free, fastest inference (Llama 3.3 70B)
      3. Groq         — 500K tokens/day free, also Llama 3.3 70B
      4. SambaNova    — 200K tokens/day free, Llama 3.1 405B (largest free model)
      5. Mistral      — 1B tokens/month free, Mistral Large
      6. HuggingFace  — free fallback, quality lower
      7. ChatGPT      — PAID — only when all 6 free providers are exhausted

    Returns ('result_dict', None) on success, (None, 'all_rate_limited') if every
    provider returned 429, (None, 'all_failed') for other failures.
    """
    providers = [
        (generate_with_gemini,       "Gemini"),
        (generate_with_cerebras,     "Cerebras"),
        (generate_with_groq,         "Groq"),
        (generate_with_sambanova,    "SambaNova"),
        (generate_with_mistral,      "Mistral"),
        (generate_with_huggingface,  "HuggingFace"),
        (generate_with_chatgpt,      "ChatGPT"),
    ]
    all_rate_limited = True  # flip to False if any provider returns non-429 error
    any_attempted = False    # track whether any provider was even configured
    for gen_fn, name in providers:
        try:
            result = gen_fn(prompt)
            if result is None:
                continue  # not configured (no API key) — silent skip
            any_attempted = True
            if "script" in result:
                lines = [l.strip() for l in result["script"].split("\n") if l.strip()]
                min_lines = 8  # Whisprs format is 12-14 lines; reject anything shorter than 8
                if len(lines) >= min_lines:
                    print(f"[script] Generated via {name}")
                    return result, None
                print(f"[script] {name} output wrong format, trying next...")
                all_rate_limited = False
        except Exception as e:
            any_attempted = True
            err_str = str(e)
            # Detect 429 / rate-limit; anything else is a real failure
            if "429" not in err_str and "rate limit" not in err_str.lower() and "Too Many Requests" not in err_str:
                all_rate_limited = False
            print(f"[script] {name} failed: {err_str[:200]}")
    if not any_attempted:
        return None, "no_providers_configured"
    return None, ("all_rate_limited" if all_rate_limited else "all_failed")


def generate_script(tone_hints="", theme_hints=None, idea_hints=""):
    import time
    templates = load_templates()
    examples = templates["example_scripts"]
    MAX_ATTEMPTS = 5

    for attempt in range(1, MAX_ATTEMPTS + 1):
        style, topic = pick_style_and_topic(templates, theme_hints=theme_hints)
        prompt = build_prompt(topic, examples, style=style, tone_hints=tone_hints, idea_hints=idea_hints)
        print(f"[script] Attempt {attempt}/{MAX_ATTEMPTS} — Style: {style} | Topic: {topic}")

        result, reason = _generate_raw(prompt, style)
        if not result:
            # When every provider returned 429, sleep before hammering them again
            if reason == "all_rate_limited":
                backoff = min(60, 15 * attempt)
                print(f"[script] All providers rate-limited (429) — sleeping {backoff}s before retry...")
                time.sleep(backoff)
            else:
                print(f"[script] All providers failed ({reason}) on attempt {attempt}, retrying...")
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

    import time
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

        result, reason = _generate_raw(prompt, style)
        if not result:
            # On rate-limit storm, sleep before re-hammering all providers
            if reason == "all_rate_limited":
                backoff = min(60, 15 * attempt)
                print(f"[script]   All providers rate-limited — sleeping {backoff}s before next candidate")
                time.sleep(backoff)
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
