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
    """Gallery reuse disabled — every panel is freshly generated with DALL-E.
    Reusing random gallery images caused wrong-topic frames to appear mid-video."""
    return {}


# ── Whisprs-matched aesthetic (2M followers in 2 months):
# - Cinematic GRAPHIC NOVEL / comic illustration style — NOT anime
# - Wide atmospheric shots: lone figure TINY against vast landscape/sky
# - Muted cinematic palettes: teal-green, dusty rose/terracotta, warm amber, deep navy
# - Visible ink lines, watercolor wash, editorial illustration feel
# - Dramatic skies fill upper 2/3 of frame; tiny figure at bottom 1/3
# - Mix of wide environmental shots + occasional close portrait illustrations
# - Lonely, contemplative, wandering — cinematic graphic novel feel

_SCENE_POOL_WIDE = [
    # ── Wide atmospheric — tiny lone figure vs vast environment (signature Whisprs look)
    "A lone figure standing in a vast field of tall wild grass, viewed from the side, "
    "figure small and isolated against a wide muted teal-grey sky with drifting clouds, "
    "cinematic graphic novel illustration, bold ink outlines with atmospheric wash, "
    "muted palette: teal sky, olive-green grass, dusty grey — contemplative, emotional",

    "A small lone figure in a dark coat walking away down a winding amber-lit forest path, "
    "viewed from high above and behind, warm orange-amber light pooling on the muddy ground, "
    "tall dark bare trees framing both sides, soft glow in the misty distance, "
    "cinematic editorial illustration, graphic novel comic art style, "
    "palette: deep forest green, warm amber, dark brown — moody and lonely",

    "A tiny lone figure in a red coat walking away along a narrow winding path "
    "beside a vast dark navy lake, the still water stretching to a distant misty horizon, "
    "tall wild grass on both sides, viewed from high behind, "
    "cinematic graphic novel illustration, ink and wash, "
    "palette: deep navy blue, teal, amber-gold grass — quiet and melancholy",

    "A person sitting alone on a park bench, figure small at the bottom of the frame, "
    "vast dusty rose and terracotta sky filling the upper three-quarters of the image, "
    "a few dark birds scattered in the atmospheric sky, "
    "cinematic graphic novel editorial illustration style, "
    "palette: muted dusty rose, terracotta, warm grey — lonely and still",

    "A woman viewed from behind standing on a wooden bridge walkway at dusk, "
    "a dramatic suspension bridge structure on the left side, "
    "vast cloudy amber-orange and teal sky above, misty city skyline in the distance, "
    "cinematic graphic novel illustration, ink and wash style, "
    "palette: warm amber, burnt orange, muted teal-grey — atmospheric",

    "A lone person sitting on a wooden chair placed in the middle of a vast open field, "
    "dramatic swirling sky with large cream and white expressive clouds above, "
    "figure tiny at the very bottom, sky painted in painterly swirling brushstrokes, "
    "cinematic illustration with oil painting style, "
    "palette: muted teal sky, cream clouds, warm green field — introspective",

    "Overhead bird's-eye view looking straight down at a lone figure "
    "standing alone and still in the center of a large moving crowd of people, "
    "all other figures blurred with motion, one person isolated and stationary, "
    "cinematic editorial illustration, graphic novel comic art style, "
    "palette: dark warm brown, terracotta, muted orange — alone in a crowd",

    "A small figure standing at the edge of a misty coastal cliff path, "
    "facing a vast grey-teal ocean horizon under a heavy overcast sky, "
    "dark wild cliff grass in the foreground, soft diffuse atmospheric light, "
    "cinematic graphic novel illustration, ink and wash, "
    "palette: deep teal-grey ocean, dusty blue-grey sky, olive-green — vast and lonely",

    "A lone figure walking away on a quiet autumn street after rain, "
    "wet pavement reflecting amber street lamp light, colorful fallen leaves, "
    "bare trees lining the street, figure small and walking into the distance, "
    "cinematic editorial illustration, graphic novel style, "
    "palette: warm amber, muted orange-red, dark grey — melancholy and beautiful",
]

