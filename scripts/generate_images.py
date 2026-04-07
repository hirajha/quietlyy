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
    """Decide which panels get reused gallery images.
    Rules: never panel 0, max MAX_REUSE_PER_VIDEO panels, random selection."""
    index = _load_gallery_index()
    if len(index) < REUSE_THRESHOLD:
        return {}  # Not enough images yet

    # Eligible panels: 1 through num_panels-1 (never 0 = start of video)
    eligible = list(range(1, num_panels))
    num_reuse = min(random.randint(2, MAX_REUSE_PER_VIDEO), len(eligible))
    reuse_panels = random.sample(eligible, num_reuse)

    # Pick random gallery images (different ones)
    chosen = random.sample(index, min(num_reuse, len(index)))
    result = {}
    for i, panel_idx in enumerate(reuse_panels):
        entry = chosen[i]
        gallery_path = os.path.join(GALLERY_DIR, entry["file"])
        if os.path.exists(gallery_path):
            result[panel_idx] = gallery_path
            print(f"[images] Panel {panel_idx+1}: reusing gallery image {entry['file']} (topic: {entry['topic']})")

    return result


# Scene pool — MIXED types for variety across panels
# Blend of: face closeups, wide landscapes, cityscapes, interior scenes, two-person scenes
# Dark cinematic graphic-novel illustration style throughout

_SCENE_POOL_CLOSEUP = [
    # Face closeups — cool-toned, emotional, rich color
    "Close-up portrait of a young woman, eyes glistening with unshed tears, "
    "soft cool moonlight on one side, teal-blue shadows, loose hair, deeply emotional expression, "
    "cool blue and teal color palette, detailed illustrated style",

    "Close-up of a young man with tired longing eyes staring into distance, "
    "soft blue-silver light on his face, cool teal shadows, "
    "contemplative and melancholy, deep cerulean and teal palette",

    "A woman seen from the side, profile close-up, eyes closed as if remembering, "
    "cool silver moonlight as backlight, teal-blue atmospheric haze, "
    "emotionally detailed face, cool color tones",

    "A woman's face lit by the cool blue glow of a window at night, "
    "one hand near her jaw, deep teal shadows, soft silver light, "
    "quiet sadness, detailed illustration, cool blue palette",

    "Side profile of a woman on a train, head resting on the window, "
    "blurred teal-blue landscape outside, cool blue interior light on her face, "
    "melancholy stillness, cool color palette",

    "Close-up of two people almost touching foreheads, eyes closed, not quite together, "
    "soft cool moonlight between them, teal-blue background, emotional and intimate, "
    "cool silver-blue tones, deeply beautiful",

    "A young man standing in the rain, face tilted slightly up, eyes closed, "
    "teal-blue rainy light all around him, cool wet reflections, "
    "emotional and atmospheric, rich cool blue-teal palette",
]

_SCENE_POOL_WIDE = [
    # Wide landscapes & cityscapes — colorful, cool-toned, atmospheric
    "Sweeping misty mountain valley at dawn, ancient pine forests bathed in blue-grey mist, "
    "a single small figure on a winding path below, dramatic scale, "
    "rich cerulean blue sky, lush green forests, silver fog — breathtaking and vast",

    "A moonlit coastline with silver waves crashing on rocks, "
    "deep midnight blue sky full of stars, silver light on the water, "
    "tiny figure standing at the edge looking out, cool blue-silver palette, cinematic and epic",

    "Rolling green hills under a dramatic blue sky with building storm clouds, "
    "shafts of golden light breaking through, small figure walking a country path, "
    "lush green grass, deep teal-blue sky — beautiful and emotional",

    "A glowing city at night seen from a hilltop, teal and blue city lights "
    "reflecting off wet streets below, cool blue-purple sky, "
    "one small figure watching from above, cinematic and atmospheric",

    "Ancient stone bridge over a misty teal-green river at twilight, "
    "silver birch trees reflected in the water, lone figure crossing, "
    "deep cerulean sky, cool blue-green palette, hauntingly beautiful",

    "Vast autumn forest in full color — deep amber, burgundy, emerald green — "
    "seen from above, a tiny figure on a path far below, "
    "dramatic overhead perspective, rich colorful palette, epic scale",

    "A lone figure in a red coat on a misty mountain road, "
    "tall pine trees either side, cool blue-grey mist ahead, "
    "deep forest greens and cool teal tones, atmospheric and cinematic",
]

_SCENE_POOL_INTERIOR = [
    # Interior scenes — warm amber lamp vs cool blue outside (highest engagement: 156 views)
    "A person sitting alone at a wooden desk by tall arched windows at night, "
    "writing in a journal by warm amber lamplight, "
    "deep cool blue moonlight flooding through the windows, rain on the glass outside, "
    "warm amber inside vs cool midnight blue outside — beautiful contrast, atmospheric",

    "A woman reading a letter by a single warm lamp near a large window at night, "
    "cool blue moonlight and city glow outside the window, "
    "warm amber pool around her, teal-blue shadows in the room, "
    "emotional and cinematic interior — warm vs cool color contrast",

    "A figure standing at a rain-streaked window, back to us, "
    "looking out at a glowing teal-blue rainy city at night, "
    "warm soft lamp behind them, cool blue street reflections outside, "
    "beautiful color contrast — the outside world glowing cool blue-teal",

    "An old library with towering bookshelves, moonlight streaming in through tall windows, "
    "cool silver-blue light mixing with warm amber lamp on a reading table, "
    "a small figure at the table below, sense of vast solitude, "
    "rich colors: deep wood browns, cool blue light, warm gold lamp",

    "A woman sitting by a window watching rain fall on a teal-lit street below, "
    "her face in warm amber lamp light, outside is cool blue and glowing, "
    "books and tea on the windowsill, deeply atmospheric and emotional",

    "A young man at a wooden desk by a floor-to-ceiling window at dusk, "
    "the sky outside is deep cerulean blue fading to teal, "
    "his desk lamp casting warm amber, papers around him, "
    "cinematic and atmospheric — warm amber meets cool blue dusk",
]

