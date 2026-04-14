"""
Quietlyy — Image Generator
DALL-E 3 ONLY — no stock photos, no gradients.
If DALL-E fails for a panel, reuse an earlier successful panel from same video.

Gallery system:
  - Generated images saved to assets/gallery/ for reuse
  - After 25 images stored, start reusing gallery images
  - Max 2-3 reused images per video, never at position 0 (start)
  - Gallery capped at 500 images — oldest are deleted
"""

import io
import os
import json
import hashlib
import random
import shutil
import time
import requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
GALLERY_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "gallery")
GALLERY_INDEX = os.path.join(GALLERY_DIR, "index.json")
GALLERY_MAX = 500
REUSE_THRESHOLD = 25  # Start reusing after this many images in gallery
MAX_REUSE_PER_VIDEO = 3  # Max reused images per video


def _load_gallery_index():
    """Load gallery index — tracks images with metadata for reuse."""
    if os.path.exists(GALLERY_INDEX):
        with open(GALLERY_INDEX) as f:
            return json.load(f)
    return []


def _save_gallery_index(index):
    with open(GALLERY_INDEX, "w") as f:
        json.dump(index, f, indent=2)


def _add_to_gallery(image_path, topic, panel_num, source):
    """Copy image to gallery with metadata. Caps at GALLERY_MAX."""
    os.makedirs(GALLERY_DIR, exist_ok=True)
    index = _load_gallery_index()

    ts = int(time.time())
    h = hashlib.md5(f"{topic}_{panel_num}_{ts}".encode()).hexdigest()[:8]
    ext = os.path.splitext(image_path)[1] or ".png"
    gallery_name = f"{h}_{panel_num}{ext}"
    gallery_path = os.path.join(GALLERY_DIR, gallery_name)

    shutil.copy2(image_path, gallery_path)

    index.append({
        "file": gallery_name,
        "topic": topic,
        "panel": panel_num,
        "source": source,
        "timestamp": ts,
    })

    # Cap at GALLERY_MAX — delete oldest
    if len(index) > GALLERY_MAX:
        to_remove = index[:len(index) - GALLERY_MAX]
        for entry in to_remove:
            old_path = os.path.join(GALLERY_DIR, entry["file"])
            if os.path.exists(old_path):
                os.remove(old_path)
        index = index[-GALLERY_MAX:]

    _save_gallery_index(index)
    print(f"[gallery] Saved {gallery_name} ({len(index)}/{GALLERY_MAX})")


def _pick_reuse_panels(num_panels):
    """Gallery reuse disabled — every panel is freshly generated with DALL-E.
    Reusing random gallery images caused wrong-topic frames to appear mid-video."""
    return {}


# ── High-performing aesthetic (based on 778-view top video "Rediscovering the Beauty of Boredom"):
# - Dark, moody, cinematic anime/illustration style
# - Deep navy blues, dark purples, soft teal, midnight indigo backgrounds
# - A single light source: lamp, moon, window glow — creates drama and depth
# - Silhouettes or semi-visible figures against atmospheric backgrounds
# - Lo-fi emotional anime vibe — NOT bright, NOT colorful, NOT Ghibli-cheerful
# - High visual contrast: dark scene + warm glowing light source
# - Feels introspective, premium, cinematic — makes viewers stop scrolling

_SCENE_POOL_CLOSEUP = [
    # Face closeups — soft glow against dark background
    "Close-up portrait of a young woman, chin resting on her hand, gazing into the distance, "
    "single warm lamp glow on her face, deep navy blue background fading to black, "
    "dark cinematic anime illustration style — moody, intimate, emotionally resonant",

    "Side profile of a young woman on a dark train at night, head gently leaning against the window, "
    "city lights blurring softly outside, reflection of her face in the glass, "
    "deep blue-black interior, single warm light source, dark atmospheric anime style",

    "Close-up of a young woman's face, eyes looking downward with a gentle melancholy, "
    "soft teal moonlight from a nearby window, dark blue-grey background, "
    "dark cinematic illustration — emotionally heavy, beautifully lit, anime aesthetic",

    "A man with tired eyes staring into the distance, single desk lamp glow on his face, "
    "deep dark navy background, shadows framing his expression, "
    "cinematic manga illustration style — contemplative, moody, visually striking",

    "Close-up of two people's hands almost touching across a dark table, "
    "one soft amber candle glow between them, deep dark background, "
    "dark illustrated style — tender, intimate, cinematic",

    "A woman reading an old letter by candlelight, flame casting warm amber on her face, "
    "surrounding darkness, deep blue shadows, "
    "dark anime illustration — emotional, cinematic, beautiful",
]

