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


def _draw_text_on_image(img, text):
    """
    Text with a tight acrylic pill scrim sized to the text — not full-width.
    Like a caption bubble that hugs the words.
    """
    import colorsys
    draw_img = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", draw_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = get_font(62)
    wrapped = textwrap.wrap(text, width=22)
    line_height = font.size + 22
    total_h = len(wrapped) * line_height

    # Vertically centered, biased slightly above center
    text_y = (HEIGHT - total_h) // 2 - 40

    # Measure the widest line to size the scrim tightly
    max_text_w = 0
    for wline in wrapped:
        bb = draw.textbbox((0, 0), wline, font=font)
        max_text_w = max(max_text_w, bb[2] - bb[0])

    # Tight scrim — acrylic blurred pill fitted to text
    SCRIM_PAD_X, SCRIM_PAD_Y, SCRIM_R = 44, 22, 20
    sx0 = (WIDTH - max_text_w) // 2 - SCRIM_PAD_X
    sy0 = text_y - SCRIM_PAD_Y
    sx1 = (WIDTH + max_text_w) // 2 + SCRIM_PAD_X
    sy1 = text_y + total_h + SCRIM_PAD_Y

    # Blur the region behind the scrim (acrylic frost)
    region = draw_img.convert("RGB").crop((sx0, sy0, sx1, sy1))
    from PIL import ImageFilter
    blurred = region.filter(ImageFilter.GaussianBlur(radius=12))
    # Sample avg color for Win11-style acrylic tint
    avg = blurred.resize((1, 1)).getpixel((0, 0))[:3]
    h, s, v = colorsys.rgb_to_hsv(avg[0]/255, avg[1]/255, avg[2]/255)
    v = min(1.0, v + 0.08)   # subtle brightening (text scrim, not pill)
    s = max(0.0, s - 0.10)
    tr, tg, tb = colorsys.hsv_to_rgb(h, s, v)
    tint = (int(tr*255), int(tg*255), int(tb*255))
    rgb = draw_img.convert("RGB")
    rgb.paste(blurred, (sx0, sy0))
    draw_img = rgb.convert("RGBA")
    overlay = Image.new("RGBA", draw_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Tinted dark glass pill behind text
    draw.rounded_rectangle([sx0, sy0, sx1, sy1], radius=SCRIM_R,
                            fill=(*tint, 140))
    draw.rounded_rectangle([sx0, sy0, sx1, sy1], radius=SCRIM_R,
                            outline=(255, 255, 255, 40), width=1)

    # Bake the text lines on top
    for i, wline in enumerate(wrapped):
        bb = draw.textbbox((0, 0), wline, font=font)
        text_w = bb[2] - bb[0]
        x = (WIDTH - text_w) // 2
        wy = text_y + i * line_height
        draw.text((x + 3, wy + 3), wline, font=font, fill=(0, 0, 0, 180))
        draw.text((x + 1, wy + 1), wline, font=font, fill=(0, 0, 0, 100))
        draw.text((x, wy), wline, font=font, fill=(255, 248, 220, 255))

    result = Image.alpha_composite(draw_img, overlay)
    return result.convert("RGB")


def _draw_cta_overlay(img):
    """Draw a subtle Follow + Save CTA at the bottom of the last panel."""
    draw_img = img.copy().convert("RGBA") if img.mode != "RGBA" else img.copy()
    overlay = Image.new("RGBA", draw_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Semi-transparent dark bar at bottom
    bar_h = 130
    bar = Image.new("RGBA", (WIDTH, bar_h), (0, 0, 0, 140))
    overlay.paste(bar, (0, HEIGHT - bar_h), bar)

    cta_font = get_font(36)
    sub_font = get_font(26)

    # Main CTA line
    cta = "💾 Save this  •  Follow @Quietlyy"
    bbox = draw.textbbox((0, 0), cta, font=cta_font)
    cta_w = bbox[2] - bbox[0]
    draw.text(((WIDTH - cta_w) // 2, HEIGHT - bar_h + 18), cta,
              font=cta_font, fill=(255, 245, 210, 230))

    # Sub line — no "Subscribe" duplicate (button already gone on last panel)
    sub = "New video every day  •  @Quietlyy"
    bbox2 = draw.textbbox((0, 0), sub, font=sub_font)
    sub_w = bbox2[2] - bbox2[0]
    draw.text(((WIDTH - sub_w) // 2, HEIGHT - bar_h + 68), sub,
              font=sub_font, fill=(255, 245, 210, 160))

    result = Image.alpha_composite(draw_img, overlay)
    return result.convert("RGB")


def _draw_follow_button(img):
    """
    Windows 11 Acrylic-style frosted-glass pill — bottom-right, panels 1+ only.
    - Blurs the region behind the pill (Gaussian radius 14)
    - Samples the average color of that region → tints the overlay with it
      (like Win11 Acrylic: glass picks up the color behind it, not flat white)
    - Thin bright border for edge definition
    - Tight margin — pill sits close to the bottom edge
    """
    from PIL import ImageFilter
    import colorsys

    draw_img = img.copy().convert("RGBA") if img.mode != "RGBA" else img.copy()

    btn_font = get_font(32)           # bigger font → bigger pill
    label = "Follow @Quietlyy"
    tmp = ImageDraw.Draw(draw_img)
    bbox = tmp.textbbox((0, 0), label, font=btn_font)
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]

    PAD_X, PAD_Y, MARGIN, RADIUS = 28, 16, 20, 22  # more padding → bigger pill
    x0 = WIDTH - bw - PAD_X * 2 - MARGIN
    y0 = HEIGHT - bh - PAD_Y * 2 - MARGIN
    x1 = WIDTH - MARGIN
    y1 = HEIGHT - MARGIN

    # Step 1 — Gaussian blur on background region
    region = draw_img.convert("RGB").crop((x0, y0, x1, y1))
    blurred = region.filter(ImageFilter.GaussianBlur(radius=14))

    # Step 2 — sample average color of the blurred region for tint
    blurred_small = blurred.resize((1, 1))
    avg_r, avg_g, avg_b = blurred_small.getpixel((0, 0))[:3]
    # Lighten the sampled color slightly for the overlay (Win11 Acrylic brightening)
    h, s, v = colorsys.rgb_to_hsv(avg_r / 255, avg_g / 255, avg_b / 255)
    v = min(1.0, v + 0.30)  # brighten
    s = max(0.0, s - 0.15)  # slightly desaturate for glass feel
    tr, tg, tb = colorsys.hsv_to_rgb(h, s, v)
    tint = (int(tr * 255), int(tg * 255), int(tb * 255))

    # Step 3 — paste blurred region back
    rgb = draw_img.convert("RGB")
    rgb.paste(blurred, (x0, y0))
    draw_img = rgb.convert("RGBA")

    # Step 4 — tinted glass overlay + border
    overlay = Image.new("RGBA", draw_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=RADIUS,
                            fill=(*tint, 90))          # color-matched tint
    draw.rounded_rectangle([x0, y0, x1, y1], radius=RADIUS,
                            outline=(255, 255, 255, 160), width=2)  # bright border

    # Step 5 — white text
    draw.text((x0 + PAD_X, y0 + PAD_Y - bbox[1]), label,
              font=btn_font, fill=(255, 255, 255, 245))

    result = Image.alpha_composite(draw_img, overlay)
    return result.convert("RGB")


def compose_video(script_data, image_paths, audio_path, subtitle_path, music_path):
    """Simple compositor: bake text onto panels, concat with ffmpeg."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    duration = get_audio_duration(audio_path)
    lines = [l.strip() for l in script_data["script"].split("\n") if l.strip()]
    num_panels = len(image_paths)
    num_lines = len(lines)

    # Use actual per-line audio durations so each panel matches its narration
    TAIL_PAD = 5.0
    AUDIO_GAP = 1.4  # must match LINE_GAP in generate_audio.py
    # Visual GAP == AUDIO_GAP: eliminates cumulative drift (each panel holds
    # for exactly line_speech + full silence, then advances with the narrator)
    GAP = AUDIO_GAP

    line_durations = []
    for i in range(num_lines):
        line_path = os.path.join(OUTPUT_DIR, f"_line_{i}.mp3")
        if os.path.exists(line_path):
            line_durations.append(get_audio_duration(line_path))

    if len(line_durations) == num_lines:
        # Each segment = line audio + full gap → perfectly in sync, no drift
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
        if i == num_lines - 1:
            # Last panel: CTA bar replaces the button (no duplicate)
            frame = _draw_cta_overlay(frame)
        elif i > 0:
            # Panels 1+: frosted-glass Follow pill (bottom-right)
            # Panel 0 is the thumbnail shown on all platforms — keep it clean
            frame = _draw_follow_button(frame)
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
    XFADE = 0.6   # slower fade between images — less jarring, more cinematic
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
            f"[2:a]volume=0.10,afade=t=in:d=2,afade=t=out:st={max(0, duration - 3):.2f}:d=3[music];"
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
