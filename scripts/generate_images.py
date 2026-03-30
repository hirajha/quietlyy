"""
Quietlyy — Image Generator
5-layer fallback (no Stability AI):
  Layer 1: Together.ai FLUX.1-schnell (free tier)
  Layer 2: Gemini 2.5 Flash Image (free 500 img/day)
  Layer 3: Pollinations.ai FLUX (free, no key)
  Layer 4: Pixabay / Pexels stock photos (free)
  Layer 5: Gradient fallback (always works, no API)

Image style: Whisprs-inspired — focus on PEOPLE, families, human
connection vs disconnection. The topic (telephone, radio etc) is just
the script's theme, visuals show human emotions.
"""

import os
import json
import base64
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


# ── Layer 1: Together.ai FLUX (free tier, no credit card) ──
def generate_with_together(prompt, output_path):
    key = os.environ.get("TOGETHER_API_KEY")
    if not key:
        return False

    try:
        resp = requests.post(
            "https://api.together.xyz/v1/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "black-forest-labs/FLUX.1-schnell-Free",
                "prompt": prompt,
                "width": 768,
                "height": 1344,
                "steps": 4,
                "n": 1,
                "response_format": "b64_json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        img_b64 = data["data"][0]["b64_json"]
        img_data = base64.b64decode(img_b64)
        with open(output_path, "wb") as f:
            f.write(img_data)
        return True
    except Exception as e:
        print(f"[images] Together.ai failed: {e}")
    return False


# ── Layer 2: Gemini 2.5 Flash Image (free 500 img/day) ──
def generate_with_gemini(prompt, output_path):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return False

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                },
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()

        for part in data["candidates"][0]["content"]["parts"]:
            if "inlineData" in part:
                img_data = base64.b64decode(part["inlineData"]["data"])
                with open(output_path, "wb") as f:
                    f.write(img_data)
                return True
    except Exception as e:
        print(f"[images] Gemini failed: {e}")
    return False


# ── Layer 3: Pollinations.ai FLUX (free, no API key needed) ──
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


# ── Layer 4a: Pixabay (free, 100 req/min) — people-focused searches ──
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


# ── Layer 4b: Pexels (free, 200 req/hour) — people-focused searches ──
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


# ── Layer 3: Gradient fallback (always works, no API) ──
def create_gradient_fallback(output_path, panel_num):
    from PIL import Image, ImageDraw, ImageFilter

    width, height = 1080, 1920
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    palettes = [
        [(65, 42, 20), (120, 75, 35)],
        [(80, 55, 28), (140, 90, 45)],
        [(50, 45, 55), (90, 70, 85)],
        [(20, 30, 55), (45, 55, 85)],
        [(15, 18, 30), (40, 35, 55)],
    ]
    top_color, bottom_color = palettes[min(panel_num, 4)]

    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    import random as rng
    rng.seed(panel_num * 42)
    for _ in range(3000):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        brightness = rng.randint(-15, 15)
        px = img.getpixel((x, y))
        img.putpixel((x, y), tuple(max(0, min(255, c + brightness)) for c in px))

    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    img.save(output_path, "PNG")
    return True


def generate_images(topic, visual_keywords, num_panels=5):
    """Generate people-focused panel images with 3-layer fallback."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    paths = []

    for i in range(num_panels):
        output_path = os.path.join(OUTPUT_DIR, f"panel_{i}.png")
        prompt = generate_image_prompt(topic, visual_keywords, i)

        print(f"[images] Panel {i+1}/{num_panels}: generating...")

        layers = [
            ("Together.ai", lambda: generate_with_together(prompt, output_path)),
            ("Gemini", lambda: generate_with_gemini(prompt, output_path)),
            ("Pollinations", lambda: generate_with_pollinations(prompt, output_path)),
            ("Pixabay", lambda: fetch_from_pixabay(visual_keywords, output_path, i)),
            ("Pexels", lambda: fetch_from_pexels(visual_keywords, output_path, i)),
            ("Gradient", lambda: create_gradient_fallback(output_path, i)),
        ]

        for name, fn in layers:
            try:
                if fn():
                    print(f"[images] Panel {i+1}: {name}")
                    break
            except Exception as e:
                print(f"[images] Panel {i+1} {name} error: {e}")

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