_SCENE_POOL_PORTRAIT = [
    # ── Close portrait illustrations — the other Whisprs look
    "Close portrait illustration of a young woman on a train or subway, "
    "eyes gently closed, face tilted slightly upward as if breathing deep, "
    "rain streaking softly down a large window behind her, blurred warm city lights outside, "
    "teal and warm beige-cream tones, soft diffuse light on face, teal jacket, "
    "cinematic graphic novel illustration, bold ink outlines, intimate portrait",

    "Close artistic illustration of a wise weathered face in profile, "
    "rich fine detail in the face — etched lines like a woodcut engraving, "
    "dark teal-green background with copper and warm bronze skin tones, "
    "contemplative and sage-like, deeply textured, "
    "cinematic portrait illustration, woodcut engraving graphic novel style",

    "Close portrait illustration of a young woman in three-quarter profile, "
    "eyes closed or gently downcast, lost in private thought, "
    "soft atmospheric background — muted teal or dusty rose wash, "
    "cinematic graphic novel illustration, bold ink lines, "
    "intimate and emotionally weighted, beautiful face fully rendered",

    "Close-up illustration of a young man gazing out a rain-streaked window, "
    "his reflection softly visible in the glass, rain blurred beyond, "
    "soft muted teal and warm amber tones, face in three-quarter view, "
    "cinematic editorial illustration, graphic novel style, quietly contemplative",
]

_SCENE_POOL_ENVIRONMENT = [
    # ── Pure environment / atmospheric establishing shots
    "An empty winding forest path at golden hour or dusk, "
    "warm orange-amber light filtering through bare trees, "
    "puddles on the path reflecting the light, misty and atmospheric, "
    "cinematic graphic novel illustration, ink and wash style, "
    "palette: deep forest green, warm amber, dark earthy shadows",

    "An empty moonlit coastal path at the edge of a vast dark sea, "
    "pale moonlight on the water, dark wild grass and cliffs, "
    "heavy overcast sky, atmospheric and lonely, "
    "cinematic illustration, graphic novel style, "
    "palette: deep navy, soft silver moonlight, dark teal — vast and still",
]

# Combined pool — weighted for Whisprs aesthetic
# Wide shots dominate (signature look), with close portraits as counterpoint
_SCENE_POOL = (
    _SCENE_POOL_WIDE * 5 +         # Dominant — signature wide atmospheric shots
    _SCENE_POOL_PORTRAIT * 2 +     # Intimate close portrait illustrations
    _SCENE_POOL_ENVIRONMENT * 1    # Pure atmospheric establishing shots
)

# ── Art style for love scripts — same graphic novel style, warmer palette
_LOVE_STYLE_VARIANTS = [
    (
        "Cinematic graphic novel illustration — editorial comic art style, ink and watercolor wash. "
        "Two people in an intimate moment, warm amber and teal palette, soft diffuse light. "
        "Wide or medium shot showing environment context — not just faces. "
        "Palette: warm amber, muted rose, soft teal, earthy tones. "
        "Style: cinematic editorial illustration — like a graphic novel or animated film concept art. "
        "NOT anime. Visible ink lines and painterly atmosphere."
    ),
    (
        "Editorial illustration — cinematic graphic novel style, bold ink lines, atmospheric wash. "
        "Two figures close together in a meaningful space — lakeside, park, rainy street. "
        "Muted romantic palette: dusty rose, warm amber, deep teal. "
        "Style: moody western illustration aesthetic — graphic novel meets editorial art. "
        "Emotionally resonant, cinematic, beautiful. NOT anime or manga."
    ),
    (
        "Cinematic illustrated art — graphic novel aesthetic, visible brushwork and ink detail. "
        "Two people in a quiet tender moment in a vast or atmospheric setting. "
        "Palette: muted warm tones — amber, rose, teal, olive. "
        "Style: editorial comic illustration — emotionally deep, cinematic, visually striking. "
        "Wide composition showing environment as much as people."
    ),
]

