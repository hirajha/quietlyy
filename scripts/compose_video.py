"""
Quietlyy — Video Compositor
Shows ONE line at a time (poem style), fading in and out.
Style: dark moody, white italic text centered, Ken Burns, @Quietlyy watermark.
"""

import json
import math
import os
import random
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
TEXT_COLOR = (255, 255, 255)
SHADOW_COLOR = (0, 0, 0)
WATERMARK_COLOR = (255, 255, 255, 80)


def get_font(size):
    """Get an italic serif font."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
        "/System/Library/Fonts/Georgia.ttf",
        os.path.join(ASSETS_DIR, "fonts", "font.ttf"),
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def get_audio_duration(audio_path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio_path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def parse_script_lines(script_text):
    lines = [line.strip() for line in script_text.split("\n") if line.strip()]
    return lines


def draw_centered_text(draw, text, y, font, alpha=255):
    """Draw text centered horizontally with shadow. Wraps long lines."""
    wrapped = textwrap.wrap(text, width=30)
    line_height = font.size + 16

    for i, wline in enumerate(wrapped):
        bbox = draw.textbbox((0, 0), wline, font=font)
        text_w = bbox[2] - bbox[0]
        x = (WIDTH - text_w) // 2
        wy = y + i * line_height

        # Shadow (offset + blur effect via multiple draws)
        for dx, dy in [(2, 2), (3, 3), (1, 3)]:
            draw.text((x + dx, wy + dy), wline, font=font,
                       fill=(*SHADOW_COLOR, int(alpha * 0.5)))

        # Main text
        draw.text((x, wy), wline, font=font, fill=(*TEXT_COLOR, alpha))

    return len(wrapped) * line_height


def create_frame(bg_img, current_line_text, line_alpha, watermark=True):
    """
    Render ONE line of text at a time, centered on screen.
    line_alpha: 0-255 for fade in/out effect.
    """
    frame = bg_img.copy().convert("RGBA")
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Subtle dark vignette around edges for depth
    for y in range(HEIGHT):
        # Top vignette
        if y < HEIGHT // 6:
            alpha = int(120 * (1 - y / (HEIGHT // 6)))
            draw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, alpha))
        # Bottom vignette (stronger for text area)
        if y > HEIGHT * 2 // 3:
            alpha = int(160 * ((y - HEIGHT * 2 // 3) / (HEIGHT // 3)))
            draw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, min(alpha, 160)))

    if current_line_text and line_alpha > 0:
        font = get_font(48)
        # Position text in lower-center area (like Whisprs)
        text_y = HEIGHT * 3 // 5
        draw_centered_text(draw, current_line_text, text_y, font, alpha=line_alpha)

    # Watermark at bottom
    if watermark:
        wm_font = get_font(28)
        wm_text = "@Quietlyy"
        bbox = draw.textbbox((0, 0), wm_text, font=wm_font)
        wm_w = bbox[2] - bbox[0]
        draw.text(
            ((WIDTH - wm_w) // 2, HEIGHT - 80),
            wm_text, font=wm_font, fill=WATERMARK_COLOR,
        )

    frame = Image.alpha_composite(frame, overlay)
    return frame.convert("RGB")


def apply_ken_burns(img, progress, direction=0):
    """Slow zoom/pan on an image."""
    # Scale up for zoom headroom
    scale_base = 1.1
    scale_end = 1.2
    scale = scale_base + (scale_end - scale_base) * progress

    new_w = int(WIDTH * scale)
    new_h = int(HEIGHT * scale)
    img_resized = img.resize((new_w, new_h), Image.LANCZOS)

    max_x = new_w - WIDTH
    max_y = new_h - HEIGHT

    if direction == 0:      # Slow zoom center
        x, y = max_x // 2, max_y // 2
    elif direction == 1:    # Pan right
        x, y = int(max_x * progress), max_y // 2
    elif direction == 2:    # Pan up
        x, y = max_x // 2, int(max_y * (1 - progress))
    else:                   # Pan left
        x, y = int(max_x * (1 - progress)), max_y // 2

    return img_resized.crop((x, y, x + WIDTH, y + HEIGHT))


def add_particles(draw, frame_num):
    """Subtle floating dust/snow particles."""
    random.seed(frame_num * 7 + 42)
    for _ in range(12):
        x = random.randint(0, WIDTH)
        base_y = (random.randint(0, HEIGHT) + frame_num * 1) % HEIGHT
        size = random.randint(1, 2)
        alpha = random.randint(30, 90)
        x_drift = int(math.sin(frame_num * 0.03 + x * 0.01) * 8)
        draw.ellipse(
            [x + x_drift - size, base_y - size, x + x_drift + size, base_y + size],
            fill=(255, 255, 255, alpha),
        )


def compose_video(script_data, image_paths, audio_path, subtitle_path):
    """Main compositor: ONE line at a time, fade in/out, poem style."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    frames_dir = os.path.join(OUTPUT_DIR, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    duration = get_audio_duration(audio_path)
    total_frames = int(duration * FPS)

    script_lines = parse_script_lines(script_data["script"])
    num_lines = len(script_lines)

    # Load and prepare images
    images = []
    for path in image_paths:
        img = Image.open(path).convert("RGBA")
        # Resize to cover frame with extra for Ken Burns
        img_ratio = img.width / img.height
        target_ratio = WIDTH / HEIGHT
        if img_ratio > target_ratio:
            new_h = HEIGHT + 200
            new_w = int(new_h * img_ratio)
        else:
            new_w = WIDTH + 200
            new_h = int(new_w / img_ratio)
        images.append(img.resize((new_w, new_h), Image.LANCZOS))

    # Load subtitle timing
    with open(subtitle_path, "r") as f:
        subtitles = json.load(f)

    line_timings = _calculate_line_timings(script_lines, subtitles, duration)

    # Add fade durations
    FADE_IN = 0.6   # seconds to fade in
    FADE_OUT = 0.4   # seconds to fade out
    GAP = 0.3        # gap between lines

    print(f"[video] Generating {total_frames} frames ({duration:.1f}s @ {FPS}fps)")
    print(f"[video] {num_lines} lines, showing ONE at a time")

    for frame_num in range(total_frames):
        current_time = frame_num / FPS
        progress = frame_num / max(total_frames - 1, 1)

        # Pick background image
        img_idx = min(int(progress * len(images)), len(images) - 1)
        img = images[img_idx]

        # Ken Burns progress for this image
        img_start = img_idx / len(images)
        img_end = (img_idx + 1) / len(images)
        local_progress = max(0, min(1, (progress - img_start) / max(img_end - img_start, 0.01)))

        bg = apply_ken_burns(img, local_progress, direction=img_idx % 4)

        # Determine which line to show and its alpha
        current_line_text = ""
        line_alpha = 0

        for i, (start, end) in enumerate(line_timings):
            line_start = start - 0.1  # Slight anticipation
            line_end = end + GAP

            if line_start <= current_time <= line_end:
                current_line_text = script_lines[i]

                # Fade in
                if current_time < line_start + FADE_IN:
                    fade_progress = (current_time - line_start) / FADE_IN
                    line_alpha = int(255 * min(1, max(0, fade_progress)))
                # Fade out
                elif current_time > line_end - FADE_OUT:
                    fade_progress = (line_end - current_time) / FADE_OUT
                    line_alpha = int(255 * min(1, max(0, fade_progress)))
                # Fully visible
                else:
                    line_alpha = 255
                break

        # Render frame
        frame = create_frame(bg, current_line_text, line_alpha)

        # Add particles
        particle_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        p_draw = ImageDraw.Draw(particle_overlay)
        add_particles(p_draw, frame_num)
        frame = Image.alpha_composite(frame.convert("RGBA"), particle_overlay).convert("RGB")

        # Save
        frame_path = os.path.join(frames_dir, f"frame_{frame_num:05d}.png")
        frame.save(frame_path, "PNG")

        if frame_num % (FPS * 5) == 0:
            print(f"[video] Frame {frame_num}/{total_frames} ({progress*100:.0f}%)")

    # Assemble final video
    output_path = os.path.join(OUTPUT_DIR, "quietlyy_video.mp4")
    _assemble_video(frames_dir, audio_path, output_path, duration)

    import shutil
    shutil.rmtree(frames_dir, ignore_errors=True)

    print(f"[video] Done: {output_path}")
    return output_path


