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


# Scene pool — character-focused, emotional, Whisprs/illustrated aesthetic
# Priority: close-up faces > two people > small figure in landscape
# Warm earthy palette: olive, dusty teal, warm brown, soft burgundy — NOT grey/cold
_SCENE_POOL = [
    # ── Close-up character portraits (highest engagement on thumbnail) ──────
    "Close-up portrait of a young woman, eyes glistening with unshed tears, looking slightly off-frame, "
    "soft warm side-light, olive and dusty teal tones, loose hair, deeply emotional expression",

    "Close-up of a young man with tired, longing eyes staring into the distance, warm amber light on one side, "
    "deep shadow on the other, contemplative and melancholy, muted brown and teal palette",

    "A woman seen from the side, profile close-up, one hand near her jaw, "
    "soft golden backlight, eyes closed as if remembering, warm earthy tones",

    "A young woman lying on her back on grass, looking up at a pale sky, "
    "loose hair spread out, soft dappled light on her face, peaceful but sad, warm olive-green palette",

    "Close-up of two people almost touching foreheads, eyes closed, not quite together, "
    "warm amber light between them, blurred background, emotional and intimate",

    "A woman's face half in shadow, half lit by warm candlelight, "
    "holding something small in her hands just off-frame, deep earthy tones, quiet grief",

    "A young man with his head down, one hand over his face, soft warm light from a window, "
    "muted browns and dusty blues, emotional weight in the posture",

    "Side profile of a woman on a train, head resting on the window, "
    "blurred landscape outside, warm interior light on her face, melancholy stillness",

    # ── Two people — connection, distance, emotion ───────────────────────────
    "Two people sitting close but facing away from each other on a bench at dusk, "
    "warm golden-hour light behind them, long shadows, earthy browns and dusty oranges",

    "A couple standing in a doorway, one staying, one leaving, warm light inside, "
    "cool blue outside, the contrast sharp and emotional, illustrated realism style",

    "Two people under one umbrella in rain, not touching, looking in different directions, "
    "warm amber streetlight reflecting in puddles, muted teal and brown tones",

    "A woman reaching out a hand toward someone just out of frame, "
    "warm olive-toned background, soft focus, yearning in her expression",

    # ── Figures in evocative settings ────────────────────────────────────────
    "A lone woman in a rust-red coat walking through golden autumn leaves, "
    "figure small against vast warm-toned trees, earthy amber and deep brown palette",

    "A person standing at the edge of a pier at dusk, back to us, "
    "warm orange-gold horizon, dark water below, one small figure against the vast sky",

    "A figure sitting beneath a large tree in a golden field, knees drawn up, "
    "warm summer light, olive greens and amber yellows, a sense of quiet solitude",

    "Two small silhouettes on a hilltop at sunset, close but silent, "
    "blazing orange and burgundy sky behind them, long grass in the foreground",

    "A woman in a cream dress standing in a corridor of tall golden-lit windows, "
    "light flooding in warm amber, her figure a soft silhouette, elegant and lonely",

    "A young man sitting on stone steps outside an old building at night, "
    "a warm streetlamp overhead, muted teal shadows, earthy olive tones, quiet streets",

    # ── Symbolic / atmospheric ────────────────────────────────────────────────
    "Cherry blossom petals falling around a lone figure on an empty path, "
    "warm dusty pink and olive green, soft golden light, illustrated watercolor feel",

    "An empty park bench in autumn with scattered red and orange leaves, "
    "warm golden hour light, suggestion of recent company now gone, earthy palette",

    "A lit window in a dark building on a rainy night, one figure visible inside, "
    "warm amber glow against deep teal-blue darkness, rain streaks on glass",

    "A woman's silhouette against a large window at dawn, city waking behind her, "
    "warm peachy morning light, her form dark and still, contemplative",

    "A lone small boat on still water at golden hour, "
    "blazing amber and dusty rose sky reflected perfectly in the surface, "
    "one figure sitting motionless, deeply peaceful and solitary",
]

# Art style — matches Whisprs: graphic novel illustration with warm earthy palette
# Key: illustrated style NOT photorealistic, character-focused, warm muted tones
_STYLE_VARIANTS = [
    (
        "Semi-realistic graphic novel illustration style, like Loish or Ilya Kuvshinov. "
        "Warm earthy color palette: olive green, dusty teal, warm brown, muted burgundy, soft amber. "
        "Detailed pencil-and-ink linework with soft painterly color wash. "
        "Emotional character portrait with expressive face as the focal point. "
        "Soft atmospheric background, warm side-lighting. "
        "NOT photorealistic. NOT cold grey. Warm, illustrated, deeply human."
    ),
    (
        "Webtoon graphic novel art style, detailed semi-realistic illustration. "
        "Warm muted palette: earthy olive, dusty rose, warm teal, soft amber and brown tones. "
        "Close-up emotional portrait — expressive eyes, soft linework, painterly texture. "
        "Warm window light or golden hour glow on the subject. "
        "Style similar to Ross Draws or Korean manhwa illustration. "
        "NOT photorealistic, NOT cold tones. Warm human emotional illustration."
    ),
    (
        "Cinematic illustration, graphic novel realism — like a high-quality manhwa panel. "
        "Earthy, warm color story: muted olive greens, warm amber, dusty blue-grey, soft burgundy. "
        "Character-focused composition — face or upper body portrait, deeply emotional. "
        "Soft detailed linework with subtle watercolor-wash background. "
        "Warm backlighting or candle-light glow. "
        "NOT anime cartoon. NOT photorealistic. Illustrated, warm, intimate."
    ),
    (
        "Painterly graphic novel illustration, warm emotional portrait style. "
        "Muted jewel tones: deep teal, warm amber, olive, dusty mauve, earthy brown. "
        "Semi-realistic face close-up with detailed eyes and soft emotional expression. "
        "Background is softly painted and atmospheric — blurred warm light or gentle nature. "
        "Style: between a painted portrait and a graphic novel panel. "
        "Warm, illustrated, NOT cold, NOT grey. Human and intimate."
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
