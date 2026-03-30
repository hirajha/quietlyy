"""
Quietlyy — Background Music Generator
Fetches mood-matching instrumental music from Freesound.
Falls back to bundled instrumental.mp3 if Freesound fails.

Each video gets a DIFFERENT track based on its topic/mood.
"""

import os
import random
import requests

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

FREESOUND_API_KEY = os.environ.get("FREESOUND_API_KEY", "")

# Mood-based search queries mapped to emotional arc of our videos
MOOD_QUERIES = [
    "soft piano emotional cinematic",
    "melancholic piano ambient",
    "sad piano instrumental nostalgia",
    "emotional ambient cinematic slow",
    "gentle piano reflective mood",
    "cinematic emotional strings piano",
    "quiet sadness piano",
    "lonely piano night ambient",
    "bittersweet piano melody",
    "contemplative piano soft",
]


def _search_freesound(query):
    """Search Freesound for instrumental tracks. Returns preview URL or None."""
    if not FREESOUND_API_KEY:
        return None

    try:
        resp = requests.get(
            "https://freesound.org/apiv2/search/text/",
            params={
                "query": query,
                "filter": "duration:[15 TO 60] tag:instrumental",
                "fields": "id,name,duration,previews",
                "page_size": 15,
                "sort": "rating_desc",
                "token": FREESOUND_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None

        # Pick a random track from top results
        track = random.choice(results)
        preview_url = track.get("previews", {}).get("preview-hq-mp3")
        if preview_url:
            print(f"[music] Found: {track['name']} ({track['duration']:.0f}s)")
            return preview_url
    except Exception as e:
        print(f"[music] Freesound search failed: {e}")
    return None


def _download_preview(url, output_path):
    """Download a Freesound preview MP3."""
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Token {FREESOUND_API_KEY}"},
            timeout=30,
        )
        if resp.status_code != 200:
            return False
        if len(resp.content) < 5000:
            return False
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"[music] Download failed: {e}")
    return False


def _get_bundled_music():
    """Get the bundled instrumental.mp3 as fallback."""
    path = os.path.join(ASSETS_DIR, "music", "instrumental.mp3")
    if os.path.exists(path):
        return path
    wav = os.path.join(ASSETS_DIR, "music", "instrumental.wav")
    if os.path.exists(wav):
        return wav
    return None


def generate_music(topic):
    """Fetch topic-matching background music.
    Primary: Freesound (different track per video).
    Fallback: bundled instrumental.mp3."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    music_path = os.path.join(OUTPUT_DIR, "background_music.mp3")

    if FREESOUND_API_KEY:
        # Build topic-specific query
        topic_query = f"{topic} piano emotional instrumental"
        queries_to_try = [topic_query] + random.sample(MOOD_QUERIES, min(3, len(MOOD_QUERIES)))

        for query in queries_to_try:
            print(f"[music] Searching: {query}")
            preview_url = _search_freesound(query)
            if preview_url and _download_preview(preview_url, music_path):
                print(f"[music] Freesound track downloaded")
                return music_path
    else:
        print("[music] No FREESOUND_API_KEY, using bundled music")

    # Fallback to bundled
    bundled = _get_bundled_music()
    if bundled:
        print(f"[music] Using bundled: {os.path.basename(bundled)}")
        return bundled

    print("[music] WARNING: No background music available")
    return None


if __name__ == "__main__":
    path = generate_music("Telephone")
    print(f"Music: {path}")