_STYLE_VARIANTS = [
    (
        "Cinematic graphic novel illustration style — bold ink outlines with atmospheric wash. "
        "Editorial comic art aesthetic with rich muted cinematic palette. "
        "Wide atmospheric composition: lone figure small against vast environment (landscape, sky, city). "
        "Palette: muted teal-green, dusty rose, warm amber, deep navy — desaturated and cinematic. "
        "Style: western editorial illustration meets animated film concept art. "
        "NOT anime. NOT manga. Visible ink lines, painterly atmosphere, moody and emotional."
    ),
    (
        "Editorial illustration — cinematic graphic novel aesthetic, ink and watercolor wash. "
        "Dramatic wide composition: tiny lone figure against enormous atmospheric sky or landscape. "
        "Muted cinematic color palette: dusty rose, amber, deep navy, olive teal. "
        "Visible ink details, brushwork, editorial comic art style. "
        "Emotionally resonant, contemplative, deeply cinematic. NOT anime."
    ),
    (
        "Cinematic illustrated art — graphic novel style, bold outlines, atmospheric color. "
        "Lone isolated figure in a vast meaningful environment: field, lakeside, city, cliff. "
        "Palette: muted teal-green, terracotta, warm amber, deep navy — never saturated. "
        "Style: editorial comic illustration — like a graphic novel or animated film still. "
        "Beautiful muted colors, heavy atmosphere, emotionally powerful. NOT anime."
    ),
    (
        "Graphic novel editorial illustration — cinematic, atmospheric, emotionally weighted. "
        "Wide shot showing lone figure small against dramatic sky or vast landscape. "
        "Muted atmospheric palette: teal, dusty rose, warm amber, deep navy. "
        "Visible ink outlines and painterly washes, rich texture, cinematic composition. "
        "Style: western illustrated art — moody, premium, makes viewers stop scrolling. NOT anime."
    ),
]

# Module-level: pick a style once per import (once per pipeline run)
_CHOSEN_STYLE = random.choice(_STYLE_VARIANTS)
# Shuffle scenes once per run for fresh panel order every video
_SHUFFLED_SCENES = random.sample(_SCENE_POOL, len(_SCENE_POOL))

# Love-specific scene pool — wide cinematic graphic novel scenes for love/relationship topics
_LOVE_SCENE_POOL = [
    "Two small figures walking side by side on a vast empty beach at dusk, "
    "huge amber and teal sky above, gentle waves, viewed from far behind, "
    "cinematic graphic novel illustration, palette: warm amber, dusty teal, golden hour",

    "Two silhouettes standing close together on a quiet bridge at twilight, "
    "city lights reflected in the water below, atmospheric muted sky, "
    "cinematic editorial illustration, palette: deep navy, soft amber reflections, muted teal",

    "Two people sitting together on a park bench, one resting head on the other's shoulder, "
    "vast autumn sky behind them, colorful fallen leaves, viewed from the side, "
    "cinematic graphic novel illustration, palette: warm amber, dusty rose, muted green",

    "A close portrait of two faces almost touching, foreheads gently resting together, "
    "soft warm light, muted atmospheric background, tender and still, "
    "cinematic editorial illustration, palette: warm amber, dusty rose, soft cream",

    "Two small figures lying in a vast field of grass looking up at enormous clouds, "
    "dramatic expressive sky, tiny against the landscape, "
    "cinematic illustration, palette: teal sky, cream clouds, green field",

    "Two people standing apart on a wide empty street in rain, "
    "one reaching toward the other, wet amber reflections, moody atmosphere, "
    "cinematic graphic novel illustration, palette: deep navy, amber, muted grey",

    "A close illustration of two hands intertwined, soft warm light, "
    "blurred atmospheric background suggesting outdoors or soft interior, "
    "cinematic portrait illustration, ink and wash style, warm palette",

    "Two silhouettes close together under a streetlamp in falling snow or rain, "
    "the light making a warm halo around them, dark street background, "
    "cinematic editorial illustration, palette: deep navy, warm amber lamp, soft white",

    "A couple viewed from behind standing at the edge of a vast misty lake, "
    "the water stretching to the horizon, atmospheric and quiet, "
    "cinematic graphic novel style, palette: deep teal, soft mist, warm gold",

    "Two people at a cafe or by a window, one looking at the other who looks away, "
    "rain outside the window blurred, warm interior light, intimate quiet moment, "
    "cinematic editorial illustration, graphic novel style, warm muted palette",
]


