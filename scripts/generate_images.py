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


# Large pool of diverse scene templates — randomly shuffled each video run
# so no two videos share the same visual sequence
_SCENE_POOL = [
    # Solo introspective — indoors
    "A person sitting alone at a kitchen table late at night, a single cup of tea steaming, dim overhead light, staring at nothing",
    "Someone lying on their bed staring at the ceiling in a dark room, city glow through the curtains, phone face-down on the mattress",
    "A person leaning against a closed door, sliding down slowly, eyes closed, emotional exhaustion",
    "A figure silhouetted at a large window, looking out at the rain, soft lamp glow behind them, reflections in the glass",
    "Someone sitting on the floor of an empty apartment, back against the wall, knees pulled up, surrounded by moving boxes",
    "A person sitting at a desk in lamplight, holding an old photograph, eyes distant and soft",
    # Solo introspective — outdoors
    "A person standing alone on a rooftop at night, city lights stretching to the horizon, wind in their hair",
    "A solitary figure on a nearly empty train, head against the window, watching dark fields pass outside",
    "Someone sitting at the end of a pier, feet dangling over dark still water, stars reflected below them",
    "A person walking alone down a long empty street at dusk, long shadow stretching behind, mist at ground level",
    "A figure standing at a crossroads under a single streetlamp, coat collar up, rain just started",
    "Someone on a fire escape, one knee up, looking at the sky between buildings at night",
    "A person sitting under a bare tree in a park at twilight, leaves scattered around, empty benches nearby",
    "A figure seen from behind standing at a cliff edge, vast ocean below, clouds heavy and low",
    # Two-person / relational
    "Two people on a bench under a streetlight at night, not touching, looking in different directions",
    "Two silhouettes walking apart on a rainy street, umbrellas not overlapping",
    "An empty bench with two coffee cups side by side, steam rising, nobody sitting there",
    "A person waiting under an awning in the rain, checking their watch, no one coming",
    "Two people on opposite sides of a glass door, one inside, one outside, not opening it",
    "A child and an elderly person sitting on porch steps in the fading light, not speaking, just present",
    # Environmental / symbolic
    "An empty swing set moving gently in the wind at night, playground deserted, soft moonlight",
    "A deserted train platform at dusk, single figure far in the distance, tracks vanishing to horizon",
    "An old telephone booth on a foggy street corner, light on inside, no one in it",
    "A narrow alley at night, warm light from a window high above, a lone cat on a windowsill",
    "A library at closing time, last person still reading at a table, librarian dimming lights around them",
]

# Art style variants — randomly picked per video to avoid every video looking identical
_STYLE_VARIANTS = [
    (
        "Digital anime illustration, Makoto Shinkai lighting style. "
        "Dark moody cinematic. Cool blue and purple tones, moonlight and streetlights. "
        "Soft painterly brush strokes, muted desaturated palette, emotional depth, subtle bokeh. "
        "Color palette: dark blues, muted purples, cool grays, soft teal. NOT warm orange or gold."
    ),
    (
        "Studio Ghibli-inspired hand-painted illustration. "
        "Quiet and melancholic atmosphere, soft watercolor textures. "
        "Evening or night setting, cool muted tones — dusty blues, faded greens, pale mauves. "
        "Gentle lighting, no harsh shadows, painterly and emotional."
    ),
    (
        "Retro 80s Japanese anime illustration style. "
        "Slightly grainy film texture, cool neon-tinged night scenes. "
        "Deep blues and teals, subtle magenta highlights from distant signs, "
        "low-key lighting, cinematic widescreen composition adapted to portrait."
    ),
    (
        "Contemporary graphic novel illustration style. "
        "High contrast between deep shadows and single warm light source. "
        "Ink-wash textures, muted palette with one accent color — a faint amber lamp "
        "against dark cool surroundings. Quiet and literary atmosphere."
    ),
]

# Module-level: pick a style once per import (i.e., once per pipeline run)
_CHOSEN_STYLE = random.choice(_STYLE_VARIANTS)
# Shuffle a copy of the scene pool once per run so panel order is always fresh
_SHUFFLED_SCENES = random.sample(_SCENE_POOL, len(_SCENE_POOL))


def generate_image_prompt(topic, visual_keywords, panel_num):
    """Create varied scene prompts — each run gets a different scene sequence and art style."""
    keywords_str = ", ".join(visual_keywords)

    # Pick scene from pre-shuffled pool (wraps around if more panels than scenes)
    scene = _SHUFFLED_SCENES[panel_num % len(_SHUFFLED_SCENES)]

    # Inject topic context into the scene naturally
    scene_with_topic = (
        f"{scene}, evoking themes of {topic} and quiet human longing, "
        f"related to: {keywords_str}"
    )

    return (
        f"{_CHOSEN_STYLE} "
        f"{scene_with_topic}. "
        f"Must look like a digital painting NOT a real photo. "
        f"No text, no watermarks, no words, no UI elements. "
        f"Portrait orientation composition (tall, not wide)."
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
