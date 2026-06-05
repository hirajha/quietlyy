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
# - Painterly editorial illustration with brush + ink + film grain (real Whisprs style)
# - Wide atmospheric shots: lone figure TINY against vast landscape/sky
# - Muted cinematic palettes: teal-green, dusty rose/terracotta, warm amber, deep navy
# - Dramatic skies fill upper 2/3 of frame; tiny figure at bottom 1/3
# - Mix of wide environmental shots + occasional close portrait illustrations
# - Lonely, contemplative — painterly textured illustration with grain
# - ONE warm accent colour (orange/amber) on a muted cool palette = signature

_SCENE_POOL_WIDE = [
    # ── Wide atmospheric — tiny lone figure vs vast environment (signature Whisprs look)
    "A lone figure standing in a vast field of tall wild grass, viewed from the side, "
    "figure small and isolated against a wide muted teal-grey sky with drifting clouds, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "muted palette: teal sky, olive-green grass, dusty grey — contemplative, emotional",

    "A small lone figure in a dark coat walking away down a winding amber-lit forest path, "
    "viewed from high above and behind, warm orange-amber light pooling on the muddy ground, "
    "tall dark bare trees framing both sides, soft glow in the misty distance, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "palette: deep forest green, warm amber, dark brown — moody and lonely",

    "A tiny lone figure in a red coat walking away along a narrow winding path "
    "beside a vast dark navy lake, the still water stretching to a distant misty horizon, "
    "tall wild grass on both sides, viewed from high behind, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "palette: deep navy blue, teal, amber-gold grass — quiet and melancholy",

    "A person sitting alone on a park bench, figure small at the bottom of the frame, "
    "vast dusty rose and terracotta sky filling the upper three-quarters of the image, "
    "a few dark birds scattered in the atmospheric sky, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "palette: muted dusty rose, terracotta, warm grey — lonely and still",

    "A woman viewed from behind standing on a wooden bridge walkway at dusk, "
    "a dramatic suspension bridge structure on the left side, "
    "vast cloudy amber-orange and teal sky above, misty city skyline in the distance, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "palette: warm amber, burnt orange, muted teal-grey — atmospheric",

    "A lone person sitting on a wooden chair placed in the middle of a vast open field, "
    "dramatic swirling sky with large cream and white expressive clouds above, "
    "figure tiny at the very bottom, sky painted in painterly swirling brushstrokes, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "palette: muted teal sky, cream clouds, warm green field — introspective",

    "Overhead bird's-eye view looking straight down at a lone figure "
    "standing alone and still in the center of a large moving crowd of people, "
    "all other figures blurred with motion, one person isolated and stationary, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "palette: dark warm brown, terracotta, muted orange — alone in a crowd",

    "A small figure standing at the edge of a misty coastal cliff path, "
    "facing a vast grey-teal ocean horizon under a heavy overcast sky, "
    "dark wild cliff grass in the foreground, soft diffuse atmospheric light, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "palette: deep teal-grey ocean, dusty blue-grey sky, olive-green — vast and lonely",

    "A lone figure walking away on a quiet autumn street after rain, "
    "wet pavement reflecting amber street lamp light, colorful fallen leaves, "
    "bare trees lining the street, figure small and walking into the distance, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "palette: warm amber, muted orange-red, dark grey — melancholy and beautiful",
]

_SCENE_POOL_PORTRAIT = [
    # ── Close portrait illustrations — the other Whisprs look
    "Close portrait illustration of a young woman on a train or subway, "
    "eyes gently closed, face tilted slightly upward as if breathing deep, "
    "rain streaking softly down a large window behind her, blurred warm city lights outside, "
    "teal and warm beige-cream tones, soft diffuse light on face, teal jacket, "
    "painterly editorial portrait illustration with brush and ink texture, subtle film grain, intimate",

    "Close artistic illustration of a wise weathered face in profile, "
    "smooth simplified features, soft flat shading, "
    "dark teal-green background with copper and warm bronze skin tones, "
    "contemplative and sage-like, deeply textured, "
    "painterly editorial portrait illustration with brush and ink texture, subtle film grain",

    "Close portrait illustration of a young woman in three-quarter profile, "
    "eyes closed or gently downcast, lost in private thought, "
    "soft atmospheric background — muted teal or dusty rose wash, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "intimate and emotionally weighted, beautiful face fully rendered",

    "Close-up illustration of a young man gazing out a rain-streaked window, "
    "his reflection softly visible in the glass, rain blurred beyond, "
    "soft muted teal and warm amber tones, face in three-quarter view, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, quietly contemplative",
]

