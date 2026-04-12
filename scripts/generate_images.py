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


# ── Whisprs-style aesthetic reference (1.6M / 1.8M view videos):
# - Semi-realistic illustrated / manga-anime art style (NOT photorealistic, NOT dark gothic)
# - Muted earthy palette: warm olive green, dusty sage, terracotta, warm beige, soft teal
# - Backgrounds: airy, misty, light — morning mist, foggy fields, soft skies — NOT dark/creepy
# - Characters: clear visible faces, warm skin tones, natural poses, readable emotions
# - Like a beautiful illustrated book cover or Studio Ghibli concept art

_SCENE_POOL_CLOSEUP = [
    # Face closeups — warm skin tones, soft natural light, clear readable faces
    "Close-up portrait of a young woman, chin resting on her hand, looking pensively to the side, "
    "soft warm natural window light, warm olive-beige tones, loose hair, "
    "semi-realistic manga illustration style — like Whisprs aesthetic",

    "Side profile of a young woman on a train, head gently resting against the window, "
    "soft afternoon light on her face, muted sage-green and warm beige interior, "
    "rolling countryside visible outside, peaceful and melancholy, illustrated manga style",

    "Close-up of a young woman's face, eyes cast slightly downward, gentle sad expression, "
    "soft diffuse daylight, warm terracotta and beige tones, hair falling loosely, "
    "semi-realistic illustrated art — clear detailed face, emotionally resonant",

    "A man with tired eyes staring into the distance, soft side light on his face, "
    "muted earthy tones — warm olive, dusty brown, sage — contemplative expression, "
    "illustrated graphic novel style — clear face, visible emotions, warm palette",

    "Close-up of two people's hands almost touching on a wooden table, "
    "warm afternoon light, soft muted earthy tones, "
    "illustrated style — tender, clear, emotionally meaningful",

    "A woman reading an old letter, soft daylight from a nearby window, "
    "warm beige and terracotta tones, books and tea nearby, "
    "semi-realistic illustration — clear face, warm and nostalgic mood",
]

_SCENE_POOL_WIDE = [
    # Wide landscapes — Whisprs aesthetic: misty, airy, muted earthy tones
    "Misty mountain valley at dawn, layered blue-green pine forests fading into pale morning mist, "
    "a tiny lone figure on a winding path, soft pale sky above, "
    "muted teal and olive greens, warm beige mist — airy, breathtaking, illustrated style",

    "A calm mountain lake reflecting snow-capped peaks, a small wooden boat with one person, "
    "misty grey-blue sky, pine forest shoreline, muted teal-grey-beige palette, "
    "vintage travel poster illustration style — peaceful and emotionally vast",

    "Wide open green field at dusk, golden-green grass, soft amber horizon, "
    "two small silhouettes in the middle distance walking together, "
    "warm muted palette: dusty gold, sage green, soft terracotta sky, "
    "illustrated Ghibli-style — airy and beautiful",

    "Misty morning countryside, rolling hills, old farmhouses in the distance, "
    "soft pale green and beige tones, light fog across the valley, birds in the pale sky, "
    "one figure walking a country lane, warm illustrated style — peaceful and nostalgic",

    "Foggy forest path at dawn, tall trees either side, soft green-grey mist, "
    "warm diffuse morning light filtering through, a small figure walking away into the mist, "
    "muted olive and sage palette, illustrated Ghibli aesthetic — serene and emotional",

    "A moonlit lake, silver reflection stretching to the horizon, "
    "two tiny silhouettes standing at the shore, deep blue-grey sky with soft moon, "
    "illustrated style — muted blues and silver, not dark/gothic, peaceful and vast",
]

_SCENE_POOL_INTERIOR = [
    # Interior scenes — warm cosy light, clear readable setting
    "A person sitting cross-legged by a large window at dusk, "
    "warm lamp beside them, soft golden light on their face, "
    "muted teal-blue evening sky outside the window, books and papers around them, "
    "semi-realistic illustration — warm amber inside, cool blue outside, peaceful",

    "A woman at a wooden table in a cosy kitchen, holding a cup of tea, "
    "looking out at rain through a window, warm amber and beige interior, "
    "illustrated manga style — clear face, warm muted palette, nostalgic mood",

    "An elderly couple sitting together at a dining table, soft warm light, "
    "simple home interior, muted earthy tones — warm cream, terracotta, olive, "
    "illustrated realistic style — warm, tender, immediately readable",

    "A young person sitting on the floor of their bedroom, back against the bed, "
    "knees drawn up, looking at an old photo, warm lamp in background, "
    "muted beige and dusty sage tones, illustrated style — clear and emotionally resonant",

    "A small family gathered around an old television set in a living room, "
    "warm amber lamp light, muted earthy 1970s tones — olive, terracotta, warm brown, "
    "illustrated vintage style — nostalgic, warm, instantly recognizable",

    "Someone writing in a journal by a window, morning light on the page, "
    "warm beige and sage tones, tea steaming beside them, "
    "illustrated semi-realistic style — peaceful, clear, inviting",
]

