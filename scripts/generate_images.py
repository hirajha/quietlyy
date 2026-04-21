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


# ── Scene pools — varied time of day, setting, and mood ───────────────────────
# Mix of: dark night, golden hour, morning, overcast day, nature, interior day
# Rule: no more than 2-3 consecutive dark night scenes per video — variety keeps viewers engaged

_SCENE_POOL_CLOSEUP = [
    "Close-up portrait of a young woman, chin resting on her hand, gazing into the distance, "
    "single warm lamp glow on her face, deep navy blue background fading to black, "
    "dark cinematic anime illustration style — moody, intimate, emotionally resonant",

    "Side profile of a young woman on a dark train at night, head gently leaning against the window, "
    "city lights blurring softly outside, reflection of her face in the glass, "
    "deep blue-black interior, single warm light source, dark atmospheric anime style",

    "Close-up of a young woman's face, eyes looking downward with a gentle melancholy, "
    "soft teal moonlight from a nearby window, dark blue-grey background, "
    "dark cinematic illustration — emotionally heavy, beautifully lit, anime aesthetic",

    "A man with tired eyes staring into the distance, single desk lamp glow on his face, "
    "deep dark navy background, shadows framing his expression, "
    "cinematic manga illustration style — contemplative, moody, visually striking",

    "Close-up of two people's hands almost touching across a dark table, "
    "one soft amber candle glow between them, deep dark background, "
    "dark illustrated style — tender, intimate, cinematic",

    "A woman reading an old letter by candlelight, flame casting warm amber on her face, "
    "surrounding darkness, deep blue shadows, dark anime illustration — emotional, cinematic, beautiful",

    "A young man leaning his forehead against a dark window at night, eyes closed, "
    "soft rain on the glass, dim interior light, deep blue-grey tones, "
    "dark cinematic illustration — heavy-hearted, still, emotionally resonant",

    "A woman with her back to us, standing in a dimly lit hallway, "
    "one ceiling light above casting a soft pool, deep dark walls, "
    "dark anime illustration — solitary, cinematic, beautifully composed",

    "Close-up of a person's eyes reflecting a candle flame, tears barely held back, "
    "surrounding darkness, warm amber light on wet lashes, "
    "dark cinematic anime art — deeply emotional, intimate, visually striking",

    "A young woman sitting cross-legged on a dark floor, phone screen lighting her face blue-white, "
    "deep dark room behind her, modern loneliness, "
    "dark anime illustration — relatable, quiet, emotionally heavy",

    "Side profile of a person listening to music on headphones, eyes closed, "
    "soft street lamp light through curtains, dark bedroom, "
    "dark cinematic anime style — introspective, peaceful, beautifully lit",

    "Close-up of a hand holding a worn photograph in soft lamp light, "
    "dark wooden table surface, blurred warm background, "
    "dark illustrated art — nostalgic, tender, emotionally resonant",

    # ── Day / golden hour close-ups ──
    "Close-up portrait of a young woman in warm golden afternoon light, "
    "half her face in soft shadow, eyes distant and pensive, "
    "cinematic anime illustration — warm amber tones, beautifully lit, emotionally resonant",

    "A person's face gently tilted toward a sunlit window, soft morning light on their skin, "
    "warm honey and ivory tones, blurred soft bokeh background, "
    "cinematic illustrated style — peaceful, intimate, high value",

    "Close-up of hands wrapped around a warm cup of tea, steam rising, "
    "soft golden morning light, wooden table with soft bokeh, "
    "cinematic illustration — quiet comfort, gentle melancholy, warm tones",

    "Side profile of a man with wind in his hair on a bright breezy day, "
    "soft afternoon light, pale sky, emotionally distant expression, "
    "cinematic anime illustration — airy, cinematic, introspective",

    "A young woman leaning against a sun-drenched wall, eyes closed, "
    "warm golden light on her face, soft shadow pattern, pale colours, "
    "illustrated cinematic art — peaceful, high value, emotionally still",
]

