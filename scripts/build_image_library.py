"""
Quietlyy — Image Library Builder

Generates a one-time batch of painterly atmospheric panel images (the same
generic lone-figure-vs-landscape scenes the pipeline uses) and banks them into
assets/gallery/. The pipeline then REUSES this library for most panels
(_pick_reuse_panels), generating only FRESH_PER_VIDEO fresh images per video.

Why: generating every panel fresh (5 × 4 videos = 20/day) hit Cloudflare's
10k-neuron/day free image limit and stopped posts. A stock library + reuse
drops daily generation to ~8, with huge headroom, and doubles as resilience
stock if a provider kills its free tier.

Free-first via the same provider chain as the pipeline (Together → Cloudflare →
Nano Banana). Stops gracefully when providers are exhausted (e.g. Cloudflare
429 daily limit) — keeps whatever it generated. Re-run on later days (after the
daily quota resets) to grow the library toward ~40 images.

USAGE:
  python scripts/build_image_library.py --count 16
  python scripts/build_image_library.py --count 20 --style emotional
"""

import argparse
import os
import sys
import time

from generate_images import (
    OUTPUT_DIR, _SCENE_POOL, _LOVE_SCENE_POOL,
    generate_image_prompt, _add_to_gallery, _load_gallery_index,
    generate_with_together, generate_with_cloudflare,
    generate_with_gemini_flash_image, generate_with_pollinations,
)

# Varied generic emotional themes so the batch isn't all the same mood — these
# only tint the prompt; the scene (lone figure vs landscape) carries the image.
_THEMES = [
    "letting go", "quiet longing", "healing slowly", "missing someone",
    "finding peace", "lonely strength", "a fresh start", "bittersweet memory",
]
_KEYWORDS = ["solitude", "stillness", "soft light", "distance", "calm", "ache"]


def _generate_one(prompt, tmp):
    """Free-first chain — same order as the pipeline, minus paid/dead providers."""
    if generate_with_together(prompt, tmp):
        return True
    if generate_with_cloudflare(prompt, tmp):
        return True
    if generate_with_gemini_flash_image(prompt, tmp):
        return True
    if generate_with_pollinations(prompt, tmp):
        return True
    return False


def build(count, style):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pool = _LOVE_SCENE_POOL if style == "love" else _SCENE_POOL
    before = len(_load_gallery_index())
    made = 0
    consecutive_fail = 0

    for i in range(count):
        theme = _THEMES[i % len(_THEMES)]
        # generate_image_prompt picks a scene by panel index from a shuffled pool;
        # vary the index across the whole pool so scenes differ.
        prompt = generate_image_prompt(theme, _KEYWORDS, i, style=style)
        tmp = os.path.join(OUTPUT_DIR, f"_lib_img_{i}.png")
        print(f"\n[img-lib] {i+1}/{count} — theme '{theme}'")
        ok = _generate_one(prompt, tmp)
        if ok and os.path.exists(tmp) and os.path.getsize(tmp) > 5000:
            _add_to_gallery(tmp, f"library:{theme}", i, "library")
            made += 1
            consecutive_fail = 0
            try:
                os.remove(tmp)
            except OSError:
                pass
        else:
            consecutive_fail += 1
            print(f"[img-lib] {i+1}: failed (provider exhausted/down)")
            # All free providers down (likely Cloudflare daily limit) — stop
            # rather than hammer. Re-run after the daily quota resets.
            if consecutive_fail >= 2:
                print("[img-lib] 2 consecutive failures — stopping "
                      "(likely daily free quota hit). Re-run after reset.")
                break
        time.sleep(2)

    after = len(_load_gallery_index())
    print(f"\n[img-lib] DONE — {made} images added "
          f"(gallery {before} → {after})")
    return made


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=16)
    p.add_argument("--style", default="emotional", choices=["emotional", "love"])
    args = p.parse_args()
    n = build(args.count, args.style)
    sys.exit(0 if n > 0 else 1)


if __name__ == "__main__":
    main()
