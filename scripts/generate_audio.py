"""
Quietlyy — Audio Generator
Uses edge-tts (free, no API key) to generate deep male voiceover.
Produces both the MP3 audio and a subtitle timing file.
"""

import asyncio
import json
import os
import edge_tts

# Voice config: deep, exhausted male
VOICE = os.environ.get("VOICE", "en-US-GuyNeural")
PITCH = os.environ.get("PITCH", "-30Hz")
RATE = os.environ.get("RATE", "-18%")
VOLUME = os.environ.get("VOLUME", "+0%")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def format_script_for_speech(script_text):
    """Add SSML-compatible pauses via ellipsis timing.
    edge-tts naturally pauses on '…' so we just ensure proper spacing."""
    # Replace multiple dots with proper ellipsis
    text = script_text.replace("...", "…")
    # Add a slight pause between lines by using period + newline
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    # Join with pause markers
    return " ... ".join(lines)


async def _generate(script_text, output_path, subtitle_path):
    """Generate audio with subtitle word-level timing."""
    formatted = format_script_for_speech(script_text)

    communicate = edge_tts.Communicate(
        formatted,
        voice=VOICE,
        pitch=PITCH,
        rate=RATE,
        volume=VOLUME,
    )

    # Collect subtitle data for text sync
    subtitles = []
    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                subtitles.append({
                    "text": chunk["text"],
                    "offset_ms": chunk["offset"] / 10000,  # Convert 100ns ticks to ms
                    "duration_ms": chunk["duration"] / 10000,
                })

    # Save subtitle timing
    with open(subtitle_path, "w") as f:
        json.dump(subtitles, f, indent=2)

    print(f"[audio] Generated: {output_path} ({len(subtitles)} word boundaries)")
    return subtitles


def generate_audio(script_text):
    """Main entry: generate audio + subtitles from script text."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio_path = os.path.join(OUTPUT_DIR, "voiceover.mp3")
    subtitle_path = os.path.join(OUTPUT_DIR, "subtitles.json")

    subtitles = asyncio.run(_generate(script_text, audio_path, subtitle_path))

    return {
        "audio_path": audio_path,
        "subtitle_path": subtitle_path,
        "subtitles": subtitles,
    }


if __name__ == "__main__":
    test_script = (
        "There was a time… when hearing someone's voice… meant everything.\n"
        "Back then… people waited hours… sometimes days… just for a call.\n"
        "Not because it was easy… but because it mattered.\n"
        "And now… They silence calls… from the people who care the most.\n"
        "Maybe… They didn't lose connection… They just stopped valuing it."
    )
    result = generate_audio(test_script)
    print(json.dumps({k: v for k, v in result.items() if k != "subtitles"}, indent=2))
