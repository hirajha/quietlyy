"""
Quietlyy — Midday Quote Image Generator

Generates a static quote image for midday Facebook/Instagram posting:
  1. OpenAI generates a short powerful life-lesson quote (6-10 words)
  2. DALL-E 3 generates a dark atmospheric illustrated background
  3. PIL overlays the quote in clean white text with a subtle gradient
  4. Output: 1080x1350px JPG (4:5 portrait — best feed format for 2026)

Style: Typewriters Voice aesthetic — dark moody atmospheric illustrated scenes,
warm amber/teal accents, white serif quote text, minimal and emotionally resonant.
"""

import os
import json
import random
import requests
import textwrap
import time

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# ── Quote generation ──────────────────────────────────────────────────────────

QUOTE_THEMES = [
    # Specific emotional moments — the kind that make people say "who told them about me?"
    "the person you used to call at 3am who stopped picking up",
    "typing a message to someone and deleting it before sending",
    "realizing you were always the one who cared more",
    "missing someone who chose to leave",
    "crying in the car because you can't cry anywhere else",
    "the person who made you feel like too much and not enough at the same time",
    "loving someone who was never fully there",
    "the silence after a relationship ends and life just keeps going",
    "people who were there only when it was convenient for them",
    "the version of yourself you lost while trying to keep someone else",
    "waiting for an apology that never comes",
    "the moment you stop explaining yourself to people who don't want to understand",
    "growing apart from someone you thought you'd always have",
    "the relief of finally letting someone go after holding on too long",
    "being strong for everyone else while falling apart inside",
    "the friendships that ended without a single fight",
    "loving someone from a distance because it's safer that way",
    "the hollow feeling after someone who promised to stay finally leaves",
    "the person you still look for in every crowd",
    "realizing home was a person, not a place",
]

QUOTE_PROMPT_TEMPLATE = """You are writing for "Quietlyy" — an emotional quote brand on Instagram and Facebook. Your quote must make people stop scrolling, feel deeply understood, and want to send it to someone specific.

Theme: "{theme}"

THE RULE: Write a FEELING, not a lesson. The best quotes describe a private emotional experience so precisely that readers feel seen — like you reached into their chest and named something they couldn't say out loud.

WRONG (lesson/advice — will be ignored):
- "Healing takes time and that is okay."
- "Rest is not a reward. It is something you deserve."
- "Choose yourself without apology."

RIGHT (feeling — will be shared):
- "Some people leave and you're still holding the door open two years later."
- "It's strange grieving someone who is still alive but just... not yours anymore."
- "You were never too much. You were just too real for people who only needed you in storms."
- "I keep waiting for the version of you I fell in love with to come back."
- "You didn't lose them. You lost who you thought they were."

Rules:
- 10 to 18 words — enough room for the feeling to land
- Write a MOMENT or a FEELING, not advice
- Be specific — not "someone" but "the one who promised" or "the 3am person"
- One unexpected twist or observation that makes it feel fresh
- No rhyming. No exclamation marks. No motivational-poster language.
- Returns ONLY the quote text. No quotation marks. Nothing else.

Generate 3 different quotes on this theme, each on a new line. I will pick the best one."""


def _pick_best_quote(candidates):
    """Pick the most emotionally specific quote from a list.
    Scores on: length (sweet spot 10-18 words), specificity markers, no clichés."""
    CLICHE_WORDS = ["believe", "deserve", "journey", "universe", "destiny",
                    "warrior", "blessed", "hustle", "grind", "manifest",
                    "okay", "healing takes", "you got this"]
    SPECIFIC_MARKERS = ["who", "when", "while", "still", "never", "always",
                        "anymore", "used to", "without", "but", "just"]

    def score(q):
        words = q.lower().split()
        n = len(words)
        length_score = 10 if 10 <= n <= 18 else max(0, 10 - abs(n - 14))
        cliche_penalty = sum(3 for c in CLICHE_WORDS if c in q.lower())
        specificity = sum(1 for m in SPECIFIC_MARKERS if m in q.lower())
        return length_score + specificity * 2 - cliche_penalty

    return max(candidates, key=score)

