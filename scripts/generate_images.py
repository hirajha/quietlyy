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
        "Semi-realistic manga illustration style — warm and intimate. "
        "Muted earthy palette: warm terracotta, soft beige, dusty rose, sage green. "
        "Two people in a tender close moment — foreheads touching, gentle embrace, holding hands. "
        "Soft natural lighting, clear visible faces with warm skin tones. "
        "Like a beautiful romance manga panel — NOT dark, NOT gothic. Warm, clear, emotionally tender."
    ),
    (
        "Illustrated anime-style romantic art — soft warm tones, clearly readable. "
        "Palette: warm dusty rose, soft cream, muted terracotta, sage. "
        "Intimate couple scene — close faces, gentle expressions, clear emotions visible. "
        "Soft diffuse light, no harsh shadows, backgrounds soft and muted. "
        "Style: beautiful illustrated romance — like a Studio Ghibli love scene. Warm and tender."
    ),
    (
        "Romantic graphic novel illustration — muted warm palette, clear characters. "
        "Warm earthy tones: dusty rose, terracotta, warm olive, soft cream. "
        "Two people close together, faces clearly visible, tender emotional expressions. "
        "Soft natural lighting from a window or lamp, backgrounds warm and simple. "
        "Like a beautifully drawn romance webtoon — NOT dark or moody. Clear, warm, loving."
    ),
]

_STYLE_VARIANTS = [
    (
        "Semi-realistic illustrated art in the style of Whisprs — muted earthy palette, airy and clear. "
        "Colors: warm olive green, dusty sage, terracotta, warm beige, soft teal-grey. "
        "Scenes feel open and breathable — NOT dark, NOT gothic, NOT creepy. "
        "Characters have clearly visible faces and warm skin tones. "
        "Backgrounds: misty fields, soft skies, cosy interiors — all readable and immediately clear. "
        "Style: Studio Ghibli meets manga illustration — beautiful, muted, emotionally resonant. "
        "NOT photorealistic. NOT dark. NOT saturated neon. Muted, warm, illustrated."
    ),
    (
        "Manga-inspired semi-realistic illustration — Whisprs aesthetic, muted and earthy. "
        "Palette: warm dusty sage, olive green, terracotta rose, warm beige, soft grey-blue sky. "
        "Scenes are clear and instantly readable — you know immediately what you're seeing. "
        "Characters: visible faces, warm natural skin tones, natural relaxed poses. "
        "Lighting: soft diffuse daylight or warm lamp — NOT dramatic, NOT dark. "
        "Style: like a beautifully illustrated graphic novel or anime film concept art. "
        "Relaxed, warm, melancholic but NOT threatening or dark."
    ),
    (
        "Illustrated art style — vintage travel poster meets Studio Ghibli, muted earthy tones. "
        "Colors: dusty teal, muted olive, warm terracotta, pale beige, soft sage — "
        "all desaturated and gentle, like faded beautiful memories. "
        "Wide scenes: misty mountains, airy fields, foggy forests — all light and breathable. "
        "Portrait scenes: clear faces, warm light, simple readable backgrounds. "
        "NOT dark, NOT gothic, NOT neon. Gentle, muted, illustrated, emotionally warm."
    ),
    (
        "Semi-realistic graphic novel illustration — Whisprs style, clean and muted. "
        "Muted earthy palette: warm sage green, dusty terracotta, beige, soft grey-blue. "
        "Every scene immediately clear and readable — no confusion, no darkness. "
        "Landscapes: misty and airy — morning fog, soft skies, gentle light. "
        "Characters: detailed visible faces, warm tones, emotionally expressive. "
        "Like a beautifully drawn illustrated novel — peaceful, melancholic, clearly illustrated. "
        "Absolutely NOT dark gothic or creepy. Clean, illustrated, emotionally resonant."
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
    """Generate image using OpenAI DALL-E 3 API.
    Uses 1024x1024 (square) to avoid sideways composition bug,
    then crops to portrait in PIL."""
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
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1024",
                    "quality": "standard",  # hd costs 2x quota — standard is fine for shorts
                    "response_format": "url",
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            img_url = data["data"][0]["url"]

            # Download the image
            img_resp = requests.get(img_url, timeout=30)
            img_resp.raise_for_status()
            if len(img_resp.content) < 5000:
                continue
            with open(output_path, "wb") as f:
                f.write(img_resp.content)

            # Crop square to portrait (9:16)
            _crop_to_portrait(output_path)
            return True
        except Exception as e:
            print(f"[images] DALL-E attempt {attempt+1} failed: {e}")
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
