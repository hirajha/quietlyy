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


def generate_image_prompt(topic, visual_keywords, panel_num):
    """Create Whisprs-style prompts — animated/illustrated, people and emotions."""
    keywords_str = ", ".join(visual_keywords)

    scene_map = {
        0: (
            f"A warm scene of a family gathered together in a cozy room, "
            f"golden lamplight, holding hands, laughing softly, "
            f"related to {topic}, {keywords_str}, feeling of togetherness and love"
        ),
        1: (
            f"Two people sitting close together, sharing a meaningful moment, "
            f"warm amber light, eye contact, genuine connection, "
            f"theme of {topic}, {keywords_str}, intimate and personal"
        ),
        2: (
            f"A person standing at a crossroads or doorway, looking back, "
            f"half warm light half cold shadow, transition from old to new, "
            f"bittersweet moment, related to {topic}, twilight atmosphere"
        ),
        3: (
            f"A person sitting alone in a modern room, cold blue light from phone screen, "
            f"empty chairs around them, isolation and disconnection, "
            f"modern loneliness, contrast with {topic} era, night time"
        ),
        4: (
            f"A solitary dark silhouette figure seen from behind, standing alone, "
            f"vast empty landscape at dusk, sense of loss and reflection, "
            f"melancholic atmosphere, thinking about {topic} and what was lost"
        ),
    }

    scene = scene_map.get(panel_num, scene_map[2])

    return (
        f"Digital anime illustration for a VERTICAL phone screen (9:16 portrait). "
        f"All people must be standing or sitting UPRIGHT — heads at the top, feet at the bottom. "
        f"The horizon line must be HORIZONTAL. The scene must look correct when viewed on a phone held upright. "
        f"Hand-painted anime style, NOT a photograph. "
        f"{scene}. "
        f"Style: illustrated anime art, Makoto Shinkai lighting, Studio Ghibli warmth, "
        f"soft painterly brush strokes, glowing atmospheric lighting, dreamy color palette, "
        f"dark moody cinematic tones, emotional depth, bokeh light particles. "
        f"Must look like a digital painting NOT a real photo. "
        f"No text, no watermarks, no words, no letters, no UI elements. "
        f"No borders, no frames — image fills the entire canvas edge to edge."
    )


def _is_portrait(image_path):
    """Check if image is portrait orientation (taller than wide)."""
    from PIL import Image
    try:
        img = Image.open(image_path)
        w, h = img.size
        print(f"[images] Image dimensions: {w}x{h}")
        return h >= w
    except Exception:
        return True  # Can't check, assume OK


def generate_with_dalle(prompt, output_path):
    """Generate image using OpenAI DALL-E 3 API. Retries up to 3 times."""
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
                    "size": "1024x1792",  # Portrait 9:16 for vertical video
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

            # Reject landscape images — retry
            if not _is_portrait(output_path):
                print(f"[images] DALL-E returned landscape, retrying...")
                os.remove(output_path)
                time.sleep(3)
                continue

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