_SCENE_POOL_WIDE = [
    # Wide scenes — dark atmospheric with single light source
    "A lone figure standing on a dark hilltop, full moon behind clouds, "
    "deep indigo-blue sky, soft moonlight spilling across the landscape, "
    "dark cinematic anime style — vast, atmospheric, emotionally powerful",

    "A person sitting alone on a park bench at night, one distant street lamp, "
    "deep navy sky, soft golden pool of light around them, dark trees silhouetted, "
    "dark anime illustration — lonely, cinematic, beautiful",

    "Wide view of a dark city at night seen from a rooftop, "
    "scattered warm window lights below, deep blue-black sky above, "
    "a lone figure at the edge looking out, "
    "cinematic dark anime style — vast, moody, introspective",

    "A quiet dark street at night after rain, wet pavement reflecting street lamp light, "
    "deep blue-black shadows, one figure walking away in the distance, "
    "dark cinematic anime illustration — melancholy, beautiful, atmospheric",

    "A person standing at the edge of a dark lake at midnight, "
    "full moon reflected perfectly in still water, deep indigo and black tones, "
    "soft silver moonlight on their silhouette, "
    "dark anime illustration — vast, emotional, visually striking",

    "A moonlit coastal cliff, dark ocean stretching to the horizon, "
    "silver moon path on the water, lone figure at the edge, deep blue-black sky, "
    "dark cinematic illustrated style — breathtaking, moody, emotional",
]

_SCENE_POOL_INTERIOR = [
    # Interior — cosy light islands in dark rooms
    "A person sitting alone at a window at 2am, small lamp beside them, "
    "dark room behind, soft blue moonlight outside the glass, "
    "deep navy and warm amber contrast, dark cinematic anime style — insomniac mood, beautiful",

    "A woman at a dark kitchen table, single candle glowing, "
    "surrounding deep shadow, warm amber flame on her face, "
    "dark anime illustration — intimate, quiet, emotionally resonant",

    "Someone lying on their bedroom floor looking up at a dark ceiling, "
    "single shaft of moonlight from a window across them, deep dark blue room, "
    "dark cinematic illustration — introspective, beautiful, emotionally heavy",

    "A person at a desk at night, monitor glow softly lighting their face, "
    "deep dark room around them, blue-white screen light, "
    "dark anime illustration — modern loneliness, cinematic, moody",

    "An old living room at night, one lamp in the corner, deep shadows everywhere, "
    "a person sitting still on a dark sofa, warm amber pool of light, "
    "dark cinematic illustrated style — nostalgic, quiet, emotionally rich",

    "Someone sitting on the floor against a bed, knees drawn up, "
    "single lamp glowing in the background, deep dark bedroom around them, "
    "dark anime illustration — vulnerable, intimate, beautiful",
]

_SCENE_POOL_TWO_PEOPLE = [
    # Two people — dark atmospheric, emotional distance or closeness
    "Two silhouettes standing apart on a dark bridge at night, "
    "city lights reflected in water below, deep blue-black sky, "
    "dark cinematic anime style — emotional distance, atmospheric, beautiful",

    "Two people sitting on opposite ends of a dark room, "
    "one lamp between them, deep shadows, warm amber pool in the middle, "
    "dark illustrated style — unspoken tension, cinematic, emotionally heavy",

    "Two silhouettes walking in opposite directions on a dark street at night, "
    "one distant street lamp between them, deep blue-black tones, "
    "dark anime illustration — separation, melancholy, visually striking",

    "Two people sitting close together in a dark car at night, "
    "city lights glowing through rain-streaked windows, warm dashboard light, "
    "dark cinematic manga style — intimate, atmospheric, deeply emotional",

    "Two figures standing under one umbrella in the dark rain, "
    "street lamp above them, dark wet street reflecting their light, "
    "deep navy and warm amber contrast, dark anime illustration",
]

# Combined pool — weighted
_SCENE_POOL = (
    _SCENE_POOL_CLOSEUP * 2 +
    _SCENE_POOL_WIDE * 2 +
    _SCENE_POOL_INTERIOR * 3 +
    _SCENE_POOL_TWO_PEOPLE * 2
)

# ── Art style variants — ALL dark cinematic anime (matching the 778-view top performer)
_LOVE_STYLE_VARIANTS = [
    (
        "Dark romantic anime illustration — deep navy blues, soft warm amber glow, cinematic. "
        "Two people in an intimate tender moment, soft single light source on their faces, "
        "surrounding darkness creating depth and drama. "
        "Palette: deep midnight blue, soft warm amber, gentle teal, muted rose. "
        "Style: dark cinematic anime — like 'A Silent Voice' or 'Your Name' — moody, beautiful, emotional."
    ),
    (
        "Cinematic dark romance illustration — moody, deep, intimate. "
        "Palette: deep indigo, soft amber candle glow, dark teal, midnight blue. "
        "Two people close together, warm light on their faces, dark atmospheric background. "
        "Style: dark anime film aesthetic — high contrast, emotionally resonant, visually striking."
    ),
    (
        "Dark romantic illustrated art — atmospheric and intimate. "
        "Deep blue-black backgrounds, one warm light source (candle, lamp, moon) illuminating the scene. "
        "Two people in a quiet tender moment, faces softly lit against darkness. "
        "Style: dark cinematic manga — like Makoto Shinkai films, moody and beautiful."
    ),
]

