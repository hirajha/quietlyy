"""
Quietlyy — Script Generator
4-layer fallback: Groq → Cerebras → Gemini → Template
No Stability AI. All free APIs, no credit card needed.
"""

import os
import json
import random
import requests

TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "scripts.json")


def load_templates():
    with open(TEMPLATES_PATH, "r") as f:
        return json.load(f)


def pick_topic(templates):
    """Pick a random topic from the pool, avoiding recently used ones."""
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

    topic = random.choice(available)
    used.append(topic)
    used = used[-20:]
    with open(used_path, "w") as f:
        json.dump(used, f)

    return topic


def build_prompt(topic, examples):
    """Build a minimal prompt with 2 examples for the AI."""
    ex = random.sample(examples, 2)
    examples_text = "\n---\n".join([
        f"Topic: {e['topic']}\n{e['script']}" for e in ex
    ])

    return f"""Write a nostalgic 30-second voiceover script about "{topic}".

Style rules:
- 5 lines maximum, short pauses shown with "…"
- Structure: "There was a time…" → "Back then…" → "Not because… but because…" → "And now…" → "Maybe…"
- Tone: heavy, exhausted, reflective male voice
- Contrast old (valued) vs modern (lost meaning)
- End with a gut-punch "Maybe…" line
- No hashtags, no emojis, no stage directions

Also provide 4 visual keywords for AI image generation (nostalgic, warm, anime-style scenes).

Return ONLY valid JSON:
{{"script": "the full script text", "visual_keywords": ["keyword1", "keyword2", "keyword3", "keyword4"]}}

Examples:
{examples_text}"""


def _call_openai_compatible(url, key, model, prompt, name):
    """Generic caller for OpenAI-compatible APIs (Groq, Cerebras, SambaNova, Mistral)."""
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
            "temperature": 0.8,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)


# ── Layer 1: Groq (free 500K tokens/day) ──
def generate_with_groq(prompt):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    return _call_openai_compatible(
        "https://api.groq.com/openai/v1/chat/completions",
        key, "llama-3.3-70b-versatile", prompt, "Groq",
    )


# ── Layer 2: Cerebras (free 1M tokens/day) ──
def generate_with_cerebras(prompt):
    key = os.environ.get("CEREBRAS_API_KEY")
    if not key:
        return None
    return _call_openai_compatible(
        "https://api.cerebras.ai/v1/chat/completions",
        key, "llama-3.3-70b", prompt, "Cerebras",
    )


# ── Layer 3: Gemini Flash (free 250 req/day) ──
def generate_with_gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None

    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": 300,
                "temperature": 0.8,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


# ── Layer 4: Template fallback (always works, no API) ──
# Built into generate_script() below


def generate_script():
    """Main entry: generate a script with 4-layer fallback."""
    templates = load_templates()
    topic = pick_topic(templates)
    prompt = build_prompt(topic, templates["example_scripts"])

    print(f"[script] Topic: {topic}")

    providers = [
        (generate_with_groq, "Groq"),
        (generate_with_cerebras, "Cerebras"),
        (generate_with_gemini, "Gemini"),
    ]

    result = None
    for gen_fn, name in providers:
        try:
            result = gen_fn(prompt)
            if result and "script" in result:
                print(f"[script] Generated via {name}")
                break
        except Exception as e:
            print(f"[script] {name} failed: {e}")
            result = None

    if not result:
        # Layer 4: template fallback — always works
        ex = random.choice(templates["example_scripts"])
        result = {"script": ex["script"], "visual_keywords": ex["visual_keywords"]}
        topic = ex["topic"]
        print("[script] Using template fallback (Layer 4)")

    result["topic"] = topic
    return result


if __name__ == "__main__":
    script = generate_script()
    print(json.dumps(script, indent=2))
