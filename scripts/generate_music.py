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
HF_TOKEN = os.environ.get("HF_TOKEN", "")

# ── MusicGen prompts per mood ─────────────────────────────────────────────────
# Engineered for Whisprs-style emotional instrumentals: piano + strings + soft
# texture, slow tempo, no vocals. These prompts are specific enough that
# MusicGen reliably produces the right vibe (vs vague terms like "sad music").
# Tested patterns: name instruments + tempo BPM + "instrumental" + "no vocals"
_MUSICGEN_PROMPTS = {
    "heartbreak": "Soft sad piano with deep cello, melancholic heartbreak ballad, slow tempo 60 BPM, cinematic instrumental, gentle strings, no drums, no vocals",
    "longing":    "Wistful piano with cello and violin, nostalgic longing melody, slow tempo 65 BPM, sparse emotional cinematic instrumental, no vocals",
    "melancholy": "Dark melancholy piano and cello, sad emotional atmosphere, slow tempo 60 BPM, cinematic instrumental, ambient strings, no vocals",
    "love":       "Tender romantic piano with soft violin, gentle love ballad, slow tempo 70 BPM, intimate emotional instrumental, no vocals",
    "hope":       "Hopeful piano with rising strings, emotional cinematic build, slow tempo 72 BPM, uplifting instrumental, no vocals",
}


def _generate_musicgen(mood, output_path, duration=30):
    """Generate Whisprs-style instrumental music via Hugging Face MusicGen.

    Free via HF Inference API. Uses facebook/musicgen-small (300M params,
    fastest model on free tier). Generation time: ~20-60s depending on cold
    start. Returns True on success, False on any failure (caller falls back).

    Output is WAV/FLAC → converted to MP3 via ffmpeg.
    """
    if not HF_TOKEN:
        return False

    prompt = _MUSICGEN_PROMPTS.get(mood, _MUSICGEN_PROMPTS["melancholy"])
    duration = min(max(duration, 5), 30)  # MusicGen max = 30s

    # Models in priority order: small (fastest, free) → medium (better, may need pro)
    models = ["facebook/musicgen-small"]

    for model in models:
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {
            "inputs": prompt,
            "parameters": {"duration": duration},
        }

        for attempt in range(2):
            try:
                print(f"[music] MusicGen {model} (try {attempt+1}/2) — '{prompt[:70]}...'")
                resp = requests.post(api_url, headers=headers, json=payload, timeout=240)

                # 503 = model cold-starting — wait then retry
                if resp.status_code == 503:
                    wait_s = 30
                    try:
                        wait_s = int(resp.json().get("estimated_time", 30))
                    except Exception:
                        pass
                    print(f"[music] MusicGen cold start — waiting {wait_s}s")
                    import time
                    time.sleep(min(wait_s + 5, 60))
                    continue

                if resp.status_code == 200 and len(resp.content) > 50_000:
                    # Save raw audio (FLAC/WAV) then convert to MP3 via ffmpeg
                    tmp_path = output_path + ".musicgen.raw"
                    with open(tmp_path, "wb") as f:
                        f.write(resp.content)

                    import subprocess
                    result = subprocess.run(
                        ["ffmpeg", "-y", "-i", tmp_path, "-b:a", "192k", output_path],
                        capture_output=True,
                    )
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

                    if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10_000:
                        print(f"[music] MusicGen generated {duration}s ({os.path.getsize(output_path)//1024}KB)")
                        return True
                    print(f"[music] MusicGen ffmpeg convert failed: {result.stderr.decode(errors='replace')[-200:]}")
                    break  # don't retry on convert failure

                # Any other status — log and abort this model
                print(f"[music] MusicGen {model} failed: status={resp.status_code}, body={resp.text[:200]}")
                break
            except Exception as e:
                print(f"[music] MusicGen {model} error: {e}")
                break

    return False

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
    # TOO BIG / too cinematic — Whisprs style needs intimate solo piano, not full orchestra
    "orchestra", "orchestral", "choir", "chorus", "choral", "surround",
    "atmo", "epic", "trailer", "blockbuster", "dramatic",
    "full orchestra", "big band", "brass",
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


