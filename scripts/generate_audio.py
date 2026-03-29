"""
Quietlyy — Audio Generator
Records each line SEPARATELY then joins with REAL silence.
This eliminates the "Oh" sound and creates proper emotional pauses.
Voice: strong, clear, deep male narrator at +20% volume.
"""

import asyncio
import json
import os
import subprocess

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# Strong deep male voices — +20% volume for strength, slight slowdown
VOICE = os.environ.get("VOICE", "en-US-GuyNeural")
RATE = os.environ.get("RATE", "-5%")
VOLUME = os.environ.get("VOLUME", "+20%")

# Silence between lines (seconds)
LINE_GAP = 1.8

# Voice fallback order
VOICES = [
    "en-US-GuyNeural",            # Strong, deep, commanding
    "en-US-BrianMultilingualNeural",  # Clear narrator
    "en-US-SteffanNeural",        # Warm, clear
    "en-GB-RyanNeural",           # Deep British
]


async def _record_line(text, voice, output_path):
    """Record a single line of speech. Strip ellipsis to prevent 'Oh' sound."""
    import edge_tts
    # Replace "…" with comma for natural pause — prevents edge-tts saying "Oh"
    clean_text = text.replace("…", ",").replace("...", ",")
    # Clean up double commas
    while ",," in clean_text:
        clean_text = clean_text.replace(",,", ",")
    clean_text = clean_text.replace(", ,", ",").strip().strip(",").strip()

    communicate = edge_tts.Communicate(
        clean_text, voice=voice, rate=RATE, volume=VOLUME, pitch="+0Hz",
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


def _create_silence(output_path, duration_s):
    """Create a silent audio file."""
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=r=24000:cl=mono",
        "-t", str(duration_s),
        "-b:a", "192k", output_path,
    ], capture_output=True, check=True)


def _concat_audio(line_files, silence_file, output_path):
    """Join line audio files with silence gaps."""
    concat_path = os.path.join(OUTPUT_DIR, "concat_list.txt")
    with open(concat_path, "w") as f:
        for i, lf in enumerate(line_files):
            f.write(f"file '{lf}'\n")
            if i < len(line_files) - 1:
                f.write(f"file '{silence_file}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_path,
        "-b:a", "192k", output_path,
    ], capture_output=True, check=True)

    # Cleanup
    os.remove(concat_path)
    for lf in line_files:
        os.remove(lf)
    os.remove(silence_file)


def generate_audio(script_text):
    """Record each line separately, join with real silence. No 'Oh' sounds."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio_path = os.path.join(OUTPUT_DIR, "voiceover.mp3")
    subtitle_path = os.path.join(OUTPUT_DIR, "subtitles.json")

    # Split into lines
    lines = [line.strip() for line in script_text.split("\n") if line.strip()]

    # Try each voice until one works
    for voice in VOICES:
        try:
            all_subtitles = []
            line_files = []
            cumulative_offset = 0

            print(f"[audio] Recording {len(lines)} lines with {voice}...")

            for i, line in enumerate(lines):
                line_path = os.path.join(OUTPUT_DIR, f"_line_{i}.mp3")

                # Record this line
                line_subs = asyncio.run(_record_line(line, voice, line_path))
                line_files.append(line_path)

                # Adjust subtitle offsets for cumulative timing
                for sub in line_subs:
                    sub["offset_ms"] += cumulative_offset
                    all_subtitles.append(sub)

                # Get line duration
                result = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                     "-of", "csv=p=0", line_path],
                    capture_output=True, text=True,
                )
                line_duration_ms = float(result.stdout.strip()) * 1000
                cumulative_offset += line_duration_ms + (LINE_GAP * 1000)

                print(f"[audio]   Line {i+1}/{len(lines)}: done")

            # Create silence gap
            silence_path = os.path.join(OUTPUT_DIR, "_silence.mp3")
            _create_silence(silence_path, LINE_GAP)

            # Join everything
            _concat_audio(line_files, silence_path, audio_path)

            # Save subtitles
            with open(subtitle_path, "w") as f:
                json.dump(all_subtitles, f, indent=2)

            print(f"[audio] Done: {voice}, {len(lines)} lines, {LINE_GAP}s gaps")
            return {
                "audio_path": audio_path,
                "subtitle_path": subtitle_path,
                "subtitles": all_subtitles,
            }

        except Exception as e:
            print(f"[audio] {voice} failed: {e}")
            # Cleanup any partial files
            for f in os.listdir(OUTPUT_DIR):
                if f.startswith("_line_") or f == "_silence.mp3":
                    os.remove(os.path.join(OUTPUT_DIR, f))

    raise RuntimeError("All voice options failed")


if __name__ == "__main__":
    test_script = (
        "There was a time… when hearing someone's voice… meant everything.\n"
        "Back then… people waited hours… sometimes days… just for a call.\n"
        "Not because it was easy… but because it mattered.\n"
        "And now… They silence calls… from the people who care the most.\n"
        "Maybe… They didn't lose connection… They just stopped valuing it."
    )
    result = generate_audio(test_script)
    print(f"Audio: {result['audio_path']}")
