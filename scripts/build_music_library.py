"""
Quietlyy — Music Library Builder

Generates a one-time batch of premium emotional/cinematic instrumental tracks
via Sonauto and stores them in assets/music_gallery/<mood>/. The pipeline then
ROTATES this library (like Whisprs reuses a set of mood tracks) instead of
generating per-video — so a small one-time Sonauto top-up gives great music
forever, no recurring cost.

Only the 3 SAFE moods matter (everything maps to these via _SAFE_MOOD_MAP):
  heartbreak / longing / melancholy

USAGE:
  python scripts/build_music_library.py --per-mood 8        # ~24 tracks
  python scripts/build_music_library.py --per-mood 10 --moods heartbreak,longing

Each Sonauto track ≈ 100 credits. 24 tracks ≈ 2400 credits.
Stops gracefully when credits run out (402) — keeps whatever it generated.
"""

import argparse
import os
import sys
import time

from generate_music import (
    _generate_elevenlabs_music, _generate_sonauto_music,
    _save_to_music_gallery, _MUSICGEN_PROMPTS,
)


def _generate_one_track(mood, tmp):
    """Try ElevenLabs Music first (premium, same key as voice), then Sonauto."""
    if _generate_elevenlabs_music(mood, tmp, duration_sec=30):
        return True
    return _generate_sonauto_music(mood, tmp, duration_sec=30)

SAFE_MOODS = ["heartbreak", "longing", "melancholy"]

# Extra prompt variety per mood so the batch isn't 8 near-identical tracks —
# we vary instrumentation/tempo/feel while staying soft + emotional + no vocals.
# SONG-STYLE ballad instrumentals (real melody + arrangement, like a sad
# song minus vocals — NOT ambient pads). Original/AI-composed = copyright-safe.
_VARIANTS = {
    "heartbreak": [
        "Emotional sad piano ballad instrumental, heartfelt memorable melody, piano + warm strings + soft beat, like an acoustic pop ballad minus vocals, slow 65 BPM, instrumental only, no vocals",
        "Modern heartbreak ballad instrumental, aching piano melody with strings and a gentle drum, song structure, emotional, like a sad pop song without vocals, no vocals",
        "Tender broken-hearted ballad, piano lead with cello and soft beat, a moving melody like an indie ballad minus vocals, slow, no vocals",
        "Cinematic heartbreak song instrumental, piano melody building with strings and light percussion, emotional pop-ballad feel, no vocals",
        "Sad acoustic ballad instrumental, guitar and piano with strings and a soft heartbeat beat, memorable melody minus vocals, no vocals",
        "Heartfelt piano ballad with a strong emotional melody, strings swell and gentle drums, like a sad radio ballad without vocals, no vocals",
        "Slow heartbreak ballad, piano and cello with a soft modern beat, a melody that aches, song-style minus vocals, no vocals",
        "Moving piano-driven ballad instrumental, warm strings, soft beat, emotional pop song feel without vocals, no vocals",
        "Bittersweet ballad instrumental, piano melody with light electronic beat and strings, modern sad song minus vocals, no vocals",
        "Emotional cinematic ballad, piano and strings with a gentle drum groove, a real melody like a heartbreak song without vocals, no vocals",
    ],
    "longing": [
        "Wistful nostalgic ballad instrumental, flowing piano melody with acoustic guitar, soft strings and gentle beat, like a tender indie love song minus vocals, slow 68 BPM, no vocals",
        "Dreamy longing ballad, piano and strings with a soft beat, a memorable melody of missing someone, song-style minus vocals, no vocals",
        "Warm nostalgic song instrumental, piano and guitar with light percussion, emotional and yearning, like a soft pop ballad without vocals, no vocals",
        "Tender yearning ballad, piano melody with cello and a gentle modern beat, indie-folk song feel minus vocals, no vocals",
        "Reflective longing ballad instrumental, piano and strings with soft drums, an emotional melody like a quiet love song without vocals, no vocals",
        "Bittersweet hopeful ballad, piano lead with strings and gentle beat, song structure, the ache of distance minus vocals, no vocals",
        "Intimate late-night ballad, warm piano melody with soft beat and strings, like an acoustic song without vocals, no vocals",
        "Nostalgic ballad instrumental, piano and acoustic guitar with light percussion, memorable yearning melody minus vocals, no vocals",
        "Gentle longing song, piano and cello with a soft heartbeat beat, emotional indie ballad feel without vocals, no vocals",
        "Emotional cinematic ballad of missing home, piano and strings with soft drums, real melody minus vocals, no vocals",
    ],
    "melancholy": [
        "Melancholic emotional ballad instrumental, clear sad piano melody with cello and a soft heartbeat drum, modern sad-pop song minus vocals, slow 62 BPM, no vocals",
        "Brooding ballad, piano melody with low strings and gentle beat, introspective sad song structure minus vocals, no vocals",
        "Somber song instrumental, piano and strings with soft percussion, grey and emotional, like a sad ballad without vocals, no vocals",
        "Quiet melancholic ballad, piano lead with cello and a gentle modern beat, a lonely melody minus vocals, no vocals",
        "Moody emotional ballad, piano with strings and light drums, reflective sorrow in song form without vocals, no vocals",
        "Heavy-hearted ballad instrumental, piano and warm pad with soft beat, cinematic sad song minus vocals, no vocals",
        "Desolate yet melodic ballad, piano and distant strings with gentle percussion, cold emotional song-style minus vocals, no vocals",
        "Pensive ballad, piano with low cello and a soft beat, the weight of sadness as a song without vocals, no vocals",
        "Dark emotional ballad instrumental, piano melody with strings and subtle drums, modern melancholic song minus vocals, no vocals",
        "Deeply emotional cinematic ballad, piano and strings with a soft drum groove, a sad memorable melody without vocals, no vocals",
    ],
}


