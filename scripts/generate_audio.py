"""
Quietlyy — Audio Generator
Primary: ElevenLabs (cloned Whisprs voice)
Fallback: edge-tts (Microsoft free TTS)

Records each line individually, joins with real silence gaps.
"""

import asyncio
import json
import os
import subprocess
import requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# ElevenLabs config
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "b0jrjvawVNjnHsrN2WGU")
ELEVENLABS_MODEL = "eleven_monolingual_v1"

# Silence between lines (seconds)
LINE_GAP = 1.5

# edge-tts fallback config
EDGE_RATE = "-5%"
EDGE_VOLUME = "+10%"
EDGE_VOICES = [
    "en-US-GuyNeural",
    "en-US-AndrewNeural",
    "en-US-SteffanNeural",
    "en-GB-RyanNeural",
]


def _clean_text(text):
    """Strip ellipsis and clean punctuation to prevent TTS artifacts."""
    clean = text.replace("…", ",").replace("...", ",")
    while ",," in clean:
        clean = clean.replace(",,", ",")
    clean = clean.replace(", ,", ",").strip().strip(",").strip()
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
            "stability": 0.65,
            "similarity_boost": 0.80,
            "style": 0.35,
            "use_speaker_boost": True,
        },
    }

    resp = requests.post(url, json=body, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise ValueError(f"ElevenLabs error {resp.status_code}: {resp.text[:200]}")

    with open(output_path, "wb") as f:
        f.write(resp.content)

    if os.path.getsize(output_path) < 500:
        raise ValueError("Audio too small")


async def _record_line_edge(text, voice, output_path):
    """Record one line using edge-tts (fallback)."""
    import edge_tts
    clean = _clean_text(text)
    communicate = edge_tts.Communicate(
        clean, voice=voice, rate=EDGE_RATE, volume=EDGE_VOLUME, pitch="+0Hz",
    )
    subtitles = []
    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                subtitles.append({
                    "text": chunk["text"],
                    "offset_ms": chunk["offset"] / 10000,
                    "duration_ms": chunk["duration"] / 10000,
                })
    if os.path.getsize(output_path) < 500:
        raise ValueError("Audio too small")
    return subtitles


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

    # Cleanup
    for f in line_files:
        os.remove(f)
    os.remove(silence_path)
    os.remove(concat_path)


def _generate_with_elevenlabs(lines):
    """Record all lines with ElevenLabs."""
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

    return line_files, timing_data


def _generate_with_edge(lines):
    """Record all lines with edge-tts (fallback)."""
    for voice in EDGE_VOICES:
        try:
            print(f"[audio] Fallback: edge-tts ({voice})")
            line_files = []
            all_subtitles = []
            cumulative_ms = 0

            for i, line in enumerate(lines):
                line_path = os.path.join(OUTPUT_DIR, f"_line_{i}.mp3")
                line_subs = asyncio.run(_record_line_edge(line, voice, line_path))
                line_files.append(line_path)

                for sub in line_subs:
                    sub["offset_ms"] += cumulative_ms
                    all_subtitles.append(sub)

                line_dur = _get_duration_ms(line_path)
                cumulative_ms += line_dur + (LINE_GAP * 1000)
                print(f"[audio]   Line {i+1}/{len(lines)}: {line_dur/1000:.1f}s")

            return line_files, all_subtitles
        except Exception as e:
            print(f"[audio] {voice} failed: {e}")
            for f in os.listdir(OUTPUT_DIR):
                if f.startswith("_"):
                    os.remove(os.path.join(OUTPUT_DIR, f))

    raise RuntimeError("All edge-tts voices failed")


def generate_audio(script_text):
    """Record each line separately, join with real silence.
    Primary: ElevenLabs. Fallback: edge-tts."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio_path = os.path.join(OUTPUT_DIR, "voiceover.mp3")
    subtitle_path = os.path.join(OUTPUT_DIR, "subtitles.json")

    lines = [line.strip() for line in script_text.split("\n") if line.strip()]

    # Try ElevenLabs first
    line_files = None
    sub_data = None

    if ELEVENLABS_API_KEY:
        try:
            line_files, timing_data = _generate_with_elevenlabs(lines)
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
        except Exception as e:
            print(f"[audio] ElevenLabs failed: {e}")
            line_files = None
            # Cleanup any partial files
            for f in os.listdir(OUTPUT_DIR):
                if f.startswith("_"):
                    os.remove(os.path.join(OUTPUT_DIR, f))
    else:
        print("[audio] No ELEVENLABS_API_KEY, using edge-tts fallback")

    # Fallback to edge-tts
    if line_files is None:
        line_files, sub_data = _generate_with_edge(lines)

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
        "There was a time… when hearing someone's voice… meant everything.\n"
        "Back then… people waited hours… sometimes days… just for a call.\n"
        "Not because it was easy… but because it mattered.\n"
        "And now… They silence calls… from the people who care the most.\n"
        "Maybe… They didn't lose connection… They just stopped valuing it."
    )
    generate_audio(test)
