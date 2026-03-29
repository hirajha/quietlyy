"""
Quietlyy — Audio Generator
3-layer fallback with NATURAL voices (no pitch shifting):
  Layer 1: edge-tts AndrewMultilingual (deep, natural, cinematic)
  Layer 2: edge-tts GuyNeural (natural male)
  Layer 3: edge-tts ChristopherNeural (natural male)
No artificial pitch/rate changes that make it sound like voice-changing software.
"""

import asyncio
import json
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# Natural deep male voices — NO pitch shifting, just slightly slower for that
# heavy, exhausted, reflective delivery. These are Microsoft's best male voices.
VOICE_CONFIGS = [
    # Andrew Multilingual — deepest, most cinematic male voice
    {"voice": "en-US-AndrewMultilingualNeural", "pitch": "+0Hz", "rate": "-12%", "volume": "+0%"},
    # Guy — natural deep US male
    {"voice": "en-US-GuyNeural", "pitch": "+0Hz", "rate": "-10%", "volume": "+0%"},
    # Christopher — warm deep US male
    {"voice": "en-US-ChristopherNeural", "pitch": "+0Hz", "rate": "-10%", "volume": "+0%"},
    # Ryan — deep British male
    {"voice": "en-GB-RyanNeural", "pitch": "+0Hz", "rate": "-10%", "volume": "+0%"},
]


def format_script_for_speech(script_text):
    """Format script with natural pauses."""
    text = script_text.replace("...", "…")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    # Use periods for natural pauses between lines
    return " ... ".join(lines)


async def _generate_edge_tts(script_text, output_path, subtitle_path, voice_config):
    import edge_tts

    formatted = format_script_for_speech(script_text)
    communicate = edge_tts.Communicate(
        formatted,
        voice=voice_config["voice"],
        pitch=voice_config["pitch"],
        rate=voice_config["rate"],
        volume=voice_config["volume"],
    )

    subtitles = []
    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                subtitles.append({
                    "text": chunk["text"],
                    "offset_ms": chunk["offset"] / 10000,
                    "duration_ms": chunk["duration"] / 10000,
                })

    with open(subtitle_path, "w") as f:
        json.dump(subtitles, f, indent=2)

    if os.path.getsize(output_path) < 1000:
        raise ValueError("Audio file too small")

    return subtitles


def generate_audio(script_text):
    """Main entry: generate audio with natural voice fallbacks."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio_path = os.path.join(OUTPUT_DIR, "voiceover.mp3")
    subtitle_path = os.path.join(OUTPUT_DIR, "subtitles.json")

    for config in VOICE_CONFIGS:
        try:
            subtitles = asyncio.run(
                _generate_edge_tts(script_text, audio_path, subtitle_path, config)
            )
            print(f"[audio] Generated with {config['voice']} (natural, no pitch shift)")
            return {
                "audio_path": audio_path,
                "subtitle_path": subtitle_path,
                "subtitles": subtitles,
            }
        except Exception as e:
            print(f"[audio] {config['voice']} failed: {e}")

    raise RuntimeError("All voice layers failed")


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