_SCENE_POOL_ENVIRONMENT = [
    # ── Pure environment / atmospheric establishing shots
    "An empty winding forest path at golden hour or dusk, "
    "warm orange-amber light filtering through bare trees, "
    "puddles on the path reflecting the light, misty and atmospheric, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "palette: deep forest green, warm amber, dark earthy shadows",

    "An empty moonlit coastal path at the edge of a vast dark sea, "
    "pale moonlight on the water, dark wild grass and cliffs, "
    "heavy overcast sky, atmospheric and lonely, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, "
    "palette: deep navy, soft silver moonlight, dark teal — vast and still",
]

# Combined pool — weighted for Whisprs aesthetic
# Wide shots dominate (signature look), with close portraits as counterpoint
_SCENE_POOL = (
    _SCENE_POOL_WIDE * 5 +         # Dominant — signature wide atmospheric shots
    _SCENE_POOL_PORTRAIT * 2 +     # Intimate close portrait illustrations
    _SCENE_POOL_ENVIRONMENT * 1    # Pure atmospheric establishing shots
)

# ── Art style for love scripts — same painterly-textured style, warmer accent
_LOVE_STYLE_VARIANTS = [
    (
        "Painterly editorial illustration — visible brushwork and ink lines, subtle film-grain texture, "
        "hand-illustrated and premium. Two figures together in an atmospheric setting (beach, bridge, rainy street). "
        "Muted desaturated palette (teal, slate, warm grey) with ONE bold warm accent colour (amber, deep rose). "
        "Tender, moody, cinematic, textured. NOT flat vector, NOT photorealistic, NOT anime."
    ),
    (
        "Moody painterly illustration — expressive brushstrokes, ink detail, grainy textured background. "
        "Two figures close together in an emotional, atmospheric space. "
        "Heavily muted base (grey-teal, charcoal, slate) broken by ONE striking warm accent (amber, crimson rose). "
        "Premium editorial-illustration feel, hand-drawn and textured. NOT flat, NOT photoreal, NOT anime."
    ),
    (
        "Hand-illustrated editorial art — fine ink linework, painterly washes, film-grain texture. "
        "Two people sharing a tender moment in an atmospheric scene. "
        "Desaturated cinematic palette with ONE bold warm focal colour against muted surroundings. "
        "Textured, emotional, premium graphic-novel-cover quality. NOT flat-matte, NOT photoreal, NOT anime."
    ),
]

# ── WHISPRS PAINTERLY-TEXTURED STYLE (from direct audit of their actual MP4s, 2026-06) ──
# Frames from 3 real Whisprs videos showed the TRUE style (NOT flat-matte —
# that was Typewriters voice, a different page):
#   • PAINTERLY editorial illustration — visible brushwork + ink linework
#   • Subtle FILM-GRAIN / paper texture overlay on every frame (signature)
#   • Muted desaturated palette + EXACTLY ONE bold saturated accent colour
#     (e.g. a red parasol against grey; copper Rumi against teal; olive man
#     against teal sky). That single bold colour is the focal pop.
#   • A single emotional figure — small-in-landscape OR medium/close portrait
#   • Moody, atmospheric, cinematic, hand-illustrated feel — premium, textured
#   • NOT flat/smooth, NOT photoreal, NOT clean-vector — it has grit and brush
_STYLE_VARIANTS = [
    (
        "Painterly editorial illustration — visible brushwork and ink linework, with a subtle "
        "film-grain and paper-texture overlay (hand-illustrated, grainy, premium). "
        "A single emotional figure in an atmospheric scene. "
        "Muted desaturated palette (teal, olive, slate, dusty grey) with EXACTLY ONE bold "
        "saturated accent colour (deep red, burnt amber, or copper) as the focal pop. "
        "Moody, cinematic, contemplative. NOT flat vector, NOT photorealistic, NOT anime."
    ),
    (
        "Moody digital painting — expressive brushstrokes, ink detail, grungy textured background "
        "with visible grain. A lone figure or silhouette, emotionally charged. "
        "Heavily desaturated muted base (grey-green, dark teal, charcoal) broken by ONE striking "
        "bold accent colour (crimson red, warm amber). "
        "Atmospheric, painterly, premium editorial-illustration feel. NOT flat, NOT photoreal, NOT anime."
    ),
    (
        "Hand-illustrated editorial art — fine ink linework and painterly washes, rich texture and "
        "subtle film grain, like a premium graphic-novel cover. "
        "A single contemplative figure (lone in a landscape, or a close emotive portrait). "
        "Muted cinematic palette with ONE bold saturated focal colour against desaturated surroundings. "
        "Deeply atmospheric, textured, emotional. NOT flat-matte, NOT photorealistic, NOT anime."
    ),
    (
        "Textured painterly illustration — brush and ink, grain overlay, moody hand-drawn quality. "
        "A solitary figure against an atmospheric muted environment. "
        "Desaturated palette (teal, slate, olive, warm grey) with EXACTLY ONE bold accent colour "
        "(red, amber, or copper) drawing the eye. "
        "Cinematic, emotional, premium illustrated look. NOT flat vector art, NOT photoreal, NOT anime."
    ),
]