def build(per_mood, moods):
    made, failed = 0, 0
    for mood in moods:
        variants = _VARIANTS.get(mood, [_MUSICGEN_PROMPTS.get(mood, "")])
        print(f"\n[lib] === {mood}: generating {per_mood} tracks ===")
        for i in range(per_mood):
            prompt = variants[i % len(variants)]
            tmp = os.path.join(os.path.dirname(__file__), "..", "output", f"_lib_{mood}_{i}.mp3")
            os.makedirs(os.path.dirname(tmp), exist_ok=True)
            print(f"[lib] {mood} {i+1}/{per_mood}: '{prompt[:55]}...'")
            # _generate_sonauto_music uses _MUSICGEN_PROMPTS[mood]; temporarily
            # override so each track gets a distinct variant prompt.
            orig = _MUSICGEN_PROMPTS.get(mood)
            _MUSICGEN_PROMPTS[mood] = prompt
            try:
                ok = _generate_one_track(mood, tmp)
            finally:
                if orig is not None:
                    _MUSICGEN_PROMPTS[mood] = orig
            if ok:
                _save_to_music_gallery(mood, tmp, prompt_used=prompt)
                made += 1
                try: os.remove(tmp)
                except OSError: pass
            else:
                failed += 1
                print(f"[lib] {mood} {i+1}: failed (likely out of credits — stopping mood)")
                # If a generation fails (credits/rate), don't keep hammering this mood
                break
            time.sleep(2)  # gentle pacing
    print(f"\n[lib] DONE — {made} tracks added to gallery, {failed} failures")
    return made


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--per-mood", type=int, default=8)
    p.add_argument("--moods", default=",".join(SAFE_MOODS))
    args = p.parse_args()
    moods = [m.strip() for m in args.moods.split(",") if m.strip()]
    if not os.environ.get("SONAUTO_API_KEY"):
        print("ERROR: SONAUTO_API_KEY not set"); sys.exit(1)
    n = build(args.per_mood, moods)
    sys.exit(0 if n > 0 else 1)


if __name__ == "__main__":
    main()