_STYLE_VARIANTS = [
    (
        "Dark cinematic anime illustration style — moody, atmospheric, emotionally powerful. "
        "Palette: deep midnight navy, dark indigo, soft teal, warm amber glow from single light source. "
        "High contrast: rich darkness surrounding a single warm or cool light. "
        "Characters semi-visible or silhouetted, faces softly lit. "
        "Style: like 'A Silent Voice', 'Your Name', 'Violet Evergarden' — "
        "dark, cinematic, deeply emotional. NOT bright. NOT colorful. NOT cheerful."
    ),
    (
        "Atmospheric dark anime illustration — cinematic and introspective. "
        "Dominant tones: deep navy blue, dark purple-indigo, muted teal, "
        "with warm amber or soft moonlight as the only light source. "
        "Scenes feel like a quiet 3am moment — beautiful, heavy, still. "
        "Style: dark lo-fi anime aesthetic — introspective, premium, visually striking. "
        "High visual contrast creates depth. Feels like a cinematic short film frame."
    ),
    (
        "Cinematic dark illustrated art — deep, moody, emotionally resonant. "
        "Dark rich backgrounds: midnight indigo, deep navy, soft dark teal. "
        "Single warm light source: window glow, candle, street lamp, moon. "
        "Figures partially in shadow — dramatic, intimate, real. "
        "Style: premium dark anime illustration — like Makoto Shinkai at night, "
        "beautiful in darkness. Makes viewers stop scrolling."
    ),
    (
        "Lo-fi dark anime aesthetic — atmospheric, quiet, emotionally heavy. "
        "Palette: deep blue-black backgrounds, soft ambient teal, "
        "warm amber island of light in darkness, muted indigo shadows. "
        "Lone figure or intimate scene bathed in a single light source. "
        "Style: dark cinematic anime illustration — introspective, premium, "
        "visually dramatic. The kind of image that looks beautiful on a phone screen at night."
    ),
]

# Module-level: pick a style once per import (once per pipeline run)
_CHOSEN_STYLE = random.choice(_STYLE_VARIANTS)
# Shuffle scenes once per run for fresh panel order every video
_SHUFFLED_SCENES = random.sample(_SCENE_POOL, len(_SCENE_POOL))

# Love-specific scene pool — dark romantic couple art (Whispers of Heart style)
_LOVE_SCENE_POOL = [
    "A couple close together in the dark, one resting head on the other's shoulder, soft moonlight",
    "Two people facing each other, eyes closed, foreheads almost touching, intimate and quiet",
    "A person holding another from behind, both looking out at a dark night sky with stars",
    "Close-up of two hands intertwined, soft diffuse light, dark background",
    "A couple sitting together in silence, one lamp casting warm light, dark room around them",
    "Side profile of two people about to kiss, soft light on faces, everything else in shadow",
    "A person leaning into another's neck, eyes closed, peaceful and safe, dark background",
    "Two silhouettes standing close in rain at night, street lamp behind them, reflections below",
    "Close-up of a face being cradled gently by two hands, eyes closed, tender moment",
    "Two people lying close, one watching the other sleep, soft window light, night outside",
]


def generate_image_prompt(topic, visual_keywords, panel_num, style="emotional"):
    """Create varied scene prompts — each run gets a different scene sequence and art style.
    Love style uses dark romantic B&W aesthetic; others use warm illustrated style."""
    keywords_str = ", ".join(visual_keywords)

    if style == "love":
        chosen_style = random.choice(_LOVE_STYLE_VARIANTS)
        shuffled_love = random.sample(_LOVE_SCENE_POOL, len(_LOVE_SCENE_POOL))
        scene = shuffled_love[panel_num % len(_LOVE_SCENE_POOL)]
    else:
        chosen_style = _CHOSEN_STYLE
        scene = _SHUFFLED_SCENES[panel_num % len(_SHUFFLED_SCENES)]

    return (
        f"{chosen_style} "
        f"Scene: {scene}. "
        f"Emotional theme: {topic}. Mood keywords: {keywords_str}. "
        f"Portrait orientation (tall, 9:16). "
        f"No text, no watermarks, no words, no UI elements."
    )