def generate_image_prompt(topic, visual_keywords, panel_num, style="emotional"):
    """Create Whisprs-matched scene prompts — cinematic graphic novel illustration style.
    Wide atmospheric shots with tiny lone figure against vast environment.
    Love style uses wide romantic couple scenes; others use solo atmospheric scenes."""
    keywords_str = ", ".join(visual_keywords)

    if style == "love":
        chosen_style = random.choice(_LOVE_STYLE_VARIANTS)
        shuffled_love = random.sample(_LOVE_SCENE_POOL, len(_LOVE_SCENE_POOL))
        scene = shuffled_love[panel_num % len(_LOVE_SCENE_POOL)]
    else:
        chosen_style = _CHOSEN_STYLE
        scene = _SHUFFLED_SCENES[panel_num % len(_SHUFFLED_SCENES)]

    return (
        f"{chosen_style} "
        f"Scene: {scene}. "
        f"Emotional theme: {topic}. Mood keywords: {keywords_str}. "
        f"Portrait orientation (tall, 9:16). "
        f"Cinematic graphic novel illustration, NOT anime, NOT photorealistic. "
        f"No text, no watermarks, no words, no letters, no UI elements in the image."
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
    """Generate image using OpenAI DALL-E 3 (primary) or gpt-image-1 (fallback).
    DALL-E 3 was the last working model — gpt-image-1 returns 400."""
    import base64
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return False

    # Try DALL-E 3 first (was working until Apr 28)
    for attempt in range(2):
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
                    "size": "1024x1024",  # Square — avoids sideways composition
                    "quality": "standard",
                    "response_format": "url",
                },
                timeout=120,
            )
            if resp.status_code != 200:
                print(f"[images] DALL-E 3 HTTP {resp.status_code}: {resp.text[:500]}")
                resp.raise_for_status()
            data = resp.json()
            img_url = data["data"][0]["url"]
            img_resp = requests.get(img_url, timeout=30)
            img_resp.raise_for_status()
            if len(img_resp.content) < 5000:
                continue
            with open(output_path, "wb") as f:
                f.write(img_resp.content)

            # Crop square to portrait and resize to 1080x1920
            from PIL import Image as PILImage, ImageEnhance
            img = PILImage.open(output_path).convert("RGB")
            w, h = img.size
            target_w = int(h * 9 / 16)
            left = (w - target_w) // 2
            img = img.crop((left, 0, left + target_w, h))
            img = ImageEnhance.Brightness(img).enhance(1.15)
            img = img.resize((1080, 1920), PILImage.LANCZOS)
            img.save(output_path)
            print(f"[images] DALL-E 3 succeeded (attempt {attempt+1})")
            return True
        except Exception as e:
            print(f"[images] DALL-E 3 attempt {attempt+1} failed: {e}")
            if attempt < 1:
                time.sleep(3)

    # Fallback: gpt-image-1 with correct params
    for attempt in range(2):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-image-1",
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1024",
                    "quality": "low",
                },
                timeout=120,
            )
            if resp.status_code != 200:
                print(f"[images] gpt-image-1 HTTP {resp.status_code}: {resp.text[:500]}")
                resp.raise_for_status()
            data = resp.json()
            item = data["data"][0]
            if "b64_json" in item:
                img_data = base64.b64decode(item["b64_json"])
            elif "url" in item:
                ir = requests.get(item["url"], timeout=30)
                ir.raise_for_status()
                img_data = ir.content
            else:
                continue
            if len(img_data) < 5000:
                continue
            with open(output_path, "wb") as f:
                f.write(img_data)

            from PIL import Image as PILImage, ImageEnhance
            img = PILImage.open(output_path).convert("RGB")
            w, h = img.size
            target_w = int(h * 9 / 16)
            left = (w - target_w) // 2
            img = img.crop((left, 0, left + target_w, h))
            img = ImageEnhance.Brightness(img).enhance(1.15)
            img = img.resize((1080, 1920), PILImage.LANCZOS)
            img.save(output_path)
            print(f"[images] gpt-image-1 succeeded (attempt {attempt+1})")
            return True
        except Exception as e:
            print(f"[images] gpt-image-1 attempt {attempt+1} failed: {e}")
            if attempt < 1:
                time.sleep(3)
    return False


