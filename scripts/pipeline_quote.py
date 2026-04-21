"""
Quietlyy — Midday Quote Carousel Pipeline

Runs at 2:30 PM IST (09:00 UTC) daily:
  1. Generate 2 powerful emotionally-resonant quotes (OpenAI)
  2. Generate dark atmospheric background (DALL-E / gpt-image-1)
  3. Build 3-slide carousel: main quote / second quote / brand CTA
  4. Post to Facebook (multi-photo album post) + Instagram (carousel)

Carousel format: 3.1x more engagement than single static images.

Usage:
  python scripts/pipeline_quote.py
  python scripts/pipeline_quote.py --skip-post   # generate only, no posting
  python scripts/pipeline_quote.py --theme="letting go"
"""

import sys
import os
import json

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

sys.path.insert(0, os.path.dirname(__file__))
import generate_quote_image
import post_quote_photo


def run(skip_post=False, theme=None):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("[pipeline_quote] Starting midday quote carousel pipeline...")

    # Step 1-3: Generate quotes + carousel slides
    result = generate_quote_image.generate(theme=theme)
    if not result:
        print("[pipeline_quote] Image generation failed — aborting")
        sys.exit(1)

    quotes = result.get("quotes", [result.get("quote", "")])
    image_paths = result.get("image_paths", [result.get("image_path")])
    image_paths = [p for p in image_paths if p and os.path.exists(p)]

    print(f"[pipeline_quote] Quotes: {quotes}")
    print(f"[pipeline_quote] Slides: {image_paths}")

    if not image_paths:
        print("[pipeline_quote] No slide images found — aborting")
        sys.exit(1)

    # Step 4: Post carousel to Facebook + Instagram
    post_results = post_quote_photo.post(image_paths, quotes[0], skip_post=skip_post)

    final = {
        "quotes": quotes,
        "theme": result.get("theme"),
        "image_paths": image_paths,
        "post_results": post_results,
    }
    result_path = os.path.join(OUTPUT_DIR, "quote_post_result.json")
    with open(result_path, "w") as f:
        json.dump(final, f, indent=2)

    print(f"[pipeline_quote] Done. Results: {result_path}")

    fb_status = post_results.get("facebook", {}).get("status", "unknown")
    ig_status = post_results.get("instagram", {}).get("status", "unknown")
    fb_slides = post_results.get("facebook", {}).get("slides", "-")
    ig_slides = post_results.get("instagram", {}).get("slides", "-")
    print(f"[pipeline_quote] Facebook: {fb_status} ({fb_slides} slides) | Instagram: {ig_status} ({ig_slides} slides)")

    return final


if __name__ == "__main__":
    skip = "--skip-post" in sys.argv
    theme = None
    for arg in sys.argv:
        if arg.startswith("--theme="):
            theme = arg.split("=", 1)[1].strip()

    run(skip_post=skip, theme=theme)
