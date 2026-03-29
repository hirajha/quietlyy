"""
Quietlyy — Video Compositor
Combines AI images + voiceover + animated text into a 30s vertical video.
Style: dark moody atmospheric, white italic text, Ken Burns effect, @Quietlyy watermark.
Uses ffmpeg + Pillow for frame generation.
"""

import json
import math
import os
import subprocess
import textwrap
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

# Video specs (vertical 9:16 for Reels)
WIDTH = 1080
HEIGHT = 1920
FPS = 30

# Text styling
TEXT_COLOR = (255, 255, 255, 240)
SHADOW_COLOR = (0, 0, 0, 160)
WATERMARK_COLOR = (255, 255, 255, 100)


def get_font(size, italic=False):
    """Get a font, trying system fonts then falling back."""
    font_names = [
        # Elegant serif/italic fonts available on most systems
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        # macOS
        "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
        "/System/Library/Fonts/Georgia.ttf",
        # Custom font in assets
        os.path.join(ASSETS_DIR, "fonts", "font.ttf"),
    ]
    for path in font_names:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # Fallback to default
    return ImageFont.load_default()


def get_audio_duration(audio_path):
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", audio_path,
        ],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def parse_script_lines(script_text):
    """Split script into display lines."""
    lines = [line.strip() for line in script_text.split("\n") if line.strip()]
    return lines


