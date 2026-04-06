"""
Quietlyy — Main Pipeline Orchestrator
Full pipeline: market research → script → audio → images → music →
              video → SEO → quality gate → Facebook/Instagram → YouTube Shorts.

Quality rules (never post incomplete videos):
  - ElevenLabs audio is STRICT: quota / key error = skip day
  - Images: DALL-E / Gemini only — no gradient fallbacks allowed
  - Music: required — no silent videos
  - Video must pass size check before any upload attempt

Quota handling:
  - HTTP 429 / quota errors = graceful skip (sys.exit(0)), retry tomorrow
  - Permanent errors = also skip gracefully, log reason
"""

import json
import os
import sys
import shutil

sys.path.insert(0, os.path.dirname(__file__))

from generate_script import generate_script
from generate_audio import generate_audio
from generate_images import generate_images
from generate_music import generate_music
from compose_video import compose_video
from generate_seo import generate_seo
from market_research import get_research, get_tone_hints, get_top_themes
from fetch_ideas import fetch_fresh_ideas, ideas_to_theme_hints
from post_to_facebook import post
from post_to_instagram import post as post_instagram
from post_to_youtube import post as post_youtube

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# ── Quality thresholds ──────────────────────────────────────────────────────
MIN_AUDIO_BYTES   = 100_000   # 100 KB — ElevenLabs audio for 5 lines
MIN_IMAGE_BYTES   =  50_000   # 50 KB  — real AI image (not gradient/placeholder)
MIN_VIDEO_BYTES   = 800_000   # 800 KB — 30s vertical video
NUM_PANELS        = 5


def clean_output():
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


def quality_check(audio_path, image_paths, music_path, video_path):
    """
    Hard quality gate — returns (passed: bool, reason: str).
    If failed, pipeline must NOT post — skip the day instead.
    """
    errors = []

    # 1. Audio
    if not os.path.exists(audio_path):
        errors.append("Audio file missing")
    elif os.path.getsize(audio_path) < MIN_AUDIO_BYTES:
        errors.append(f"Audio too small ({os.path.getsize(audio_path)} bytes) — likely not ElevenLabs")

    # 2. Images — all panels must exist and be real AI images
    if len(image_paths) < NUM_PANELS:
        errors.append(f"Only {len(image_paths)}/{NUM_PANELS} image panels generated")
    else:
        for i, img in enumerate(image_paths):
            if not os.path.exists(img):
                errors.append(f"Panel {i} missing: {img}")
            elif os.path.getsize(img) < MIN_IMAGE_BYTES:
                errors.append(f"Panel {i} too small ({os.path.getsize(img)} bytes) — may be placeholder")

    # 3. Music
    if not music_path or not os.path.exists(music_path):
        errors.append("Background music missing")

    # 4. Video
    if not os.path.exists(video_path):
        errors.append("Video file missing")
    elif os.path.getsize(video_path) < MIN_VIDEO_BYTES:
        errors.append(f"Video too small ({os.path.getsize(video_path)} bytes)")

    if errors:
        return False, " | ".join(errors)
    return True, "OK"


def _is_quota_error(exc):
    """Detect API quota / rate limit errors."""
    msg = str(exc).lower()
    return any(k in msg for k in ["429", "quota", "rate limit", "rate_limit",
                                   "resource_exhausted", "insufficient_quota",
                                   "credits"])