_SCENE_POOL_TWO_PEOPLE = [
    # Two people — connection and distance
    "Two people under one umbrella in the rain, not touching, looking in different directions, "
    "warm amber streetlight reflecting in puddles, muted teal and brown tones",

    "Two small silhouettes on a hilltop at sunset, close but silent, "
    "blazing orange and burgundy sky behind them, long grass in the foreground",

    "A couple standing in a doorway, one staying, one leaving, warm light inside, "
    "cool blue outside, the contrast sharp and emotional, illustrated realism style",

    "Two people sitting on a rooftop at night, city lights below, "
    "one looking up at stars, one looking down, warm amber tones, cinematic",

    "Two figures walking apart on a rainy cobblestone street at night, "
    "streetlamps glowing amber, dark puddles, distance between them feels immense",
]

# Combined pool — weighted: more wide + interior (they get highest engagement)
_SCENE_POOL = (
    _SCENE_POOL_CLOSEUP * 2 +   # 14 entries
    _SCENE_POOL_WIDE * 2 +       # 14 entries
    _SCENE_POOL_INTERIOR * 3 +   # 18 entries (highest weight — 156 views)
    _SCENE_POOL_TWO_PEOPLE * 1   # 5 entries
)

# Art style — matches Whisprs: graphic novel illustration with warm earthy palette
# Key: illustrated style NOT photorealistic, character-focused, warm muted tones
# Dark romantic style — matches Whispers of Heart: B&W anime couple art, moody, high contrast
_LOVE_STYLE_VARIANTS = [
    (
        "Dark romantic anime illustration style, black and white with soft grey tones. "
        "Intimate couple scene — close faces, gentle touch, tender moment. "
        "High contrast: deep blacks, soft white highlights, cinematic mood. "
        "Style similar to romantic manhwa or webtoon — detailed linework, emotional expressions. "
        "Dark background, subjects softly lit. NOT colorful. Moody, intimate, beautifully dark."
    ),
    (
        "Romantic illustrated art, dark and cinematic. Monochrome palette — charcoal, silver, soft white. "
        "Two people in an intimate moment — forehead to forehead, holding hands, close together. "
        "Detailed semi-realistic illustration, soft linework, deeply emotional. "
        "Dark atmospheric background with subtle light source (moon, lamp, window). "
        "Style: beautiful dark romance illustration. NOT colorful. Moody and tender."
    ),
    (
        "Black and white romantic illustration, manga-inspired emotional art. "
        "Close-up of a couple in a tender quiet moment — not dramatic, just present with each other. "
        "Soft detailed facial expressions, gentle touch or gaze. "
        "Deep dark background, subjects illuminated by soft diffuse light. "
        "High contrast, cinematic composition. Style: romantic webtoon meets fine art illustration."
    ),
]

_STYLE_VARIANTS = [
    (
        "Cinematic graphic novel illustration — rich, colorful, and emotionally atmospheric. "
        "Color palette: deep cerulean blue, teal, forest green, soft purple, moonlit silver — cool-toned but vibrant. "
        "Scenes feel alive with color: lush night skies, glowing city lights, moonlit water, misty forests. "
        "Characters have detailed emotional expressions. Semi-realistic illustration, painterly style. "
        "Think: Studio Ghibli meets graphic novel — beautiful, colorful, atmospheric. NOT dark grey. NOT near-black. "
        "Has real color throughout. Cinematic but visually stunning and cool-toned."
    ),
    (
        "Illustrated emotional art — cool-toned cinematic palette, rich and colorful. "
        "Dominant colors: deep teal, midnight blue, moonlit silver, forest green, soft lavender. "
        "Scenes: moonlit landscapes, glowing city at night, misty mountains, interior with warm lamp vs cool blue outside. "
        "Graphic novel illustration style — detailed linework, rich color fills, dramatic lighting. "
        "Mountains and fields: lush green or misty blue-green, NOT grey. "
        "Night scenes: deep blue sky with bright moon and stars, NOT black. "
        "Colorful, beautiful, atmospheric. Cool tones. Emotionally stirring."
    ),
    (
        "Painterly cinematic illustration — atmospheric and colorful. "
        "Cool color palette: cerulean blue, teal-green, misty grey-blue, soft gold moonlight, silver fog. "
        "Landscapes feel ALIVE: verdant rolling hills under dramatic blue sky, "
        "misty blue mountains with golden sunset, moonlit valleys with silver mist. "
        "Interior scenes: warm amber lamp glow against cool blue window light. "
        "Characters detailed and emotional. Semi-realistic illustrated style. "
        "NOT dark and creepy. Rich colors. Breathtaking. Like a beautiful animated film frame."
    ),
    (
        "Emotional illustrated art, cinematic color grading — cool blue-teal dominant. "
        "Think: moonlit nights with rich deep blue, glowing amber street lamps, "
        "teal-lit rain-soaked streets, misty green forests with filtered light. "
        "Wide scenes: dramatic mountain valleys in misty blue-grey, golden-hour fields with deep sky. "
        "Interior scenes: arched windows with moonlight, warm lamp against cool dark. "
        "Graphic novel art style — detailed, colorful, emotionally immersive. "
        "Colors should feel COOL and BEAUTIFUL not warm/orange/dark. Teal, blue, green, silver."
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
