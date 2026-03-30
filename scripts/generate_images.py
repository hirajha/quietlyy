"""
Quietlyy — Image Generator
3-layer fallback:
  Layer 1: Pollinations.ai FLUX (free, no key) — PRIMARY
  Layer 2: Pixabay / Pexels stock photos (free)
  NO gradient fallback — if all fail, pipeline fails.

Image style: Whisprs-inspired — focus on PEOPLE, families, human
connection vs disconnection. The topic (telephone, radio etc) is just
the script's theme, visuals show human emotions.
"""

import os
import json
import random
import time
import requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def generate_image_prompt(topic, visual_keywords, panel_num):
    """Create Whisprs-style prompts focused on PEOPLE and emotions, not objects."""
    keywords_str = ", ".join(visual_keywords)

    # Each panel tells the human story, not the object story
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
        f"Anime illustration, cinematic vertical portrait composition. "
        f"{scene}. "
        f"Style: detailed anime art like Whisprs Facebook page, atmospheric lighting, "
        f"dark moody tones, Studio Ghibli inspired, painterly textures, emotional depth, "
        f"no text, no watermarks, no words, no letters."
    )


# ── Layer 1: Pollinations.ai FLUX (free, no API key needed) — PRIMARY ──
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


# ── Layer 2a: Pixabay (free, 100 req/min) — people-focused searches ──
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
                "key": key,
                "q": query,
                "image_type": "photo",
                "orientation": "vertical",
                "per_page": 15,
                "safesearch": "true",
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


# ── Layer 2b: Pexels (free, 200 req/hour) — people-focused searches ──
def fetch_from_pexels(visual_keywords, output_path, panel_num):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return False

    # Search for PEOPLE scenes, not objects
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
    """Generate people-focused panel images. Pollinations primary, Pixabay/Pexels fallback.
    Raises error if any panel fails (no gradient fallback)."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    paths = []

    for i in range(num_panels):
        output_path = os.path.join(OUTPUT_DIR, f"panel_{i}.png")
        prompt = generate_image_prompt(topic, visual_keywords, i)

        print(f"[images] Panel {i+1}/{num_panels}: generating...")

        layers = [
            ("Pollinations", lambda p=prompt, o=output_path: generate_with_pollinations(p, o)),
            ("Pixabay", lambda kw=visual_keywords, o=output_path, idx=i: fetch_from_pixabay(kw, o, idx)),
            ("Pexels", lambda kw=visual_keywords, o=output_path, idx=i: fetch_from_pexels(kw, o, idx)),
        ]

        success = False
        for name, fn in layers:
            try:
                if fn():
                    print(f"[images] Panel {i+1}: {name}")
                    success = True
                    break
            except Exception as e:
                print(f"[images] Panel {i+1} {name} error: {e}")

        if not success:
            raise RuntimeError(f"All image sources failed for panel {i+1}. Cannot produce quality video.")

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
