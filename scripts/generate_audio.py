"""
Quietlyy — Audio Generator
ElevenLabs ONLY. No fallbacks — if ElevenLabs fails, pipeline fails.
Records each line individually, joins with real silence gaps.
"""

import json
import os
import subprocess
import requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# ElevenLabs config
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_MODEL = "eleven_turbo_v2_5"

# Silence between lines — 1.3s gives breathing room that matches 60-75 BPM music
# Whispers-style pages: the space between lines IS part of the emotional impact
LINE_GAP = 1.3

# CTA patterns — lines matching these are NOT narrated; shown as baked text overlay instead.
# Check both startswith (for clean CTA lines) and contains (for embedded CTAs).
_CTA_STARTS = [
    "send this to",
    "send this",
    "send it to",
    "share this with",
    "share this",
    "tag the",
    "tag someone",
    "tag them",
    "tag a",
    "save this for",
    "save this if",
    "save this.",
    "save this —",
    "save this -",
    "comment below",
    "drop a ",
    "follow for",
    "like if",
    "forward this",
    "pass this on",
]
_CTA_CONTAINS = [
    "who needs to hear this",
    "who needs this",
    "who needs it",
    "send it to them",
    "needs to see this",
    "share with someone",
    "tag someone who",
    "save for the days",
    "save for when",
]


def _is_cta_line(text):
    """Return True if this line is a social CTA that should not be narrated."""
    t = text.lower().strip()
    if any(t.startswith(p) for p in _CTA_STARTS):
        return True
    # Also catch CTAs embedded mid-line (short lines only — avoids false positives)
    if len(t) < 120 and any(k in t for k in _CTA_CONTAINS):
        return True
    return False


def extract_cta(script_text):
    """Return the first CTA line from a script, or None."""
    for line in script_text.split("\n"):
        line = line.strip()
        if line and _is_cta_line(line):
            return line
    return None


def _clean_text(text):
    """Clean text for TTS — preserve ellipsis as natural pauses."""
    # Keep … as ... so ElevenLabs reads it as a pause, not a comma rush
    clean = text.replace("\u2026", "...").strip()
    return clean


def _record_line_elevenlabs(text, output_path):
    """Record one line via ElevenLabs with-timestamps endpoint.

    Returns word-level timing data extracted from ElevenLabs' character alignment.
    Falls back to plain TTS (no timestamps) if the endpoint fails.
    """
    import base64
    clean = _clean_text(text)
    voice_settings = {
        "stability": 0.45,
        "similarity_boost": 0.80,
        "style": 0.40,
        "use_speaker_boost": False,
        "speed": 0.85,
    }
    body = {
        "text": clean,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": voice_settings,
    }

    # Try with-timestamps endpoint first — gives real per-character timing
    ts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/with-timestamps"
    headers_json = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    word_timings = None
    try:
        resp = requests.post(ts_url, json=body, headers=headers_json, timeout=40)
        if resp.status_code == 200:
            data = resp.json()
            audio_bytes = base64.b64decode(data["audio_base64"])
            with open(output_path, "wb") as f:
                f.write(audio_bytes)

            # Build word-level timings from character alignment
            alignment = data.get("alignment", {})
            chars = alignment.get("characters", [])
            starts = alignment.get("character_start_times_seconds", [])
            ends = alignment.get("character_end_times_seconds", [])

            if chars and starts and ends:
                word_timings = _chars_to_word_timings(chars, starts, ends)
    except Exception as e:
        print(f"[audio] with-timestamps failed ({e}), falling back to plain TTS")

    # Fallback: plain TTS endpoint
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 500:
        plain_url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers_mp3 = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        resp = requests.post(plain_url, json=body, headers=headers_mp3, timeout=30)
        if resp.status_code != 200:
            raise ValueError(f"ElevenLabs error {resp.status_code}: {resp.text[:200]}")
        with open(output_path, "wb") as f:
            f.write(resp.content)

    if os.path.getsize(output_path) < 500:
        raise ValueError("Audio too small")

    return word_timings  # None if timestamps unavailable


def _chars_to_word_timings(chars, starts, ends):
    """Convert ElevenLabs character-level alignment into word-level timing dicts."""
    words = []
    current_word = []
    current_starts = []
    current_ends = []

    for ch, s, e in zip(chars, starts, ends):
        if ch == " ":
            if current_word:
                words.append(("".join(current_word), current_starts[0], current_ends[-1]))
                current_word, current_starts, current_ends = [], [], []
        else:
            current_word.append(ch)
            current_starts.append(s)
            current_ends.append(e)

    if current_word:
        words.append(("".join(current_word), current_starts[0], current_ends[-1]))

    return [{"word": w, "start_s": s, "end_s": e} for w, s, e in words]


