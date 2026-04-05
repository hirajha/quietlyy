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
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "b0jrjvawVNjnHsrN2WGU")
ELEVENLABS_MODEL = "eleven_multilingual_v2"  # clear, natural, supports speed param

# Silence between lines (seconds)
LINE_GAP = 1.9


def _clean_text(text):
    """Clean text for TTS — preserve ellipsis as natural pauses."""
    # Keep … as ... so ElevenLabs reads it as a pause, not a comma rush
    clean = text.replace("\u2026", "...").strip()
    return clean


def _record_line_elevenlabs(text, output_path):
    """Record one line using ElevenLabs API."""
    clean = _clean_text(text)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": clean,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": 0.65,        # lower = more expressive and human
            "similarity_boost": 0.80, # higher = stays true to the voice
            "style": 0.20,
            "use_speaker_boost": True,
            "speed": 0.90,            # slight slowdown, not sluggish
        },
    }

    resp = requests.post(url, json=body, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise ValueError(f"ElevenLabs error {resp.status_code}: {resp.text[:200]}")

    with open(output_path, "wb") as f:
        f.write(resp.content)

    if os.path.getsize(output_path) < 500:
        raise ValueError("Audio too small")


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

    lines = [line.strip() for line in script_text.split("\n") if line.strip()]

    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set. Cannot generate audio.")

    print(f"[audio] Using ElevenLabs (voice: {ELEVENLABS_VOICE_ID})")
    line_files = []
    cumulative_ms = 0
    timing_data = []

    for i, line in enumerate(lines):
        line_path = os.path.join(OUTPUT_DIR, f"_line_{i}.mp3")
        _record_line_elevenlabs(line, line_path)
        line_files.append(line_path)

        line_dur = _get_duration_ms(line_path)
        timing_data.append({
            "line": i,
            "start_ms": cumulative_ms,
            "duration_ms": line_dur,
        })
        cumulative_ms += line_dur + (LINE_GAP * 1000)
        print(f"[audio]   Line {i+1}/{len(lines)}: {line_dur/1000:.1f}s")

    # Convert timing data to subtitle-compatible format
    sub_data = []
    for td in timing_data:
        words = lines[td["line"]].split()
        word_dur = td["duration_ms"] / max(len(words), 1)
        for wi, word in enumerate(words):
            sub_data.append({
                "text": word,
                "offset_ms": td["start_ms"] + wi * word_dur,
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
