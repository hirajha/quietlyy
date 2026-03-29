"""
Quietlyy — Image Generator
4-layer fallback: Gemini → Pexels → Pixabay → Gradient
No Stability AI. All free APIs.
"""

import os
import json
import base64
import random
import requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def generate_image_prompt(topic, visual_keywords, panel_num, total_panels):
    """Create a prompt for one panel image."""
    keywords_str = ", ".join(visual_keywords)
    mood_map = {
        0: "warm nostalgic golden-hour lighting, peaceful past, sepia warmth",
        1: "warm sepia tones, people connecting meaningfully, intimate",
        2: "bittersweet transition, fading warmth to cool tones",
        3: "cold modern blue tones, isolation, person alone with phone, disconnection",
        4: "melancholic wide shot, solitary figure in vast space, dusk, loss",
    }
    mood = mood_map.get(panel_num, mood_map[2])

    return (
        f"Anime illustration, cinematic vertical composition (9:16 aspect ratio), "
        f"topic: {topic}, scene keywords: {keywords_str}. "
        f"Mood: {mood}. "
        f"Style: detailed anime art, soft lighting, atmospheric, Studio Ghibli inspired, "
        f"muted warm color palette, painterly textures, no text or watermarks. "
        f"High quality, emotional, nostalgic."
    )


# ── Layer 1: Gemini Image Generation (free tier) ──
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


# ── Layer 2: Pexels (free, 200 req/hour) ──
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


# ── Layer 3: Pixabay (free, 100 req/min, no key needed for low volume) ──
def fetch_from_pixabay(keywords, output_path):
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        # Pixabay allows limited keyless access
        return False

    query = "+".join(keywords[:2])
    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": key,
                "q": query,
                "image_type": "photo",
                "orientation": "vertical",
                "per_page": 10,
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


# ── Layer 4: Gradient fallback (always works, no API) ──
def create_gradient_fallback(output_path, panel_num):
    from PIL import Image, ImageDraw, ImageFilter

    width, height = 1080, 1920
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # Warm-to-cool gradient palettes matching the moody aesthetic
    palettes = [
        [(65, 42, 20), (120, 75, 35)],     # warm amber
        [(80, 55, 28), (140, 90, 45)],      # sepia gold
        [(50, 45, 55), (90, 70, 85)],       # dusty purple transition
        [(20, 30, 55), (45, 55, 85)],       # cold blue isolation
        [(15, 18, 30), (40, 35, 55)],       # dark dusk melancholy
    ]
    top_color, bottom_color = palettes[min(panel_num, 4)]

    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Add some noise/texture for atmosphere
    import random as rng
    rng.seed(panel_num * 42)
    for _ in range(3000):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        brightness = rng.randint(-15, 15)
        px = img.getpixel((x, y))
        img.putpixel((x, y), tuple(max(0, min(255, c + brightness)) for c in px))

    # Slight blur for softness
    img = img.filter(ImageFilter.GaussianBlur(radius=2))

    img.save(output_path, "PNG")
    return True


def generate_images(topic, visual_keywords, num_panels=5):
    """Generate panel images with 4-layer fallback per panel."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    paths = []

    for i in range(num_panels):
        output_path = os.path.join(OUTPUT_DIR, f"panel_{i}.png")
        prompt = generate_image_prompt(topic, visual_keywords, i, num_panels)

        print(f"[images] Panel {i+1}/{num_panels}: generating...")

        # Try each layer in order
        success = False
        for layer_fn, layer_name in [
            (lambda: generate_with_gemini(prompt, output_path), "Gemini"),
            (lambda: fetch_from_pexels(visual_keywords, output_path), "Pexels"),
            (lambda: fetch_from_pixabay(visual_keywords, output_path), "Pixabay"),
            (lambda: create_gradient_fallback(output_path, i), "Gradient"),
        ]:
            try:
                if layer_fn():
                    print(f"[images] Panel {i+1}: {layer_name}")
                    success = True
                    break
            except Exception as e:
                print(f"[images] Panel {i+1} {layer_name} error: {e}")

        if not success:
            # This should never happen since gradient always works
            create_gradient_fallback(output_path, i)

        paths.append(output_path)

    print(f"[images] Generated {len(paths)} panels")
    return paths


if __name__ == "__main__":
    paths = generate_images(
        "Telephone",
        ["old telephone", "rotary phone", "vintage phone booth", "phone cord"],
    )
    print(json.dumps(paths, indent=2))
