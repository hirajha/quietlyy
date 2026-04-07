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
    "letting go of people who no longer choose you",
    "healing quietly while life keeps moving",
    "the exhaustion of pretending to be okay",
    "finding peace in the ordinary moments",
    "missing someone you never really had",
    "choosing yourself without guilt",
    "growing through seasons of silence and solitude",
    "the courage of starting over",
    "loving deeply in a world that moves too fast",
    "the quiet strength of those who never complain",
    "grief that visits long after the loss",
    "the beauty of an ordinary Sunday morning",
    "learning to trust life's unexpected turns",
    "people who stay without being asked",
    "the version of you that survived everything",
]

QUOTE_PROMPT_TEMPLATE = """Write ONE single powerful life-lesson quote on this theme: "{theme}"

Rules:
- Maximum 12 words total
- No rhyming — should feel like a real thought, not a poem
- No clichés like "believe in yourself" or "follow your dreams"
- Should feel deeply personal, like pulled from someone's private journal
- Emotional and specific — makes the reader stop scrolling
- Do NOT use em dashes or fancy punctuation — keep it plain
- Return ONLY the quote text, nothing else, no quotation marks

Examples of the style:
- The people who stay quiet about their pain are carrying the most.
- You didn't lose them. You lost who you thought they were.
- Rest is not a reward. It's something you've always deserved.
- Some goodbyes were never said out loud. They just happened.
"""

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
    """Use OpenAI to generate a short powerful quote."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return "The people who stay without being asked are the ones worth keeping."

    if not theme:
        theme = random.choice(QUOTE_THEMES)

    prompt = QUOTE_PROMPT_TEMPLATE.format(theme=theme)

    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.9,
                    "max_tokens": 60,
                },
                timeout=30,
            )
            resp.raise_for_status()
            quote = resp.json()["choices"][0]["message"]["content"].strip().strip('"').strip("'")
            if quote and len(quote) > 10:
                print(f"[quote_image] Quote: {quote}")
                return quote
        except Exception as e:
            print(f"[quote_image] Quote generation attempt {attempt+1} failed: {e}")
            time.sleep(2)

    return "The people who stay without being asked are the ones worth keeping."


# ── Image generation ──────────────────────────────────────────────────────────

def _generate_dalle_background(scene_prompt, output_path):
    """Generate atmospheric background with DALL-E 3."""
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
                    "model": "dall-e-3",
                    "prompt": full_prompt,
                    "n": 1,
                    "size": "1024x1792",  # Portrait for quote images
                    "quality": "standard",
                    "response_format": "url",
                },
                timeout=120,
            )
            resp.raise_for_status()
            img_url = resp.json()["data"][0]["url"]
            img_resp = requests.get(img_url, timeout=30)
            img_resp.raise_for_status()
            if len(img_resp.content) < 5000:
                continue
            with open(output_path, "wb") as f:
                f.write(img_resp.content)
            print(f"[quote_image] Background saved: {output_path}")
            return True
        except Exception as e:
            print(f"[quote_image] DALL-E attempt {attempt+1} failed: {e}")
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
    font_size = 68
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

    # Wrap quote text — max 20 chars per line for large font
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