_SCENE_POOL_WIDE = [
    "A lone figure standing on a dark hilltop, full moon behind clouds, "
    "deep indigo-blue sky, soft moonlight spilling across the landscape, "
    "dark cinematic anime style — vast, atmospheric, emotionally powerful",

    "A person sitting alone on a park bench at night, one distant street lamp, "
    "deep navy sky, soft golden pool of light around them, dark trees silhouetted, "
    "dark anime illustration — lonely, cinematic, beautiful",

    "Wide view of a dark city at night seen from a rooftop, "
    "scattered warm window lights below, deep blue-black sky above, "
    "a lone figure at the edge looking out, cinematic dark anime style — vast, moody, introspective",

    "A quiet dark street at night after rain, wet pavement reflecting street lamp light, "
    "deep blue-black shadows, one figure walking away in the distance, "
    "dark cinematic anime illustration — melancholy, beautiful, atmospheric",

    "A person standing at the edge of a dark lake at midnight, "
    "full moon reflected perfectly in still water, deep indigo and black tones, "
    "soft silver moonlight on their silhouette, dark anime illustration — vast, emotional",

    "A moonlit coastal cliff, dark ocean stretching to the horizon, "
    "silver moon path on the water, lone figure at the edge, deep blue-black sky, "
    "dark cinematic illustrated style — breathtaking, moody, emotional",

    "A lone figure walking across a dark empty field under a vast night sky, "
    "Milky Way above, soft silver starlight, deep blue-black, "
    "dark cinematic anime illustration — vast solitude, beautiful, emotionally powerful",

    "A person standing in a dark forest clearing, moonlight filtering through tall trees, "
    "silver beams through dark branches, mist at ground level, "
    "dark atmospheric anime art — mysterious, beautiful, introspective",

    "A quiet rural road at night, one street lamp at the curve, "
    "warm amber light on the wet asphalt, dark fields stretching into black, "
    "dark cinematic illustration — isolated, quietly beautiful, melancholic",

    "A figure standing on a dark train platform, single overhead light, "
    "train pulling away in the distance, steam and motion blur, "
    "dark anime illustration — departure, loneliness, cinematic",

    "A person sitting on stone steps of an old building at dusk, "
    "last golden light fading behind dark rooftops, deep purple-blue sky, "
    "dark atmospheric illustrated art — reflective, beautiful, emotionally rich",

    "A lone silhouette on a dark bridge at dawn, fog below, soft purple-grey light, "
    "the city silent and sleeping, "
    "dark cinematic anime style — solitary, peaceful, emotionally heavy",

    # ── Golden hour / sunset wide scenes ──
    "A lone silhouette standing in a golden wheat field at sunset, "
    "vast warm amber sky, sun low on the horizon, long shadow stretching behind them, "
    "cinematic anime illustration — breathtaking, emotional, warm and beautiful",

    "A person walking on a coastal cliff at golden hour, "
    "orange and pink sky above the ocean, warm amber light on the path, "
    "cinematic illustrated art — vast, beautiful, quietly hopeful",

    "A lone figure on a hilltop at dusk, purple-pink sky behind them, "
    "last light fading over rolling hills, soft warm tones, "
    "atmospheric cinematic anime — peaceful solitude, golden hour beauty",

    "Wide view of autumn forest path in golden afternoon light, "
    "orange and amber leaves falling, a lone figure walking away, "
    "cinematic illustrated style — warm, melancholic, stunningly beautiful",

    "A person sitting on a wooden dock over a calm lake, "
    "golden sunset reflected perfectly in still water, soft warm light, "
    "cinematic anime illustration — serene, emotionally resonant, high value",

    "Early morning mist over a quiet valley, a lone figure on a stone wall, "
    "pale silver-grey light, soft colours, pastoral and cinematic, "
    "illustrated art — peaceful, beautiful, contemplative",

    "A person standing in an open sunlit field, arms open, "
    "bright blue sky with soft clouds, tall grass moving in the wind, "
    "cinematic anime illustration — freedom, release, beautifully hopeful",
]