def generate_with_gemini_imagen(prompt, output_path):
    """Fallback: Google Imagen 3 via google-genai SDK."""
    import base64, io
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return False
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key)
        # Google deprecated imagen-3.0-generate-002 → use imagen-4.0-generate-001
        # (current GA model as of 2026). Falls back to imagen-3.0-fast-generate-001
        # if 4.0 isn't available on the user's project.
        model_ids = ["imagen-4.0-generate-001", "imagen-3.0-fast-generate-001"]
        response = None
        last_err = None
        for model_id in model_ids:
            try:
                response = client.models.generate_images(
                    model=model_id,
                    prompt=prompt[:2000],
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="9:16",
                        safety_filter_level="BLOCK_ONLY_HIGH",
                    ),
                )
                break  # success
            except Exception as e:
                last_err = e
                err_str = str(e)
                if "404" not in err_str and "NOT_FOUND" not in err_str:
                    raise  # non-404 error → propagate immediately
                # Try the next model_id
                continue
        if response is None:
            raise last_err if last_err else RuntimeError("No Imagen model available")
        if not response.generated_images:
            print("[images]   Gemini Imagen: no images returned")
            return False
        img_bytes = response.generated_images[0].image.image_bytes
        if not img_bytes or len(img_bytes) < 5000:
            return False
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        from PIL import Image as PILImage, ImageEnhance
        img = PILImage.open(output_path).convert("RGB")
        img = ImageEnhance.Brightness(img).enhance(1.15)
        img = img.resize((1080, 1920), PILImage.LANCZOS)
        img.save(output_path)
        print("[images]   Gemini Imagen 3 succeeded")
        return True
    except Exception as e:
        print(f"[images]   Gemini Imagen fallback failed: {e}")
        return False


def generate_with_pollinations(prompt, output_path):
    """Free fallback: Pollinations.ai FLUX — no API key needed."""
    try:
        from urllib.parse import quote
        url = (f"https://image.pollinations.ai/prompt/{quote(prompt[:500])}"
               f"?width=576&height=1024&model=flux&nologo=true&seed={random.randint(1,99999)}")
        resp = requests.get(url, timeout=90)
        if resp.status_code != 200 or len(resp.content) < 5000:
            return False
        with open(output_path, "wb") as f:
            f.write(resp.content)
        from PIL import Image as PILImage
        img = PILImage.open(output_path).convert("RGB")
        img = img.resize((1080, 1920), PILImage.LANCZOS)
        img.save(output_path)
        print("[images]   Pollinations succeeded")
        return True
    except Exception as e:
        print(f"[images]   Pollinations failed: {e}")
        return False


