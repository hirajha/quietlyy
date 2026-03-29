"""
Quietlyy — Audio Generator
3-layer fallback: edge-tts (primary) → edge-tts alt voice → gTTS
edge-tts is free forever, no API key, no limits.
"""

import asyncio
import json
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# Voice configs ranked by preference for deep exhausted male voice
VOICE_CONFIGS = [
    {"voice": "en-US-GuyNeural", "pitch": "-30Hz", "rate": "-18%", "volume": "+0%"},
    {"voice": "en-US-ChristopherNeural", "pitch": "-25Hz", "rate": "-15%", "volume": "+0%"},
    {"voice": "en-GB-RyanNeural", "pitch": "-20Hz", "rate": "-15%", "volume": "+0%"},
]


def format_script_for_speech(script_text):
    """Add natural pauses via ellipsis."""
    text = script_text.replace("...", "…")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return " ... ".join(lines)


# ── Layer 1 & 2: edge-tts (free, unlimited, multiple voice fallbacks) ──
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

    # Verify file was created and has content
    if os.path.getsize(output_path) < 1000:
        raise ValueError("Audio file too small, likely failed")

    return subtitles


def generate_with_edge_tts(script_text, output_path, subtitle_path):
    """Try multiple edge-tts voices as fallback layers."""
    for i, config in enumerate(VOICE_CONFIGS):
        try:
            subs = asyncio.run(_generate_edge_tts(script_text, output_path, subtitle_path, config))
            print(f"[audio] Generated via edge-tts ({config['voice']})")
            return subs
        except Exception as e:
            print(f"[audio] edge-tts voice {config['voice']} failed: {e}")
    return None


# ── Layer 3: gTTS fallback (Google Translate TTS, free, no key) ──
def generate_with_gtts(script_text, output_path, subtitle_path):
    """Last resort: gTTS. Less natural but always works."""
    try:
        from gtts import gTTS
    except ImportError:
        # Install on the fly in GitHub Actions
        import subprocess
        subprocess.run(["pip", "install", "gTTS"], check=True, capture_output=True)
        from gtts import gTTS

    formatted = format_script_for_speech(script_text)
    tts = gTTS(text=formatted, lang="en", slow=True)
    tts.save(output_path)

    # gTTS doesn't provide word timing, create approximate subtitles
    words = formatted.split()
    # Rough estimate: 2 words/second for slow speech
    subtitles = []
    for i, word in enumerate(words):
        subtitles.append({
            "text": word,
            "offset_ms": i * 500,
            "duration_ms": 400,
        })

    with open(subtitle_path, "w") as f:
        json.dump(subtitles, f, indent=2)

    print("[audio] Generated via gTTS (fallback)")
    return subtitles


def generate_audio(script_text):
    """Main entry: generate audio + subtitles with 3-layer fallback."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio_path = os.path.join(OUTPUT_DIR, "voiceover.mp3")
    subtitle_path = os.path.join(OUTPUT_DIR, "subtitles.json")

    # Layer 1 & 2: edge-tts with multiple voices
    subtitles = generate_with_edge_tts(script_text, audio_path, subtitle_path)

    # Layer 3: gTTS
    if subtitles is None:
        subtitles = generate_with_gtts(script_text, audio_path, subtitle_path)

    if subtitles is None:
        raise RuntimeError("All audio generation layers failed")

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