_SCENE_POOL_INTERIOR = [
    "A person sitting alone at a window at 2am, small lamp beside them, "
    "dark room behind, soft blue moonlight outside the glass, "
    "deep navy and warm amber contrast, dark cinematic anime style — insomniac mood, beautiful",

    "A woman at a dark kitchen table, single candle glowing, "
    "surrounding deep shadow, warm amber flame on her face, "
    "dark anime illustration — intimate, quiet, emotionally resonant",

    "Someone lying on their bedroom floor looking up at a dark ceiling, "
    "single shaft of moonlight from a window across them, deep dark blue room, "
    "dark cinematic illustration — introspective, beautiful, emotionally heavy",

    "A person at a desk at night, monitor glow softly lighting their face, "
    "deep dark room around them, blue-white screen light, "
    "dark anime illustration — modern loneliness, cinematic, moody",

    "An old living room at night, one lamp in the corner, deep shadows everywhere, "
    "a person sitting still on a dark sofa, warm amber pool of light, "
    "dark cinematic illustrated style — nostalgic, quiet, emotionally rich",

    "Someone sitting on the floor against a bed, knees drawn up, "
    "single lamp glowing in the background, deep dark bedroom around them, "
    "dark anime illustration — vulnerable, intimate, beautiful",

    "A person standing in a dark kitchen doorway, one light on inside, "
    "surrounding darkness, warm amber rectangle of light, watching from the threshold, "
    "dark cinematic anime — liminal, quiet, emotionally loaded",

    "An empty dark hallway with one door ajar, soft warm light spilling through the crack, "
    "deep shadows in the corridor, "
    "dark illustrated art — mysterious, lonely, visually striking",

    "A person in a dark library, one reading lamp illuminating a small circle of books, "
    "towering dark shelves disappearing into shadow, "
    "dark cinematic anime illustration — intellectual solitude, warm and moody",

    "A dark staircase lit only by one window at the top, "
    "a figure mid-step, face in soft light and shadow, "
    "dark cinematic manga art — cinematic composition, emotionally resonant",

    "Someone asleep on a dark sofa, one blanket, lamp left on, "
    "warm amber glow, deep shadows, a quiet empty room, "
    "dark anime illustration — peaceful solitude, tender, cinematic",

    "A person in a dark bathroom, sink running, face in the mirror, "
    "single light above, deep shadow framing their reflection, "
    "dark cinematic anime illustration — self-confrontation, raw, emotionally powerful",

    # ── Day interior scenes ──
    "A woman sitting by a large bright window, morning light flooding in, "
    "coffee cup in hand, soft white and cream interior, looking outside thoughtfully, "
    "cinematic illustration — peaceful, high value, quietly emotional",

    "A person writing in a journal at a sunlit desk, "
    "warm golden morning light, books and plants around them, "
    "soft illustrated style — intimate, warm, beautifully composed",

    "An airy white bedroom in morning light, soft curtains billowing gently, "
    "a person still in bed looking up at the ceiling, pale soft tones, "
    "cinematic anime illustration — gentle melancholy, morning stillness, beautiful",
]

_SCENE_POOL_TWO_PEOPLE = [
    "Two silhouettes standing apart on a dark bridge at night, "
    "city lights reflected in water below, deep blue-black sky, "
    "dark cinematic anime style — emotional distance, atmospheric, beautiful",

    "Two people sitting on opposite ends of a dark room, "
    "one lamp between them, deep shadows, warm amber pool in the middle, "
    "dark illustrated style — unspoken tension, cinematic, emotionally heavy",

    "Two silhouettes walking in opposite directions on a dark street at night, "
    "one distant street lamp between them, deep blue-black tones, "
    "dark anime illustration — separation, melancholy, visually striking",

    "Two people sitting close together in a dark car at night, "
    "city lights glowing through rain-streaked windows, warm dashboard light, "
    "dark cinematic manga style — intimate, atmospheric, deeply emotional",

    "Two figures standing under one umbrella in the dark rain, "
    "street lamp above them, dark wet street reflecting their light, "
    "deep navy and warm amber contrast, dark anime illustration",

    "A person watching another sleep in a dark room, "
    "soft moonlight on the sleeping figure, deep shadows, "
    "dark cinematic anime — tender watching, quiet love, emotionally resonant",

    "Two people on a dark rooftop looking up at stars, lying side by side, "
    "vast dark sky above, soft ambient light, "
    "dark anime illustration — closeness, wonder, beautifully intimate",

    "Two figures in silhouette hugging on a dark empty platform, "
    "one train light in the far distance, deep blue-black tones, "
    "dark cinematic illustration — goodbye or reunion, emotionally powerful",

    "Two people at a dark cafe window, faces lit by cold rain-light outside, "
    "dim warm interior behind them, leaning toward each other, "
    "dark anime art — connection, intimacy, cinematic atmosphere",

    "A person sitting alone at a table set for two, one empty chair opposite, "
    "single candle, surrounding dark, "
    "dark cinematic illustration — absence, waiting, quietly devastating",

    # ── Two people in daytime / golden hour ──
    "Two people sitting on a grassy hill at golden hour, "
    "warm amber light on their backs, looking out over a wide valley together, "
    "cinematic anime illustration — closeness, quiet companionship, beautiful",

    "Two people walking on a sunlit coastal path, "
    "blue sky, warm afternoon light, the ocean visible below, "
    "cinematic illustrated art — belonging, peaceful, high value",
]