def generate_with_huggingface(prompt, output_path):
    """Generate image using Hugging Face Inference API (free tier).
    Primary generator — FLUX.1-schnell is production-quality and free.
    Falls back to SDXL if FLUX quota is exceeded."""
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        return False

    models = [
        (
            "black-forest-labs/FLUX.1-schnell",
            {"num_inference_steps": 4, "guidance_scale": 0.0},
        ),
        (
            "stabilityai/stable-diffusion-xl-base-1.0",
            {"num_inference_steps": 25, "guidance_scale": 7.5},
        ),
    ]

    for model_id, params in models:
        try:
            resp = requests.post(
                f"https://api-inference.huggingface.co/models/{model_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"inputs": prompt[:500], "parameters": params},
                timeout=120,
            )
            if resp.status_code == 503:
                print(f"[images] HF {model_id} loading (503) — skipping")
                continue
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type and len(resp.content) < 5000:
                print(f"[images] HF {model_id} returned non-image: {resp.text[:200]}")
                continue

            with open(output_path, "wb") as f:
                f.write(resp.content)

            from PIL import Image as PILImage, ImageEnhance
            img = PILImage.open(output_path).convert("RGB")
            # Crop to 9:16 portrait if needed
            w, h = img.size
            target_h = int(w * 16 / 9)
            if target_h <= h:
                top = (h - target_h) // 2
                img = img.crop((0, top, w, top + target_h))
            else:
                target_w = int(h * 9 / 16)
                left = (w - target_w) // 2
                img = img.crop((left, 0, left + target_w, h))
            img = ImageEnhance.Brightness(img).enhance(1.5)
            img = img.resize((1080, 1920), PILImage.LANCZOS)
            img.save(output_path)
            print(f"[images] HF {model_id} succeeded")
            return True
        except Exception as e:
            print(f"[images] HF {model_id} failed: {e}")
            continue
    return False


def generate_images(topic, visual_keywords, num_panels=5, style="emotional"):
    """Generate panel images — free-first provider chain.
    Order: HuggingFace (free FLUX) → gpt-image-1 → Gemini Imagen 3.
    - Max 8 panels per video
    - If all providers fail for a panel, reuse an earlier successful panel
    - After 25 gallery images: reuse 2-3 panels (never panel 0)
    At least 1 image must succeed or pipeline fails."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    num_panels = min(num_panels, 8)  # Hard cap at 8 — enough for poetic scripts
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

        prompt = generate_image_prompt(topic, visual_keywords, i, style=style)

        # Free-first chain: HF → Gemini Imagen → Pollinations → OpenAI (paid, last resort)
        print(f"[images] Panel {i+1}/{num_panels}: trying HuggingFace (free)...")
        success = generate_with_huggingface(prompt, output_path)
        if not success:
            print(f"[images]   HF failed — trying Gemini Imagen 3 (free)...")
            success = generate_with_gemini_imagen(prompt, output_path)
        if not success:
            print(f"[images]   Gemini failed — trying Pollinations (free)...")
            success = generate_with_pollinations(prompt, output_path)
        if not success:
            print(f"[images]   Pollinations failed — trying OpenAI as last resort (paid)...")
            success = generate_with_dalle(prompt, output_path)

        if success:
            print(f"[images] Panel {i+1}: generated")
            successful_paths.append(output_path)
        else:
            # All providers failed — reuse an earlier panel from THIS video
            if successful_paths:
                reuse_src = random.choice(successful_paths)
                shutil.copy2(reuse_src, output_path)
                print(f"[images] Panel {i+1}: reusing earlier panel (all providers failed)")
            else:
                raise RuntimeError(f"Image generation failed for panel {i+1} (tried HF, Gemini, Pollinations, OpenAI). No earlier panels to reuse.")

        paths.append(output_path)

        if i < num_panels - 1:
            time.sleep(2)

    print(f"[images] Generated {len(paths)} panels ({len(reuse_map)} from gallery, {len(successful_paths)} fresh)")
    return paths


if __name__ == "__main__":
    paths = generate_images(
        "Telephone",
        ["old telephone", "rotary phone", "vintage phone booth", "warm lamp light"],
    )
    print(json.dumps(paths, indent=2))