SCENE_PROMPTS = [
    "A lone figure with a red umbrella standing in golden wheat fields under a storm-lit sky, cinematic illustrated art, warm amber and teal tones, dark atmospheric, moody",
    "An old stone cottage with warm glowing windows at night, fog rolling over silent hills, illustrated art style, deep navy and amber, melancholic and beautiful",
    "A solitary person sitting on a wooden dock at dusk, still water reflecting orange sky, painterly illustration, dark and emotional, muted warm palette",
    "A narrow cobblestone lane at twilight with lanterns glowing softly, illustrated art, deep teal and gold tones, cinematic and atmospheric",
    "A small red tent in a vast dark forest with firefly lights, illustrated, moody and serene, midnight blue and amber",
    "An empty park bench under a tree losing its leaves in autumn rain, illustrated atmospheric art, dark muted palette, deeply melancholic",
    "A lighthouse on rocky cliffs at stormy dusk, dramatic sky, illustrated painterly art, navy and gold tones, emotional",
    "A person standing at a rain-streaked window looking out at a quiet street at night, warm interior light, illustrated art style, moody and introspective",
    "Rolling misty hills at golden hour with a tiny silhouette walking a winding path, illustrated art, warm amber haze, atmospheric and peaceful",
    "An old wooden bridge over a still river in autumn, fallen leaves, soft fog, illustrated art, muted earth tones, deeply serene",
]


