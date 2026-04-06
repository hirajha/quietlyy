"""
Quietlyy — Background Music Generator (AI Emotion-Aware)
Analyzes script emotion and picks cinematic/emotional music accordingly.
Different music each video — "low not slow" (quiet but energetic, not boring).

Emotion → Music mapping:
  heartbreak / longing → bittersweet cinematic strings
  nostalgia / memories → warm piano vintage
  friendship / connection → uplifting soft acoustic
  loss / grief → deep melancholic ambient
  hope / healing → gentle rising cinematic
  betrayal / anger → tense dramatic underscore
  solitude / loneliness → sparse piano night
  love / warmth → tender romantic strings
"""

import os
import random
import re
import requests

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

FREESOUND_API_KEY = os.environ.get("FREESOUND_API_KEY", "")

# Emotion → Freesound search queries (cinematic, not just boring piano loops)
# Each emotion has multiple queries — pick one randomly for variety
EMOTION_MUSIC_MAP = {
    "heartbreak": [
        "cinematic heartbreak emotional strings",
        "bittersweet piano strings sad film score",
        "melancholic violin piano cinematic",
        "emotional breakup piano cinematic",
    ],
    "longing": [
        "longing cinematic ambient piano",
        "yearning emotional strings orchestra",
        "nostalgic piano longing film score",
        "wistful cinematic ambient",
    ],
    "nostalgia": [
        "nostalgic warm piano vintage",
        "vintage emotional piano cinematic",
        "warm nostalgic strings piano",
        "bittersweet memory piano ambient",
    ],
    "loss": [
        "grief cinematic ambient deep",
        "loss melancholic strings slow cinematic",
        "sad orchestral ambient film score",
        "mourning piano ambient cinematic",
    ],
    "friendship": [
        "friendship warm acoustic guitar piano",
        "gentle connection piano acoustic",
        "uplifting soft cinematic piano",
        "warm emotional piano tender",
    ],
    "hope": [
        "hope rising cinematic piano strings",
        "hopeful emotional film score",
        "gentle rise piano cinematic",
        "uplifting soft orchestral piano",
    ],
    "healing": [
        "healing gentle piano ambient",
        "peaceful warm piano cinematic",
        "calm emotional strings healing",
        "soft cinematic piano reflection",
    ],
    "betrayal": [
        "tense dramatic cinematic underscore",
        "betrayal dramatic strings piano",
        "emotional tension piano cinematic",
        "dark emotional piano film score",
    ],
    "solitude": [
        "solitude sparse piano night ambient",
        "lonely piano minimal cinematic",
        "quiet solitude piano atmospheric",
        "empty night piano ambient",
    ],
    "love": [
        "tender romantic piano strings",
        "love cinematic strings piano",
        "warm romance piano ambient",
        "gentle love piano film score",
    ],
    "missing": [
        "missing someone piano ambient cinematic",
        "absence emotional piano",
        "piano longing ambient sad",
        "tender piano absent memory",
    ],
    "growing": [
        "growing apart piano ambient",
        "emotional change cinematic piano",
        "transition cinematic strings",
        "gentle piano bittersweet change",
    ],
}

# Default fallback queries if emotion detection fails
DEFAULT_QUERIES = [
    "emotional cinematic piano strings",
    "cinematic ambient piano tender",
    "soft emotional film score piano",
    "bittersweet piano cinematic ambient",
    "quiet emotional piano strings cinematic",
]

# Emotion keyword → emotion category (simple NLP)
EMOTION_KEYWORDS = {
    "heartbreak": ["heartbreak", "broken heart", "hurt", "ache", "shattered", "broke"],
    "longing": ["longing", "yearning", "missing", "ache for", "wish", "long for"],
    "nostalgia": ["nostalgia", "nostalgic", "remember", "memories", "used to", "back then",
                  "used to be", "telephone", "vinyl", "cassette", "letter", "childhood",
                  "sunday", "library", "radio", "bench", "front porch", "landline",
                  "pen pal", "bicycle", "album", "neighbor"],
    "loss": ["loss", "lose", "lost", "gone", "grief", "mourn", "passed", "death", "left"],
    "friendship": ["friend", "friendship", "together", "bond", "connection", "shared",
                   "laugh", "companion"],
    "hope": ["hope", "hopeful", "new start", "begin", "sunrise", "light", "better",
             "future", "forward", "rise", "bloom"],
    "healing": ["heal", "healing", "recovery", "piece", "mend", "whole", "okay"],
    "betrayal": ["betray", "betrayal", "used", "convenient", "fake", "deceive", "lied"],
    "solitude": ["alone", "solitude", "lonely", "empty", "silence", "quiet", "solo",
                 "just me", "by myself"],
    "love": ["love", "loved", "loving", "tender", "warm", "close", "romance", "cherish"],
    "missing": ["missing", "miss you", "not there", "without you", "far", "away",
                "distance", "absence"],
    "growing": ["outgrow", "grow apart", "change", "different", "moved on", "fade",
                "drift", "apart", "distance"],
}


