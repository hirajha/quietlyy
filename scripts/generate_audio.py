"""
Quietlyy — Audio Generator
Matches the Whisprs reference voice style:
  - Calm, slightly intense, personal
  - Slow to medium pace
  - Intentional pauses between lines (real silence, no "Oh")
  - Each line recorded separately for clean delivery

Records each line individually, joins with actual silence gaps.
"""

import asyncio
import json
import os
import subprocess

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# Voice config matching reference: calm, intense, personal
# GuyNeural is closest to the Whisprs reference voice
RATE = "-5%"       # Slightly slower for weight
VOLUME = "+10%"    # Strong but not shouting

# Silence between lines (seconds) — creates the "intentional pause" effect
LINE_GAP = 1.5

# Voice fallback order (closest to reference first)
VOICES = [
    "en-US-GuyNeural",              # Closest to Whisprs reference
    "en-US-AndrewNeural",           # Clear, personal narrator
    "en-US-SteffanNeural",          # Warm, intimate
    "en-GB-RyanNeural",             # Deep British alternative
]


async def _record_line(text, voice, output_path):
    """Record one line. Strip ellipsis to prevent 'Oh' sound."""
    import edge_tts

    # Replace "…" with comma — prevents edge-tts vocalizing it as "Oh"
    clean = text.replace("…", ",").replace("...", ",")
    while ",," in clean:
        clean = clean.replace(",,", ",")
    clean = clean.replace(", ,", ",").strip().strip(",").strip()

    communicate = edge_tts.Communicate(
        clean, voice=voice, rate=RATE, volume=VOLUME, pitch="+0Hz",
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


def generate_audio(script_text):
    """Record each line separately, join with real silence. No 'Oh' sounds."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio_path = os.path.join(OUTPUT_DIR, "voiceover.mp3")
    subtitle_path = os.path.join(OUTPUT_DIR, "subtitles.json")

    lines = [line.strip() for line in script_text.split("\n") if line.strip()]

    for voice in VOICES:
        try:
            all_subtitles = []
            line_files = []
            cumulative_ms = 0

            print(f"[audio] Recording {len(lines)} lines with {voice}...")

            for i, line in enumerate(lines):
                line_path = os.path.join(OUTPUT_DIR, f"_line_{i}.mp3")
                line_subs = asyncio.run(_record_line(line, voice, line_path))
                line_files.append(line_path)

                # Adjust subtitle timing
                for sub in line_subs:
                    sub["offset_ms"] += cumulative_ms
                    all_subtitles.append(sub)

                line_dur = _get_duration_ms(line_path)
                cumulative_ms += line_dur + (LINE_GAP * 1000)
                print(f"[audio]   Line {i+1}/{len(lines)}: {line_dur/1000:.1f}s")

            # Create silence gap
            silence_path = os.path.join(OUTPUT_DIR, "_silence.mp3")
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i",
                f"anullsrc=r=24000:cl=mono",
                "-t", str(LINE_GAP), "-b:a", "192k", silence_path,
            ], capture_output=True, check=True)

            # Concat all lines with silence
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

            # Cleanup temp files
            for f in line_files:
                os.remove(f)
            os.remove(silence_path)
            os.remove(concat_path)

            # Save subtitles
            with open(subtitle_path, "w") as f:
                json.dump(all_subtitles, f, indent=2)

            total_dur = _get_duration_ms(audio_path) / 1000
            print(f"[audio] Done: {voice}, {len(lines)} lines, {total_dur:.1f}s total")

            return {
                "audio_path": audio_path,
                "subtitle_path": subtitle_path,
                "subtitles": all_subtitles,
            }

        except Exception as e:
            print(f"[audio] {voice} failed: {e}")
            for f in os.listdir(OUTPUT_DIR):
                if f.startswith("_"):
                    os.remove(os.path.join(OUTPUT_DIR, f))

    raise RuntimeError("All voice options failed")


if __name__ == "__main__":
    test = (
        "There was a time… when hearing someone's voice… meant everything.\n"
        "Back then… people waited hours… sometimes days… just for a call.\n"
        "Not because it was easy… but because it mattered.\n"
        "And now… They silence calls… from the people who care the most.\n"
        "Maybe… They didn't lose connection… They just stopped valuing it."
    )
    generate_audio(test)