def _get_duration_ms(filepath):
    """Get audio duration in milliseconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", filepath],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip()) * 1000


def _join_lines_with_silence(line_files, audio_path):
    """Concatenate line audio files with silence gaps between them."""
    silence_path = os.path.join(OUTPUT_DIR, "_silence.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"anullsrc=r=24000:cl=mono",
        "-t", str(LINE_GAP), "-b:a", "192k", silence_path,
    ], capture_output=True, check=True)

    concat_path = os.path.join(OUTPUT_DIR, "_concat.txt")
    with open(concat_path, "w") as f:
        for i, lf in enumerate(line_files):
            f.write(f"file '{lf}'\n")
            if i < len(line_files) - 1:
                f.write(f"file '{silence_path}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_path, "-b:a", "192k", audio_path,
    ], capture_output=True, check=True)

    # Cleanup (keep _line_*.mp3 — compositor uses them for per-line timing)
    os.remove(silence_path)
    os.remove(concat_path)


def generate_audio(script_text):
    """Record each line separately, join with real silence.
    ElevenLabs ONLY. Raises error on failure."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio_path = os.path.join(OUTPUT_DIR, "voiceover.mp3")
    subtitle_path = os.path.join(OUTPUT_DIR, "subtitles.json")

    all_lines = [line.strip() for line in script_text.split("\n") if line.strip()]

    # Filter out CTA lines — they appear as baked text overlay, not narrated by voice
    lines = [l for l in all_lines if not _is_cta_line(l)]
    skipped = len(all_lines) - len(lines)
    if skipped:
        print(f"[audio] Skipping {skipped} CTA line(s) from narration")

    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set. Cannot generate audio.")

    print(f"[audio] Using ElevenLabs (voice: {ELEVENLABS_VOICE_ID})")
    line_files = []
    cumulative_ms = 0
    timing_data = []

    all_word_timings = []  # per-line word timing lists (None if unavailable)

    for i, line in enumerate(lines):
        line_path = os.path.join(OUTPUT_DIR, f"_line_{i}.mp3")
        word_timings = _record_line_elevenlabs(line, line_path)
        line_files.append(line_path)
        all_word_timings.append(word_timings)

        line_dur = _get_duration_ms(line_path)
        timing_data.append({
            "line": i,
            "start_ms": cumulative_ms,
            "duration_ms": line_dur,
        })
        cumulative_ms += line_dur + (LINE_GAP * 1000)
        src = "ElevenLabs timestamps" if word_timings else "estimated"
        print(f"[audio]   Line {i+1}/{len(lines)}: {line_dur/1000:.1f}s ({src})")

    # Build subtitle data — use real timestamps when available, fall back to estimate
    sub_data = []
    for td, word_timings in zip(timing_data, all_word_timings):
        line_start_ms = td["start_ms"]
        if word_timings:
            # Real per-word timing from ElevenLabs character alignment
            for wt in word_timings:
                sub_data.append({
                    "text": wt["word"],
                    "offset_ms": line_start_ms + wt["start_s"] * 1000,
                    "duration_ms": (wt["end_s"] - wt["start_s"]) * 1000,
                })
        else:
            # Fallback: divide line duration evenly across words
            words = lines[td["line"]].split()
            word_dur = td["duration_ms"] / max(len(words), 1)
            for wi, word in enumerate(words):
                sub_data.append({
                    "text": word,
                    "offset_ms": line_start_ms + wi * word_dur,
                    "duration_ms": word_dur,
                })

    print("[audio] ElevenLabs: success")

    # Join all lines with silence gaps
    _join_lines_with_silence(line_files, audio_path)

    # Save subtitles
    with open(subtitle_path, "w") as f:
        json.dump(sub_data, f, indent=2)

    total_dur = _get_duration_ms(audio_path) / 1000
    print(f"[audio] Done: {len(lines)} lines, {total_dur:.1f}s total")

    return {
        "audio_path": audio_path,
        "subtitle_path": subtitle_path,
        "subtitles": sub_data,
    }


if __name__ == "__main__":
    test = (
        "There was a time\u2026 when hearing someone's voice\u2026 meant everything.\n"
        "Back then\u2026 people waited hours\u2026 sometimes days\u2026 just for a call.\n"
        "Not because it was easy\u2026 but because it mattered.\n"
        "And now\u2026 They silence calls\u2026 from the people who care the most.\n"
        "Maybe\u2026 They didn't lose connection\u2026 They just stopped valuing it."
    )
    generate_audio(test)
