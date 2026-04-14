"""
Quietlyy — Video Compositor
Clean background panels + word-by-word ASS subtitle animation.
Words appear as the narrator speaks, via ffmpeg subtitles filter.
No text baked onto panels — keeps images clean and bright.
"""

import colorsys
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


def _generate_ass_subtitles(subtitles, lines, output_path):
    """
    Generate an ASS subtitle file with word-by-word fade-in reveal.

    The FULL LINE text is present in every dialogue event so layout never shifts.
    - Past words (already spoken): no tag — fully visible.
    - Current word: \\alpha&HFF& (all layers transparent) → fades to \\alpha&H00& (opaque)
      over FADE_MS ms. Using \\alpha kills fill + outline + shadow simultaneously,
      so there is no ghost outline visible before the word reveals.
    - Future words: \\alpha&HFF& — completely invisible including all outline/shadow layers.
    """
    FADE_MS = 200  # ms for each word to fade from invisible to fully visible

    def ms_to_ass(ms):
        ms = max(0, int(ms))
        h = ms // 3600000
        m = (ms % 3600000) // 60000
        s = (ms % 60000) // 1000
        cs = (ms % 1000) // 10
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    # Find available font for ASS style name
    font_name = "DejaVu Serif"
    for path, name in [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf", "DejaVu Serif"),
        ("/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf", "Liberation Serif"),
    ]:
        if os.path.exists(path):
            font_name = name
            break

    # Group subtitle words into their original script lines (words are in order)
    line_word_groups = []
    sub_idx = 0
    for line in lines:
        words = line.split()
        group = []
        for _ in words:
            if sub_idx < len(subtitles):
                group.append(subtitles[sub_idx])
                sub_idx += 1
        if group:
            line_word_groups.append(group)

    events = []
    for g_i, group in enumerate(line_word_groups):
        if not group:
            continue

        words = [g["text"] for g in group]

        # Compute the stable wrap layout once per line (full text, no tags)
        full_text = " ".join(words)
        wrapped = textwrap.wrap(full_text, width=22) or [full_text]

        # Line ends: 50ms before next line starts, or 800ms linger after last word
        if g_i + 1 < len(line_word_groups) and line_word_groups[g_i + 1]:
            line_end_ms = line_word_groups[g_i + 1][0]["offset_ms"] - 50
        else:
            line_end_ms = group[-1]["offset_ms"] + group[-1]["duration_ms"] + 800

        for w_i in range(len(group)):
            word_start_ms = group[w_i]["offset_ms"]
            if w_i + 1 < len(group):
                event_end_ms = group[w_i + 1]["offset_ms"]
            else:
                event_end_ms = line_end_ms

            if event_end_ms <= word_start_ms:
                event_end_ms = word_start_ms + 100

            # Build display_text: full line with per-word alpha override tags.
            # Walk through wrapped word groups to preserve line breaks (\N).
            tagged_lines = []
            global_wi = 0
            for wl in wrapped:
                wl_words = wl.split()
                line_parts = []
                for k, w in enumerate(wl_words):
                    if global_wi < w_i:
                        # Already spoken — no tag, fully visible
                        line_parts.append(w)
                    elif global_wi == w_i:
                        # Currently being spoken — fade from fully transparent to opaque
                        line_parts.append(
                            f"{{\\alpha&HFF&\\t(0,{FADE_MS},\\alpha&H00&)}}{w}"
                        )
                    else:
                        # Not yet spoken — fully transparent (kills outline+shadow too)
                        line_parts.append(f"{{\\alpha&HFF&}}{w}")
                    if k < len(wl_words) - 1:
                        line_parts.append(" ")
                    global_wi += 1
                tagged_lines.append("".join(line_parts))
            display_text = r"\N".join(tagged_lines)

            # \an8\pos(540,680): top-center anchor at fixed position — never moves
            events.append(
                f"Dialogue: 0,{ms_to_ass(word_start_ms)},{ms_to_ass(event_end_ms)},"
                f"Default,,0,0,0,,{{\\an8\\pos(540,680)}}{display_text}"
            )

    # ASS file — warm cream text, 4px black outline, 2px shadow, italic serif
    # Colours in ASS ABGR hex: &HAABBGGRR
    ass = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, Strikeout, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},68,"
        "&H00DCF8FF,"   # Primary: warm cream (ABGR of #FFF8DC)
        "&H00FFFFFF,"   # Secondary: white
        "&H00000000,"   # Outline: black
        "&H80000000,"   # Back: semi-transparent black
        "0,1,0,0,"      # Bold=no, Italic=yes
        "100,100,2,0,"  # ScaleX/Y, Spacing, Angle
        "1,4,2,"        # BorderStyle=1, Outline=4px, Shadow=2px
        "8,"            # Alignment=8 (top center, overridden per-event by \an8\pos)
        "60,60,200,1\n" # MarginL/R/V, Encoding
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        + "\n".join(events)
        + "\n"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass)

    print(f"[video] ASS subtitles written: {output_path} ({len(events)} events)")
    return output_path


