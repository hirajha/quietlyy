"""
Quietlyy — Image Generator
4-layer fallback:
  Layer 1: Gemini 2.5 Flash Image (via google-genai SDK)
  Layer 2: Pollinations.ai FLUX (free, no key)
  Layer 3: Pixabay / Pexels stock photos (free)
  NO gradient fallback — if all fail, pipeline fails.

Generated images are saved to assets/gallery/ for reuse.
Gallery is capped at 500 images — oldest are deleted.
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

    # Generate unique filename
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


def generate_image_prompt(topic, visual_keywords, panel_num):
    """Create Whisprs-style prompts focused on PEOPLE and emotions."""
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
        f"Digital anime illustration, hand-painted style, NOT a photograph. "
        f"Cinematic vertical portrait composition. "
        f"{scene}. "
        f"Style: illustrated anime art, Makoto Shinkai lighting, Studio Ghibli warmth, "
        f"soft painterly brush strokes, visible illustration textures, "
        f"glowing atmospheric lighting, dreamy color palette, "
        f"dark moody cinematic tones, emotional depth, bokeh light particles. "
        f"Must look like a digital painting NOT a real photo. "
        f"No text, no watermarks, no words, no letters, no UI elements."
    )


# ── Layer 1: Gemini 2.5 Flash Image (via google-genai SDK) ──
def generate_with_gemini(prompt, output_path):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return False
    try:
        from google import genai
        from google.genai import types
        from PIL import Image

        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                img = Image.open(io.BytesIO(part.inline_data.data))
                img.save(output_path, "PNG")
                return True
        return False
    except Exception as e:
        print(f"[images] Gemini SDK failed: {e}")
    return False


# ── Layer 2: Pollinations.ai FLUX (free, no API key needed) ──
def generate_with_pollinations(prompt, output_path):
    try:
        from urllib.parse import quote
        url = f"https://image.pollinations.ai/prompt/{quote(prompt)}?width=768&height=1344&model=flux&nologo=true"
        resp = requests.get(url, timeout=90)
        if resp.status_code != 200:
            return False
        if len(resp.content) < 5000:
            return False
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"[images] Pollinations failed: {e}")
    return False


# ── Layer 3a: Pixabay (free, 100 req/min) ──
def fetch_from_pixabay(visual_keywords, output_path, panel_num):
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return False

    people_queries = {
        0: "family together love home",
        1: "couple connection intimate",
        2: "person silhouette window thinking",
        3: "lonely person phone dark",
        4: "solitary figure sunset alone",
    }
    query = people_queries.get(panel_num, "person nostalgic alone")

    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": key, "q": query, "image_type": "photo",
                "orientation": "vertical", "per_page": 15, "safesearch": "true",
            },
            timeout=15,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            return False

        photo = random.choice(hits)
        img_url = photo.get("largeImageURL", photo.get("webformatURL"))
        if not img_url:
            return False

        img_resp = requests.get(img_url, timeout=30)
        img_resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(img_resp.content)
        return True
    except Exception as e:
        print(f"[images] Pixabay failed: {e}")
    return False


# ── Layer 3b: Pexels (free, 200 req/hour) ──
def fetch_from_pexels(visual_keywords, output_path, panel_num):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return False

    people_queries = {
        0: "family together warm home love",
        1: "two people connection intimate moment",
        2: "person alone window silhouette thinking",
        3: "lonely person phone dark room night",
        4: "solitary figure dusk landscape alone walking",
    }
    query = people_queries.get(panel_num, "person alone thinking nostalgic")

    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": key},
            params={"query": query, "per_page": 15, "orientation": "portrait"},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            return False

        photo = random.choice(photos)
        img_url = photo["src"]["large2x"]

        img_resp = requests.get(img_url, timeout=30)
        img_resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(img_resp.content)
        return True
    except Exception as e:
        print(f"[images] Pexels failed: {e}")
    return False


def generate_images(topic, visual_keywords, num_panels=5):
    """Generate people-focused panel images. Saves to gallery for reuse.
    Raises error if any panel fails."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    paths = []

    for i in range(num_panels):
        output_path = os.path.join(OUTPUT_DIR, f"panel_{i}.png")
        prompt = generate_image_prompt(topic, visual_keywords, i)

        print(f"[images] Panel {i+1}/{num_panels}: generating...")

        layers = [
            ("Gemini", lambda p=prompt, o=output_path: generate_with_gemini(p, o)),
            ("Pollinations", lambda p=prompt, o=output_path: generate_with_pollinations(p, o)),
            ("Pixabay", lambda kw=visual_keywords, o=output_path, idx=i: fetch_from_pixabay(kw, o, idx)),
            ("Pexels", lambda kw=visual_keywords, o=output_path, idx=i: fetch_from_pexels(kw, o, idx)),
        ]

        success = False
        source = None
        for name, fn in layers:
            try:
                if fn():
                    print(f"[images] Panel {i+1}: {name}")
                    success = True
                    source = name
                    break
            except Exception as e:
                print(f"[images] Panel {i+1} {name} error: {e}")

        if not success:
            raise RuntimeError(f"All image sources failed for panel {i+1}. Cannot produce quality video.")

        # Save to gallery for future reuse
        _add_to_gallery(output_path, topic, i, source)

        paths.append(output_path)

        if i < num_panels - 1:
            time.sleep(1)

    print(f"[images] Generated {len(paths)} panels")
    return paths


if __name__ == "__main__":
    paths = generate_images(
        "Telephone",
        ["old telephone", "rotary phone", "vintage phone booth", "warm lamp light"],
    )
    print(json.dumps(paths, indent=2))
