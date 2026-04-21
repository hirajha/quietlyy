"""
Quietlyy — Midday Quote Image Generator

Generates a 3-slide CAROUSEL quote post (3.1x more engagement than single images):
  Slide 1: Main quote — atmospheric background, bold centered text, accent highlight
  Slide 2: Second quote — darker treatment, alt composition
  Slide 3: Brand CTA slide — minimal dark aesthetic, "Follow @Quietlyy"

Output: 1080x1350px JPG slides (4:5 portrait — optimal feed format)
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
    "the exhaustion of pretending you're okay when you're not",
    "the day you realised they never missed you the way you missed them",
    "conversations you replay at 2am wondering where it all went wrong",
    "loving someone who didn't know how to stay",
    "the moment you chose yourself and it still hurt",
]

QUOTE_PROMPT_TEMPLATE = """You are writing for "Quietlyy" — an emotional quote brand on Instagram and Facebook. Your quotes must make people stop scrolling, feel deeply understood, and want to DM them to someone specific.

Theme: "{theme}"

THE MISSION: Write a FEELING, not a lesson. The best quotes describe a private emotional experience so precisely that readers feel seen — like you reached into their chest and named something they couldn't say out loud.

HIGH-ENGAGEMENT FORMULA (what goes viral):
- Name a private experience that feels embarrassing to admit
- Use one unexpected, specific observation ("still holding the door open two years later")
- Trigger AWE: a truth so real it gives goosebumps
- 12 to 20 words — enough for the feeling to fully land

WRONG (generic/advice — gets scrolled past):
- "Healing takes time and that is okay."
- "Choose yourself without apology."
- "Rest is not a reward."

RIGHT (specific/feeling — gets shared):
- "Some people leave and you're still holding the door open two years later."
- "It's strange grieving someone who is still alive but just... not yours anymore."
- "You were never too much. You were just too real for people who only needed you in storms."
- "You didn't lose them. You lost who you thought they were."
- "She was the kind of person who made you feel at home, until she wasn't."