# Module-level: pick a style once per import (once per pipeline run)
_CHOSEN_STYLE = random.choice(_STYLE_VARIANTS)
# Shuffle scenes once per run for fresh panel order every video
_SHUFFLED_SCENES = random.sample(_SCENE_POOL, len(_SCENE_POOL))

# Love-specific scene pool — wide painterly-textured scenes for love/relationship topics
_LOVE_SCENE_POOL = [
    "Two small figures walking side by side on a vast empty beach at dusk, "
    "huge amber and teal sky above, gentle waves, viewed from far behind, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, palette: warm amber, dusty teal, golden hour",

    "Two silhouettes standing close together on a quiet bridge at twilight, "
    "city lights reflected in the water below, atmospheric muted sky, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, palette: deep navy, soft amber reflections, muted teal",

    "Two people sitting together on a park bench, one resting head on the other's shoulder, "
    "vast autumn sky behind them, colorful fallen leaves, viewed from the side, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, palette: warm amber, dusty rose, muted green",

    "A close portrait of two faces almost touching, foreheads gently resting together, "
    "soft warm light, muted atmospheric background, tender and still, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, palette: warm amber, dusty rose, soft cream",

    "Two small figures lying in a vast field of grass looking up at enormous clouds, "
    "dramatic expressive sky, tiny against the landscape, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, palette: teal sky, cream clouds, green field",

    "Two people standing apart on a wide empty street in rain, "
    "one reaching toward the other, wet amber reflections, moody atmosphere, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, palette: deep navy, amber, muted grey",

    "A close illustration of two hands intertwined, soft warm light, "
    "blurred atmospheric background suggesting outdoors or soft interior, "
    "painterly editorial portrait illustration with brush and ink texture, subtle film grain, warm palette",

    "Two silhouettes close together under a streetlamp in falling snow or rain, "
    "the light making a warm halo around them, dark street background, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, palette: deep navy, warm amber lamp, soft white",

    "A couple viewed from behind standing at the edge of a vast misty lake, "
    "the water stretching to the horizon, atmospheric and quiet, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, palette: deep teal, soft mist, warm gold",

    "Two people at a cafe or by a window, one looking at the other who looks away, "
    "rain outside the window blurred, warm interior light, intimate quiet moment, "
    "painterly editorial illustration with visible brushwork and ink lines, subtle film-grain texture, warm muted palette",
]


