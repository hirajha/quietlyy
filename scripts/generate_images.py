"""
Quietlyy — Image Generator
Uses Gemini's image generation to create anime-style nostalgic panels.
Falls back to Pexels stock images if Gemini image gen fails.
"""

import os
import json
import base64
import requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def generate_image_prompt(topic, visual_keywords, panel_num, total_panels):
    """Create a prompt for one panel image."""
    keywords_str = ", ".join(visual_keywords)
    mood_map = {
        0: "warm nostalgic golden-hour lighting, peaceful past",
        1: "warm sepia tones, people connecting meaningfully",
        2: "transition moment, bittersweet contrast",
        3: "cold modern blue tones, isolation, disconnection",
        4: "melancholic wide shot, solitary figure, dusk",
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


def generate_with_gemini(prompt, output_path):
    """Use Gemini 2.0 Flash to generate an image."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return False

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                    "imageSizes": ["1024x1792"],
                },
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract image from response
        for part in data["candidates"][0]["content"]["parts"]:
            if "inlineData" in part:
                img_data = base64.b64decode(part["inlineData"]["data"])
                with open(output_path, "wb") as f:
                    f.write(img_data)
                return True

    except Exception as e:
        print(f"[images] Gemini image gen failed: {e}")

    return False


def fetch_from_pexels(keywords, output_path):
    """Fallback: download a relevant image from Pexels."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return False

    query = " ".join(keywords[:2]) + " vintage nostalgic"
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": key},
            params={"query": query, "per_page": 5, "orientation": "portrait"},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            return False

        import random
        photo = random.choice(photos)
        img_url = photo["src"]["large2x"]  # High quality

        img_resp = requests.get(img_url, timeout=30)
        img_resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(img_resp.content)
        return True

    except Exception as e:
        print(f"[images] Pexels fallback failed: {e}")
        return False


def create_gradient_fallback(output_path, panel_num):
    """Ultimate fallback: create a moody gradient image with Pillow."""
    from PIL import Image, ImageDraw

    width, height = 1080, 1920
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # Warm-to-cool gradient based on panel position
    colors = [
        [(45, 30, 15), (80, 50, 25)],     # warm brown
        [(60, 40, 20), (90, 60, 30)],     # sepia
        [(40, 35, 45), (70, 55, 65)],     # transition
        [(20, 25, 45), (40, 45, 70)],     # cold blue
        [(15, 15, 25), (35, 30, 50)],     # dark dusk
    ]
    top_color, bottom_color = colors[min(panel_num, 4)]

    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    img.save(output_path, "PNG")
    return True


def generate_images(topic, visual_keywords, num_panels=5):
    """Generate panel images for the video."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    paths = []

    for i in range(num_panels):
        output_path = os.path.join(OUTPUT_DIR, f"panel_{i}.png")
        prompt = generate_image_prompt(topic, visual_keywords, i, num_panels)

        print(f"[images] Panel {i+1}/{num_panels}: generating...")

        success = generate_with_gemini(prompt, output_path)

        if not success:
            print(f"[images] Panel {i+1}: trying Pexels fallback...")
            success = fetch_from_pexels(visual_keywords, output_path)

        if not success:
            print(f"[images] Panel {i+1}: using gradient fallback")
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
