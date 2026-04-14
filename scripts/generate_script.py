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


# Evening rotation styles — 2-day cycle (1 evening post/day = repeats every 2 days)
# Morning slot is always "nostalgic" (set in pipeline.py)
# Use --style= flag or workflow input to force any style (poetic, wisdom, etc.)
STYLES = ["love", "emotional"]

def pick_style_and_topic(templates, theme_hints=None):
    """Rotate between styles each run."""
    state_path = os.path.join(os.path.dirname(__file__), "..", "output", "used_topics.json")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)

    state = {"used_nostalgic": [], "used_emotional": [], "used_poetic": [], "used_love": [], "used_wisdom": [], "last_style": "nostalgic"}
    if os.path.exists(state_path):
        with open(state_path) as f:
            try:
                state = json.load(f)
            except Exception:
                pass

    # Rotate through styles: emotional → poetic → nostalgic → emotional…
    last = state.get("last_style", "nostalgic")
    idx = STYLES.index(last) if last in STYLES else 0
    style = STYLES[(idx + 1) % len(STYLES)]

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
        return f"""Generate a viral 25-35 second spoken-word poem in "Quietlyy" style — lyrical, image-driven, emotionally resonant.{audience_block}{avoid_block}

Topic: {topic}
Tone: lyrical, deeply felt — like spoken-word poetry meets a life lesson people have never heard said so simply

Rules:
- NEVER start with "You were...", "You weren't...", "You were never...", "You were cherished" — banned
- NEVER use the phrase "you call it / they call it" or "you called it / they called it" — banned cliché
- Open with a vivid, unexpected observation — a moment in nature, a small human detail, an image that arrests attention
- Build ONE central metaphor that carries the emotional truth (not a list of metaphors — ONE)
- Use short fragmented lines — 4-8 words per line, lots of breathing room, reads like music
- Use "…" for pauses, em-dashes for emotional breaks
- The paradox/turn must feel DISCOVERED, not stated — show the contradiction through image, not through a formula
- End with a single quiet line that lands like an exhale — NOT a slogan, NOT a moral announcement
- 10-15 lines total with natural stanza breaks
- NO hashtags, NO emojis, NO stage directions, NO preachy lessons

Structure:
Stanza 1 (2-3 lines): An image or observation — pulls the viewer in before they know why
Stanza 2 (3-4 lines): Deepen the metaphor — the emotional weight builds
Stanza 3 (2-3 lines): The unexpected turn — a reframing, a contradiction, a paradox discovered through the image (NOT stated as a formula)
Stanza 4 (2-4 lines): The quiet truth — one line that makes everything before it land differently

Also provide 4 visual keywords (symbolic, metaphorical scenes — not literal objects).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\n\\nline3\\nline4\\nline5\\n\\nline6\\nline7\\n\\nline8\\nline9", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}

EXAMPLES (notice: no formula, paradox lives inside the image):
{examples_text}"""

    elif style == "love":
        style_examples = [e for e in examples if e.get("style") == "love"][:2]
        examples_text = "".join(f'\nTopic: {e["topic"]}\n{e["script"]}\n' for e in style_examples)
        return f"""Generate a viral 20-30 second love poem for "Quietlyy" — soft, intimate, the kind that makes people immediately think of one specific person.{audience_block}{avoid_block}

Topic: {topic}
Tone: tender, romantic, deeply personal — inspired by the best of Pablo Neruda, Rupi Kaur, Atticus — but rewritten as something completely new and Quietlyy

Rules:
- Write in second person ("you") — speak directly to the person being loved, like a letter never sent
- Short fragmented lines — 4-8 words, feels like a whisper or a held breath
- Use ONE specific, sensory detail that makes it feel real (how they laugh, the way they listen, a moment only these two people know)
- The love described should feel QUIET and SAFE — not dramatic or desperate
- Build toward a feeling, not a statement — the reader should feel it before they understand it
- Use "…" for pauses
- End with a warm, inviting CTA: "Tag the person who makes life feel like this ❤️" or "Send this to them. They deserve to know. ❤️" or "Tag the one who is your home ❤️"
- 8-13 lines total including CTA
- NO clichés: no "my heart", no "soul mate", no "forever and always" — fresh language only

Also provide 4 visual keywords: intimate couple moments, warm soft light, tender gestures.

Return ONLY valid JSON:
{{"script": "line1\\nline2\\n\\nline3\\nline4\\n\\nline5\\nline6\\n\\ncta_line", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}

EXAMPLES:
{examples_text}"""

    elif style == "nostalgic":
        return f"""Generate a viral 25-30 second script in "Quietlyy" nostalgic style.{audience_block}{avoid_block}

Topic: {topic}
Audience: Adults 45-65, mostly American — they remember when family togetherness, neighborhood warmth, and real conversation were everyday things. Speak to that ache.
Tone: warm, melancholic, deeply human — like a memory that still aches beautifully

CRITICAL RULES:
- The topic is a trigger for a FEELING, not the subject of the poem
  WRONG: "Remember when we gathered around the television?" (about the object)
  RIGHT: "Remember when nobody wanted the night to end?" (about the connection)
- NEVER mention the physical object or technology directly
- NEVER start with "There was a time", "In a world", "Have you ever", "We live in", "Some people", "Not everyone"
- Short punchy lines — 8-12 words max, feels like a quiet spoken memory
- Use "…" for emotional pauses
- 6-9 lines total

Structure:
Line 1-2: HOOK — paint a picture of people together, warmth, belonging (not the thing)
Line 3-4: The specific feeling that existed then — why it mattered
Line 5-6: The quiet shift — honest but not bitter, just true
Line 7-8: Gentle ache or realization
Last line: Soft share nudge — "Send this to someone you used to be closer to." or "Save this for the people who still matter."

Also provide 4 visual keywords (warm human scenes: family gatherings, people together, shared moments — NO objects).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5\\nline6\\nline7", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}

EXAMPLES:
{examples_text}"""

    elif style == "wisdom":
        return f"""Generate a viral 30-40 second life-lesson script for "Quietlyy" — opens with a famous quote (or a quote written in the authentic spirit of a great thinker), then unpacks it as a personal life lesson.{audience_block}{avoid_block}

Topic: {topic}

FORMAT (follow exactly):
Line 1: Attribution — e.g. "Rumi once wrote…" / "Marcus Aurelius kept this in his journal…" / "An old Japanese proverb says…" / "Kahlil Gibran once said…" / "Buddha taught…" / "Maya Angelou wrote…"
Lines 2-3: The quote itself — short, powerful, plain language (not archaic or stiff), split across 2 lines
Line 4: A soft bridge — e.g. "And quietly… that changed everything." / "I didn't understand it then." / "Most people never realize this."
Lines 5-7: The personal reflection — 3 short lines that unpack what this means for a real human life. Specific, felt, honest. NOT a motivational poster. NOT generic advice.
Last line: Soft share nudge — "Save this for the days you forget." / "Send this to someone carrying something heavy." / "Tag someone who needs to hear this today."

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
- Lines 5-7 reflection must feel personal, not like a TED talk or a self-help book
- Keep every line short — 6-12 words
- Use "…" for breath pauses throughout
- End warm, not dramatic

Also provide 4 visual keywords: peaceful contemplative scenes — solitude, nature, quiet interiors.

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5\\nline6\\nline7\\nline8", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}"""

    else:  # emotional — life lessons, human truths, motivation
        return f"""Generate a viral 25-30 second emotional life-lesson script for "Quietlyy" — the kind that makes people stop, feel something true, and immediately want to share it.{audience_block}{avoid_block}

Topic: {topic}
Tone: raw, deeply human — draws from the emotional truth of the topic and turns it into a lesson people feel in their chest

Rules:
- Line 1 MUST be a scroll-stopping hook — a specific moment, action, or truth that hits instantly
- NEVER start with "You were...", "You weren't...", "You were never...", "You were cherished", "You were too much" — banned
- NEVER start with "There was a time", "In a world", "Some people", "Not everyone" — banned
- Draw from the emotional truth behind famous ideas — but express it through a specific human moment, not an abstract statement
- Short punchy lines — 5-10 words each, reads fast, lands hard
- One central image or metaphor that makes the pain/lesson concrete
- MUST contain a turn — a realization, shift, or unexpected truth that reframes the opening
- MUST end with something empowering or honest — not just sadness, something they can hold onto
- 7-10 short lines total
- NO hashtags, NO emojis, NO stage directions

Structure:
Line 1-2: HOOK — a specific painful or universal human moment, phrased in a way they've never heard
Line 3-4: Deepen it — the WHY, the metaphor, the emotional truth underneath
Line 5-6: The turn — a realization, a shift in perspective, an unexpected truth
Line 7-8: The LESSON — quiet, honest, empowering — something they'll screenshot
Last line (optional): A natural share nudge — "Send this to someone who needs to hear it." / "Save this for the heavy days."

Also provide 4 visual keywords (emotional human scenes, symbolic moments — no objects).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5\\nline6\\nline7", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}

EXAMPLES (study how the hook + turn + lesson work together):
{examples_text}"""


def _call_openai_compatible(url, key, model, prompt):
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 350,
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


def _generate_raw(prompt, style):
    """Try all providers until one returns a valid script."""
    providers = [
        (generate_with_chatgpt, "ChatGPT"),
        (generate_with_gemini, "Gemini"),
        (generate_with_groq, "Groq"),
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
    return best


if __name__ == "__main__":
    script = generate_best_script()
    print(json.dumps(script, indent=2))