# ── CC0/CC-BY fallback tracks ─────────────────────────────────────────────────
# Used when Pixabay is unavailable. Kevin MacLeod (incompetech.com) CC-BY 3.0.
# Piano-only and more generic-sounding than Pixabay song-style tracks.
# Kept as reliable fallback — they always download and are always mood-safe.
#
# mood → list of (url, label) — tried in shuffled order until one downloads
_CC0_TRACKS = {
    "heartbreak": [
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Heartbreaking.mp3",       "Kevin MacLeod - Heartbreaking"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Wish%20Background.mp3",   "Kevin MacLeod - Wish Background"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sad%20Trio.mp3",          "Kevin MacLeod - Sad Trio"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Dreamy%20Flashback.mp3",  "Kevin MacLeod - Dreamy Flashback"),
    ],
    "longing": [
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Wish%20Background.mp3",   "Kevin MacLeod - Wish Background"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Piano%20Moment.mp3",      "Kevin MacLeod - Piano Moment"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Heartbreaking.mp3",       "Kevin MacLeod - Heartbreaking"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Dreamy%20Flashback.mp3",  "Kevin MacLeod - Dreamy Flashback"),
    ],
    "love": [
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Touching%20Moments.mp3",  "Kevin MacLeod - Touching Moments"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Wish%20Background.mp3",   "Kevin MacLeod - Wish Background"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Healing.mp3",             "Kevin MacLeod - Healing"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Dreamy%20Flashback.mp3",  "Kevin MacLeod - Dreamy Flashback"),
    ],
    "nostalgia": [
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Dreamy%20Flashback.mp3",  "Kevin MacLeod - Dreamy Flashback"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Piano%20Moment.mp3",      "Kevin MacLeod - Piano Moment"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Wish%20Background.mp3",   "Kevin MacLeod - Wish Background"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Bittersweet.mp3",         "Kevin MacLeod - Bittersweet"),
    ],
    "melancholy": [
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Heartbreaking.mp3",       "Kevin MacLeod - Heartbreaking"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Wish%20Background.mp3",   "Kevin MacLeod - Wish Background"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sad%20Trio.mp3",          "Kevin MacLeod - Sad Trio"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Piano%20Moment.mp3",      "Kevin MacLeod - Piano Moment"),
    ],
    "hope": [
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Wish%20Background.mp3",   "Kevin MacLeod - Wish Background"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Healing.mp3",             "Kevin MacLeod - Healing"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Piano%20Moment.mp3",      "Kevin MacLeod - Piano Moment"),
        ("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Dreamy%20Flashback.mp3",  "Kevin MacLeod - Dreamy Flashback"),
    ],
}


# ── Pixabay query-based search — mood-targeted text queries for SONG-style instrumentals ──
# These queries are tuned to return full-production tracks (piano + strings + bass +
# soft drums) rather than generic ambient piano. The terms "instrumental", "cinematic",
# and "song" push Pixabay's algorithm toward Whisprs-style tracks: real song
# arrangements with vocals removed, not stripped-down ambient piano.
_MOOD_TO_PIXABAY_QUERIES = {
    "heartbreak": [
        "emotional heartbreak cinematic instrumental",
        "sad piano strings song instrumental",
        "melancholic emotional song background",
        "heartbreak emotional cinematic music",
        "sad emotional ballad instrumental",
    ],
    "longing": [
        "longing emotional cinematic instrumental",
        "nostalgic piano strings song",
        "wistful emotional instrumental music",
        "missing someone cinematic instrumental",
        "longing romantic emotional background",
    ],
    "melancholy": [
        "melancholy cinematic emotional instrumental",
        "sad emotional song background music",
        "dark emotional piano cinematic",
        "melancholic ambient cinematic instrumental",
        "sad piano strings emotional song",
    ],
    "love": [
        "romantic emotional instrumental cinematic",
        "tender love song instrumental",
        "emotional love ballad instrumental",
        "romantic piano strings cinematic",
        "love emotional song background music",
    ],
    "hope": [
        "emotional cinematic uplifting instrumental",
        "hopeful cinematic emotional music",
        "inspiring emotional piano cinematic",
        "emotional cinematic song instrumental",
        "hopeful piano strings cinematic",
    ],
}