# Combined pool — ALL unique, no duplication
_SCENE_POOL = (
    _SCENE_POOL_CLOSEUP +
    _SCENE_POOL_WIDE +
    _SCENE_POOL_INTERIOR +
    _SCENE_POOL_TWO_PEOPLE
)

# ── Wisdom-specific scene pool — contemplative, timeless, philosophical ────────
_WISDOM_SCENE_POOL = [
    "An ancient stone library interior, warm candlelight on rows of leather books, "
    "a lone scholar reading at a wooden desk, dust motes in golden light, "
    "cinematic illustrated art — timeless, contemplative, high value",

    "A misty mountain peak at dawn, lone figure seated in meditation, "
    "soft golden light breaking through low clouds, vast quiet landscape, "
    "cinematic anime illustration — transcendent, peaceful, breathtaking",

    "An old moss-covered stone bridge in a Japanese forest, "
    "soft morning mist, ancient trees, dappled light through bamboo, "
    "cinematic illustrated art — serene, wise, deeply beautiful",

    "A wooden temple porch at golden hour, an elder seated in stillness, "
    "warm amber light on ancient wood, mountain view in background, "
    "cinematic anime illustration — timeless wisdom, peaceful, high value",

    "A narrow cobblestone courtyard in golden afternoon light, "
    "old stone walls, a single figure seated reading under a tree, "
    "warm illustrated art — contemplative, beautiful, quietly wise",

    "A lone figure on an ancient stone pathway leading into soft morning fog, "
    "tall old trees on either side, pale gold light filtering through, "
    "cinematic illustrated style — journey, wisdom, beautifully atmospheric",

    "An open-air library at sunset, warm amber light on books and pages, "
    "a peaceful figure turning the last page, golden hour sky behind, "
    "cinematic anime art — knowledge, beauty, deeply resonant",

    "An ancient lighthouse at golden dusk, sea calm and luminous, "
    "a person standing at the top looking out at a vast horizon, "
    "illustrated cinematic art — perspective, wisdom, breathtaking",

    "A quiet garden at dawn, stone lanterns lit softly, cherry blossoms falling, "
    "a lone figure in still contemplation on a wooden bench, "
    "cinematic anime illustration — peace, transience, beautifully composed",

    "Wide view of rolling golden hills at sunrise, ancient ruins on a hilltop, "
    "soft long shadows, a single figure walking toward the light, "
    "cinematic illustrated art — timeless, hopeful, deeply beautiful",

    "An old wooden writing desk by a tall window, afternoon light on an open journal, "
    "a quill pen, soft bokeh garden outside, warm golden tones, "
    "illustrated art — wisdom, introspection, beautifully quiet",

    "A meditation hall with shafts of golden light from high windows, "
    "a lone seated figure in stillness, dust motes in light, ancient stone floor, "
    "cinematic anime illustration — peace, transcendence, high value",
]

# ── Art style variants — mix of dark night, golden hour, dusk, morning ─────────
# Variety keeps viewers engaged — not every frame should look identical.
_LOVE_STYLE_VARIANTS = [
    (
        "Dark romantic anime illustration — deep navy blues, soft warm amber glow, cinematic. "
        "Two people in an intimate tender moment, soft single light source on their faces, "
        "surrounding darkness creating depth and drama. "
        "Palette: deep midnight blue, soft warm amber, gentle teal, muted rose. "
        "Style: dark cinematic anime — like 'A Silent Voice' or 'Your Name' — moody, beautiful, emotional."
    ),
    (
        "Cinematic dark romance illustration — moody, deep, intimate. "
        "Palette: deep indigo, soft amber candle glow, dark teal, midnight blue. "
        "Two people close together, warm light on their faces, dark atmospheric background. "
        "Style: dark anime film aesthetic — high contrast, emotionally resonant, visually striking."
    ),
    (
        "Dark romantic illustrated art — atmospheric and intimate. "
        "Deep blue-black backgrounds, one warm light source (candle, lamp, moon) illuminating the scene. "
        "Two people in a quiet tender moment, faces softly lit against darkness. "
        "Style: dark cinematic manga — like Makoto Shinkai films, moody and beautiful."
    ),
]

