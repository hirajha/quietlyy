"""
Quietlyy — Video Compositor (Simple & Clean)
Bakes text directly onto panel images with PIL.
Uses ffmpeg only for concat + audio mix. No complex filter_complex.
Text style: clean italic, subtle shadow — like Whisprs.
"""

import json
import os
import subprocess
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

WIDTH = 1080
HEIGHT = 1920
FPS = 30


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


def get_audio_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def _draw_text_on_image(img, text, watermark=True):
    """Draw clean Whisprs-style text on image. Subtle shadow, no heavy backdrop."""
    draw_img = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", draw_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = get_font(52)
    wrapped = textwrap.wrap(text, width=28)
    line_height = font.size + 18
    total_h = len(wrapped) * line_height

    # Text position — center of screen vertically, like Whisprs
    text_y = (HEIGHT - total_h) // 2

    for i, wline in enumerate(wrapped):
        bbox = draw.textbbox((0, 0), wline, font=font)
        text_w = bbox[2] - bbox[0]
        x = (WIDTH - text_w) // 2
        wy = text_y + i * line_height

        # Subtle shadow — just 2 layers, not heavy
        draw.text((x + 2, wy + 2), wline, font=font, fill=(0, 0, 0, 160))
        draw.text((x + 1, wy + 1), wline, font=font, fill=(0, 0, 0, 120))
        # Main text — bright white
        draw.text((x, wy), wline, font=font, fill=(255, 255, 255, 255))

    # Watermark
    if watermark:
        wm_font = get_font(26)
        wm = "@Quietlyy"
        bbox = draw.textbbox((0, 0), wm, font=wm_font)
        wm_w = bbox[2] - bbox[0]
        draw.text(((WIDTH - wm_w) // 2, HEIGHT - 80), wm, font=wm_font,
                  fill=(255, 255, 255, 80))

    result = Image.alpha_composite(draw_img, overlay)
    return result.convert("RGB")


def compose_video(script_data, image_paths, audio_path, subtitle_path, music_path=None):
    """Simple compositor: bake text onto panels, concat with ffmpeg."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    duration = get_audio_duration(audio_path)
    lines = [l.strip() for l in script_data["script"].split("\n") if l.strip()]
    num_panels = len(image_paths)
    num_lines = len(lines)

    # Use actual per-line audio durations so each panel matches its narration
    TAIL_PAD = 5.0
    GAP = 1.5  # silence gap between lines in audio

    line_durations = []
    for i in range(num_lines):
        line_path = os.path.join(OUTPUT_DIR, f"_line_{i}.mp3")
        if os.path.exists(line_path):
            line_durations.append(get_audio_duration(line_path))

    if len(line_durations) == num_lines:
        # Each segment = line audio + gap (except last = line + tail pad)
        seg_durations = [d + GAP for d in line_durations]
        seg_durations[-1] = line_durations[-1] + TAIL_PAD
        print(f"[video] Using per-line durations: {[f'{d:.1f}s' for d in seg_durations]}")
    else:
        # Fallback: split evenly
        per_seg = duration / num_lines
        seg_durations = [per_seg] * num_lines
        seg_durations[-1] = per_seg + TAIL_PAD

    total_video = sum(seg_durations)
    print(f"[video] Audio: {duration:.1f}s, Video: {total_video:.1f}s (last segment +{TAIL_PAD}s pad)")

    print(f"[video] Baking text onto {num_panels} panels...")

    # Step 1: For each line, bake text onto its panel image
    panel_videos = []
    for i in range(num_lines):
        panel_idx = min(i, num_panels - 1)
        img = Image.open(image_paths[panel_idx]).convert("RGBA")

        # Start with black canvas — guarantees exact 1080x1920, no colored bars
        canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))

        # Scale image to COVER the frame (crop excess, never leave gaps)
        img_ratio = img.width / img.height
        target_ratio = WIDTH / HEIGHT
        if img_ratio > target_ratio:
            # Image is wider — scale to match height, crop sides
            new_h = HEIGHT
            new_w = int(new_h * img_ratio)
        else:
            # Image is taller — scale to match width, crop top/bottom
            new_w = WIDTH
            new_h = int(new_w / img_ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        # Center crop to exact 1080x1920
        left = (new_w - WIDTH) // 2
        top = (new_h - HEIGHT) // 2
        img = img.crop((left, top, left + WIDTH, top + HEIGHT))

        # Paste onto black canvas (safety — covers any rounding pixel gaps)
        canvas.paste(img, (0, 0))
        img = canvas

        # Darken image slightly for text readability
        dark = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 60))
        img = Image.alpha_composite(img, dark)

        # Bake text
        frame = _draw_text_on_image(img, lines[i])
        frame_path = os.path.join(OUTPUT_DIR, f"_panel_{i}.png")
        frame.save(frame_path, "PNG")

        # Create a short video clip from this static image
        clip_path = os.path.join(OUTPUT_DIR, f"_clip_{i}.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", frame_path,
            "-t", f"{seg_durations[i]:.3f}",
            "-vf", f"fps={FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            clip_path,
        ], capture_output=True, check=True)

        panel_videos.append(clip_path)
        print(f"[video]   Panel {i+1}/{num_lines}: {seg_durations[i]:.1f}s")

    # Step 2: Concat all clips with crossfade
    XFADE = 0.6
    output_no_audio = os.path.join(OUTPUT_DIR, "_video_noaudio.mp4")

    if len(panel_videos) == 1:
        # Just copy
        import shutil
        shutil.copy2(panel_videos[0], output_no_audio)
    else:
        # Build xfade chain
        filters = []
        offsets = []
        cumulative = 0
        for i in range(len(panel_videos) - 1):
            offset = cumulative + seg_durations[i] - XFADE
            offsets.append(offset)
            cumulative += seg_durations[i] - XFADE

        inputs = []
        for v in panel_videos:
            inputs += ["-i", v]

        # Chain xfade filters
        if len(panel_videos) == 2:
            filters.append(
                f"[0:v][1:v]xfade=transition=fade:duration={XFADE}:offset={offsets[0]:.3f}[vout]"
            )
        else:
            # First xfade
            filters.append(
                f"[0:v][1:v]xfade=transition=fade:duration={XFADE}:offset={offsets[0]:.3f}[xf0]"
            )
            # Middle xfades
            for i in range(1, len(panel_videos) - 2):
                filters.append(
                    f"[xf{i-1}][{i+1}:v]xfade=transition=fade:duration={XFADE}:offset={offsets[i]:.3f}[xf{i}]"
                )
            # Last xfade
            last = len(panel_videos) - 2
            filters.append(
                f"[xf{last-1}][{last+1}:v]xfade=transition=fade:duration={XFADE}:offset={offsets[last]:.3f}[vout]"
            )

        filter_str = ";".join(filters)
        subprocess.run(
            ["ffmpeg", "-y"] + inputs + [
                "-filter_complex", filter_str,
                "-map", "[vout]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-pix_fmt", "yuv420p",
                output_no_audio,
            ], capture_output=True, check=True,
        )

    # Step 3: Mix audio (voice + music)
    output_path = os.path.join(OUTPUT_DIR, "quietlyy_video.mp4")

    if music_path:
        print(f"[video] Mixing voice + {os.path.basename(music_path)}")
        # NOTE: No loudnorm (adds latency that cuts off last line).
        # NOTE: No -shortest (video is already padded to be longer than audio).
        # amix duration=first = use voice duration (first input after filter).
        subprocess.run([
            "ffmpeg", "-y",
            "-i", output_no_audio,
            "-i", audio_path,
            "-stream_loop", "-1", "-i", music_path,
            "-filter_complex",
            f"[1:a]aresample=async=1[voice];"
            f"[2:a]volume=0.18,afade=t=in:d=2,afade=t=out:st={max(0, duration - 3):.2f}:d=3[music];"
            f"[voice][music]amix=inputs=2:duration=first:normalize=0[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ], capture_output=True, check=True)
    else:
        # No music — just mux video + voice. No -shortest.
        subprocess.run([
            "ffmpeg", "-y",
            "-i", output_no_audio,
            "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ], capture_output=True, check=True)

    # Cleanup temp files
    for f in panel_videos:
        os.remove(f)
    for f in os.listdir(OUTPUT_DIR):
        if f.startswith("_"):
            os.remove(os.path.join(OUTPUT_DIR, f))

    print(f"[video] Done: {output_path}")
    return output_path


if __name__ == "__main__":
    print("Video compositor ready. Run via pipeline.py")
