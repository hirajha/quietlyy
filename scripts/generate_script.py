"""
Quietlyy — Script Generator
Generates nostalgic POETRY in the exact Quietlyy voice.
4-layer fallback: Groq → Cerebras → Gemini → Template
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
    """Build prompt that forces the EXACT poetic structure."""
    # Always show all 3 original examples — they define the voice
    examples_text = ""
    for e in examples[:3]:
        examples_text += f'\nTopic: {e["topic"]}\n{e["script"]}\n'

    return f"""You are a poet writing about "{topic}" for the page Quietlyy.

STRICT FORMAT — follow this EXACTLY:
Line 1: "There was a time… when [something emotional about {topic}]."
Line 2: "Back then… [how people used to do it with care/love/patience]."
Line 3: "Not because [practical reason]… but because [emotional reason]."
Line 4: "And now… [how modern people have ruined/lost it]."
Line 5: "Maybe… [they didn't lose X]… [they just stopped Y]."

RULES:
- Use "…" for pauses (NOT "...")
- Each line is its OWN paragraph (separated by newline)
- Write like POETRY — each line hits emotionally
- The "Maybe…" line must be a GUT PUNCH
- DO NOT use hashtags, emojis, or stage directions
- Keep it about PEOPLE and HUMAN CONNECTION, not the object itself
- Write exactly 5 lines, no more

Also provide 4 visual keywords showing PEOPLE/EMOTIONS (not objects).

Return ONLY valid JSON:
{{"script": "line1\\nline2\\nline3\\nline4\\nline5", "visual_keywords": ["keyword1", "keyword2", "keyword3", "keyword4"]}}

EXAMPLES (match this exact tone and structure):
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


def generate_with_groq(prompt):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    return _call_openai_compatible(
        "https://api.groq.com/openai/v1/chat/completions",
        key, "llama-3.3-70b-versatile", prompt,
    )


def generate_with_cerebras(prompt):
    key = os.environ.get("CEREBRAS_API_KEY")
    if not key:
        return None
    return _call_openai_compatible(
        "https://api.cerebras.ai/v1/chat/completions",
        key, "llama-3.3-70b", prompt,
    )


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
                "maxOutputTokens": 350,
                "temperature": 0.7,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def generate_script():
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
                # Validate it has the right structure
                lines = [l.strip() for l in result["script"].split("\n") if l.strip()]
                if len(lines) >= 4 and "…" in result["script"]:
                    print(f"[script] Generated via {name}")
                    break
                else:
                    print(f"[script] {name} output wrong format, trying next...")
                    result = None
        except Exception as e:
            print(f"[script] {name} failed: {e}")
            result = None

    if not result:
        ex = random.choice(templates["example_scripts"])
        result = {"script": ex["script"], "visual_keywords": ex["visual_keywords"]}
        topic = ex["topic"]
        print("[script] Using template fallback")

    result["topic"] = topic
    return result


if __name__ == "__main__":
    script = generate_script()
    print(json.dumps(script, indent=2))