def _detect_emotion(script_text, topic):
    """Detect primary emotion from script text and topic using keyword matching.
    Returns emotion category string."""
    combined = (script_text + " " + topic).lower()

    scores = {}
    for emotion, keywords in EMOTION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[emotion] = score

    if not scores:
        return None

    # Return highest-scoring emotion
    return max(scores, key=scores.get)


def _detect_emotion_with_llm(script_text, topic):
    """Use OpenAI/Gemini to identify the primary emotion for music selection.
    Returns one of the keys in EMOTION_MUSIC_MAP, or None on failure."""
    emotion_list = ", ".join(EMOTION_MUSIC_MAP.keys())
    prompt = (
        f"Analyze the emotional tone of this script and pick ONE word from this list: "
        f"{emotion_list}\n\n"
        f"Topic: {topic}\n"
        f"Script:\n{script_text}\n\n"
        f"Reply with ONLY the single emotion word, nothing else."
    )

    # Try OpenAI first
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                    "temperature": 0.0,
                },
                timeout=15,
            )
            resp.raise_for_status()
            word = resp.json()["choices"][0]["message"]["content"].strip().lower()
            word = re.sub(r"[^a-z]", "", word)
            if word in EMOTION_MUSIC_MAP:
                print(f"[music] LLM emotion: {word}")
                return word
        except Exception as e:
            print(f"[music] LLM emotion detection failed: {e}")

    # Try Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 10, "temperature": 0.0},
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip().lower()
            word = re.sub(r"[^a-z]", "", text)
            if word in EMOTION_MUSIC_MAP:
                print(f"[music] LLM emotion (Gemini): {word}")
                return word
        except Exception as e:
            print(f"[music] Gemini emotion detection failed: {e}")

    return None


def _get_music_queries(script_text, topic):
    """Get ordered list of Freesound queries based on script emotion."""
    # Try LLM detection first (most accurate)
    emotion = _detect_emotion_with_llm(script_text, topic)

    # Fall back to keyword matching
    if not emotion:
        emotion = _detect_emotion(script_text, topic)

    if emotion:
        print(f"[music] Detected emotion: {emotion}")
        queries = list(EMOTION_MUSIC_MAP[emotion])
        random.shuffle(queries)  # randomize order for variety
        # Add a few default queries as backup
        extra = random.sample(DEFAULT_QUERIES, min(2, len(DEFAULT_QUERIES)))
        return queries + extra

    print("[music] No emotion detected — using default cinematic queries")
    shuffled = list(DEFAULT_QUERIES)
    random.shuffle(shuffled)
    return shuffled


def _search_freesound(query):
    """Search Freesound for instrumental tracks. Returns preview URL or None."""
    if not FREESOUND_API_KEY:
        return None

    try:
        resp = requests.get(
            "https://freesound.org/apiv2/search/text/",
            params={
                "query": query,
                "filter": "duration:[20 TO 120] tag:instrumental",
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

        # Pick a random track from top results for variety
        track = random.choice(results[:10]) if len(results) >= 10 else random.choice(results)
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


def generate_music(topic, script_text=""):
    """Fetch emotion-matched background music.
    Primary: Freesound (AI-selected based on script emotion).
    Fallback: bundled instrumental.mp3.
    Music is "low not slow" — quiet volume, matching emotional energy."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    music_path = os.path.join(OUTPUT_DIR, "background_music.mp3")

    if FREESOUND_API_KEY:
        queries = _get_music_queries(script_text, topic)

        for query in queries:
            print(f"[music] Searching: {query}")
            preview_url = _search_freesound(query)
            if preview_url and _download_preview(preview_url, music_path):
                print(f"[music] Freesound track downloaded")
                return music_path

        print("[music] All Freesound queries failed")
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
    test_script = (
        "You didn't lose them in a fight.\n"
        "You lost them in a silence that grew too long.\n"
        "One day they were your whole world.\n"
        "The next, just someone you used to know.\n"
    )
    path = generate_music("The Friend Who Disappeared", test_script)
    print(f"Music: {path}")
