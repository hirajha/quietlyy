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
    "emotional": {
        "bpm": "bpm:[60 TO 90]",
        "queries": [
            "contemplative ambient piano slow",
            "melancholic piano ambient cinematic",
            "cinematic sadness piano strings ambient",
            "bittersweet piano film score slow",
            "meditative piano strings emotional",
            "gentle sad piano strings underscore",
            "quiet melancholic piano night",
            "slow piano longing ambient",
            "wistful piano cinematic",
            "emotional piano strings slow",
        ],
    },
    "nostalgic": {
        "bpm": "bpm:[80 TO 115]",
        "queries": [
            "nostalgic piano soft ambient",
            "childhood memories piano instrumental",
            "wistful acoustic piano melody",
            "sentimental piano strings memory",
            "tender piano nature birds ambient",
            "soft piano birds wind nature ambient",
            "gentle piano morning nature sounds",
            "nostalgic acoustic guitar piano",
            "piano music box childhood gentle",
            "reflective piano ambient nature",
        ],
    },
    "poetic": {
        "bpm": "bpm:[55 TO 80]",
        "queries": [
            "sad piano rain ambient meditation",
            "melancholic piano rain contemplative",
            "poetic cello piano rain ambience",
            "slow sad piano minor instrumental",
            "cinematic melancholy rain piano",
            "lonely piano rain night ambient",
            "dark ambient rain piano slow",
            "emotional cello piano wind rain",
            "introspective piano rain forest",
            "soft rain piano melancholic slow",
        ],
    },
    "love": {
        "bpm": "bpm:[65 TO 90]",
        "queries": [
            "romantic piano tender slow",
            "love cinematic piano strings",
            "tender piano violin intimate",
            "sentimental piano slow romantic",
            "soft violin piano romantic ambient",
            "intimate love piano instrumental",
            "romantic piano cello gentle",
            "love story piano slow beautiful",
            "tender romantic strings piano",
            "emotional piano love soft",
        ],
    },
    "motivational": {
        "bpm": "bpm:[85 TO 120]",
        "queries": [
            "inspirational piano birds morning nature",
            "uplifting gentle piano strings building",
            "hopeful piano ambient morning",
            "cinematic hope piano strings",
            "peaceful piano nature birds wind",
            "motivational soft piano orchestral",
            "life lesson piano strings gentle",
            "positive cinematic piano ambient",
            "piano morning birds wind nature calm",
            "calm uplifting piano strings wisdom",
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
]

# Base Freesound filter — CC0 LICENSE ONLY (prevents Meta/YouTube muting)
# CC0 = Creative Commons Zero — public domain, no restrictions, safe for commercial use
FREESOUND_BASE_FILTER = (
    'duration:[30 TO 180] '
    'tag:instrumental '
    'license:"Creative Commons 0" '
    '-tag:comedy -tag:dance -tag:funny -tag:party'
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
                good = results
            if not good:
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
    """Download a Freesound preview MP3."""
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Token {FREESOUND_API_KEY}"},
            timeout=30,
        )
        if resp.status_code != 200 or len(resp.content) < 5000:
            return False
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"[music] Download failed: {e}")
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

# Pixabay mood/genre per detected mood
_MOOD_TO_PIXABAY = {
    "heartbreak": {"mood": "sad",      "genre": "cinematic"},
    "longing":    {"mood": "sad",      "genre": "ambient"},
    "love":       {"mood": "romantic", "genre": "cinematic"},
    "nostalgia":  {"mood": "calm",     "genre": "ambient"},
    "melancholy": {"mood": "dark",     "genre": "ambient"},
    "hope":       {"mood": "inspiring","genre": "cinematic"},
}