def run(skip_post=False, skip_youtube=False):
    print("=" * 50)
    print("  QUIETLYY — Automated Video Pipeline")
    print("=" * 50)

    clean_output()

    # ── Step 0: Market research (cached weekly, always fast) ───────────────
    print("\n[0/7] Loading audience intelligence...")
    try:
        research = get_research()
        tone_hints = get_tone_hints(research)
        top_themes = get_top_themes(research)
        peak_times = research.get("peak_posting_times_IST", {})
        print(f"  Top geo: {', '.join(research.get('target_demographics', {}).get('top_geos', [])[:3])}")
        print(f"  Peak FB/IG: {peak_times.get('instagram_reels', ['?', '?'])}")
        print(f"  Peak YT: {peak_times.get('youtube_shorts', ['?', '?'])}")
    except Exception as e:
        print(f"  Market research failed ({e}), continuing with defaults")
        tone_hints = ""
        top_themes = []

    # ── Step 0b: Fresh Ideas Agent (web search for trending emotional topics) ─
    print("\n[0b/7] Fetching fresh ideas from web...")
    idea_hints = ""
    try:
        fresh_ideas = fetch_fresh_ideas(existing_topics=top_themes)
        idea_hints = ideas_to_theme_hints(fresh_ideas)
        if idea_hints:
            print(f"  {len(fresh_ideas)} fresh ideas loaded from web research")
        else:
            print("  No web ideas — using topic pool only")
    except Exception as e:
        print(f"  Ideas agent failed ({e}) — continuing without web ideas")

    # ── Step 1: Generate script (Ideas → Script → Quality Gate) ────────────
    print("\n[1/7] Generating script (with quality gate)...")
    try:
        script_data = generate_script(tone_hints=tone_hints, theme_hints=top_themes, idea_hints=idea_hints)
    except Exception as e:
        if _is_quota_error(e):
            print(f"\nSkipping today — quota exceeded. Will retry tomorrow.")
            sys.exit(0)
        elif "quality gate failed" in str(e).lower():
            print(f"\nERROR — Script quality gate exhausted all attempts: {e}")
            print("Check logs above to see why scripts were rejected.")
            sys.exit(1)  # Fail visibly so it shows in GitHub Actions
        else:
            print(f"\nSkipping today — script failed: {e}. Will retry tomorrow.")
            sys.exit(0)

    topic = script_data["topic"]
    script_text = script_data["script"]
    visual_keywords = script_data.get("visual_keywords", [topic.lower()])
    print(f"  Topic: {topic}")
    print(f"  Preview: {script_text[:80]}...")

    with open(os.path.join(OUTPUT_DIR, "script.json"), "w") as f:
        json.dump(script_data, f, indent=2)

    # ── Step 2: Audio (ElevenLabs only — quota = skip day) ─────────────────
    print("\n[2/7] Generating voiceover...")
    try:
        audio_result = generate_audio(script_text)
    except Exception as e:
        if _is_quota_error(e):
            print(f"\nSkipping today — ElevenLabs quota exceeded. Will retry tomorrow.")
        else:
            print(f"\nSkipping today — audio failed: {e}. Will retry tomorrow.")
        sys.exit(0)

    audio_path = audio_result["audio_path"]
    subtitle_path = audio_result["subtitle_path"]
    print(f"  Audio: {audio_path}")

    # ── Step 3: Images (AI only — quota = skip day) ─────────────────────────
    print("\n[3/7] Generating panel images...")
    try:
        image_paths = generate_images(topic, visual_keywords, num_panels=NUM_PANELS)
    except Exception as e:
        if _is_quota_error(e):
            print(f"\nSkipping today — image API quota exceeded. Will retry tomorrow.")
        else:
            print(f"\nSkipping today — image generation failed: {e}. Will retry tomorrow.")
        sys.exit(0)

    print(f"  Generated {len(image_paths)} panels")

    # ── Step 4: Music ───────────────────────────────────────────────────────
    print("\n[4/7] Fetching background music...")
    try:
        music_path = generate_music(topic)
    except Exception as e:
        print(f"\nSkipping today — music failed: {e}. Will retry tomorrow.")
        sys.exit(0)
    if not music_path:
        print(f"\nSkipping today — no background music available. Will retry tomorrow.")
        sys.exit(0)
    print(f"  Music: {music_path}")

    # ── Step 5: Compose video ───────────────────────────────────────────────
    print("\n[5/7] Compositing video...")
    video_path = compose_video(script_data, image_paths, audio_path, subtitle_path, music_path)
    print(f"  Video: {video_path}")

    # ── QUALITY GATE — must pass before any upload ──────────────────────────
    print("\n[QC] Running quality check...")
    passed, reason = quality_check(audio_path, image_paths, music_path, video_path)
    if not passed:
        print(f"\nQUALITY GATE FAILED: {reason}")
        print("Skipping today — will not post an incomplete video. Retry tomorrow.")
        sys.exit(0)
    print(f"  Quality check passed ✓")

    # ── Step 6: SEO metadata ────────────────────────────────────────────────
    print("\n[6/7] Generating SEO metadata...")
    try:
        seo_metadata = generate_seo(topic, script_text, visual_keywords)
        print(f"  {len(seo_metadata['facebook']['hashtags'])} FB/IG tags | "
              f"YT title: {seo_metadata['youtube']['title'][:50]}...")
        with open(os.path.join(OUTPUT_DIR, "seo_metadata.json"), "w") as f:
            json.dump(seo_metadata, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  SEO failed ({e}), using fallback")
        seo_metadata = None

    # ── Step 7a: Facebook ───────────────────────────────────────────────────
    if skip_post:
        print("\n[7a/7] Skipping Facebook post (--skip-post)")
    else:
        print("\n[7a/7] Posting to Facebook...")
        try:
            result = post(video_path, topic, script_text, seo_metadata=seo_metadata)
            print(f"  Facebook posted!")
            with open(os.path.join(OUTPUT_DIR, "post_result.json"), "w") as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            print(f"  Facebook posting failed: {e}")
            print("  Video saved — post manually.")

    # ── Step 7a2: Instagram (direct) ────────────────────────────────────────
    if skip_post:
        print("\n[7a2/7] Skipping Instagram post (--skip-post)")
    elif not os.environ.get("INSTAGRAM_USER_ID"):
        print("\n[7a2/7] Skipping Instagram post (INSTAGRAM_USER_ID not set)")
    else:
        print("\n[7a2/7] Posting to Instagram Reels (direct)...")
        try:
            ig_caption = ""
            if seo_metadata and "facebook" in seo_metadata:
                ig_caption = seo_metadata["facebook"]["description"]
            else:
                ig_caption = f"{script_text}\n\n— Quietlyy\n\n#Quietlyy #emotional #quotes"
            ig_result = post_instagram(video_path, ig_caption)
            print(f"  Instagram Reel posted! ID: {ig_result.get('id')}")
            with open(os.path.join(OUTPUT_DIR, "instagram_result.json"), "w") as f:
                json.dump(ig_result, f, indent=2)
        except Exception as e:
            print(f"  Instagram posting failed: {e}")
            print("  Video saved — post manually to Instagram.")

    # ── Step 7b: YouTube Shorts ─────────────────────────────────────────────
    if skip_youtube:
        print("\n[7b/7] Skipping YouTube post (--skip-youtube)")
    elif not os.environ.get("YOUTUBE_CLIENT_ID"):
        print("\n[7b/7] Skipping YouTube post (YOUTUBE_CLIENT_ID not set)")
    else:
        print("\n[7b/7] Posting to YouTube Shorts...")
        try:
            yt_result = post_youtube(video_path, topic, script_text, seo_metadata=seo_metadata)
            print(f"  Short posted: {yt_result['url']}")
            with open(os.path.join(OUTPUT_DIR, "youtube_result.json"), "w") as f:
                json.dump(yt_result, f, indent=2)
        except Exception as e:
            if _is_quota_error(e):
                print(f"  YouTube quota exceeded — will retry tomorrow.")
            else:
                print(f"  YouTube posting failed: {e}")
            print("  Video saved — upload manually if needed.")

    print("\n" + "=" * 50)
    print("  PIPELINE COMPLETE")
    print(f"  Topic: {topic}")
    print(f"  Video: {video_path}")
    print("=" * 50)

    return video_path


if __name__ == "__main__":
    skip = "--skip-post" in sys.argv
    skip_yt = "--skip-youtube" in sys.argv
    run(skip_post=skip, skip_youtube=skip_yt)
