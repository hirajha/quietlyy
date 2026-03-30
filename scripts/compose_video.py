"""
Quietlyy — Video Compositor (ffmpeg-native)
Uses ffmpeg filters for Ken Burns, text overlay, and audio mixing.
~1 minute instead of 16 minutes.

Text overlays rendered with PIL (5 images, <1 second),
everything else done with ffmpeg filter_complex.
"""

import json
import os
import subprocess
import textwrap
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

WIDTH = 1080
HEIGHT = 1920
FPS = 30

TEXT_COLOR = (255, 255, 255)
SHADOW_COLOR = (0, 0, 0)
WATERMARK_COLOR = (255, 255, 255, 80)


def get_font(size):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
        "/System/Library/Fonts/Georgia.ttf",
        os.path.join(ASSETS_DIR, "fonts", "font.ttf"),
    ]:
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
    return [line.strip() for line in script_text.split("\n") if line.strip()]


def _render_text_image(text, output_path):
    """Render one line of text on a transparent 1080x1920 canvas."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_font(56)

    wrapped = textwrap.wrap(text, width=26)
    line_height = font.size + 20
    text_y = HEIGHT * 3 // 5
    total_h = len(wrapped) * line_height

    # Semi-transparent dark backdrop for readability
    pad_x, pad_y = 60, 30
    draw.rounded_rectangle(
        [(pad_x, text_y - pad_y), (WIDTH - pad_x, text_y + total_h + pad_y)],
        radius=20,
        fill=(0, 0, 0, 90),
    )

    for i, wline in enumerate(wrapped):
        bbox = draw.textbbox((0, 0), wline, font=font)
        text_w = bbox[2] - bbox[0]
        x = (WIDTH - text_w) // 2
        wy = text_y + i * line_height

        # Strong shadow/glow for visibility
        for dx, dy in [(0, 4), (4, 0), (0, -2), (-2, 0),
                       (3, 3), (-3, 3), (3, -3), (-3, -3),
                       (0, 2), (2, 0), (0, -1), (-1, 0)]:
            draw.text((x + dx, wy + dy), wline, font=font,
                      fill=(*SHADOW_COLOR, 102))

        draw.text((x, wy), wline, font=font, fill=(*TEXT_COLOR, 255))

    img.save(output_path, "PNG")


def _render_watermark(output_path):
    """Render @Quietlyy watermark on transparent canvas."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_font(28)
    text = "@Quietlyy"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text(((WIDTH - text_w) // 2, HEIGHT - 80), text, font=font, fill=WATERMARK_COLOR)
    img.save(output_path, "PNG")


def _calculate_line_timings(script_lines, subtitles, total_duration):
    if not subtitles:
        gap = total_duration / len(script_lines)
        return [(i * gap, (i + 0.8) * gap) for i in range(len(script_lines))]

    sub_words = [s["text"].lower().strip(".,\u2026!?\"'") for s in subtitles]
    line_timings = []
    sub_idx = 0

    for line in script_lines:
        line_words = [w.lower().strip(".,\u2026!?\"'") for w in line.split()
                      if w.strip(".,\u2026!?\"'")]
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


def compose_video(script_data, image_paths, audio_path, subtitle_path, music_path=None):
    """Compose video using ffmpeg filters. ~1 min instead of 16 min.

    Approach:
    1. Render 5 text overlay PNGs with PIL (<1 second)
    2. Use ffmpeg for everything: Ken Burns, concat, overlay, audio mix
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    duration = get_audio_duration(audio_path)
    lines = parse_script_lines(script_data["script"])
    num_panels = len(image_paths)
    seg_dur = duration / num_panels

    with open(subtitle_path) as f:
        subtitles = json.load(f)
    line_timings = _calculate_line_timings(lines, subtitles, duration)

    # Step 1: Render text overlays with PIL (~0.5s total)
    print(f"[video] Rendering {len(lines)} text overlays...")
    text_paths = []
    for i, line in enumerate(lines):
        path = os.path.join(OUTPUT_DIR, f"_text_{i}.png")
        _render_text_image(line, path)
        text_paths.append(path)

    wm_path = os.path.join(OUTPUT_DIR, "_watermark.png")
    _render_watermark(wm_path)

    # Step 2: Build ffmpeg inputs
    # Layout: [0..P-1] panels, [P..P+L-1] text overlays, [P+L] watermark, [P+L+1] voice, [P+L+2] music
    inputs = []
    for p in image_paths:
        inputs += ["-loop", "1", "-t", f"{seg_dur:.3f}", "-i", p]
    for tp in text_paths:
        inputs += ["-loop", "1", "-t", f"{duration:.3f}", "-i", tp]
    inputs += ["-loop", "1", "-t", f"{duration:.3f}", "-i", wm_path]

    voice_idx = num_panels + len(lines) + 1
    inputs += ["-i", audio_path]

    music_idx = None
    if music_path:
        music_idx = voice_idx + 1
        inputs += ["-stream_loop", "-1", "-i", music_path]

    # Step 3: Build filter_complex
    filters = []

    # Ken Burns on each panel (scale up, crop, slow zoom)
    for i in range(num_panels):
        frames = int(seg_dur * FPS)
        filters.append(
            f"[{i}:v]scale=1400:2400:force_original_aspect_ratio=increase,"
            f"crop=1400:2400,"
            f"zoompan=z='min(zoom+0.0008,1.12)'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
            f"format=yuv420p[v{i}]"
        )

    # Concat all panels
    concat_in = "".join(f"[v{i}]" for i in range(num_panels))
    filters.append(f"{concat_in}concat=n={num_panels}:v=1:a=0[vcat]")

    # Vignette for cinematic look
    filters.append("[vcat]vignette=angle=PI/6[vvig]")

    # Overlay text lines with fade in/out
    FADE_IN = 0.6
    FADE_OUT = 0.4
    GAP = 0.3
    current = "vvig"

    for i, (start, end) in enumerate(line_timings):
        s = max(0, start - 0.1)
        e = end + GAP
        ti = num_panels + i

        # Fade the text overlay alpha
        filters.append(
            f"[{ti}:v]fade=t=in:st={s:.2f}:d={FADE_IN}:alpha=1,"
            f"fade=t=out:st={e - FADE_OUT:.2f}:d={FADE_OUT}:alpha=1[tf{i}]"
        )

        nxt = f"vo{i}"
        filters.append(
            f"[{current}][tf{i}]overlay=format=auto:"
            f"enable='between(t,{s:.2f},{e:.2f})'[{nxt}]"
        )
        current = nxt

    # Overlay watermark (always visible)
    wm_input = num_panels + len(lines)
    filters.append(f"[{current}][{wm_input}:v]overlay=format=auto[vout]")

    # Audio mixing
    if music_idx is not None:
        filters.append(f"[{voice_idx}:a]loudnorm=I=-16:TP=-1.5[voice]")
        filters.append(
            f"[{music_idx}:a]volume=0.20,"
            f"afade=t=in:d=3,afade=t=out:st={max(0, duration - 3):.2f}:d=3[music]"
        )
        filters.append("[voice][music]amix=inputs=2:duration=shortest:normalize=0[aout]")
    else:
        filters.append(f"[{voice_idx}:a]loudnorm=I=-16:TP=-1.5[aout]")

    # Write filter to script file (avoids command-line length limits)
    filter_str = ";\n".join(filters)
    filter_path = os.path.join(OUTPUT_DIR, "_filter.txt")
    with open(filter_path, "w") as f:
        f.write(filter_str)

    output_path = os.path.join(OUTPUT_DIR, "quietlyy_video.mp4")

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex_script", filter_path,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        output_path,
    ]

    print(f"[video] Compositing {num_panels} panels, {len(lines)} lines, {duration:.1f}s...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[video] ffmpeg error:\n{result.stderr[-1000:]}")
        raise RuntimeError("Video composition failed")

    # Cleanup temp files
    os.remove(filter_path)
    for p in text_paths:
        os.remove(p)
    os.remove(wm_path)

    print(f"[video] Done: {output_path}")
    return output_path


if __name__ == "__main__":
    print("Video compositor ready. Run via pipeline.py")
