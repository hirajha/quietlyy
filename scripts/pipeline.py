"""
Quietlyy — Main Pipeline Orchestrator
Runs the full pipeline: script -> audio -> images -> video -> post to Facebook.
Quality control: if images or audio fail, skip the day gracefully.
"""

import json
import os
import sys
import shutil

# Add parent to path
sys.path.insert(0, os.path.dirname(__file__))

from generate_script import generate_script
from generate_audio import generate_audio
from generate_images import generate_images
from generate_music import generate_music
from compose_video import compose_video
from post_to_facebook import post

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def clean_output():
    """Clean previous output files (keep used_topics.json)."""
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            path = os.path.join(OUTPUT_DIR, f)
            if f == "used_topics.json":
                continue
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def run(skip_post=False):
    """Run the full Quietlyy pipeline."""
    print("=" * 50)
    print("  QUIETLYY — Automated Video Pipeline")
    print("=" * 50)

    clean_output()

    # Step 1: Generate script
    print("\n[1/5] Generating script...")
    try:
        script_data = generate_script()
    except Exception as e:
        print(f"\nSkipping today — script generation failed: {e}. Will retry tomorrow.")
        sys.exit(0)

    topic = script_data["topic"]
    script_text = script_data["script"]
    visual_keywords = script_data.get("visual_keywords", [topic.lower()])
    print(f"  Topic: {topic}")
    print(f"  Script preview: {script_text[:80]}...")

    # Save script for reference
    with open(os.path.join(OUTPUT_DIR, "script.json"), "w") as f:
        json.dump(script_data, f, indent=2)

    # Step 2: Generate voiceover audio (STRICT — fail = skip day)
    print("\n[2/5] Generating voiceover...")
    try:
        audio_result = generate_audio(script_text)
    except Exception as e:
        print(f"\nSkipping today — audio generation failed: {e}. Will retry tomorrow.")
        sys.exit(0)

    audio_path = audio_result["audio_path"]
    subtitle_path = audio_result["subtitle_path"]
    print(f"  Audio: {audio_path}")

    # Step 3: Generate images (STRICT — fail = skip day)
    print("\n[3/5] Generating panel images...")
    try:
        image_paths = generate_images(topic, visual_keywords, num_panels=5)
    except Exception as e:
        print(f"\nSkipping today — image generation failed: {e}. Will retry tomorrow.")
        sys.exit(0)

    print(f"  Generated {len(image_paths)} panels")

    # Step 4: Fetch background music (topic-specific)
    print("\n[4/6] Fetching background music...")
    try:
        music_path = generate_music(topic)
    except Exception as e:
        print(f"\nSkipping today — music failed: {e}. Will retry tomorrow.")
        sys.exit(0)
    if music_path:
        print(f"  Music: {music_path}")
    else:
        print(f"\nSkipping today — no background music available. Will retry tomorrow.")
        sys.exit(0)

    # Step 5: Compose video
    print("\n[5/6] Compositing video...")
    video_path = compose_video(script_data, image_paths, audio_path, subtitle_path, music_path)
    print(f"  Video: {video_path}")

    # Step 6: Post to Facebook
    if skip_post:
        print("\n[6/6] Skipping Facebook post (--skip-post)")
    else:
        print("\n[6/6] Posting to Facebook...")
        try:
            result = post(video_path, topic, script_text)
            print(f"  Posted successfully!")

            # Save post record
            with open(os.path.join(OUTPUT_DIR, "post_result.json"), "w") as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            print(f"  Facebook posting failed: {e}")
            print("  Video saved locally — you can post manually.")

    print("\n" + "=" * 50)
    print("  PIPELINE COMPLETE")
    print(f"  Topic: {topic}")
    print(f"  Video: {video_path}")
    print("=" * 50)

    return video_path


if __name__ == "__main__":
    skip = "--skip-post" in sys.argv
    run(skip_post=skip)