def generate_quote(theme=None):
    """Generate 3 candidate quotes and pick the most emotionally specific one."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return "Some people leave and you're still holding the door open two years later."

    if not theme:
        theme = random.choice(QUOTE_THEMES)

    print(f"[quote_image] Theme: {theme}")
    prompt = QUOTE_PROMPT_TEMPLATE.format(theme=theme)

    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.95,
                    "max_tokens": 200,
                },
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()

            # Parse the 3 candidates (one per line, strip numbering/bullets)
            candidates = []
            for line in raw.split("\n"):
                line = line.strip().lstrip("123456789.-) ").strip().strip('"').strip("'")
                if len(line) > 15:
                    candidates.append(line)

            if candidates:
                best = _pick_best_quote(candidates)
                print(f"[quote_image] Candidates ({len(candidates)}):")
                for i, c in enumerate(candidates):
                    marker = "★" if c == best else " "
                    print(f"  {marker} {c}")
                print(f"[quote_image] Selected: {best}")
                return best

        except Exception as e:
            print(f"[quote_image] Quote generation attempt {attempt+1} failed: {e}")
            time.sleep(2)

    return "Some people leave and you're still holding the door open two years later."


# ── Image generation ──────────────────────────────────────────────────────────

def _generate_dalle_background(scene_prompt, output_path):
    """Generate atmospheric background with gpt-image-1 (migrated from dall-e-3)."""
    import base64
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return False

    full_prompt = (
        f"{scene_prompt}. "
        "Illustrated art style — NOT photorealistic. Dark atmospheric. "
        "Cinematic composition. Emotional and melancholic. "
        "Leave the lower third of the image dark enough for white text overlay. "
        "High quality, detailed, painterly. No text in the image."
    )

    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-image-1",
                    "prompt": full_prompt,
                    "n": 1,
                    "size": "1024x1536",  # Portrait (replaces 1024x1792 — not supported by gpt-image-1)
                    "quality": "medium",
                },
                timeout=120,
            )
            resp.raise_for_status()
            item = resp.json()["data"][0]
            if "b64_json" in item:
                img_data = base64.b64decode(item["b64_json"])
            elif "url" in item:
                img_resp = requests.get(item["url"], timeout=30)
                img_resp.raise_for_status()
                img_data = img_resp.content
            else:
                continue
            if len(img_data) < 5000:
                continue
            with open(output_path, "wb") as f:
                f.write(img_data)
            print(f"[quote_image] Background saved: {output_path}")
            return True
        except Exception as e:
            print(f"[quote_image] gpt-image-1 attempt {attempt+1} failed: {e}")
            time.sleep(3)
    return False


def _overlay_quote(bg_path, quote_text, output_path):
    """Overlay quote text on background image. Output: 1080x1350 JPG."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
    except ImportError:
        print("[quote_image] Pillow not available — saving background as-is")
        import shutil
        shutil.copy(bg_path, output_path)
        return

    img = Image.open(bg_path).convert("RGB")

    # Resize/crop to exactly 4:5 (1080x1350)
    target_w, target_h = 1080, 1350
    orig_w, orig_h = img.size
    scale = max(target_w / orig_w, target_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))

    draw = ImageDraw.Draw(img)

    # Dark gradient overlay on bottom 45% for text readability
    from PIL import Image as PILImage
    overlay = PILImage.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    gradient_top = int(target_h * 0.55)
    for y in range(gradient_top, target_h):
        alpha = int(200 * (y - gradient_top) / (target_h - gradient_top))
        overlay_draw.line([(0, y), (target_w, y)], fill=(0, 0, 0, alpha))
    img = img.convert("RGBA")
    img = PILImage.alpha_composite(img, overlay)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Font — try Liberation Serif (installed in CI), fallback to DejaVu, then default
    font_paths = [
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/dejavu/DejaVuSerif.ttf",
    ]
    font = None
    font_size = 76  # larger — more readable on mobile feed
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                from PIL import ImageFont
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
    if font is None:
        from PIL import ImageFont
        font = ImageFont.load_default()

    # Wrap quote text — max 22 chars per line
    lines = textwrap.wrap(quote_text, width=22)
    line_height = font_size + 18
    total_text_h = len(lines) * line_height

    # Position: vertically centered in the bottom 40%
    text_top = int(target_h * 0.6) + (int(target_h * 0.35) - total_text_h) // 2

    # Draw each line centered
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (target_w - text_w) // 2
        y = text_top + i * line_height
        # Shadow for depth
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=font, fill=(255, 248, 235))  # warm white

    # Subtle brand watermark at very bottom
    try:
        small_font = ImageFont.truetype(font_paths[0], 28) if font_paths else font
        watermark = "— Quietlyy"
        wm_bbox = draw.textbbox((0, 0), watermark, font=small_font)
        wm_w = wm_bbox[2] - wm_bbox[0]
        draw.text(((target_w - wm_w) // 2, target_h - 70), watermark,
                  font=small_font, fill=(200, 185, 165, 180))
    except Exception:
        pass

    img.save(output_path, "JPEG", quality=92)
    print(f"[quote_image] Final image saved: {output_path}")


# ── Main entry ────────────────────────────────────────────────────────────────

def generate(theme=None, scene=None):
    """
    Generate quote image.
    Returns dict: {quote, image_path, theme}
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    bg_path = os.path.join(OUTPUT_DIR, "quote_bg.png")
    final_path = os.path.join(OUTPUT_DIR, "quote_image.jpg")

    # 1. Generate quote
    if not theme:
        theme = random.choice(QUOTE_THEMES)
    quote = generate_quote(theme)

    # 2. Generate background
    if not scene:
        scene = random.choice(SCENE_PROMPTS)
    ok = _generate_dalle_background(scene, bg_path)
    if not ok:
        print("[quote_image] DALL-E failed — using solid dark background")
        try:
            from PIL import Image
            img = Image.new("RGB", (1080, 1350), (18, 18, 22))
            img.save(bg_path)
        except Exception:
            return None

    # 3. Overlay text
    _overlay_quote(bg_path, quote, final_path)

    # Clean up temp background
    if os.path.exists(bg_path):
        os.remove(bg_path)

    result = {"quote": quote, "theme": theme, "image_path": final_path}
    with open(os.path.join(OUTPUT_DIR, "quote_image.json"), "w") as f:
        json.dump(result, f, indent=2)

    return result


if __name__ == "__main__":
    result = generate()
    if result:
        print(f"Quote: {result['quote']}")
        print(f"Image: {result['image_path']}")