def create_text_frame(img, text_lines, visible_lines, progress_in_line, watermark=True):
    """
    Render text overlay on an image.
    visible_lines: how many lines are fully visible
    progress_in_line: 0.0-1.0 fade progress of the current line
    """
    frame = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Add dark gradient at bottom for text readability
    for y in range(HEIGHT // 3, HEIGHT):
        alpha = int(180 * ((y - HEIGHT // 3) / (HEIGHT * 2 / 3)))
        draw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, min(alpha, 180)))

    # Main text
    font = get_font(52)
    line_height = 72
    total_text_height = len(text_lines) * line_height
    start_y = HEIGHT // 2 - total_text_height // 2 + 100  # Slightly below center

    for i, line in enumerate(text_lines):
        if i > visible_lines:
            break

        # Calculate alpha for this line
        if i < visible_lines:
            alpha = 240  # Fully visible
        elif i == visible_lines:
            alpha = int(240 * progress_in_line)  # Fading in
        else:
            continue

        y = start_y + i * line_height

        # Word wrap long lines
        wrapped = textwrap.wrap(line, width=28)
        for wi, wline in enumerate(wrapped):
            wy = y + wi * (line_height - 10)
            # Calculate text position (centered)
            bbox = draw.textbbox((0, 0), wline, font=font)
            text_w = bbox[2] - bbox[0]
            x = (WIDTH - text_w) // 2

            # Shadow
            draw.text((x + 3, wy + 3), wline, font=font, fill=(*SHADOW_COLOR[:3], min(alpha, SHADOW_COLOR[3])))
            # Main text
            draw.text((x, wy), wline, font=font, fill=(*TEXT_COLOR[:3], alpha))

    # Watermark
    if watermark:
        wm_font = get_font(32)
        wm_text = "@Quietlyy"
        bbox = draw.textbbox((0, 0), wm_text, font=wm_font)
        wm_w = bbox[2] - bbox[0]
        draw.text(
            ((WIDTH - wm_w) // 2, HEIGHT - 100),
            wm_text, font=wm_font, fill=WATERMARK_COLOR,
        )

    frame = Image.alpha_composite(frame, overlay)
    return frame.convert("RGB")


def apply_ken_burns(img, progress, direction=0):
    """Apply slow zoom/pan (Ken Burns effect) to an image."""
    # Ensure image covers the frame
    img_ratio = img.width / img.height
    target_ratio = WIDTH / HEIGHT

    if img_ratio > target_ratio:
        new_h = int(img.width / target_ratio)
        img = img.resize((img.width, new_h), Image.LANCZOS)
    else:
        new_w = int(img.height * target_ratio)
        img = img.resize((new_w, img.height), Image.LANCZOS)

    # Scale up for zoom headroom
    scale_base = 1.15
    scale_end = 1.25
    scale = scale_base + (scale_end - scale_base) * progress

    new_w = int(WIDTH * scale)
    new_h = int(HEIGHT * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Pan based on direction
    max_x = new_w - WIDTH
    max_y = new_h - HEIGHT

    if direction == 0:  # Zoom in center
        x = max_x // 2
        y = max_y // 2
    elif direction == 1:  # Pan right
        x = int(max_x * progress)
        y = max_y // 2
    elif direction == 2:  # Pan up
        x = max_x // 2
        y = int(max_y * (1 - progress))
    else:  # Pan left
        x = int(max_x * (1 - progress))
        y = max_y // 2

    return img.crop((x, y, x + WIDTH, y + HEIGHT))


def add_particle_effect(draw, frame_num, particle_type="snow"):
    """Add subtle snow/dust particles."""
    import random
    random.seed(frame_num * 7)  # Deterministic but varied

    for _ in range(15):
        x = random.randint(0, WIDTH)
        # Particles drift down slowly
        base_y = (random.randint(0, HEIGHT) + frame_num * 2) % HEIGHT
        size = random.randint(1, 3)
        alpha = random.randint(40, 120)
        # Slight horizontal drift
        x_drift = int(math.sin(frame_num * 0.05 + x * 0.01) * 10)
        draw.ellipse(
            [x + x_drift - size, base_y - size, x + x_drift + size, base_y + size],
            fill=(255, 255, 255, alpha),
        )


def compose_video(script_data, image_paths, audio_path, subtitle_path):
    """
    Main compositor: generates frames and assembles final video.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    frames_dir = os.path.join(OUTPUT_DIR, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    # Get audio duration
    duration = get_audio_duration(audio_path)
    total_frames = int(duration * FPS)

    # Parse script lines
    script_lines = parse_script_lines(script_data["script"])
    num_lines = len(script_lines)

    # Load images
    images = []
    for path in image_paths:
        img = Image.open(path).convert("RGBA")
        # Resize to cover frame
        img_ratio = img.width / img.height
        target_ratio = WIDTH / HEIGHT
        if img_ratio > target_ratio:
            new_h = HEIGHT + 200  # Extra for Ken Burns
            new_w = int(new_h * img_ratio)
        else:
            new_w = WIDTH + 200
            new_h = int(new_w / img_ratio)
        images.append(img.resize((new_w, new_h), Image.LANCZOS))

    # Load subtitle timing for text sync
    with open(subtitle_path, "r") as f:
        subtitles = json.load(f)

    # Calculate line timing from subtitle data
    # Map subtitle words back to script lines
    line_timings = _calculate_line_timings(script_lines, subtitles, duration)

    print(f"[video] Generating {total_frames} frames ({duration:.1f}s @ {FPS}fps)")

    # Generate frames
    for frame_num in range(total_frames):
        current_time = frame_num / FPS
        progress = frame_num / max(total_frames - 1, 1)

        # Determine which image to show (distribute across duration)
        img_idx = min(int(progress * len(images)), len(images) - 1)
        img = images[img_idx]

        # Calculate per-image progress for Ken Burns
        img_progress_start = img_idx / len(images)
        img_progress_end = (img_idx + 1) / len(images)
        img_local_progress = (progress - img_progress_start) / max(img_progress_end - img_progress_start, 0.01)
        img_local_progress = max(0, min(1, img_local_progress))

        # Apply Ken Burns
        frame = apply_ken_burns(img, img_local_progress, direction=img_idx % 4)

        # Determine visible text lines
        visible_lines = 0
        line_progress = 0.0
        for i, (start, end) in enumerate(line_timings):
            if current_time >= end:
                visible_lines = i + 1
            elif current_time >= start:
                visible_lines = i
                line_progress = min(1.0, (current_time - start) / max(end - start, 0.1))
                break

        # Apply text overlay
        frame = frame.convert("RGBA")
        frame = create_text_frame(frame, script_lines, visible_lines, line_progress)

        # Add particles
        particle_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        p_draw = ImageDraw.Draw(particle_overlay)
        add_particle_effect(p_draw, frame_num)
        frame_rgba = frame.convert("RGBA")
        frame = Image.alpha_composite(frame_rgba, particle_overlay).convert("RGB")

        # Save frame
        frame_path = os.path.join(frames_dir, f"frame_{frame_num:05d}.png")
        frame.save(frame_path, "PNG")

        if frame_num % (FPS * 5) == 0:
            print(f"[video] Frame {frame_num}/{total_frames} ({progress*100:.0f}%)")

    # Assemble with ffmpeg
    output_path = os.path.join(OUTPUT_DIR, "quietlyy_video.mp4")
    _assemble_video(frames_dir, audio_path, output_path, duration)

    # Cleanup frames
    import shutil
    shutil.rmtree(frames_dir, ignore_errors=True)

    print(f"[video] Done: {output_path}")
    return output_path


def _calculate_line_timings(script_lines, subtitles, total_duration):
    """Map subtitle word timings back to script lines to sync text appearance."""
    if not subtitles:
        # Even distribution fallback
        gap = total_duration / len(script_lines)
        return [(i * gap, (i + 0.7) * gap) for i in range(len(script_lines))]

    # Build a flat string of subtitle words
    sub_words = [s["text"].lower().strip(".,…!?\"'") for s in subtitles]
    line_timings = []

    sub_idx = 0
    for line in script_lines:
        line_words = [w.lower().strip(".,…!?\"'") for w in line.split() if w.strip(".,…!?\"'")]
        if not line_words:
            continue

        # Find first word of this line in subtitles
        start_time = None
        end_time = None
        search_start = sub_idx

        for si in range(search_start, len(subtitles)):
            word = sub_words[si] if si < len(sub_words) else ""
            if word == line_words[0] or (len(line_words[0]) > 3 and line_words[0] in word):
                start_time = subtitles[si]["offset_ms"] / 1000.0
                sub_idx = si
                break

        # Find approximate end (look for last word of line)
        for si in range(sub_idx, min(sub_idx + len(line_words) + 5, len(subtitles))):
            end_time = (subtitles[si]["offset_ms"] + subtitles[si]["duration_ms"]) / 1000.0

        if start_time is None:
            # Fallback: distribute evenly from last known time
            last_end = line_timings[-1][1] if line_timings else 0
            start_time = last_end + 0.3
            end_time = start_time + (total_duration / len(script_lines)) * 0.7

        sub_idx = min(sub_idx + len(line_words), len(subtitles) - 1)
        line_timings.append((start_time, end_time))

    return line_timings


def _assemble_video(frames_dir, audio_path, output_path, duration):
    """Use ffmpeg to combine frames + audio into final MP4."""
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(frames_dir, "frame_%05d.png"),
        "-i", audio_path,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]
    print(f"[video] Assembling with ffmpeg...")
    subprocess.run(cmd, check=True, capture_output=True)


if __name__ == "__main__":
    # Test with existing output files
    script_data = {"script": "Test line 1\nTest line 2\nTest line 3"}
    print("Video compositor ready. Run via pipeline.py")
