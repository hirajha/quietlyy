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

# Base Freesound filter — applied to all styles
FREESOUND_BASE_FILTER = (
    "duration:[30 TO 180] "
    "tag:instrumental "
    "-tag:comedy -tag:dance -tag:funny -tag:party"
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


def _get_bundled_music():
    """Get bundled instrumental.mp3 as fallback."""
    path = os.path.join(ASSETS_DIR, "music", "instrumental.mp3")
    if os.path.exists(path):
        return path
    return None


def generate_music(topic, script_text="", style="emotional"):
    """Fetch background music that emotionally matches the script style.

    Styles:
      emotional    → contemplative piano/strings (default)
      nostalgic    → warm piano + subtle nature/birds/wind
      poetic       → melancholic piano/cello + rain/wind
      love         → tender piano + violin, heartbeat tempo
      motivational → building piano/strings + morning nature sounds
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    music_path = os.path.join(OUTPUT_DIR, "background_music.mp3")

    # Map script styles to music profile
    style_map = {
        "emotional": "emotional",
        "nostalgic": "nostalgic",
        "poetic": "poetic",
        "love": "love",
        "motivational": "motivational",
    }
    music_style = style_map.get(style, "emotional")
    profile = STYLE_PROFILES[music_style]

    print(f"[music] Style: {style} → music profile: {music_style} ({profile['bpm']})")

    if FREESOUND_API_KEY:
        queries = list(profile["queries"])
        random.shuffle(queries)

        for query in queries[:6]:  # try up to 6 queries
            print(f"[music] Searching: {query}")
            preview_url, track_name = _search_freesound(query, music_style)
            if preview_url and _download_preview(preview_url, music_path):
                print(f"[music] Track selected: {track_name}")
                return music_path

        # If style-specific search failed, fall back to emotional (safe default)
        if music_style != "emotional":
            print(f"[music] Style search exhausted — falling back to emotional profile")
            fallback_queries = list(STYLE_PROFILES["emotional"]["queries"])
            random.shuffle(fallback_queries)
            for query in fallback_queries[:4]:
                preview_url, track_name = _search_freesound(query, "emotional")
                if preview_url and _download_preview(preview_url, music_path):
                    print(f"[music] Fallback track: {track_name}")
                    return music_path

        print("[music] All Freesound queries failed — using bundled fallback")
    else:
        print("[music] No FREESOUND_API_KEY — using bundled music")

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
