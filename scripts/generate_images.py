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
    # Countryside / nature — dramatic skies
    "A lone stone cottage with a glowing amber window in a dark golden field, massive swirling storm clouds above, red poppies in the foreground",
    "A woman in a red coat walking alone on a winding country road at dusk, cypress trees on both sides, stormy violet sky above",
    "A small farmhouse on a hill, warm light in one window, dark dramatic clouds rolling in, golden wheat in the foreground",
    "A solitary figure with a red umbrella crossing a flooded stone bridge in heavy rain, dark medieval castle behind them, golden reflections in water",
    "A man standing on a rocky cliff overlooking a misty valley, massive mountain peaks in fog, single tree beside him bending in wind",
    # Architecture — Mediterranean / European / Eastern
    "A cobblestone Mediterranean courtyard at night, two figures near an arched doorway with warm amber lamp light, palm fronds and rain",
    "A Japanese pagoda nestled in misty mountains at dawn, ancient trees surrounding it, soft mist rising from forest below",
    "A narrow European village alley at night, rain-slicked cobblestones reflecting amber street lamps, one figure disappearing around a corner",
    "An ancient stone archway with warm golden light pouring through, two cloaked figures meeting beneath it in the rain",
    "A tall Mediterranean villa at night, one lit window high up, dark palm trees, rain falling diagonally across the scene",
    # Human figures — emotional close-ups
    "A woman silhouette holding a large red umbrella against a dark grey rainy sky, her figure in rich burgundy coat, dramatic and solitary",
    "A samurai figure from behind standing on a misty mountain peak, traditional robes flowing, vast foggy valley below",
    "An old man sitting alone on a bench in a winter park, bare trees, cold blue light, a letter in his hands",
    "A young woman at an old wooden desk by a rain-streaked window, single candle lit, writing a letter, storm outside",
    "Two silhouettes on a bridge over a river at night, not touching, city lights reflected in the water below",
    # Dramatic nature — symbolic
    "A lone lighthouse on dark jagged rocks, massive waves crashing, single warm beam sweeping through storm clouds",
    "A figure in a small rowboat on a perfectly still dark lake, surrounded by misty mountains, predawn grey light",
    "A cherry blossom tree in full bloom at night, one person sitting beneath it alone, pale petals falling like snow",
    "An ancient stone staircase climbing through dense forest, golden light filtering down through dark canopy, figure ascending alone",
    "Autumn forest path, carpet of red and gold leaves, a figure walking away into the distance, mist between the trees",
    # Interior — intimate and warm
    "An old wooden library interior at night, warm amber lamp on a reading table, single figure surrounded by tall shelves of books",
    "A small café window at night, rain outside, one person inside holding a cup looking out, warm light inside vs dark street",
    "A vintage train compartment, one passenger looking out the rain-streaked window at passing dark countryside at night",
    "An attic room with a round window showing a stormy sky, old trunk open, letters scattered, warm single lamp",
    "A kitchen in an old stone house, fire in the hearth, elderly hands cradling a teacup, rain on the window",
]

# Art style — matches Typewriters Voice: woodcut/linocut illustration with warm amber + bold red accent
_STYLE_VARIANTS = [
    (
        "Dark cinematic woodcut illustration style. Deep dark background (near-black forest green or charcoal). "
        "Warm golden-amber foreground lighting — glowing fields, lamp light, fire. "
        "Bold red accent color on one element (umbrella, coat, flowers, roof). "
        "Heavy cross-hatching texture, bold ink lines, dramatic light contrast. "
        "Style: Tim Burton meets classic linocut print meets vintage storybook illustration. "
        "Rich textured look, NOT photorealistic, NOT anime."
    ),
    (
        "Painterly dark illustration in the style of a vintage graphic novel. "
        "Deep navy and forest green backgrounds, single warm amber light source. "
        "One vivid accent color — deep crimson or burnt orange on a focal element. "
        "Lush textured brush strokes, heavily stylized, cinematic composition. "
        "Atmospheric rain or mist adding drama. NOT photorealistic."
    ),
    (
        "Dramatic storybook illustration, dark fantasy atmosphere. "
        "Dark moody backgrounds with rich deep greens, blacks, indigos. "
        "Warm candlelight or lamp glow as the hero light — amber and gold. "
        "A single bold accent: red poppies, a red door, crimson clothing. "
        "Detailed texture: hatching, stippling, layered ink washes. Cinematic and emotional."
    ),
    (
        "High-contrast painterly illustration in the style of classic Eastern ink painting meets Western graphic novel. "
        "Misty grey-blue mountains or landscape in background, dark foreground. "
        "Small human figure dwarfed by vast landscape — epic scale, emotional weight. "
        "Muted palette with ONE warm accent: amber lantern, red garment, golden light. "
        "Textured, painterly, NOT anime, NOT photo."
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
                    "quality": "standard",
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
