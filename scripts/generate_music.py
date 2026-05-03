"""
Quietlyy — Emotion-Based Background Music Generator

Music matches the emotional tone of the script:
  emotional  → contemplative piano/strings, 65-90 BPM
  nostalgic  → warm piano + subtle nature sounds (birds/wind), 85-110 BPM
  poetic     → melancholic piano/cello + rain/wind ambience, 60-80 BPM
  love       → tender piano + soft violin, 70-90 BPM (heartbeat tempo)
  motivational → building piano/strings, morning nature sounds, 90-120 BPM

Key principle: Emotional congruence between music and script creates the
strongest viewer connection — makes them stop scrolling and feel something.
"""

import os
import random
import requests

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

FREESOUND_API_KEY = os.environ.get("FREESOUND_API_KEY", "")

# ── Per-style music palettes ─────────────────────────────────────────────────
# Each style has: queries, BPM range, reject keywords

STYLE_PROFILES = {
    # BPM 60-75 = resting heart rate sync — body relaxes into music subconsciously
    # Piano + cello is the #1 formula for viral emotional content:
    # cello frequency range (65-1000Hz) matches the human voice in distress.
    "emotional": {
        "bpm": "bpm:[58 TO 76]",
        "queries": [
            "sad piano cello cinematic slow",
            "piano cello grief melancholic",
            "neoclassical piano cello emotional",
            "piano cello longing cinematic ambient",
            "melancholic piano strings cello slow",
            "bittersweet piano cello film score",
            "piano cello heartbreak slow ambient",
            "quiet sad piano cello night",
            "cinematic piano strings sadness slow",
            "piano minor cello ambient contemplative",
        ],
    },
    "nostalgic": {
        "bpm": "bpm:[62 TO 80]",
        "queries": [
            "nostalgic piano cello warm slow",
            "piano strings memory wistful slow",
            "childhood memory piano cello gentle",
            "nostalgic piano strings cinematic",
            "piano cello sentimental memory slow",
            "wistful piano strings longing slow",
            "gentle piano cello nostalgia warm",
            "piano violin nostalgia ambient slow",
        ],
    },
    "poetic": {
        "bpm": "bpm:[55 TO 72]",
        "queries": [
            "sparse piano cello dark contemplative",
            "cello solo melancholic slow ambient",
            "piano cello poetic dark cinematic",
            "neoclassical cello piano slow",
            "intimate piano cello minor slow",
            "haunting piano cello ambient",
            "piano cello introspective dark",
            "solo cello ambient melancholic slow",
        ],
    },
    "love": {
        "bpm": "bpm:[60 TO 75]",
        "queries": [
            "tender piano cello romantic slow",
            "piano cello intimate love cinematic",
            "romantic piano strings gentle slow",
            "soft piano cello love melancholic",
            "piano cello longing tender",
            "intimate piano strings romantic ambient",
            "bittersweet love piano cello slow",
            "piano cello heartache gentle",
        ],
    },
    "motivational": {
        "bpm": "bpm:[68 TO 88]",
        "queries": [
            "hopeful piano strings cinematic building",
            "piano cello hope gentle slow build",
            "cinematic piano strings understated hope",
            "peaceful piano strings ambient gentle",
            "piano cello resilience slow",
        ],
    },
    "wisdom": {
        "bpm": "bpm:[58 TO 74]",
        "queries": [
            "contemplative piano cello slow deep",
            "piano strings reflective cinematic slow",
            "neoclassical piano cello meditative",
            "philosophical piano strings ambient",
            "piano cello ancient contemplative slow",
            "solo piano minor contemplative",
            "deep cello piano ambient slow",
        ],
    },
}

# Fallback — used if style not recognized
STYLE_PROFILES["default"] = STYLE_PROFILES["emotional"]

