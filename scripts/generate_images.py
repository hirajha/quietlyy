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


# Scene pool — cinematic, atmospheric, varied settings
# Matches the Typewriters Voice / Whisprs aesthetic:
# dark environments, warm accent light, solitary or paired figures, epic or intimate scale
_SCENE_POOL = [
    # Epic landscapes — figure small vs vast world
    "A lone figure in a red coat standing at the edge of a cliff, vast misty grey mountains stretching endlessly behind them, cold pale sky",
    "A samurai seen from behind on a rocky peak, traditional flowing robes, enormous misty mountain range disappearing into fog below",
    "A woman in a deep crimson dress standing on ancient stone steps, a massive Japanese temple gate above her, grey mist all around",
    "A small human figure walking a narrow path through towering misty pine forest, shafts of pale light cutting through the fog",
    "A solitary figure on a wooden pier extending into a perfectly still lake, surrounded by misty mountains, predawn silence",
    # Rain and weather — cinematic
    "A woman holding a vivid red umbrella, silhouetted against a dark grey rainy sky, wet cobblestones reflecting her figure below",
    "A person standing in heavy rain on an empty city bridge at night, neon lights blurred in the wet pavement, alone",
    "Two people under one umbrella on a rain-drenched street at night, not touching, looking in different directions",
    "A lone figure walking away down a long alley in the rain, puddles reflecting warm amber streetlight, mist in the distance",
    "A woman in red walking through rain toward distant city lights, wet street, dark sky, one umbrella, one direction",
    # Japanese / Asian aesthetic
    "A Japanese pagoda rising from thick morning mist, ancient pine trees surrounding it, cool blue-grey atmospheric haze",
    "A red torii gate standing in shallow misty water, pale grey sky, single figure approaching from distance",
    "Cherry blossoms falling at night, one person sitting alone beneath the tree, soft pink petals against dark sky",
    "A narrow Japanese alley at night, paper lanterns casting warm amber glow, wet stone path, one figure passing",
    "Ancient stone steps ascending through dense bamboo forest, dappled pale light, a lone figure climbing upward",
    # Emotional human moments
    "A person sitting alone in an empty train at night, head resting on the window, dark countryside passing, reflection visible in glass",
    "A woman at a rain-streaked window in a dark room, one candle, holding a letter, city lights blurred outside",
    "An old man on a park bench in winter, bare trees, cold blue light, a single red scarf around his neck",
    "Two people sitting on opposite ends of a park bench at dusk, mist between them, neither looking at the other",
    "A figure standing in a doorway looking out at falling snow, warm light behind them, cold white world ahead",
    # Epic nature — symbolic scale
    "A small rowing boat on a vast dark lake, perfect reflection of stormy sky above, mountains in the distance",
    "A lone tree on a hilltop in autumn, figure sitting beneath it, red and gold leaves swirling, horizon wide and pale",
    "Ancient stone bridge over a misty gorge, single figure crossing, fog filling the valley below, cold morning light",
    "A lighthouse on dark rocks in a storm, massive waves, one warm beam of light cutting through grey-black clouds",
    "A field of tall grass at dusk, figure walking through it away from us, golden light at the horizon, purple sky above",
]

# Art style — matches Typewriters Voice: woodcut/linocut illustration with warm amber + bold red accent
_STYLE_VARIANTS = [
    (
        "Ultra-realistic cinematic digital art, Makoto Shinkai / Solo Leveling style. "
        "Photorealistic quality with painterly details. "
        "Atmospheric mist, volumetric light rays, epic scale. "
        "Cool blue-grey misty tones for backgrounds (mountains, fog, sky). "
        "ONE vivid accent color on the focal subject: deep red coat, crimson umbrella, or amber lamp glow. "
        "Hyper-detailed textures: fabric folds, stone surfaces, water reflections. "
        "Cinematic depth of field, soft bokeh in background. NOT cartoon, NOT woodcut."
    ),
    (
        "Modern cinematic concept art, semi-realistic digital painting. "
        "Dramatic atmospheric perspective — vast misty landscape with small human figure. "
        "Cool desaturated background (grey mist, pale blue sky, dark storm clouds). "
        "Warm golden or deep red accent on one element — a lantern, a coat, a gate. "
        "Highly detailed, photorealistic quality, moody and cinematic. "
        "Style: movie poster illustration meets fine art photography. NOT anime cartoon."
    ),
    (
        "Cinematic digital painting, Korean webtoon realism style. "
        "Dark dramatic sky — deep navy or slate grey with subtle light breaking through. "
        "Lush detailed foreground: wet cobblestones, cherry blossoms, ancient stone steps. "
        "Figure dressed in bold color (red, deep burgundy) against the muted scene. "
        "Photorealistic textures, cinematic lighting, dramatic emotional atmosphere. "
        "High detail, sharp focus on subject with soft background. NOT illustration."
    ),
    (
        "Atmospheric cinematic digital art, painterly realism. "
        "Japanese aesthetic — misty mountain peaks, stone temples, bamboo forest at dusk. "
        "Cool grey-blue atmospheric haze, soft diffused light. "
        "One element in vivid contrast: red torii gate, crimson kimono, amber lantern. "
        "Ultra-detailed, cinematic quality, emotional and still. "
        "Style: between a photograph and a painting. NOT cartoon, NOT flat illustration."
    ),
]

# Module-level: pick a style once per import (once per pipeline run)
_CHOSEN_STYLE = random.choice(_STYLE_VARIANTS)
# Shuffle scenes once per run for fresh panel order every video
_SHUFFLED_SCENES = random.sample(_SCENE_POOL, len(_SCENE_POOL))


def generate_image_prompt(topic, visual_keywords, panel_num):
    """Create varied scene prompts — each run gets a different scene sequence and art style."""
    keywords_str = ", ".join(visual_keywords)

    # Pick scene from pre-shuffled pool (wraps if more panels than scenes)
    scene = _SHUFFLED_SCENES[panel_num % len(_SHUFFLED_SCENES)]

    return (
        f"{_CHOSEN_STYLE} "
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
                    "size": "1024x1024",  # Square — no sideways composition
                    "quality": "hd",      # HD = sharper, more detailed, more vibrant
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


def generate_images(topic, visual_keywords, num_panels=5):
    """Generate panel images using DALL-E ONLY.
    - Max 5 panels per video
    - DALL-E is the only generator — no stock photos or gradients
    - If DALL-E fails for a panel, reuse an earlier successful panel from same video
    - After 25 gallery images: reuse 2-3 panels (never panel 0)
    - Saves new images to gallery (capped at 500)
    At least 1 image must succeed or pipeline fails."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    num_panels = min(num_panels, 5)  # Hard cap at 5
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
        prompt = generate_image_prompt(topic, visual_keywords, i)
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
