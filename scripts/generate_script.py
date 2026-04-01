"""
Quietlyy — Script Generator
Generates nostalgic POETRY in the exact Quietlyy voice.
2-layer fallback: Gemini (primary) -> Groq (fallback)
"""

import os
import json
import random
import requests

TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "scripts.json")


def load_templates():
    with open(TEMPLATES_PATH, "r") as f:
        return json.load(f)


def pick_topic(templates, theme_hints=None):
    used_path = os.path.join(os.path.dirname(__file__), "..", "output", "used_topics.json")
    os.makedirs(os.path.dirname(used_path), exist_ok=True)
    used = []
    if os.path.exists(used_path):
        with open(used_path, "r") as f:
            used = json.load(f)

    pool = templates["topics_pool"]
    available = [t for t in pool if t not in used]
    if not available:
        used = []
        available = pool

    # Bias toward high-performing themes from market research (30% chance)
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
    used = used[-20:]
    with open(used_path, "w") as f:
        json.dump(used, f)
    return topic


def build_prompt(topic, examples, tone_hints=""):
    """Build prompt that forces the EXACT poetic structure."""
    examples_text = ""
    for e in examples[:3]:
        examples_text += f'\nTopic: {e["topic"]}\n{e["script"]}\n'

    audience_block = ""
    if tone_hints:
        audience_block = f"\nAudience intelligence (apply these to maximise engagement):\n{tone_hints}\n"

    return f"""Generate a viral 25-second script in "Quietlyy Quotes" style.{audience_block}

Make it:
- Hook in first 2 lines
- Emotional build in middle
- Strong, relatable ending that hits like a gut punch

Topic: {topic}
Tone: deep + quiet pain

Important:
- Avoid clich\u00e9s
- Avoid repeated sentence structures — VARY how each line opens
- Make it feel personal, like a real thought someone had at 3 AM
- Use "\u2026" for emotional pauses
- Each line is its OWN paragraph (separated by newline)
- Write exactly 5 lines, no more
- DO NOT use hashtags, emojis, or stage directions
- Keep it about PEOPLE and HUMAN CONNECTION, not the object itself
- The last line should make someone stop scrolling

STRUCTURE GUIDE (vary the openings — don't always use the same words):
Line 1: Set the scene — something we lost (can start with "There was a time\u2026", "Remember when\u2026", "Once\u2026", etc)
Line 2: How it used to feel — the beauty of the old way
Line 3: The contrast — "Not because X\u2026 but because Y" or similar emotional turn
Line 4: The modern reality — what we do now instead (cold, distant, hollow)
Line 5: The gut punch — a quiet realization that stings ("Maybe\u2026", "Perhaps\u2026", "The truth is\u2026")

Also provide 4 visual keywords showing PEOPLE/EMOTIONS (not objects).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5", "visual_keywords": ["keyword1", "keyword2", "keyword3", "keyword4"]}}

EXAMPLES (match this emotional depth but VARY the structure):
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


def generate_script(tone_hints="", theme_hints=None):
    templates = load_templates()
    topic = pick_topic(templates, theme_hints=theme_hints)
    prompt = build_prompt(topic, templates["example_scripts"], tone_hints=tone_hints)

    print(f"[script] Topic: {topic}")

    providers = [
        (generate_with_chatgpt, "ChatGPT"),
        (generate_with_gemini, "Gemini"),
        (generate_with_groq, "Groq"),
    ]

    result = None
    for gen_fn, name in providers:
        try:
            result = gen_fn(prompt)
            if result and "script" in result:
                # Validate it has the right structure
                lines = [l.strip() for l in result["script"].split("\n") if l.strip()]
                if len(lines) >= 4 and "\u2026" in result["script"]:
                    print(f"[script] Generated via {name}")
                    break
                else:
                    print(f"[script] {name} output wrong format, trying next...")
                    result = None
        except Exception as e:
            print(f"[script] {name} failed: {e}")
            result = None

    if not result:
        raise RuntimeError("All script generators failed (Gemini + Groq). Cannot proceed.")

    result["topic"] = topic
    return result


if __name__ == "__main__":
    script = generate_script()
    print(json.dumps(script, indent=2))