_SCENE_POOL_TWO_PEOPLE = [
    # Two people — connection, warmth, distance
    "Two people sitting on a train facing each other through the window, "
    "soft afternoon light, warm sage-green and beige tones, "
    "illustrated manga style — clear faces, warm muted palette, tender mood",

    "Two silhouettes standing in a misty green field at dawn, "
    "pale morning light, soft fog around their feet, "
    "warm olive and beige tones, illustrated Ghibli style — peaceful and emotional",

    "Two people walking side by side down a leafy autumn path, "
    "dappled golden afternoon light, muted amber and olive tones, "
    "illustrated style — warm, nostalgic, clear and beautiful",

    "A couple sitting on a park bench in soft autumn light, "
    "not talking, both looking into the distance, fallen leaves around them, "
    "muted earthy palette — dusty gold, sage, warm beige, illustrated graphic novel style",

    "Two people at a cafe window, one looking out, one looking at the other, "
    "warm interior light, rain visible outside, muted warm palette, "
    "illustrated semi-realistic style — intimate, clear, emotionally rich",
]

# Combined pool — weighted for variety
_SCENE_POOL = (
    _SCENE_POOL_CLOSEUP * 2 +
    _SCENE_POOL_WIDE * 2 +
    _SCENE_POOL_INTERIOR * 3 +
    _SCENE_POOL_TWO_PEOPLE * 2
)

# ── Art style variants — ALL based on Whisprs aesthetic ──────────────────────
# Key: muted earthy illustrated, NOT dark gothic, NOT photorealistic, NOT creepy
_LOVE_STYLE_VARIANTS = [
    (
        "Vibrant romantic anime illustration — rich warm colors, intimate and beautiful. "
        "Rich palette: deep rose pink, warm amber golden light, soft lavender sky, glowing coral sunset. "
        "Two people in a tender close moment — foreheads touching, gentle embrace. "
        "Colorful, vivid, emotionally warm backgrounds — garden, golden field, sunset light. "
        "Like a beautiful Ghibli love scene — NOT dark, NOT muted. Vibrant, warm, romantic."
    ),
    (
        "Beautiful illustrated romance — vivid warm saturated colors. "
        "Palette: glowing amber lamp light, rich rose, soft golden sunset, deep teal evening sky. "
        "Intimate couple scene — close faces, tender gentle expressions, clear warm skin tones. "
        "Rich colorful backgrounds: blooming garden, golden-lit room, soft glowing sunset. "
        "Style: high-quality romantic anime art — vibrant, warm, emotionally alive."
    ),
    (
        "Romantic illustrated art — colorful, warm, radiant. "
        "Colors: warm gold, deep rose, soft amber, emerald green, glowing sunset orange and pink. "
        "Two people close together, soft expressions, warm faces clearly visible. "
        "Beautiful rich backgrounds: glowing sunset, colorful garden, warm lit interior. "
        "Like a stunning romance illustration — NOT dark or grey. Vibrant, loving, colorful."
    ),
]

_STYLE_VARIANTS = [
    (
        "Vibrant Studio Ghibli illustration style — rich, saturated, beautiful colors. "
        "Palette: deep cerulean blue sky, lush emerald green fields, warm golden sunset orange, "
        "bright coral, soft lavender clouds, glowing amber lamplight. "
        "Scenes feel alive with color — like a Ghibli film frame. "
        "Characters have clearly visible warm faces, natural poses. "
        "NOT dark. NOT muted. NOT washed out. Colorful, warm, emotionally radiant. "
        "Like Spirited Away or Howl's Moving Castle — vivid illustrated art, full of life and feeling."
    ),
    (
        "Beautiful anime illustration art — vibrant and emotionally warm. "
        "Rich color palette: sapphire blue skies, golden wheat fields, bright teal water, "
        "warm sunset gradient of orange and pink, deep green forests, glowing interior lamp light. "
        "Scenes are painterly and alive — color is the mood. "
        "Characters: clear expressive faces, natural warm skin tones, emotionally present. "
        "Style: high-quality anime film concept art — NOT realistic, NOT dark, NOT washed out. "
        "Vivid, lush, illustrated, radiant with color and feeling."
    ),
    (
        "Illustrated art — colorful digital painting style, emotionally resonant. "
        "Rich saturated palette: deep indigo night skies with warm glowing stars, "
        "lush green countryside, golden morning light flooding a scene, "
        "rich teal oceans, warm amber autumn colors, bright soft morning mist. "
        "Every scene vibrant and beautiful — colors tell the emotion. "
        "Characters clearly visible with warm expressive faces. "
        "NOT dark gothic. NOT muted grey. NOT boring. Full of beautiful rich color. "
        "Like a stunning illustrated book cover or high-quality animated film still."
    ),
    (
        "Semi-realistic illustrated art — vivid warm colors, painterly and emotional. "
        "Dominant colors: warm golden light, rich blue-green landscape, bright coral sunrise, "
        "glowing amber interior light, lush emerald greens, soft rose and peach tones. "
        "Scenes feel lush, alive, and emotionally rich. "
        "Every element contributes to a beautiful, colorful, readable image. "
        "Characters: visible, warm, expressive. Style: illustrated graphic novel with Ghibli soul. "
        "NOT muted, NOT dark, NOT creepy. Beautiful, colorful, human, warm."
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

        if success:
            print(f"[images] Panel {i+1}: DALL-E")
            successful_paths.append(output_path)

            # Save to gallery for future reuse (disabled until test approval)
            # _add_to_gallery(output_path, topic, i, "DALL-E")
        else:
            # DALL-E failed — reuse an earlier panel from THIS video
            if successful_paths:
                reuse_src = random.choice(successful_paths)
                shutil.copy2(reuse_src, output_path)
                print(f"[images] Panel {i+1}: reusing earlier panel (DALL-E failed)")
            else:
                raise RuntimeError(f"DALL-E failed for panel {i+1} and no earlier panels to reuse. Cannot proceed.")

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