Rules:
- 12 to 20 words per quote — no shorter, no longer
- Name a MOMENT or FEELING, never advice
- Be specific and intimate — the kind of thing someone thinks but never says
- No rhyming. No exclamation marks. No motivational-poster language.
- Return ONLY 5 quotes, one per line. No numbering. No quotes marks. Nothing else."""


def _pick_top_two(candidates):
    """Rank by emotional specificity. Return top 2."""
    CLICHE_WORDS = ["believe", "deserve", "journey", "universe", "destiny",
                    "warrior", "blessed", "hustle", "grind", "manifest",
                    "okay", "healing takes", "you got this", "never give up"]
    SPECIFIC_MARKERS = ["who", "when", "while", "still", "never", "always",
                        "anymore", "used to", "without", "but", "just", "until",
                        "strange", "kind of", "still", "two years", "3am", "door"]

    def score(q):
        words = q.lower().split()
        n = len(words)
        length_score = 12 if 12 <= n <= 20 else max(0, 12 - abs(n - 16))
        cliche_penalty = sum(4 for c in CLICHE_WORDS if c in q.lower())
        specificity = sum(2 for m in SPECIFIC_MARKERS if m in q.lower())
        return length_score + specificity - cliche_penalty

    ranked = sorted(candidates, key=score, reverse=True)
    return ranked[:2] if len(ranked) >= 2 else ranked + ranked[:1]


def generate_quotes(theme=None):
    """Generate 5 candidates, return top 2 most emotionally specific."""
    key = os.environ.get("OPENAI_API_KEY")
    fallbacks = [
        "Some people leave and you're still holding the door open two years later.",
        "It's strange grieving someone who is still alive but just... not yours anymore.",
    ]
    if not key:
        return fallbacks

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
                    "max_tokens": 400,
                },
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()

            candidates = []
            for line in raw.split("\n"):
                line = line.strip().lstrip("123456789.-) ").strip().strip('"').strip("'")
                if len(line.split()) >= 8:
                    candidates.append(line)

            if len(candidates) >= 2:
                top2 = _pick_top_two(candidates)
                print(f"[quote_image] Picked quotes:")
                for i, q in enumerate(top2):
                    print(f"  [{i+1}] {q}")
                return top2

        except Exception as e:
            print(f"[quote_image] Quote generation attempt {attempt+1} failed: {e}")
            time.sleep(2)

    return fallbacks


# ── Background generation ─────────────────────────────────────────────────────

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
    "Two empty chairs on a porch at dusk, warm lantern light, fog over distant hills, illustrated art, amber and dark blue palette",
    "A single candle in a dark room, rain on window, bokeh lights outside, illustrated moody art, deep amber and shadow",
    "An old train station at dawn, mist on the platform, illustrated art, navy and warm gold, deeply nostalgic",
    "A sunflower field at twilight, single silhouette walking away, dark sky, illustrated cinematic art, amber and indigo",
]


def _generate_dalle_background(scene_prompt, output_path):
    """Generate atmospheric background with gpt-image-1."""
    import base64
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return False

    full_prompt = (
        f"{scene_prompt}. "
        "Illustrated art style — NOT photorealistic. Dark atmospheric. "
        "Cinematic composition. Emotional and melancholic. "
        "Dark enough overall for white text overlay anywhere on the image. "
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
                    "size": "1024x1536",
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


# ── Image composition ─────────────────────────────────────────────────────────

TARGET_W, TARGET_H = 1080, 1350

_FONT_PATHS = [
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/dejavu/DejaVuSerif.ttf",
]

_FONT_SMALL_PATHS = [
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
]


def _get_font(size, bold=True):
    from PIL import ImageFont
    paths = _FONT_PATHS if bold else _FONT_SMALL_PATHS
    for fp in paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _resize_crop(img):
    """Resize and center-crop to TARGET_W x TARGET_H."""
    from PIL import Image
    orig_w, orig_h = img.size
    scale = max(TARGET_W / orig_w, TARGET_H / orig_h)
    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - TARGET_W) // 2
    top = (new_h - TARGET_H) // 2
    return img.crop((left, top, left + TARGET_W, top + TARGET_H))


def _draw_quote_centered(draw, img, quote_text, font_size=88, y_center_frac=0.50,
                          text_color=(255, 248, 235), accent_color=(255, 176, 70),
                          box_alpha=175):
    """
    Draw quote text centered on image with a semi-transparent rounded backing box.
    First line rendered in accent_color for visual hierarchy.
    Returns the image with text composited.
    """
    from PIL import Image as PILImage, ImageDraw, ImageFont

    font = _get_font(font_size, bold=True)
    small_font = _get_font(30, bold=False)

    # Wrap text — 24 chars per line for large font
    lines = textwrap.wrap(quote_text, width=24)
    line_height = font_size + 16
    total_text_h = len(lines) * line_height

    # Measure max line width
    temp_draw = ImageDraw.Draw(img)
    max_line_w = max(
        temp_draw.textbbox((0, 0), line, font=font)[2]
        for line in lines
    )

    # Backing box dimensions
    pad_x, pad_y = 52, 44
    box_w = min(max_line_w + pad_x * 2, TARGET_W - 60)
    box_h = total_text_h + pad_y * 2 + 50  # extra 50 for brand line below
    box_x = (TARGET_W - box_w) // 2
    box_y = int(TARGET_H * y_center_frac) - box_h // 2

    # Draw semi-transparent backing box
    overlay = PILImage.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rounded_rectangle(
        [(box_x, box_y), (box_x + box_w, box_y + box_h)],
        radius=24,
        fill=(0, 0, 0, box_alpha),
    )
    img = img.convert("RGBA")
    img = PILImage.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # Draw lines
    text_start_y = box_y + pad_y
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x = (TARGET_W - line_w) // 2
        y = text_start_y + i * line_height

        color = accent_color if i == 0 else text_color

        # Soft drop shadow
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 140))
        draw.text((x, y), line, font=font, fill=color)

    # Brand tag inside box
    brand_text = "— Quietlyy"
    wm_bbox = draw.textbbox((0, 0), brand_text, font=small_font)
    wm_w = wm_bbox[2] - wm_bbox[0]
    brand_y = text_start_y + total_text_h + 14
    draw.text(
        ((TARGET_W - wm_w) // 2, brand_y),
        brand_text,
        font=small_font,
        fill=(220, 195, 155, 200),
    )

    return img.convert("RGB")


def _overlay_slide1(bg_path, quote_text, output_path):
    """Slide 1: Main quote — centered upper-middle, large bold, accent on first line."""
    from PIL import Image, ImageDraw
    img = Image.open(bg_path).convert("RGB")
    img = _resize_crop(img)

    # Darken overall for readability (overlay 30% black)
    from PIL import Image as PILImage
    dark = PILImage.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 76))
    img = PILImage.alpha_composite(img.convert("RGBA"), dark).convert("RGB")

    draw = ImageDraw.Draw(img)
    img = _draw_quote_centered(
        draw, img, quote_text,
        font_size=88,
        y_center_frac=0.48,
        accent_color=(255, 176, 70),   # warm amber
        box_alpha=170,
    )
    img.save(output_path, "JPEG", quality=92)
    print(f"[quote_image] Slide 1 saved: {output_path}")


def _overlay_slide2(bg_path, quote_text, output_path):
    """Slide 2: Second quote — darker treatment, text at 58% height."""
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.open(bg_path).convert("RGB")
    img = _resize_crop(img)

    # Mirror horizontally for visual variety
    img = img.transpose(Image.FLIP_LEFT_RIGHT)

    # Darken more than slide 1
    from PIL import Image as PILImage
    dark = PILImage.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 110))
    img = PILImage.alpha_composite(img.convert("RGBA"), dark).convert("RGB")

    # Slight warm tint
    tint = PILImage.new("RGBA", (TARGET_W, TARGET_H), (40, 20, 0, 40))
    img = PILImage.alpha_composite(img.convert("RGBA"), tint).convert("RGB")

    draw = ImageDraw.Draw(img)
    img = _draw_quote_centered(
        draw, img, quote_text,
        font_size=80,
        y_center_frac=0.52,
        accent_color=(255, 200, 100),  # softer gold
        box_alpha=185,
    )
    img.save(output_path, "JPEG", quality=92)
    print(f"[quote_image] Slide 2 saved: {output_path}")


def _make_brand_slide(output_path):
    """
    Slide 3: Brand CTA slide.
    Solid dark gradient, decorative quote mark, @Quietlyy, follow prompt.
    """
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (TARGET_W, TARGET_H), (12, 12, 18))
    draw = ImageDraw.Draw(img)

    # Subtle radial-ish gradient — lighter in center
    from PIL import Image as PILImage
    center_glow = PILImage.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(center_glow)
    for r in range(300, 0, -1):
        alpha = int(60 * (1 - r / 300))
        glow_draw.ellipse(
            [(TARGET_W // 2 - r, TARGET_H // 2 - r),
             (TARGET_W // 2 + r, TARGET_H // 2 + r)],
            fill=(80, 50, 20, alpha),
        )
    img = PILImage.alpha_composite(img.convert("RGBA"), center_glow).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Large decorative opening quotation mark
    quote_mark_font = _get_font(220, bold=True)
    qm = "\u201c"
    qm_bbox = draw.textbbox((0, 0), qm, font=quote_mark_font)
    qm_w = qm_bbox[2] - qm_bbox[0]
    draw.text(
        ((TARGET_W - qm_w) // 2, int(TARGET_H * 0.12)),
        qm,
        font=quote_mark_font,
        fill=(255, 176, 70, 60),
    )

    # Brand name
    brand_font = _get_font(96, bold=True)
    brand = "Quietlyy"
    b_bbox = draw.textbbox((0, 0), brand, font=brand_font)
    b_w = b_bbox[2] - b_bbox[0]
    draw.text(
        ((TARGET_W - b_w) // 2, int(TARGET_H * 0.44)),
        brand,
        font=brand_font,
        fill=(255, 248, 235),
    )

    # Tagline
    tag_font = _get_font(42, bold=False)
    tagline = "Daily feelings. Daily truths."
    t_bbox = draw.textbbox((0, 0), tagline, font=tag_font)
    t_w = t_bbox[2] - t_bbox[0]
    draw.text(
        ((TARGET_W - t_w) // 2, int(TARGET_H * 0.44) + 110),
        tagline,
        font=tag_font,
        fill=(200, 175, 140),
    )

    # Separator line
    line_y = int(TARGET_H * 0.67)
    line_x1 = TARGET_W // 2 - 80
    line_x2 = TARGET_W // 2 + 80
    draw.line([(line_x1, line_y), (line_x2, line_y)], fill=(255, 176, 70, 120), width=2)

    # CTA
    cta_font = _get_font(38, bold=False)
    cta = "Follow for more"
    c_bbox = draw.textbbox((0, 0), cta, font=cta_font)
    c_w = c_bbox[2] - c_bbox[0]
    draw.text(
        ((TARGET_W - c_w) // 2, int(TARGET_H * 0.70)),
        cta,
        font=cta_font,
        fill=(180, 160, 130),
    )

    img.save(output_path, "JPEG", quality=92)
    print(f"[quote_image] Slide 3 (brand) saved: {output_path}")


# ── Main entry ────────────────────────────────────────────────────────────────

def generate(theme=None, scene=None):
    """
    Generate 3-slide carousel.
    Returns dict: {quotes, image_paths, theme}
      image_paths: [slide1.jpg, slide2.jpg, slide3.jpg]
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Generate 2 quotes
    if not theme:
        theme = random.choice(QUOTE_THEMES)
    quotes = generate_quotes(theme)

    # 2. Generate background
    if not scene:
        scene = random.choice(SCENE_PROMPTS)
    bg_path = os.path.join(OUTPUT_DIR, "quote_bg.png")
    ok = _generate_dalle_background(scene, bg_path)
    if not ok:
        print("[quote_image] DALL-E failed — using solid dark background")
        try:
            from PIL import Image
            img = Image.new("RGB", (TARGET_W, TARGET_H), (18, 18, 22))
            img.save(bg_path, "PNG")
        except Exception:
            return None

    # 3. Build 3 slides
    slide1_path = os.path.join(OUTPUT_DIR, "quote_slide_1.jpg")
    slide2_path = os.path.join(OUTPUT_DIR, "quote_slide_2.jpg")
    slide3_path = os.path.join(OUTPUT_DIR, "quote_slide_3.jpg")

    _overlay_slide1(bg_path, quotes[0], slide1_path)
    _overlay_slide2(bg_path, quotes[1] if len(quotes) > 1 else quotes[0], slide2_path)
    _make_brand_slide(slide3_path)

    # Keep slide1 as the legacy single-image path too
    import shutil
    shutil.copy(slide1_path, os.path.join(OUTPUT_DIR, "quote_image.jpg"))

    # Clean up temp background
    if os.path.exists(bg_path):
        os.remove(bg_path)

    result = {
        "quotes": quotes,
        "theme": theme,
        "image_paths": [slide1_path, slide2_path, slide3_path],
        # legacy single-image compat
        "quote": quotes[0],
        "image_path": os.path.join(OUTPUT_DIR, "quote_image.jpg"),
    }
    with open(os.path.join(OUTPUT_DIR, "quote_image.json"), "w") as f:
        json.dump({k: v for k, v in result.items() if k != "image_paths" or True}, f, indent=2)

    return result


if __name__ == "__main__":
    result = generate()
    if result:
        print(f"Quotes: {result['quotes']}")
        print(f"Slides: {result['image_paths']}")