def _search_pixabay_by_query(mood, output_path):
    """Search Pixabay Music by mood-targeted text query for song-like instrumentals.

    This bypasses Pixabay's mood/genre params (unreliable) and uses direct text
    search. Queries include 'instrumental', 'cinematic', 'song' to push toward
    full-production tracks rather than ambient piano. Returns True if a track
    was downloaded successfully.
    """
    if not PIXABAY_API_KEY:
        return False

    queries = list(_MOOD_TO_PIXABAY_QUERIES.get(mood, _MOOD_TO_PIXABAY_QUERIES["melancholy"]))
    random.shuffle(queries)

    for q in queries[:4]:
        try:
            resp = requests.get(
                "https://pixabay.com/api/music/",
                params={"key": PIXABAY_API_KEY, "q": q, "per_page": 50},
                timeout=15,
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            if not hits:
                continue

            # Filter by combined name + tags against REJECT_KEYWORDS
            def _good(t):
                tags_raw = t.get("tags", "")
                tags_str = " ".join(tags_raw.split(",")) if isinstance(tags_raw, str) else " ".join(tags_raw)
                combined = (
                    (t.get("title", "") or "").lower() + " " +
                    (t.get("name", "") or "").lower() + " " +
                    tags_str.lower()
                )
                return not any(kw in combined for kw in REJECT_KEYWORDS)

            good = [h for h in hits if _good(h)]
            if not good:
                continue

            track = random.choice(good[:15])
            url = (
                track.get("audio")
                or track.get("download_url")
                or track.get("previewURL")
                or track.get("audio_download")
            )
            name = track.get("title") or track.get("name") or "Pixabay track"
            if url and _download_pixabay(url, output_path):
                print(f"[music] Pixabay query '{q}' → {name[:60]}")
                return True
        except Exception as e:
            print(f"[music] Pixabay query '{q}' failed: {e}")
    return False


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

    # ── Primary: Hugging Face MusicGen — AI-generated Whisprs-style instrumentals ──
    # Unique per-video instrumental track from a mood-targeted text prompt.
    # Free via HF Inference API. ~20-60s generation time. Quality varies but at
    # its best produces piano + strings + soft texture indistinguishable from
    # commercial library music. Falls through to Pixabay if generation fails.
    if HF_TOKEN:
        if _generate_musicgen(script_mood, music_path, duration=30):
            print(f"[music] MusicGen succeeded — unique AI-generated instrumental")
            return music_path, "musicgen_hf"
        print("[music] MusicGen failed — falling back to Pixabay")
    else:
        print("[music] No HF_TOKEN set — skipping MusicGen")

    # ── Secondary: Pixabay text-query — targets song-style instrumentals ──
    # Pixabay's library includes many full-production tracks (piano + strings +
    # soft beat) with no vocals. Text-query search ('emotional cinematic song
    # instrumental') is more reliable than their mood/genre params.
    if PIXABAY_API_KEY:
        if _search_pixabay_by_query(script_mood, music_path):
            print(f"[music] Pixabay query-search succeeded")
            return music_path, "pixabay_query"
        print("[music] Pixabay query-search exhausted — trying CC0 library")
    else:
        print("[music] No PIXABAY_API_KEY set — skipping Pixabay")

    # ── Tertiary: CC0 library — pre-vetted, ALWAYS sad/melancholic, no API needed ──
    if _download_cc0_track(script_mood, music_path):
        print(f"[music] CC0 library track used (guaranteed safe mood)")
        return music_path, "cc0_library"
    print("[music] CC0 download failed — trying Freesound")

    # ── Quaternary: Freesound — mood-locked queries only ──
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

    # ── Quinary: Pixabay legacy mood/genre search (different endpoint than primary) ──
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