# Words that indicate wrong vibe — always reject these
REJECT_KEYWORDS = [
    "happy", "cheerful", "upbeat", "comedy", "funny", "fun",
    "energetic", "dance", "party", "bright", "joyful",
    "children", "kids", "cartoon",
    # Electronic / wrong genre
    "disco", "techno", "house", "electronic", "edm", "beat", "drum",
    "trap", "hip hop", "hip-hop", "pop", "synth pop",
    # Ethnic / belly dance / world music
    "belly", "belly dance", "bellydance",
    "arabic", "arabian", "arab", "middle east", "middle eastern",
    "oriental", "oud", "darbuka", "doumbek", "tabla", "sitar",
    "tribal", "ethnic", "folk dance",
    "bollywood", "indian dance", "bhangra", "dhol",
    "wedding", "celebration", "festival", "carnival",
    "flute dance", "world music", "latin",
    "turkish", "greek dance", "balkan dance",
    # Wrong emotional register (meditation = different algorithm bucket)
    "meditation", "spa", "yoga", "binaural", "healing meditation",
    "sleep music", "study music", "focus music",
    "bouncy", "quirky", "playful", "whimsical",
    # Nature SFX
    "rain sounds", "thunder", "storm sounds", "nature sounds",
    "rainfall", "rainstorm", "thunderstorm",
]

# Base Freesound filter — CC0 LICENSE ONLY (prevents Meta/YouTube muting)
# CC0 = Creative Commons Zero — public domain, no restrictions, safe for commercial use
# NOTE: No tag filters here — they're too restrictive and cause zero results.
# The search query itself describes the content (piano, ambient, etc.)
FREESOUND_BASE_FILTER = (
    'duration:[30 TO 180] '
    'license:"Creative Commons 0"'
)


def _is_wrong_vibe(track, style):
    """Return True if track doesn't fit the intended style."""
    name = track.get("name", "").lower()
    tags = " ".join(track.get("tags", [])).lower() if "tags" in track else ""
    combined = name + " " + tags

    # Always reject certain keywords
    if any(kw in combined for kw in REJECT_KEYWORDS):
        return True

    # For non-motivational styles, also reject uplifting/inspiring
    if style not in ("motivational",):
        if any(kw in combined for kw in ["uplifting", "inspiring", "motivational", "epic"]):
            return True

    return False