_STYLE_VARIANTS = [
    # ── Dark night / moody (classic Quietlyy aesthetic) ──
    (
        "Dark cinematic anime illustration style — moody, atmospheric, emotionally powerful. "
        "Palette: deep midnight navy, dark indigo, soft teal, warm amber glow from single light source. "
        "High contrast: rich darkness surrounding a single warm or cool light. "
        "Characters semi-visible or silhouetted, faces softly lit. "
        "Style: like 'A Silent Voice', 'Your Name', 'Violet Evergarden' — "
        "dark, cinematic, deeply emotional."
    ),
    (
        "Atmospheric dark anime illustration — cinematic and introspective. "
        "Dominant tones: deep navy blue, dark purple-indigo, muted teal, "
        "warm amber or soft moonlight as the only light source. "
        "Scenes feel like a quiet 3am moment — beautiful, heavy, still. "
        "Style: dark lo-fi anime aesthetic — introspective, premium, visually striking."
    ),
    (
        "Cinematic dark illustrated art — deep, moody, emotionally resonant. "
        "Dark rich backgrounds: midnight indigo, deep navy, soft dark teal. "
        "Single warm light source: window glow, candle, street lamp, moon. "
        "Figures partially in shadow — dramatic, intimate, real. "
        "Style: premium dark anime illustration — like Makoto Shinkai at night."
    ),
    # ── Golden hour / sunset (warm, cinematic, high value) ──
    (
        "Cinematic golden hour anime illustration — warm, atmospheric, emotionally resonant. "
        "Palette: warm amber, soft orange, golden light, long shadows, pale blue sky. "
        "Figures bathed in the last warm light of day — faces glowing, colours rich and deep. "
        "Style: Makoto Shinkai golden hour aesthetic — 'Your Name', 'Weathering With You' — "
        "warm cinematic beauty, stunningly composed, visually arresting."
    ),
    (
        "Sunset cinematic illustrated art — warm amber and rose, deeply emotional. "
        "Rich warm tones: burnt orange, soft gold, deep amber, pale lavender sky. "
        "Silhouettes and half-lit figures against a luminous sunset backdrop. "
        "Style: premium anime illustration — warm, beautiful, cinematic. "
        "The kind of frame that stops someone mid-scroll."
    ),
    # ── Soft morning / overcast (quiet, pale, melancholic) ──
    (
        "Soft morning cinematic anime illustration — quiet, pale, emotionally still. "
        "Palette: pale ivory, soft grey-blue, silver morning light, muted sage and cream. "
        "Gentle diffuse light — no harsh shadows, everything soft and hazy. "
        "Style: quiet illustrated art — like a painting, peaceful and beautifully sad."
    ),
    (
        "Overcast day cinematic illustration — muted, gentle, melancholic. "
        "Soft grey-blue tones, pale diffuse light, no harsh shadows. "
        "Figures in soft focus against quiet scenery — fields, streets, windows. "
        "Style: premium illustrated art — painterly, quiet, emotionally resonant. "
        "Beautiful in its stillness."
    ),
    # ── Dusk / blue hour ──
    (
        "Blue hour cinematic anime illustration — twilight, moody, deeply beautiful. "
        "Palette: deep blue-purple sky, soft teal, pale rose, first stars appearing. "
        "The world between day and night — uncertain, still, emotionally rich. "
        "Style: premium cinematic anime — atmospheric, introspective, visually striking."
    ),
]