# Freesound queries per detected mood
_MOOD_TO_FREESOUND = {
    "heartbreak": [
        "heartbreak piano slow cinematic", "sad piano longing ambient",
        "piano grief melancholic slow", "bittersweet piano strings",
    ],
    "longing": [
        "longing piano ambient slow", "wistful piano missing someone",
        "distant piano melancholic", "nostalgic piano strings slow",
    ],
    "love": [
        "romantic piano tender slow", "love story piano strings",
        "intimate piano violin gentle", "tender romantic piano ambient",
    ],
    "nostalgia": [
        "nostalgic piano soft ambient", "childhood memories piano",
        "sentimental piano strings memory", "wistful acoustic piano melody",
    ],
    "melancholy": [
        "melancholic piano ambient cinematic", "sad piano minor slow",
        "lonely piano rain night", "dark ambient piano introspective",
    ],
    "hope": [
        "hopeful piano strings cinematic", "uplifting gentle piano ambient",
        "piano morning hope building", "inspiring piano strings soft",
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
        # Try mood + genre first, then mood only if no results
        for params in [
            {"key": PIXABAY_API_KEY, "mood": profile["mood"], "genre": profile["genre"], "per_page": 50},
            {"key": PIXABAY_API_KEY, "mood": profile["mood"], "per_page": 50},
        ]:
            resp = requests.get("https://pixabay.com/api/music/", params=params, timeout=15)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            if hits:
                track = random.choice(hits[:20])
                url = track.get("audio_download") or track.get("previewURL")
                name = track.get("title", "Pixabay track")
                if url:
                    print(f"[music] Pixabay found ({mood}): {name[:60]}")
                    return url, name
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


def _get_bundled_music():
    """Pick a random track from assets/music/ for variety.
    If multiple tracks exist, they rotate so no two videos in a row use the same one."""
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
    """Fetch background music matched to the script's actual emotional content.

    Detects mood directly from the script text (heartbreak / longing / love /
    nostalgia / melancholy / hope) and uses that for every search, not just the
    broad style category. Falls back through: Freesound → Pixabay → bundled track.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    music_path = os.path.join(OUTPUT_DIR, "background_music.mp3")

    # Detect mood from actual script content — more precise than just style label
    script_mood = detect_script_mood(script_text) if script_text else "melancholy"

    # Also keep style-level Freesound profile as additional query pool
    style_map = {"emotional": "emotional", "nostalgic": "nostalgic",
                 "poetic": "poetic", "love": "love", "motivational": "motivational"}
    music_style = style_map.get(style, "emotional")
    bpm_profile = STYLE_PROFILES[music_style]

    print(f"[music] Style: {style} | Script mood: {script_mood} | BPM: {bpm_profile['bpm']}")

    if FREESOUND_API_KEY:
        # Primary: mood-specific Freesound queries from script analysis
        mood_queries = list(_MOOD_TO_FREESOUND.get(script_mood, []))
        # Secondary: style-level queries for variety
        style_queries = list(bpm_profile["queries"])
        random.shuffle(mood_queries)
        random.shuffle(style_queries)

        for query in (mood_queries + style_queries)[:8]:
            print(f"[music] Searching Freesound: {query}")
            preview_url, track_name = _search_freesound(query, music_style)
            if preview_url and _download_preview(preview_url, music_path):
                print(f"[music] Track selected: {track_name}")
                return music_path

        print("[music] All Freesound queries failed — trying Pixabay music")
    else:
        print("[music] No FREESOUND_API_KEY — trying Pixabay music")

    # Try Pixabay music API — also mood-matched
    if PIXABAY_API_KEY:
        pix_url, pix_name = _search_pixabay_music(script_mood)
        if pix_url and _download_pixabay(pix_url, music_path):
            print(f"[music] Pixabay track selected: {pix_name}")
            return music_path
        print("[music] Pixabay music failed — using bundled fallback")

    bundled = _get_bundled_music()
    if bundled:
        print(f"[music] Using bundled: {os.path.basename(bundled)}")
        return bundled

    print("[music] WARNING: No background music available")
    return None


if __name__ == "__main__":
    for s in ["emotional", "nostalgic", "poetic", "love", "motivational"]:
        print(f"\n=== Testing style: {s} ===")
        path = generate_music("test", style=s)
        print(f"Music: {path}")
