"""
Quietlyy — Image Generator
3-layer fallback for AI art (no Stability AI):
  Layer 1: Gemini 2.5 Flash Image (free 500 img/day — primary on GitHub Actions)
  Layer 2: Pexels stock photos (free 200 req/hr — moody/atmospheric search)
  Layer 3: Gradient fallback (always works, no API)
"""

import os
import json
import base64
import random
import time
import requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def generate_image_prompt(topic, visual_keywords, panel_num):
    """Create a prompt for one panel image."""
    keywords_str = ", ".join(visual_keywords)
    mood_map = {
        0: "warm nostalgic golden-hour lighting, peaceful past, sepia warmth, cozy interior",
        1: "warm amber tones, people connecting meaningfully, intimate moment, gentle light",
        2: "bittersweet transition scene, fading warmth to cool tones, twilight",
        3: "cold modern blue tones, person alone with phone, isolation, disconnection, night",
        4: "melancholic wide shot, solitary dark figure from behind, dusk sky, vast emptiness",
    }
    mood = mood_map.get(panel_num, mood_map[2])

    return (
        f"Anime illustration, cinematic vertical portrait composition, "
        f"topic: {topic}, {keywords_str}. "
        f"Mood: {mood}. "
        f"Style: detailed anime art, atmospheric lighting, Studio Ghibli inspired, "
        f"muted color palette, painterly textures, emotional, no text, no watermarks, no words."
    )


# ── Layer 1: Gemini 2.5 Flash Image (free 500 img/day) ──
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


# ── Layer 3: Pexels (free, 200 req/hour) ──
def fetch_from_pexels(keywords, output_path):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return False

    query = " ".join(keywords[:2]) + " vintage nostalgic"
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": key},
            params={"query": query, "per_page": 10, "orientation": "portrait"},
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


# ── Layer 4: Gradient fallback (always works, no API) ──
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
    """Generate panel images with 4-layer fallback per panel."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    paths = []

    for i in range(num_panels):
        output_path = os.path.join(OUTPUT_DIR, f"panel_{i}.png")
        prompt = generate_image_prompt(topic, visual_keywords, i)

        print(f"[images] Panel {i+1}/{num_panels}: generating...")

        # Try each layer in order
        layers = [
            ("Gemini", lambda: generate_with_gemini(prompt, output_path)),
            ("Pexels", lambda: fetch_from_pexels(visual_keywords, output_path)),
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

        # Small delay between API calls to be polite
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