# Wisdom-specific style — contemplative, timeless, warm and beautiful
_WISDOM_STYLE_VARIANTS = [
    (
        "Cinematic illustrated art with a timeless, contemplative quality. "
        "Warm golden light — morning sun, candlelight, lanterns — on ancient stone and wood. "
        "Palette: warm amber, deep walnut, soft ivory, aged gold. "
        "Style: beautifully composed, high value, like a film still from a Miyazaki masterwork — "
        "peaceful, wise, deeply beautiful."
    ),
    (
        "Golden hour cinematic illustration — ancient, contemplative, peaceful. "
        "Rich warm tones: amber, honey, deep gold, pale blue sky. "
        "Old stone, ancient paths, quiet gardens, mountain light. "
        "Style: premium illustrated art — timeless beauty, deeply resonant, visually stunning."
    ),
    (
        "Soft morning light cinematic illustration — serene, philosophical, beautiful. "
        "Pale gold dawn light on ancient architecture or nature. "
        "Misty, quiet, the world waking — peaceful and profound. "
        "Style: Ghibli-meets-cinematic-anime — warm, wise, stunningly composed."
    ),
]

_STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "used_topics.json")

def _pick_scenes_for_video(num_panels, style):
    """Pick `num_panels` scenes that were NOT used in recent videos.

    Tracks used scenes in assets/used_topics.json (same file as script rotation).
    Scene key = first 30 chars of the scene text (unique enough to identify each scene).
    Resets the exclusion list when < num_panels fresh scenes remain.
    """
    # Load state
    state = {}
    if os.path.exists(_STATE_PATH):
        try:
            with open(_STATE_PATH) as f:
                state = json.load(f)
        except Exception:
            pass

    used_keys = set(state.get("used_scene_keys", []))
    if style == "love":
        pool = _LOVE_SCENE_POOL
    elif style == "wisdom":
        pool = _WISDOM_SCENE_POOL
    else:
        pool = _SCENE_POOL

    def key(s):
        return s[:30]

    available = [s for s in pool if key(s) not in used_keys]
    if len(available) < num_panels:
        # All scenes exhausted — start fresh
        print(f"[images] All scenes used — resetting scene history")
        used_keys = set()
        available = list(pool)

    # Pick num_panels scenes without replacement
    chosen = random.sample(available, min(num_panels, len(available)))
    # If pool smaller than num_panels (love pool has 10 scenes), allow some repeat
    while len(chosen) < num_panels:
        chosen.append(random.choice(pool))

    # Save updated used keys
    new_keys = [key(s) for s in chosen]
    updated = list(used_keys) + new_keys
    state["used_scene_keys"] = updated[-80:]  # keep last 80 (covers ~10 videos of 8 panels)
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)

    print(f"[images] Scenes picked: {len(chosen)} fresh ({len(available)} were available from {len(pool)} total)")
    return chosen


# Love-specific scene pool — dark romantic couple art (Whispers of Heart style)
_LOVE_SCENE_POOL = [
    "A couple close together in the dark, one resting head on the other's shoulder, soft moonlight",
    "Two people facing each other, eyes closed, foreheads almost touching, intimate and quiet",
    "A person holding another from behind, both looking out at a dark night sky with stars",
    "Close-up of two hands intertwined, soft diffuse light, dark background",
    "A couple sitting together in silence, one lamp casting warm light, dark room around them",
    "Side profile of two people about to kiss, soft light on faces, everything else in shadow",
    "A person leaning into another's neck, eyes closed, peaceful and safe, dark background",
    "Two silhouettes standing close in rain at night, street lamp behind them, reflections below",
    "Close-up of a face being cradled gently by two hands, eyes closed, tender moment",
    "Two people lying close, one watching the other sleep, soft window light, night outside",
]