def _draw_cta_overlay(img, cta_line=None):
    """
    Draw the script CTA as a prominent highlighted card on the last panel.
    cta_line: the CTA text from the script (e.g. "Send this to someone who needs it.")
    Below the card, show the brand Follow line.
    """
    import textwrap as _textwrap
    draw_img = img.copy().convert("RGBA") if img.mode != "RGBA" else img.copy()
    overlay = Image.new("RGBA", draw_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # ── CTA card — amber/gold highlighted pill ──────────────────────────────
    if cta_line:
        # Strip emoji from CTA for cleaner baked text rendering
        import re
        clean_cta = re.sub(r'[^\x00-\x7F❤️💾📩🤍]', '', cta_line).strip()
        if not clean_cta:
            clean_cta = cta_line

        cta_font = get_font(40)
        # Wrap to fit within card width
        wrapped = _textwrap.wrap(clean_cta, width=26) or [clean_cta]

        line_h = 52
        PAD_X, PAD_Y = 48, 28
        card_w = WIDTH - 120
        card_h = len(wrapped) * line_h + PAD_Y * 2
        card_x = 60
        # Position: lower-center of panel, above follow button
        card_y = HEIGHT - card_h - 320

        # Draw card: deep warm amber with semi-transparent black shadow
        shadow = Image.new("RGBA", (card_w + 8, card_h + 8), (0, 0, 0, 80))
        overlay.paste(shadow, (card_x + 4, card_y + 4), shadow)

        card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card)
        # Warm amber gradient effect: solid amber background
        card_draw.rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=20,
                                    fill=(220, 150, 30, 235))
        # Subtle inner highlight at top
        card_draw.rounded_rectangle([0, 0, card_w - 1, card_h // 2], radius=20,
                                    fill=(240, 175, 50, 40))
        overlay.paste(card, (card_x, card_y), card)

        # Draw wrapped CTA text (white, bold appearance via outline)
        for li, wline in enumerate(wrapped):
            bbox = draw.textbbox((0, 0), wline, font=cta_font)
            tw = bbox[2] - bbox[0]
            tx = card_x + (card_w - tw) // 2
            ty = card_y + PAD_Y + li * line_h - bbox[1]
            # Soft shadow
            draw.text((tx + 2, ty + 2), wline, font=cta_font, fill=(0, 0, 0, 100))
            # Main white text
            draw.text((tx, ty), wline, font=cta_font, fill=(255, 255, 255, 255))

    # ── Brand follow line at very bottom ────────────────────────────────────
    follow_font = get_font(28)
    brand_text = "Follow @Quietlyy for more"
    bbox = draw.textbbox((0, 0), brand_text, font=follow_font)
    bw = bbox[2] - bbox[0]
    by = HEIGHT - 180
    # Soft dark pill behind brand text
    pill = Image.new("RGBA", (bw + 40, 44), (0, 0, 0, 140))
    overlay.paste(pill, ((WIDTH - bw - 40) // 2, by - 8), pill)
    draw.text(((WIDTH - bw) // 2, by - bbox[1]), brand_text,
              font=follow_font, fill=(255, 245, 210, 210))

    result = Image.alpha_composite(draw_img, overlay)
    return result.convert("RGB")


def _draw_follow_button(img):
    """
    Windows 11 Acrylic-style frosted-glass pill — CENTER-BOTTOM, panels 1+ only.
    """
    import colorsys

    draw_img = img.copy().convert("RGBA") if img.mode != "RGBA" else img.copy()

    btn_font = get_font(32)
    label = "Follow @Quietlyy"
    tmp = ImageDraw.Draw(draw_img)
    bbox = tmp.textbbox((0, 0), label, font=btn_font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    PAD_X, PAD_Y, BOTTOM_MARGIN, RADIUS = 28, 16, 160, 22
    btn_w = text_w + PAD_X * 2
    btn_h = text_h + PAD_Y * 2
    x0 = (WIDTH - btn_w) // 2
    y0 = HEIGHT - btn_h - BOTTOM_MARGIN
    x1 = x0 + btn_w
    y1 = y0 + btn_h

    region = draw_img.convert("RGB").crop((x0, y0, x1, y1))
    blurred = region.filter(ImageFilter.GaussianBlur(radius=14))

    avg_r, avg_g, avg_b = blurred.resize((1, 1)).getpixel((0, 0))[:3]
    h, s, v = colorsys.rgb_to_hsv(avg_r / 255, avg_g / 255, avg_b / 255)
    v = min(1.0, v + 0.30)
    s = max(0.0, s - 0.15)
    tr, tg, tb = colorsys.hsv_to_rgb(h, s, v)
    tint = (int(tr * 255), int(tg * 255), int(tb * 255))

    rgb = draw_img.convert("RGB")
    rgb.paste(blurred, (x0, y0))
    draw_img = rgb.convert("RGBA")

    overlay = Image.new("RGBA", draw_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=RADIUS,
                            fill=(*tint, 90))
    draw.rounded_rectangle([x0, y0, x1, y1], radius=RADIUS,
                            outline=(255, 255, 255, 160), width=2)
    draw.text((x0 + PAD_X, y0 + PAD_Y - bbox[1]), label,
              font=btn_font, fill=(255, 255, 255, 245))

    result = Image.alpha_composite(draw_img, overlay)
    return result.convert("RGB")


def compose_video(script_data, image_paths, audio_path, subtitle_path, music_path, cta_line=None):
    """
    Compositor: clean background panels + ASS word-by-word subtitle animation.
    Text appears word-by-word in sync with narration via ffmpeg subtitles filter.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    duration = get_audio_duration(audio_path)
    lines = [l.strip() for l in script_data["script"].split("\n") if l.strip()]
    num_panels = len(image_paths)
    num_lines = len(lines)

    # Group 2 lines per panel
    line_groups = []
    gi = 0
    while gi < num_lines:
        line_groups.append(lines[gi:min(gi + 2, num_lines)])
        gi += 2
    num_groups = len(line_groups)

    XFADE = 0.6    # crossfade between panels — defined early for drift compensation
    TAIL_PAD = 4.0 # tail silence after last word
    AUDIO_GAP = 1.0  # must match LINE_GAP in generate_audio.py
    GAP = AUDIO_GAP

    # Build per-group durations from per-line audio files
    line_durations = []
    for i in range(num_lines):
        line_path = os.path.join(OUTPUT_DIR, f"_line_{i}.mp3")
        if os.path.exists(line_path):
            line_durations.append(get_audio_duration(line_path))

    if len(line_durations) == num_lines:
        seg_durations = []
        li = 0
        for g_i, group in enumerate(line_groups):
            is_last = g_i == num_groups - 1
            group_dur = sum(line_durations[li + j] + GAP for j in range(len(group)))
            if is_last:
                group_dur = group_dur - GAP + TAIL_PAD
            else:
                group_dur += XFADE  # compensate xfade overlap so images don't drift ahead
            seg_durations.append(group_dur)
            li += len(group)
        print(f"[video] Per-group durations ({num_groups}): {[f'{d:.1f}s' for d in seg_durations]}")
    else:
        per_seg = duration / num_groups
        seg_durations = [per_seg] * num_groups
        seg_durations[-1] = per_seg + TAIL_PAD

    total_video = sum(seg_durations)
    print(f"[video] Audio: {duration:.1f}s, Video: {total_video:.1f}s, {num_groups} panels")

    # ── Step 1: Generate clean background panels (no text baked in) ────────────
    panel_videos = []
    for g_i, group in enumerate(line_groups):
        panel_idx = min(g_i, num_panels - 1)
        img = Image.open(image_paths[panel_idx]).convert("RGBA")

        # Black canvas → cover-scale → center-crop to exact 1080×1920
        canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
        img_ratio = img.width / img.height
        target_ratio = WIDTH / HEIGHT
        if img_ratio > target_ratio:
            new_h = HEIGHT
            new_w = int(new_h * img_ratio)
        else:
            new_w = WIDTH
            new_h = int(new_w / img_ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - WIDTH) // 2
        top = (new_h - HEIGHT) // 2
        img = img.crop((left, top, left + WIDTH, top + HEIGHT))
        canvas.paste(img, (0, 0))
        img = canvas

        # NO dark overlay — keep images bright and colorful.
        # Subtitle text uses its own 4px outline + shadow for readability.

        frame = img.convert("RGB")

        # Bake only fixed UI elements (not script text)
        if g_i == num_groups - 1:
            frame = _draw_cta_overlay(frame, cta_line=cta_line)
        elif g_i > 0:
            frame = _draw_follow_button(frame)

        frame_path = os.path.join(OUTPUT_DIR, f"_panel_{g_i}.png")
        frame.save(frame_path, "PNG")

        clip_path = os.path.join(OUTPUT_DIR, f"_clip_{g_i}.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", frame_path,
            "-t", f"{seg_durations[g_i]:.3f}",
            "-vf", f"fps={FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            clip_path,
        ], capture_output=True, check=True)

        panel_videos.append(clip_path)
        lines_label = " | ".join(f'"{l[:18]}…"' if len(l) > 18 else f'"{l}"' for l in group)
        print(f"[video]   Panel {g_i+1}/{num_groups} ({seg_durations[g_i]:.1f}s): {lines_label}")

    # ── Step 2: Concatenate panels with crossfade ───────────────────────────────
    output_no_audio = os.path.join(OUTPUT_DIR, "_video_noaudio.mp4")

    if len(panel_videos) == 1:
        import shutil
        shutil.copy2(panel_videos[0], output_no_audio)
    else:
        offsets = []
        cumulative = 0
        for i in range(len(panel_videos) - 1):
            offset = cumulative + seg_durations[i] - XFADE
            offsets.append(offset)
            cumulative += seg_durations[i] - XFADE

        inputs = []
        for v in panel_videos:
            inputs += ["-i", v]

        filters = []
        if len(panel_videos) == 2:
            filters.append(
                f"[0:v][1:v]xfade=transition=fade:duration={XFADE}:offset={offsets[0]:.3f}[vout]"
            )
        else:
            filters.append(
                f"[0:v][1:v]xfade=transition=fade:duration={XFADE}:offset={offsets[0]:.3f}[xf0]"
            )
            for i in range(1, len(panel_videos) - 2):
                filters.append(
                    f"[xf{i-1}][{i+1}:v]xfade=transition=fade:duration={XFADE}:offset={offsets[i]:.3f}[xf{i}]"
                )
            last = len(panel_videos) - 2
            filters.append(
                f"[xf{last-1}][{last+1}:v]xfade=transition=fade:duration={XFADE}:offset={offsets[last]:.3f}[vout]"
            )

        subprocess.run(
            ["ffmpeg", "-y"] + inputs + [
                "-filter_complex", ";".join(filters),
                "-map", "[vout]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-pix_fmt", "yuv420p",
                output_no_audio,
            ], capture_output=True, check=True,
        )

    # ── Step 3: Generate ASS word-by-word subtitle file ────────────────────────
    ass_path = None
    if subtitle_path and os.path.exists(subtitle_path):
        try:
            with open(subtitle_path) as f:
                subtitles = json.load(f)
            ass_path = os.path.join(OUTPUT_DIR, "subtitles.ass")
            _generate_ass_subtitles(subtitles, lines, ass_path)
        except Exception as e:
            print(f"[video] ASS generation failed ({e}) — video will have no subtitles")
            ass_path = None

    # ── Step 4: Mix audio (voice + music) + bake ASS subtitles ─────────────────
    output_path = os.path.join(OUTPUT_DIR, "quietlyy_video.mp4")

    # Video filter: apply ASS subtitles if available
    # Path must be escaped for ffmpeg filter syntax (colons and backslashes)
    def _escape_filter_path(p):
        return p.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")

    if ass_path:
        video_filter = f"subtitles='{_escape_filter_path(ass_path)}'"
    else:
        video_filter = "null"  # pass-through filter when no subtitles

    if music_path:
        print(f"[video] Mixing voice + {os.path.basename(music_path)}")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", output_no_audio,
            "-i", audio_path,
            "-stream_loop", "-1", "-i", music_path,
            "-filter_complex",
            f"[0:v]{video_filter}[vout];"
            f"[1:a]loudnorm=I=-16:LRA=7:TP=-1.5,apad=pad_dur=1[voice];"
            f"[2:a]volume=0.35,"
            f"afade=t=in:d=3,afade=t=out:st={max(0, duration - 4):.2f}:d=4[music];"
            f"[voice][music]amix=inputs=2:duration=first:normalize=0[aout]",
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ], capture_output=True, check=True)
    else:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", output_no_audio,
            "-i", audio_path,
            "-filter_complex",
            f"[0:v]{video_filter}[vout];"
            f"[1:a]loudnorm=I=-16:LRA=7:TP=-1.5,apad=pad_dur=1[voice]",
            "-map", "[vout]", "-map", "[voice]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ], capture_output=True, check=True)

    # Cleanup temp files
    for f in panel_videos:
        try:
            os.remove(f)
        except OSError:
            pass
    for fname in os.listdir(OUTPUT_DIR):
        if fname.startswith("_"):
            try:
                os.remove(os.path.join(OUTPUT_DIR, fname))
            except OSError:
                pass

    print(f"[video] Done: {output_path}")
    return output_path


if __name__ == "__main__":
    print("Video compositor ready. Run via pipeline.py")
