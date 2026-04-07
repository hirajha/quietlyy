"""
Quietlyy — Background Music Generator
Always meditative, sad-beautiful, contemplative — the Quietlyy brand tone.
Like a fancy restaurant: music fills silence between narrator paragraphs,
keeps listeners emotionally connected even when no one is speaking.

Target profile (from reference tracks):
  Key: B minor | BPM: 60-85 | Sadness: 90%+ | Relaxed: 90%+ | Happiness: <10%
  Never cheerful, upbeat, comedy, or happy — regardless of script content.

Each video gets a different track from this palette for variety.
"""

import os
import random
import requests

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

FREESOUND_API_KEY = os.environ.get("FREESOUND_API_KEY", "")

# Fixed Quietlyy music palette — all meditative/sad-beautiful.
# Emotion in the script DOES NOT change this — brand tone is always contemplative.
# Randomized per video for variety while staying in the right emotional register.
QUIETLYY_QUERIES = [
    "sad piano meditation slow ambient",
    "melancholic piano ambient contemplative",
    "lonely piano strings slow cinematic",
    "bittersweet piano ambient film score",
    "slow sad piano instrumental reflection",
    "meditative piano strings emotional",
    "contemplative ambient piano slow",
    "cinematic sadness piano ambient",
    "gentle sad piano strings underscore",
    "quiet melancholic piano ambient night",
    "slow piano longing ambient meditation",
    "wistful piano cinematic slow",
    "emotional piano ambient strings slow",
    "peaceful sad piano meditation",
    "soft melancholic strings piano cinematic",
]

# Words in a track name/tags that indicate it's the WRONG vibe — skip these
REJECT_KEYWORDS = [
    "happy", "cheerful", "upbeat", "comedy", "funny", "fun",
    "energetic", "dance", "party", "bright", "positive", "joyful",
    "uplifting", "inspiring", "motivational", "epic", "action",
    "children", "kids", "cartoon", "comedy",
]

# Freesound filter: 30-180s tracks, 55-90 BPM (matches Whisprs 65-83 BPM profile),
# instrumental only, exclude happy/upbeat tags
FREESOUND_FILTER = (
    "duration:[30 TO 180] "
    "tag:instrumental "
    "-tag:happy -tag:cheerful -tag:upbeat -tag:comedy -tag:dance -tag:funny"
)

# BPM range filter — added separately as Freesound supports bpm field filter
FREESOUND_BPM_FILTER = FREESOUND_FILTER + " bpm:[55 TO 90]"


def _is_wrong_vibe(track):
    """Return True if track name or tags suggest it's cheerful/upbeat."""
    name = track.get("name", "").lower()
    tags = " ".join(track.get("tags", [])).lower() if "tags" in track else ""
    combined = name + " " + tags
    return any(kw in combined for kw in REJECT_KEYWORDS)


def _search_freesound(query):
    """Search Freesound for a meditative track matching 55-90 BPM.
    Returns (preview_url, track_name) or (None, None)."""
    if not FREESOUND_API_KEY:
        return None, None

    # Try BPM-filtered search first, then fall back to no BPM filter
    for filt in [FREESOUND_BPM_FILTER, FREESOUND_FILTER]:
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

            good = [t for t in results if not _is_wrong_vibe(t)]
            if not good:
                good = results
            if not good:
                continue

            pool = good[:8] if len(good) >= 8 else good
            track = random.choice(pool)
            preview_url = track.get("previews", {}).get("preview-hq-mp3")
            if preview_url:
                bpm_note = "(BPM-filtered)" if filt == FREESOUND_BPM_FILTER else "(no BPM filter)"
                print(f"[music] Found {bpm_note}: {track['name'][:60]} ({track['duration']:.0f}s)")
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


def generate_music(topic, script_text=""):
    """Fetch meditative background music for Quietlyy.
    Always sad-beautiful / contemplative — never cheerful or upbeat.
    Different track each video (randomized from fixed palette).
    Volume is mixed at 0.10 (low presence, fills silence without overpowering narrator)."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    music_path = os.path.join(OUTPUT_DIR, "background_music.mp3")

    if FREESOUND_API_KEY:
        # Shuffle the palette so each video gets a different starting point
        queries = list(QUIETLYY_QUERIES)
        random.shuffle(queries)

        for query in queries[:6]:  # try up to 6 queries before falling back
            print(f"[music] Searching: {query}")
            preview_url, track_name = _search_freesound(query)
            if preview_url and _download_preview(preview_url, music_path):
                print(f"[music] Track selected: {track_name}")
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
    path = generate_music("The Friend Who Disappeared")
    print(f"Music: {path}")
