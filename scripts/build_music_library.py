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
    _generate_sonauto_music, _save_to_music_gallery, _MUSICGEN_PROMPTS,
)

SAFE_MOODS = ["heartbreak", "longing", "melancholy"]

# Extra prompt variety per mood so the batch isn't 8 near-identical tracks —
# we vary instrumentation/tempo/feel while staying soft + emotional + no vocals.
_VARIANTS = {
    "heartbreak": [
        "Soft sad piano with deep cello, melancholic heartbreak ballad, slow 60 BPM, cinematic, gentle strings, no drums, no vocals",
        "Sparse mournful piano, distant violin, aching heartbreak, very slow, intimate, reverb, no vocals",
        "Tender broken piano melody with warm cello swells, grief and longing, cinematic, no vocals",
        "Fragile solo piano, soft string pad underneath, quiet heartbreak, slow and spacious, no vocals",
        "Emotional piano with subtle ambient texture, sorrowful, film-score feel, no drums, no vocals",
        "Slow heartbreaking piano and cello duet, melancholic, cinematic, delicate, no vocals",
        "Dark tender piano, low strings, the ache after goodbye, slow and heavy, no vocals",
        "Wistful piano with soft violin counter-melody, bittersweet heartbreak, cinematic, no vocals",
        "Minimal aching piano, warm analog pad, lonely and emotional, very slow, no vocals",
        "Cinematic heartbreak piano with rising strings, deeply moving, slow build, no vocals",
    ],
    "longing": [
        "Wistful piano with cello and violin, nostalgic longing melody, slow 65 BPM, sparse cinematic, no vocals",
        "Distant dreamy piano, soft strings, missing someone, gentle and yearning, no vocals",
        "Warm nostalgic piano with light ambient texture, longing and memory, cinematic, no vocals",
        "Soft piano arpeggios with cello, quiet yearning, slow and tender, film-score, no vocals",
        "Reflective piano and violin, the ache of distance, spacious and emotional, no vocals",
        "Gentle longing piano, faint strings swell, bittersweet hope, slow cinematic, no vocals",
        "Sparse intimate piano with warm reverb, wistful, late-night feel, no vocals",
        "Nostalgic piano melody with soft pad, longing and calm, cinematic, no drums, no vocals",
        "Tender piano with distant cello, yearning and quiet, slow and delicate, no vocals",
        "Emotional cinematic piano, light strings, the feeling of missing home, no vocals",
    ],
    "melancholy": [
        "Dark melancholy piano and cello, sad atmosphere, slow 60 BPM, cinematic, ambient strings, no vocals",
        "Brooding minimal piano, low ambient drone, introspective sadness, very slow, no vocals",
        "Somber piano with deep strings, grey and contemplative, cinematic, no drums, no vocals",
        "Quiet melancholic piano, soft cello underneath, lonely and still, slow, no vocals",
        "Moody piano with subtle dissonance, reflective sorrow, ambient, cinematic, no vocals",
        "Slow melancholy piano and warm pad, heavy-hearted, spacious, film-score, no vocals",
        "Desolate piano melody, distant strings, cold and emotional, very slow, no vocals",
        "Pensive piano with low cello, the weight of sadness, cinematic, no vocals",
        "Soft dark piano, ambient texture, introspective and heavy, slow, no vocals",
        "Melancholic cinematic piano with strings, deeply emotional, slow and somber, no vocals",
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
                ok = _generate_sonauto_music(mood, tmp, duration_sec=30)
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