def generate_image_prompt(topic, visual_keywords, scene, style="emotional"):
    """Build the full DALL-E prompt for one panel given a pre-selected scene."""
    keywords_str = ", ".join(visual_keywords)
    if style == "love":
        chosen_style = random.choice(_LOVE_STYLE_VARIANTS)
    elif style == "wisdom":
        chosen_style = random.choice(_WISDOM_STYLE_VARIANTS)
    else:
        chosen_style = random.choice(_STYLE_VARIANTS)
    return (
        f"{chosen_style} "
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
    """Generate image using OpenAI gpt-image-1 API.
    Migrated from dall-e-3 which is deprecated May 12 2026.
    Uses 1024x1536 native portrait — no cropping needed."""
    import base64
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
                    "model": "gpt-image-1",
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1536",   # native portrait — no crop needed
                    "quality": "medium",   # low/medium/high (was standard/hd)
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            item = data["data"][0]

            # gpt-image-1 returns b64_json; fall back to url if present
            if "b64_json" in item:
                img_data = base64.b64decode(item["b64_json"])
            elif "url" in item:
                img_resp = requests.get(item["url"], timeout=30)
                img_resp.raise_for_status()
                img_data = img_resp.content
            else:
                continue

            if len(img_data) < 5000:
                continue
            with open(output_path, "wb") as f:
                f.write(img_data)

            # Resize to exactly 1080x1920 (aspect is already 9:16)
            # Brighten by 30% — keeps dark cinematic mood but objects visible in daylight
            from PIL import Image as PILImage, ImageEnhance
            img = PILImage.open(output_path).convert("RGB")
            img = ImageEnhance.Brightness(img).enhance(1.3)
            img = img.resize((1080, 1920), PILImage.LANCZOS)
            img.save(output_path)
            return True
        except Exception as e:
            print(f"[images] gpt-image-1 attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(3)
    return False


def generate_with_gemini_imagen(prompt, output_path):
    """Fallback: Google Imagen 3 via Gemini API (uses GEMINI_API_KEY).
    Replaces DALL-E 3 which was deprecated May 2026."""
    import base64
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return False
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict?key={key}",
            headers={"Content-Type": "application/json"},
            json={
                "instances": [{"prompt": prompt[:2000]}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": "9:16",
                    "safetyFilterLevel": "block_only_high",
                },
            },
            timeout=90,
        )
        resp.raise_for_status()
        predictions = resp.json().get("predictions", [])
        if not predictions:
            print("[images]   Gemini Imagen: no predictions returned")
            return False
        b64 = predictions[0].get("bytesBase64Encoded")
        if not b64:
            return False
        img_data = base64.b64decode(b64)
        if len(img_data) < 5000:
            return False
        with open(output_path, "wb") as f:
            f.write(img_data)
        from PIL import Image as PILImage, ImageEnhance
        img = PILImage.open(output_path).convert("RGB")
        img = ImageEnhance.Brightness(img).enhance(1.3)
        img = img.resize((1080, 1920), PILImage.LANCZOS)
        img.save(output_path)
        print("[images]   Gemini Imagen 3 fallback succeeded")
        return True
    except Exception as e:
        print(f"[images]   Gemini Imagen fallback failed: {e}")
        return False


def generate_images(topic, visual_keywords, num_panels=5, style="emotional"):
    """Generate panel images using DALL-E ONLY.
    - Max 5 panels per video
    - DALL-E is the only generator — no stock photos or gradients
    - If DALL-E fails for a panel, reuse an earlier successful panel from same video
    - After 25 gallery images: reuse 2-3 panels (never panel 0)
    - Saves new images to gallery (capped at 500)
    At least 1 image must succeed or pipeline fails."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    num_panels = min(num_panels, 8)  # Hard cap at 8 — enough for poetic scripts
    paths = []
    successful_paths = []  # Track successfully generated images for reuse within this video

    # Check if we should reuse some panels from gallery
    reuse_map = _pick_reuse_panels(num_panels)

    # Pick unique scenes for this video — never reuses scenes from recent videos
    scenes = _pick_scenes_for_video(num_panels, style)

    for i in range(num_panels):
        output_path = os.path.join(OUTPUT_DIR, f"panel_{i}.png")

        # Use reused gallery image if assigned
        if i in reuse_map:
            shutil.copy2(reuse_map[i], output_path)
            paths.append(output_path)
            continue

        # Generate fresh image with DALL-E
        prompt = generate_image_prompt(topic, visual_keywords, scenes[i], style=style)
        print(f"[images] Panel {i+1}/{num_panels}: generating with DALL-E...")

        success = generate_with_dalle(prompt, output_path)
        if not success:
            print(f"[images]   gpt-image-1 failed — trying Gemini Imagen 3 fallback...")
            success = generate_with_gemini_imagen(prompt, output_path)

        if success:
            print(f"[images] Panel {i+1}: generated")
            successful_paths.append(output_path)
        else:
            # Both models failed — reuse an earlier panel from THIS video
            if successful_paths:
                reuse_src = random.choice(successful_paths)
                shutil.copy2(reuse_src, output_path)
                print(f"[images] Panel {i+1}: reusing earlier panel (both models failed)")
            else:
                raise RuntimeError(f"Image generation failed for panel {i+1} (tried gpt-image-1 and dall-e-3). No earlier panels to reuse.")

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