def _crop_to_portrait(image_path):
    """Crop square image to 9:16 portrait (center crop, keep top for faces)."""
    from PIL import Image
    img = Image.open(image_path)
    w, h = img.size
    print(f"[images] Raw dimensions: {w}x{h}")

    # Target: 9:16 ratio. From 1024x1024 → crop to 576x1024
    target_w = int(h * 9 / 16)
    if target_w > w:
        target_w = w
    # Center crop horizontally
    left = (w - target_w) // 2
    img = img.crop((left, 0, left + target_w, h))
    img.save(image_path)
    print(f"[images] Cropped to portrait: {img.size[0]}x{img.size[1]}")


def generate_with_dalle(prompt, output_path):
    """Generate image using OpenAI gpt-image-1 API.
    Migrated from dall-e-3 which is deprecated May 12 2026.
    Uses 1024x1536 native portrait — no cropping needed."""
    import base64
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return False

    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-image-1",
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1536",   # native portrait — no crop needed
                    "quality": "medium",   # low/medium/high (was standard/hd)
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            item = data["data"][0]

            # gpt-image-1 returns b64_json; fall back to url if present
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

            # Resize to exactly 1080x1920 (aspect is already 9:16)
            from PIL import Image as PILImage
            img = PILImage.open(output_path).convert("RGB")
            img = img.resize((1080, 1920), PILImage.LANCZOS)
            img.save(output_path)
            return True
        except Exception as e:
            print(f"[images] gpt-image-1 attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(3)
    return False


def generate_with_dalle3_fallback(prompt, output_path):
    """Fallback: DALL-E 3 (still available, wider tier access than gpt-image-1)."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return False
    try:
        resp = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "dall-e-3",
                "prompt": prompt[:4000],
                "n": 1,
                "size": "1024x1792",  # closest 9:16 portrait
                "quality": "standard",
                "response_format": "url",
            },
            timeout=90,
        )
        resp.raise_for_status()
        url = resp.json()["data"][0]["url"]
        img_resp = requests.get(url, timeout=30)
        img_resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(img_resp.content)
        from PIL import Image as PILImage
        img = PILImage.open(output_path).convert("RGB")
        img = img.resize((1080, 1920), PILImage.LANCZOS)
        img.save(output_path)
        print(f"[images]   DALL-E 3 fallback succeeded")
        return True
    except Exception as e:
        print(f"[images]   DALL-E 3 fallback failed: {e}")
        return False


def generate_images(topic, visual_keywords, num_panels=5, style="emotional"):
    """Generate panel images using DALL-E ONLY.
    - Max 5 panels per video
    - DALL-E is the only generator — no stock photos or gradients
    - If DALL-E fails for a panel, reuse an earlier successful panel from same video
    - After 25 gallery images: reuse 2-3 panels (never panel 0)
    - Saves new images to gallery (capped at 500)
    At least 1 image must succeed or pipeline fails."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    num_panels = min(num_panels, 8)  # Hard cap at 8 — enough for poetic scripts
    paths = []
    successful_paths = []  # Track successfully generated images for reuse within this video

    # Check if we should reuse some panels from gallery
    reuse_map = _pick_reuse_panels(num_panels)

    for i in range(num_panels):
        output_path = os.path.join(OUTPUT_DIR, f"panel_{i}.png")

        # Use reused gallery image if assigned
        if i in reuse_map:
            shutil.copy2(reuse_map[i], output_path)
            paths.append(output_path)
            continue

        # Generate fresh image with DALL-E
        prompt = generate_image_prompt(topic, visual_keywords, i, style=style)
        print(f"[images] Panel {i+1}/{num_panels}: generating with DALL-E...")

        success = generate_with_dalle(prompt, output_path)
        if not success:
            print(f"[images]   gpt-image-1 failed — trying DALL-E 3 fallback...")
            success = generate_with_dalle3_fallback(prompt, output_path)

        if success:
            print(f"[images] Panel {i+1}: generated")
            successful_paths.append(output_path)
        else:
            # Both models failed — reuse an earlier panel from THIS video
            if successful_paths:
                reuse_src = random.choice(successful_paths)
                shutil.copy2(reuse_src, output_path)
                print(f"[images] Panel {i+1}: reusing earlier panel (both models failed)")
            else:
                raise RuntimeError(f"Image generation failed for panel {i+1} (tried gpt-image-1 and dall-e-3). No earlier panels to reuse.")

        paths.append(output_path)

        if i < num_panels - 1:
            time.sleep(2)  # Respect rate limits between DALL-E calls

    print(f"[images] Generated {len(paths)} panels ({len(reuse_map)} from gallery, {len(successful_paths)} fresh DALL-E)")
    return paths


if __name__ == "__main__":
    paths = generate_images(
        "Telephone",
        ["old telephone", "rotary phone", "vintage phone booth", "warm lamp light"],
    )
    print(json.dumps(paths, indent=2))