def _calculate_line_timings(script_lines, subtitles, total_duration):
    """Map subtitle word timings to script lines."""
    if not subtitles:
        gap = total_duration / len(script_lines)
        return [(i * gap, (i + 0.8) * gap) for i in range(len(script_lines))]

    sub_words = [s["text"].lower().strip(".,…!?\"'") for s in subtitles]
    line_timings = []
    sub_idx = 0

    for line in script_lines:
        line_words = [w.lower().strip(".,…!?\"'") for w in line.split() if w.strip(".,…!?\"'")]
        if not line_words:
            continue

        start_time = None
        end_time = None

        for si in range(sub_idx, len(subtitles)):
            word = sub_words[si] if si < len(sub_words) else ""
            if word == line_words[0] or (len(line_words[0]) > 3 and line_words[0] in word):
                start_time = subtitles[si]["offset_ms"] / 1000.0
                sub_idx = si
                break

        for si in range(sub_idx, min(sub_idx + len(line_words) + 5, len(subtitles))):
            end_time = (subtitles[si]["offset_ms"] + subtitles[si]["duration_ms"]) / 1000.0

        if start_time is None:
            last_end = line_timings[-1][1] if line_timings else 0
            start_time = last_end + 0.5
            end_time = start_time + (total_duration / len(script_lines)) * 0.8

        sub_idx = min(sub_idx + len(line_words), len(subtitles) - 1)
        line_timings.append((start_time, end_time))

    return line_timings