def generate_image_prompt(topic, visual_keywords, panel_num, style="emotional"):
    """Create Whisprs-matched scene prompts — painterly textured illustration style.
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
        f"PAINTERLY editorial illustration — visible brushwork and ink lines, subtle film-grain texture, "
        f"hand-illustrated and premium. Single emotional figure, atmospheric scene. Muted desaturated "
        f"palette with EXACTLY ONE bold saturated accent colour (red, amber, or copper) as the focal pop. "
        f"NOT flat vector, NOT photorealistic, NOT anime, NOT 3D render. "
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


def generate_with_gemini_flash_image(prompt, output_path):
    """Google 'Nano Banana' (gemini-2.5-flash-image) native image generation.

    Unlike Imagen (imagen-* models, PAID only), the Gemini Flash native image
    model runs on the STANDARD Gemini free quota — the same key/quota as our
    script generation. Uses the generateContent endpoint with
    responseModalities=['IMAGE']; the image comes back base64 in
    candidates[0].content.parts[*].inline_data.data.

    This is the primary free generator after Pollinations went paid (HTTP 402)
    in June 2026, leaving us with no working free image source.
    """
    import base64
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return False
    # Try current image-capable Gemini models in order
    models = ["gemini-2.5-flash-image", "gemini-2.0-flash-preview-image-generation"]
    for model_id in models:
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text":
                        prompt + " Vertical 9:16 portrait composition, tall format."}]}],
                    "generationConfig": {"responseModalities": ["IMAGE"]},
                },
                timeout=90,
            )
            if resp.status_code != 200:
                print(f"[images]   Nano Banana {model_id}: {resp.status_code} {resp.text[:150]}")
                continue
            data = resp.json()
            img_b64 = None
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        img_b64 = inline["data"]
                        break
                if img_b64:
                    break
            if not img_b64:
                print(f"[images]   Nano Banana {model_id}: no image in response")
                continue
            img_bytes = base64.b64decode(img_b64)
            if len(img_bytes) < 5000:
                continue
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            from PIL import Image as PILImage
            img = PILImage.open(output_path).convert("RGB")
            # Crop to 9:16 portrait then resize to 1080x1920
            w, h = img.size
            target_w = int(h * 9 / 16)
            if target_w <= w:
                left = (w - target_w) // 2
                img = img.crop((left, 0, left + target_w, h))
            else:
                target_h = int(w * 16 / 9)
                top = max(0, (h - target_h) // 2)
                img = img.crop((0, top, w, top + min(target_h, h)))
            img = img.resize((1080, 1920), PILImage.LANCZOS)
            img.save(output_path)
            print(f"[images]   ✅ Nano Banana ({model_id}) generated")
            return True
        except Exception as e:
            print(f"[images]   Nano Banana {model_id} error: {str(e)[:150]}")
            continue
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
                        # API now ONLY accepts BLOCK_LOW_AND_ABOVE (was BLOCK_ONLY_HIGH,
                        # which started 400ing: "Only block_low_and_above is supported").
                        # Our content is atmospheric landscapes so strict filtering is fine.
                        safety_filter_level="BLOCK_LOW_AND_ABOVE",
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
    """PRIMARY (and only working free) image generator: Pollinations.ai FLUX.

    Imagen requires a paid Google plan; HF Inference API is deprecated; DALL-E
    is decommissioned. So FLUX via Pollinations does all our images.

    Quality tuning (2026-06):
      - Native 768x1366 (was 576x1024) → sharper source before the 1080x1920
        upscale. FLUX handles higher res well.
      - Prompt kept to 950 chars (was 500) so the trailing 'painterly / NOT
        anime / no text' instructions survive — truncating at 500 cut them off,
        which is partly why earlier output drifted off-style.
    """
    try:
        from urllib.parse import quote
        url = (f"https://image.pollinations.ai/prompt/{quote(prompt[:950])}"
               f"?width=768&height=1366&model=flux&nologo=true&seed={random.randint(1,99999)}")
        resp = requests.get(url, timeout=120)
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
    Order: Gemini Imagen 4.0 (free, best) → Pollinations FLUX → HuggingFace FLUX.
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

        # Chain (2026-06-05) — Pollinations went PAID (HTTP 402), so the new
        # free primary is Google 'Nano Banana' (gemini-2.5-flash-image) on the
        # standard Gemini free quota (our existing key):
        #   1. Nano Banana (Gemini Flash image) — FREE on Gemini quota
        #   2. Pollinations FLUX — now 402/paid, tried in case they restore free
        #   3. Gemini Imagen — PAID plan only
        #   4. HuggingFace FLUX — deprecated endpoint, last-ditch
        print(f"[images] Panel {i+1}/{num_panels}: trying Nano Banana (Gemini Flash image, free)...")
        success = generate_with_gemini_flash_image(prompt, output_path)
        if not success:
            print(f"[images]   Nano Banana failed — trying Pollinations FLUX...")
            success = generate_with_pollinations(prompt, output_path)
        if not success:
            print(f"[images]   Pollinations failed — trying Gemini Imagen (paid plan only)...")
            success = generate_with_gemini_imagen(prompt, output_path)
        if not success:
            print(f"[images]   Imagen failed — trying HuggingFace FLUX (deprecated, flaky)...")
            success = generate_with_huggingface(prompt, output_path)

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
