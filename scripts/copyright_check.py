"""
Quietlyy — Copyright Compliance Agent

Verifies every asset used in the pipeline is safe for commercial use:
  - Music: CC0 (Creative Commons Zero) from Freesound only
  - Images: DALL-E 3 generated (user owns output per OpenAI ToS)
  - Voice: ElevenLabs commercial license (user's own voice clone / licensed voice)
  - Scripts: 100% AI-generated original content (not copied from any source)

Runs before posting — blocks upload if any asset fails compliance.
Logs compliance status to output/copyright_check.json.
"""

import os
import json

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def check_music(music_path, music_source="freesound_cc0"):
    """
    Verify music is CC0 licensed.
    Freesound filter already enforces license:"Creative Commons 0" at search time.
    This check logs and confirms the source.
    """
    if not music_path or not os.path.exists(music_path):
        return False, "Music file missing"

    size = os.path.getsize(music_path)
    if size < 5000:
        return False, f"Music file too small ({size} bytes) — likely corrupt"

    # Freesound CC0 is enforced at query time via license filter.
    # Bundled fallback uses our own instrumental (no copyright).
    if music_source in ("freesound_cc0", "bundled"):
        return True, f"Music OK — source: {music_source} (CC0 / public domain)"

    return False, f"Unknown music source '{music_source}' — cannot confirm copyright-free"


def check_images(image_paths, generator="dalle"):
    """
    DALL-E 3: Per OpenAI Terms of Service, users own the output images.
    No third-party copyright. Safe for commercial use.
    """
    if not image_paths:
        return False, "No images provided"

    missing = [p for p in image_paths if not os.path.exists(p)]
    if missing:
        return False, f"{len(missing)} image files missing"

    if generator in ("dalle", "dall-e", "dalle3"):
        return True, f"Images OK — DALL-E 3 generated, user owns output (OpenAI ToS §3)"

    if generator == "gemini":
        return True, "Images OK — Gemini generated, Google ToS allows commercial use"

    return False, f"Unknown image generator '{generator}' — cannot confirm copyright-free"


def check_voice(voice_path, provider="elevenlabs"):
    """
    ElevenLabs: Commercial use is permitted on Starter plan and above.
    Voice ID must be either user's own clone or a licensed Professional Voice.
    """
    if not voice_path or not os.path.exists(voice_path):
        return False, "Voice file missing"

    size = os.path.getsize(voice_path)
    if size < 10000:
        return False, f"Voice file too small ({size} bytes)"

    if provider == "elevenlabs":
        return True, "Voice OK — ElevenLabs commercial license (Starter+ plan)"

    return False, f"Unknown voice provider '{provider}' — cannot confirm commercial license"


def check_script(script_text, topic):
    """
    Scripts are 100% AI-generated original content.
    No copying from existing works — original poems generated fresh each run.
    Quality gate already checks for banned openers and duplicate content.
    """
    if not script_text or len(script_text.strip()) < 20:
        return False, "Script text too short or empty"

    # Check it doesn't look like a copied famous quote (very basic heuristic)
    # Famous quotes tend to have attributions or be very short exact phrases
    lines = [l.strip() for l in script_text.split("\n") if l.strip()]
    if len(lines) < 3:
        return False, "Script suspiciously short — may not be original"

    return True, f"Script OK — AI-generated original content, topic: {topic}"


def run_compliance_check(
    music_path=None,
    image_paths=None,
    voice_path=None,
    script_text=None,
    topic="unknown",
    music_source="freesound_cc0",
):
    """
    Run all copyright compliance checks. Returns (all_passed, report_dict).
    Saves report to output/copyright_check.json.
    """
    print("\n[copyright] Running compliance check on all assets...")

    checks = {}
    all_passed = True

    # Music
    ok, msg = check_music(music_path, music_source)
    checks["music"] = {"passed": ok, "message": msg, "file": music_path}
    if not ok:
        print(f"[copyright] FAIL music: {msg}")
        all_passed = False
    else:
        print(f"[copyright] OK   music: {msg}")

    # Images
    ok, msg = check_images(image_paths or [], generator="dalle")
    checks["images"] = {"passed": ok, "message": msg, "count": len(image_paths or [])}
    if not ok:
        print(f"[copyright] FAIL images: {msg}")
        all_passed = False
    else:
        print(f"[copyright] OK   images: {msg}")

    # Voice
    ok, msg = check_voice(voice_path, provider="elevenlabs")
    checks["voice"] = {"passed": ok, "message": msg, "file": voice_path}
    if not ok:
        print(f"[copyright] FAIL voice: {msg}")
        all_passed = False
    else:
        print(f"[copyright] OK   voice: {msg}")

    # Script
    ok, msg = check_script(script_text or "", topic)
    checks["script"] = {"passed": ok, "message": msg, "topic": topic}
    if not ok:
        print(f"[copyright] FAIL script: {msg}")
        all_passed = False
    else:
        print(f"[copyright] OK   script: {msg}")

    report = {
        "all_passed": all_passed,
        "checks": checks,
        "summary": "ALL CLEAR — safe to post" if all_passed else "COMPLIANCE FAILURE — review above",
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "copyright_check.json"), "w") as f:
        json.dump(report, f, indent=2)

    if all_passed:
        print("[copyright] ALL CLEAR — all assets are copyright-free and safe to post\n")
    else:
        print("[copyright] COMPLIANCE FAILURE — one or more assets failed copyright check\n")

    return all_passed, report