def _pick_background_music():
    """Pick background music — prefer instrumental.mp3 (reference track)."""
    music_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "music")
    if not os.path.exists(music_dir):
        return None
    # Prefer the reference instrumental
    preferred = os.path.join(music_dir, "instrumental.mp3")
    if os.path.exists(preferred):
        return preferred
    tracks = [f for f in os.listdir(music_dir) if f.endswith((".mp3", ".wav"))]
    if not tracks:
        return None
    return os.path.join(music_dir, tracks[0])


def _assemble_video(frames_dir, audio_path, output_path, duration):
    """
    Combine frames + voiceover + background music.
    Music style (from reference analysis):
      - Starts low
      - Builds slightly in middle
      - Supports emotion without overpowering
      - Voice is clear and dominant
    """
    music_path = _pick_background_music()

    if music_path:
        print(f"[video] Mixing: voice + {os.path.basename(music_path)}")
        # Music at 20% volume — present but never overpowering voice
        # Fade in 3s, fade out last 3s
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", os.path.join(frames_dir, "frame_%05d.png"),
            "-i", audio_path,
            "-stream_loop", "-1", "-i", music_path,
            "-filter_complex",
            f"[1:a]loudnorm=I=-16:TP=-1.5[voice];"
            f"[2:a]volume=0.20,afade=t=in:d=3,afade=t=out:st={max(0,duration-3)}:d=3[music];"
            f"[voice][music]amix=inputs=2:duration=shortest:normalize=0[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", os.path.join(frames_dir, "frame_%05d.png"),
            "-i", audio_path,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart",
            output_path,
        ]

    subprocess.run(cmd, check=True, capture_output=True)


if __name__ == "__main__":
    print("Video compositor ready. Run via pipeline.py")