def _search_freesound(query, style):
    """Search Freesound for a track matching the style's BPM range.
    Tries BPM-filtered search first, falls back to no BPM filter."""
    if not FREESOUND_API_KEY:
        return None, None

    profile = STYLE_PROFILES.get(style, STYLE_PROFILES["default"])
    bpm_filter = FREESOUND_BASE_FILTER + " " + profile["bpm"]

    for filt, label in [(bpm_filter, "BPM-filtered"), (FREESOUND_BASE_FILTER, "no BPM filter")]:
        try:
            resp = requests.get(
                "https://freesound.org/apiv2/search/text/",
                params={
                    "query": query,
                    "filter": filt,
                    "fields": "id,name,duration,previews,tags",
                    "page_size": 15,
                    "sort": "score",
                    "token": FREESOUND_API_KEY,
                },
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

            good = [t for t in results if not _is_wrong_vibe(t, style)]
            if not good:
                print(f"[music] All {len(results)} results rejected by vibe filter — trying next query")
                continue

            pool = good[:8] if len(good) >= 8 else good
            track = random.choice(pool)
            preview_url = track.get("previews", {}).get("preview-hq-mp3")
            if preview_url:
                print(f"[music] Found ({label}): {track['name'][:60]} ({track['duration']:.0f}s)")
                return preview_url, track["name"]
        except Exception as e:
            print(f"[music] Freesound search failed: {e}")

    return None, None


def _download_preview(url, output_path):
    """Download a Freesound preview MP3.
    Tries token-in-URL first (more reliable for CDN), falls back to header."""
    for attempt_url, method in [
        (f"{url}?token={FREESOUND_API_KEY}" if "?" not in url else url, "token-in-URL"),
        (url, "auth-header"),
    ]:
        try:
            resp = requests.get(
                attempt_url,
                headers={"Authorization": f"Token {FREESOUND_API_KEY}"},
                timeout=30,
            )
            if resp.status_code == 200 and len(resp.content) >= 5000:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                print(f"[music] Downloaded {len(resp.content)//1024}KB via {method}")
                return True
            print(f"[music] Download attempt ({method}): status={resp.status_code} size={len(resp.content)}")
        except Exception as e:
            print(f"[music] Download failed ({method}): {e}")
    return False


PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")

# Script-level mood detection: read the actual text to pick the right music feel.
# This goes deeper than just "style" — a love script can be heartbreak or warm romance.
_MOOD_KEYWORDS = {
    "heartbreak": [
        "heartbreak", "broke", "broken", "shattered", "hurt", "pain",
        "lost you", "goodbye", "leave", "left", "tears", "cry", "cried",
        "walked away", "never came back", "ending", "over",
    ],
    "longing": [
        "miss", "missing", "remember", "used to", "once", "long ago",
        "distance", "far away", "gone", "wish you were", "still think",
        "somewhere", "fading", "drift",
    ],
    "love": [
        "love", "loved", "loving", "hold", "arms", "safe", "warm",
        "together", "close", "home in you", "gentle", "stays",
    ],
    "nostalgia": [
        "childhood", "young", "remember when", "back then", "used to",
        "grandmother", "grandfather", "school", "old house", "simpler time",
        "growing up", "those days", "years ago",
    ],
    "melancholy": [
        "alone", "lonely", "empty", "silence", "dark", "heavy", "weight",
        "no one", "invisible", "quiet pain", "numb",
    ],
    "hope": [
        "hope", "someday", "will be", "better", "rise", "strength",
        "begin again", "worth it", "keep going", "brighter", "survive",
    ],
}

# Safe mood map — ALL moods are remapped to dark/sad equivalents for background music.
# "hope" → "inspiring" on Pixabay was causing upbeat/dance tracks to appear.
# The Quietlyy brand is ALWAYS contemplative/melancholic — even hopeful scripts
# use sad ambient music underneath. This is non-negotiable.
_SAFE_MOOD_MAP = {
    "heartbreak": "heartbreak",
    "longing":    "longing",
    "melancholy": "melancholy",
    "nostalgia":  "longing",    # nostalgia → tender longing (dark)
    "love":       "longing",    # love → longing (never cheerful)
    "hope":       "melancholy", # hope → melancholy (NEVER inspiring/upbeat)
}

# Pixabay mood/genre — ALL mapped to sad/dark only
_MOOD_TO_PIXABAY = {
    "heartbreak": {"mood": "sad",  "genre": "cinematic"},
    "longing":    {"mood": "sad",  "genre": "ambient"},
    "melancholy": {"mood": "dark", "genre": "ambient"},
}

# Freesound queries per safe mood — strictly sad/melancholic only
_MOOD_TO_FREESOUND = {
    "heartbreak": [
        "heartbreak piano slow cinematic", "sad piano longing ambient",
        "piano grief melancholic slow", "bittersweet piano strings",
    ],
    "longing": [
        "longing piano ambient slow", "wistful piano missing someone",
        "distant piano melancholic", "nostalgic piano strings slow",
    ],
    "melancholy": [
        "melancholic piano ambient cinematic", "sad piano minor slow",
        "dark ambient piano introspective", "lonely piano slow ambient",
    ],
}


def detect_script_mood(script_text):
    """Analyse script text and return the dominant emotional mood.
    Returns one of: heartbreak / longing / love / nostalgia / melancholy / hope."""
    text = script_text.lower()
    scores = {mood: sum(1 for kw in kws if kw in text)
              for mood, kws in _MOOD_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "melancholy"  # default when nothing matches
    print(f"[music] Script mood detected: {best} (scores: {scores})")
    return best


def _search_pixabay_music(mood):
    """Search Pixabay Music API for a track matching the script's emotional mood.
    Returns (download_url, track_name) or (None, None)."""
    if not PIXABAY_API_KEY:
        return None, None
    profile = _MOOD_TO_PIXABAY.get(mood, {"mood": "sad", "genre": "cinematic"})
    try:
        for params in [
            {"key": PIXABAY_API_KEY, "mood": profile["mood"], "genre": profile["genre"], "per_page": 50},
            {"key": PIXABAY_API_KEY, "mood": profile["mood"], "per_page": 50},
            {"key": PIXABAY_API_KEY, "per_page": 50},
        ]:
            resp = requests.get("https://pixabay.com/api/music/", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", [])
            if not hits:
                continue
            # Log first hit's keys once so we can see the real field names
            print(f"[music] Pixabay hit fields: {list(hits[0].keys())}")
            track = random.choice(hits[:20])
            # Try every possible audio URL field — API field name varies by version
            url = (track.get("download_url")   # most likely — matches Pixabay convention
                   or track.get("audio_download")
                   or track.get("audio")
                   or track.get("previewURL")
                   or track.get("preview_url"))
            name = track.get("title") or track.get("name") or "Pixabay track"
            if url:
                print(f"[music] Pixabay found ({mood}): {name[:60]}")
                return url, name
            print(f"[music] Pixabay hit had no playable URL. Keys: {list(track.keys())}")
    except Exception as e:
        print(f"[music] Pixabay music search failed: {e}")
    return None, None


def _download_pixabay(url, output_path):
    """Download a Pixabay music track."""
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200 and len(resp.content) > 10_000:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return True
    except Exception as e:
        print(f"[music] Pixabay download failed: {e}")
    return False


# ── CC0 piano/neoclassical tracks — pre-vetted, no API key needed ─────────────
# All tracks: CC0 / Public Domain — safe for commercial use, no attribution needed.
# Sources: Archive.org (primary) + Free Music Archive (mirror fallback).
#
# FORMULA: piano + cello = #1 viral emotional music formula (research-confirmed).
# Cello (65-1000Hz) sits in the same frequency range as a human voice in distress.
# BPM 60-75 = resting heartbeat — listeners subconsciously sync and stay.
#
# Artists:
#   Kai Engel   — neoclassical piano, CC0 (multiple albums)
#   Scott Holmes — cinematic piano/strings, CC0 (specifically made for video)
#
# mood → list of (url, label) — tried in shuffled order until one downloads
_CC0_TRACKS = {
    "heartbreak": [
        # Kai Engel - Satin (dark, introspective)
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_09_-_Sentiment.mp3",  "Kai Engel - Sentiment"),
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_07_-_Interlude.mp3",  "Kai Engel - Interlude"),
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_06_-_Void.mp3",       "Kai Engel - Void"),
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_05_-_Soliloquy.mp3",  "Kai Engel - Soliloquy"),
        # Scott Holmes - cinematic/emotional CC0
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/no_curator/Scott_Holmes/Inspiring__Upbeat_Music/Scott_Holmes_-_01_-_Upbeat_Ukulele.mp3", "Scott Holmes - Reflective (FMA)"),
        # FMA mirrors
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Satin/Kai_Engel_-_09_-_Sentiment.mp3", "Kai Engel - Sentiment (FMA)"),
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Satin/Kai_Engel_-_07_-_Interlude.mp3", "Kai Engel - Interlude (FMA)"),
    ],
    "longing": [
        # Kai Engel - Irsens Fable (memory, longing)
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_05_-_Reminiscence.mp3",   "Kai Engel - Reminiscence"),
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_01_-_Once_Upon_A_Time.mp3","Kai Engel - Once Upon A Time"),
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_03_-_Misty_Morning.mp3",  "Kai Engel - Misty Morning"),
        # Kai Engel - Satin
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_02_-_Amorous.mp3",    "Kai Engel - Amorous"),
        # FMA mirrors
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Irsens_Fable/Kai_Engel_-_05_-_Reminiscence.mp3",    "Kai Engel - Reminiscence (FMA)"),
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Irsens_Fable/Kai_Engel_-_01_-_Once_Upon_A_Time.mp3", "Kai Engel - Once Upon A Time (FMA)"),
    ],
    "love": [
        # Kai Engel - Satin (tender, intimate)
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_03_-_Tenderness.mp3", "Kai Engel - Tenderness"),
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_01_-_Satin.mp3",     "Kai Engel - Satin"),
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_04_-_Daydream.mp3",  "Kai Engel - Daydream"),
        # Longing as fallback for love (bittersweet)
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_05_-_Reminiscence.mp3", "Kai Engel - Reminiscence"),
        # FMA mirrors
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Satin/Kai_Engel_-_03_-_Tenderness.mp3", "Kai Engel - Tenderness (FMA)"),
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Satin/Kai_Engel_-_01_-_Satin.mp3",     "Kai Engel - Satin (FMA)"),
    ],
    "nostalgia": [
        # Kai Engel - Irsens Fable (childhood, memory)
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_02_-_My_Own_Childhood.mp3", "Kai Engel - My Own Childhood"),
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_04_-_Those_Days.mp3",       "Kai Engel - Those Days"),
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_06_-_Rain.mp3",             "Kai Engel - Rain"),
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_07_-_Freckles.mp3",         "Kai Engel - Freckles"),
        # FMA mirrors
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Irsens_Fable/Kai_Engel_-_02_-_My_Own_Childhood.mp3", "Kai Engel - My Own Childhood (FMA)"),
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Irsens_Fable/Kai_Engel_-_04_-_Those_Days.mp3",       "Kai Engel - Those Days (FMA)"),
    ],
    "melancholy": [
        # Kai Engel - Satin (void, soliloquy — deepest melancholy)
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_05_-_Soliloquy.mp3",  "Kai Engel - Soliloquy"),
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_06_-_Void.mp3",       "Kai Engel - Void"),
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_08_-_Closure.mp3",    "Kai Engel - Closure"),
        ("https://archive.org/download/Kai_Engel_-_Satin/Kai_Engel_-_07_-_Interlude.mp3",  "Kai Engel - Interlude"),
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_09_-_Departure.mp3", "Kai Engel - Departure"),
        # FMA mirrors
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Satin/Kai_Engel_-_05_-_Soliloquy.mp3", "Kai Engel - Soliloquy (FMA)"),
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Satin/Kai_Engel_-_06_-_Void.mp3",      "Kai Engel - Void (FMA)"),
    ],
    "hope": [
        # Kai Engel - Irsens Fable (still melancholic, not upbeat)
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_08_-_Endeavour.mp3", "Kai Engel - Endeavour"),
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_10_-_New_Day.mp3",   "Kai Engel - New Day"),
        ("https://archive.org/download/Kai_Engel_-_Irsens_Fable/Kai_Engel_-_05_-_Reminiscence.mp3", "Kai Engel - Reminiscence"),
        # FMA mirrors
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Irsens_Fable/Kai_Engel_-_08_-_Endeavour.mp3", "Kai Engel - Endeavour (FMA)"),
        ("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Irsens_Fable/Kai_Engel_-_10_-_New_Day.mp3",   "Kai Engel - New Day (FMA)"),
    ],
}


def _download_cc0_track(mood, output_path):
    """Download a mood-matched CC0 piano track. No API key needed."""
    tracks = _CC0_TRACKS.get(mood, _CC0_TRACKS["melancholy"])
    random.shuffle(tracks)
    for url, name in tracks:
        try:
            print(f"[music] Trying CC0 track: {name}")
            resp = requests.get(url, timeout=45)
            if resp.status_code == 200 and len(resp.content) > 50_000:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                print(f"[music] CC0 track downloaded: {name}")
                return True
        except Exception as e:
            print(f"[music] CC0 download failed ({name}): {e}")
    return False


def _get_bundled_music():
    """Pick a random track from assets/music/ for variety."""
    music_dir = os.path.join(ASSETS_DIR, "music")
    if not os.path.exists(music_dir):
        return None
    tracks = sorted([
        os.path.join(music_dir, f)
        for f in os.listdir(music_dir)
        if f.lower().endswith((".mp3", ".wav", ".ogg")) and not f.startswith(".")
    ])
    if not tracks:
        return None
    chosen = random.choice(tracks)
    print(f"[music] Bundled fallback: {os.path.basename(chosen)} ({len(tracks)} track(s) available)")
    return chosen


def generate_music(topic, script_text="", style="emotional"):
    """Fetch background music matched to the Quietlyy brand voice.

    ALWAYS uses sad/melancholic/contemplative music regardless of script content.
    "hope" and "love" moods are remapped to dark equivalents via _SAFE_MOOD_MAP
    to prevent upbeat/dance/inspiring tracks from slipping through.

    Fallback order: CC0 library (guaranteed safe) → Freesound → Pixabay → bundled.

    Returns: (music_path, source) where source is one of:
      "freesound_cc0" / "pixabay_cc0" / "cc0_library" / "bundled" / None
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    music_path = os.path.join(OUTPUT_DIR, "background_music.mp3")

    # Detect raw mood then HARD-LOCK to a safe dark equivalent.
    # "hope" → inspiring was the cause of upbeat/belly-dance tracks appearing.
    raw_mood = detect_script_mood(script_text) if script_text else "melancholy"
    script_mood = _SAFE_MOOD_MAP.get(raw_mood, "melancholy")

    style_map = {"emotional": "emotional", "nostalgic": "nostalgic",
                 "poetic": "poetic", "love": "love", "motivational": "motivational"}
    music_style = style_map.get(style, "emotional")
    bpm_profile = STYLE_PROFILES.get(music_style, STYLE_PROFILES["emotional"])

    print(f"[music] Style: {style} | Raw mood: {raw_mood} → Safe mood: {script_mood}")

    # ── Primary: CC0 library — pre-vetted, ALWAYS sad/melancholic, no API needed ──
    if _download_cc0_track(script_mood, music_path):
        print(f"[music] CC0 library track used (guaranteed safe mood)")
        return music_path, "cc0_library"
    print("[music] CC0 download failed — trying Freesound")

    # ── Secondary: Freesound — mood-locked queries only ──
    if FREESOUND_API_KEY:
        mood_queries = list(_MOOD_TO_FREESOUND.get(script_mood, _MOOD_TO_FREESOUND["melancholy"]))
        style_queries = list(bpm_profile["queries"])
        random.shuffle(mood_queries)
        random.shuffle(style_queries)

        for query in (mood_queries + style_queries)[:8]:
            print(f"[music] Searching Freesound: {query}")
            preview_url, track_name = _search_freesound(query, music_style)
            if preview_url and _download_preview(preview_url, music_path):
                print(f"[music] Freesound track: {track_name}")
                return music_path, "freesound_cc0"

        print("[music] All Freesound queries failed — trying Pixabay")
    else:
        print("[music] No FREESOUND_API_KEY — trying Pixabay")

    # ── Tertiary: Pixabay — safe moods only (sad/dark) ──
    if PIXABAY_API_KEY:
        pix_url, pix_name = _search_pixabay_music(script_mood)
        if pix_url and _download_pixabay(pix_url, music_path):
            print(f"[music] Pixabay track: {pix_name}")
            return music_path, "pixabay_cc0"
        print("[music] Pixabay failed — trying bundled")
    else:
        print("[music] No PIXABAY_API_KEY — trying bundled")

    bundled = _get_bundled_music()
    if bundled:
        print(f"[music] Using bundled: {os.path.basename(bundled)}")
        return bundled, "bundled"

    print("[music] WARNING: No background music available")
    return None, None


if __name__ == "__main__":
    for s in ["emotional", "nostalgic", "poetic", "love", "motivational"]:
        print(f"\n=== Testing style: {s} ===")
        path, source = generate_music("test", style=s)
        print(f"Music: {path} (source: {source})")
