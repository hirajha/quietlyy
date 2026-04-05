"""
Quietlyy — Script Generator
Generates nostalgic POETRY in the exact Quietlyy voice.
2-layer fallback: Gemini (primary) -> Groq (fallback)
"""

import os
import json
import random
import requests

from review_script import review_script, save_used_script

TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "scripts.json")


def load_templates():
    with open(TEMPLATES_PATH, "r") as f:
        return json.load(f)


def pick_style_and_topic(templates, theme_hints=None):
    """Alternate between 'nostalgic' and 'emotional' styles each run."""
    state_path = os.path.join(os.path.dirname(__file__), "..", "output", "used_topics.json")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)

    state = {"used_nostalgic": [], "used_emotional": [], "last_style": "emotional"}
    if os.path.exists(state_path):
        with open(state_path) as f:
            try:
                state = json.load(f)
            except Exception:
                pass

    # Alternate style each run
    style = "nostalgic" if state.get("last_style") == "emotional" else "emotional"

    pool = templates["topics_pool"][style]
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


def build_prompt(topic, examples, style="nostalgic", tone_hints="", idea_hints=""):
    """Build prompt for the given style: 'nostalgic' or 'emotional'."""
    style_examples = [e for e in examples if e.get("style") == style][:3]
    examples_text = "".join(f'\nTopic: {e["topic"]}\n{e["script"]}\n' for e in style_examples)

    audience_block = ""
    if tone_hints:
        audience_block += f"\nAudience intelligence:\n{tone_hints}\n"
    if idea_hints:
        audience_block += f"\n{idea_hints}\n"

    if style == "nostalgic":
        return f"""Generate a viral 25-second script in "Quietlyy" nostalgic style.{audience_block}

Topic: {topic}
Tone: quiet, melancholic, deeply human

Rules:
- Hook in first 2 lines. Gut-punch ending.
- NEVER start with "There was a time" — this is strictly banned. Use a different, more personal opener.
- NEVER start with "In a world", "We live in", "Have you ever", or any generic opener.
- Use "\u2026" for emotional pauses
- Exactly 5 lines, each on its own line
- About PEOPLE and HUMAN CONNECTION, not the object itself
- NO hashtags, emojis, stage directions

Structure:
Line 1: HOOK — something we lost or used to have (make it feel personal, not generic)
Line 2: Why it mattered — the warmth or beauty of that time
Line 3: The emotional turn — when things changed
Line 4: The cold modern contrast — what we do now instead
Line 5: Quiet lesson or realization — give them something to carry

Also provide 4 visual keywords (emotional scenes/people, not objects).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}

EXAMPLES:
{examples_text}"""

    else:
        return f"""Generate a viral 25-second emotional script in "Quietlyy" spoken-word style.{audience_block}

Topic: {topic}
Tone: raw, deeply human — heartbreak, friendship, missing someone, growing apart

Rules:
- Line 1 MUST be a scroll-stopping hook — something people feel in their chest instantly
- Write about real human pain: heartbreak, lost friendships, missing someone, being used, moving on
- Short punchy lines — NOT long sentences
- Use a single powerful image or metaphor in the middle
- MUST end with a lesson, realization, or quiet empowerment — not just sadness
- Write 6-9 short lines total
- NO hashtags, emojis, stage directions
- Do NOT start with "There was a time"

Structure (follow this exactly):
Line 1-2: HOOK — something universally painful that stops the scroll
Line 3-4: The deeper truth or metaphor — why it really hurts
Line 5-6: The twist or quiet realization
Line 7-8: LESSON — a piece of wisdom, empowerment, or truth that gives them something to hold onto

Also provide 4 visual keywords (emotional scenes, symbolic moments, people — no objects).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5\\nline6\\nline7", "visual_keywords": ["kw1","kw2","kw3","kw4"]}}

EXAMPLES (study the hook + lesson structure carefully):
{examples_text}"""


def _call_openai_compatible(url, key, model, prompt):
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 350,
            "temperature": 0.7,
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
                "temperature": 0.7,
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


if __name__ == "__main__":
    script = generate_script()
    print(json.dumps(script, indent=2))
