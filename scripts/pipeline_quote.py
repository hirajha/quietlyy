"""
Quietlyy — Midday Quote Image Pipeline

Runs at 2:30 PM IST (09:00 UTC) daily:
  1. Generate short powerful life-lesson quote (OpenAI)
  2. Generate dark atmospheric illustrated background (DALL-E 3)
  3. Overlay quote text with PIL → 1080x1350 JPG
  4. Post to Facebook (photo) + Instagram (static image)

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
    print("[pipeline_quote] Starting midday quote image pipeline...")

    # Step 1 & 2 & 3: Generate quote + image
    result = generate_quote_image.generate(theme=theme)
    if not result:
        print("[pipeline_quote] Image generation failed — aborting")
        sys.exit(1)

    quote = result["quote"]
    image_path = result["image_path"]
    print(f"[pipeline_quote] Quote: {quote}")
    print(f"[pipeline_quote] Image: {image_path}")

    # Step 4: Post to Facebook + Instagram
    post_results = post_quote_photo.post(image_path, quote, skip_post=skip_post)

    # Save full result
    final = {
        "quote": quote,
        "theme": result.get("theme"),
        "image_path": image_path,
        "post_results": post_results,
    }
    result_path = os.path.join(OUTPUT_DIR, "quote_post_result.json")
    with open(result_path, "w") as f:
        json.dump(final, f, indent=2)

    print(f"[pipeline_quote] Done. Results saved to {result_path}")

    fb_status = post_results.get("facebook", {}).get("status", "unknown")
    ig_status = post_results.get("instagram", {}).get("status", "unknown")
    print(f"[pipeline_quote] Facebook: {fb_status} | Instagram: {ig_status}")

    return final


if __name__ == "__main__":
    skip = "--skip-post" in sys.argv
    theme = None
    for arg in sys.argv:
        if arg.startswith("--theme="):
            theme = arg.split("=", 1)[1].strip()

    run(skip_post=skip, theme=theme)
