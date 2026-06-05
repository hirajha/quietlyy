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
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter


def _ffmpeg(*args, **kwargs):
    """Run ffmpeg, printing stderr to stdout on failure for GitHub Actions visibility."""
    result = subprocess.run(list(args), capture_output=True, **kwargs)
    if result.returncode != 0:
        print(f"[ffmpeg ERROR] exit={result.returncode}")
        print(result.stderr.decode(errors="replace")[-3000:])
        result.check_returncode()
    return result

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

WIDTH = 1080
HEIGHT = 1920
FPS = 30

# ── Whisprs-style cursive font (downloaded on first run) ──────────────────────
_CURSIVE_FONT_PATH = os.path.join(ASSETS_DIR, "fonts", "Kalam-Regular.ttf")
_CURSIVE_FONT_NAME = "Kalam"

def _ensure_cursive_font():
    """Download Kalam handwriting font from Google Fonts for Whisprs-style subtitles."""
    if os.path.exists(_CURSIVE_FONT_PATH) and os.path.getsize(_CURSIVE_FONT_PATH) > 10_000:
        return _CURSIVE_FONT_PATH
    os.makedirs(os.path.dirname(_CURSIVE_FONT_PATH), exist_ok=True)
    urls = [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/kalam/Kalam-Regular.ttf",
        "https://github.com/google/fonts/raw/main/ofl/kalam/Kalam-Regular.ttf",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200 and len(r.content) > 10_000:
                with open(_CURSIVE_FONT_PATH, "wb") as f:
                    f.write(r.content)
                print(f"[video] Downloaded Kalam font ({len(r.content)//1024}KB) for Whisprs-style text")
                return _CURSIVE_FONT_PATH
        except Exception as e:
            print(f"[video] Font download failed ({url}): {e}")
    print("[video] Cursive font unavailable — falling back to serif")
    return None


def get_font(size):
    # Try cursive/handwriting font first (Whisprs style)
    cursive_path = _ensure_cursive_font()
    if cursive_path:
        try:
            return ImageFont.truetype(cursive_path, size)
        except Exception:
            pass
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

    # Use Kalam cursive font (Whisprs-style) if available, else serif italic fallback
    cursive_ok = os.path.exists(_CURSIVE_FONT_PATH) and os.path.getsize(_CURSIVE_FONT_PATH) > 10_000
    if cursive_ok:
        font_name = _CURSIVE_FONT_NAME
    else:
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

            # \an8\pos(540,750): top-center anchor — Whisprs-style upper-center position
            events.append(
                f"Dialogue: 0,{ms_to_ass(word_start_ms)},{ms_to_ass(event_end_ms)},"
                f"Default,,0,0,0,,{{\\an8\\pos(540,750)}}{display_text}"
            )

    # ASS file — Whisprs style: pure white cursive text, thin 2px outline, subtle shadow
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
        f"Style: Default,{font_name},104,"  # 104 (62→84→104; user: still too small)
        "&H00FFFFFF,"   # Primary: pure white (Whisprs style)
        "&H00FFFFFF,"   # Secondary: white
        "&H00000000,"   # Outline: black
        "&H60000000,"   # Back: subtle semi-transparent black
        "0,0,0,0,"      # Bold=no, Italic=no (Kalam has its own natural style)
        "100,100,1,0,"  # ScaleX/Y, Spacing=1, Angle
        "1,3,2,"        # BorderStyle=1, Outline=3px (thicker for the bigger font), Shadow=2px
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


def _draw_watermark(img):
    """
    Draw '@Quietlyy' watermark — Whisprs-style: small cursive white text,
    semi-transparent, bottom-center of frame. Matches @Whisprs brand placement.
    """
    draw_img = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", draw_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    watermark_font = get_font(44)  # was 30 — bigger, the ONLY branding now
    text = "@Quietlyy"
    bbox = draw.textbbox((0, 0), text, font=watermark_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (WIDTH - tw) // 2
    # Single branding, at the BOTTOM but lifted up a bit (was middle @ HEIGHT-870,
    # plus a separate bottom Follow button — user wanted ONE, at bottom, raised).
    y = HEIGHT - 360

    # Subtle shadow for readability on any background
    draw.text((x + 1, y + 1 - bbox[1]), text, font=watermark_font, fill=(0, 0, 0, 100))
    # Main watermark — white, slightly transparent (like @Whisprs)
    draw.text((x, y - bbox[1]), text, font=watermark_font, fill=(255, 255, 255, 190))

    result = Image.alpha_composite(draw_img, overlay)
    return result.convert("RGB")


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

    # ── CTA text — CLEAN white text, NO box (Whisprs style) ──────────────────
    # Replaced the amber pill (2026-06): the box was clipping/hiding its own
    # text and looked off-brand vs Whisprs' clean overlays. Now the CTA renders
    # as large white text with a heavy dark outline — readable on any image,
    # no box to hide it.
    if cta_line:
        import re
        clean_cta = re.sub(r'[^\x00-\x7F❤️💾📩🤍]', '', cta_line).strip()
        if not clean_cta:
            clean_cta = cta_line

        cta_font = get_font(58)  # large + readable
        wrapped = _textwrap.wrap(clean_cta, width=22) or [clean_cta]
        line_h = 74
        block_h = len(wrapped) * line_h
        # Position the CTA block above the @Quietlyy watermark (now at HEIGHT-360)
        # with clearance so they never overlap.
        start_y = HEIGHT - block_h - 440

        for li, wline in enumerate(wrapped):
            bbox = draw.textbbox((0, 0), wline, font=cta_font)
            tw = bbox[2] - bbox[0]
            tx = (WIDTH - tw) // 2
            ty = start_y + li * line_h - bbox[1]
            # Heavy black outline so white text reads on any background
            for ox in range(-3, 4):
                for oy in range(-3, 4):
                    if ox * ox + oy * oy <= 9:
                        draw.text((tx + ox, ty + oy), wline, font=cta_font, fill=(0, 0, 0, 230))
            draw.text((tx, ty), wline, font=cta_font, fill=(255, 255, 255, 255))

    # (Removed the "Follow @Quietlyy for more" line — user wanted only ONE
    # branding. The single @Quietlyy watermark at the bottom is added by
    # _draw_watermark on every panel, including this one.)

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


HOOK_DURATION = 2.5  # seconds — scroll-stopper card at video start
HOOK_DURATION_MS = int(HOOK_DURATION * 1000)


def _render_hook_card(hook_text, background_image_path, output_path):
    """Build a static PNG hook card: dimmed background image + giant bold centered text.

    The hook plays before the narrator starts speaking. Purpose: stop the
    scroll. Whisprs-style: a single powerful line, large enough to read in
    0.5s, centered, with high-contrast outline.
    """
    # Background: heavily dimmed copy of first image
    if background_image_path and os.path.exists(background_image_path):
        bg = Image.open(background_image_path).convert("RGBA")
        # Cover-scale + crop to 1080x1920
        img_ratio = bg.width / bg.height
        target_ratio = WIDTH / HEIGHT
        if img_ratio > target_ratio:
            new_h, new_w = HEIGHT, int(HEIGHT * img_ratio)
        else:
            new_w, new_h = WIDTH, int(WIDTH / img_ratio)
        bg = bg.resize((new_w, new_h), Image.LANCZOS)
        left, top = (new_w - WIDTH) // 2, (new_h - HEIGHT) // 2
        bg = bg.crop((left, top, left + WIDTH, top + HEIGHT))
    else:
        bg = Image.new("RGBA", (WIDTH, HEIGHT), (15, 15, 22, 255))

    # Dim overlay (60% black) so text reads clearly
    dim = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 150))
    canvas = Image.alpha_composite(bg, dim)

    # Render bold hook text — large, centered, with outline
    draw = ImageDraw.Draw(canvas)
    # Strip trailing punctuation for cleaner card display
    display_text = hook_text.strip().rstrip(".,;:—-")

    # ── MEASURE-BASED WORD WRAP + AUTO-SHRINK FONT ──────────────────────────
    # Bug fix (2026): old logic split by word COUNT (≤4 words = 1 line) without
    # ever measuring pixel width, so long lines overflowed both frame edges and
    # first/last letters were cut off. Now we:
    #   1. Reserve a safe margin (text must fit within MAX_TEXT_W)
    #   2. Greedy word-wrap by MEASURED pixel width
    #   3. If too many lines result, shrink the font and re-wrap
    SIDE_MARGIN = 90                       # px of guaranteed clear space each side
    MAX_TEXT_W = WIDTH - 2 * SIDE_MARGIN    # 1080 - 180 = 900px usable width
    MAX_LINES = 4                           # beyond this, shrink font instead

    def _wrap_to_width(text, font_obj):
        """Greedy wrap: add words to a line until the next word would overflow."""
        words = text.split()
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            tw = draw.textbbox((0, 0), trial, font=font_obj)[2] - draw.textbbox((0, 0), trial, font=font_obj)[0]
            if tw <= MAX_TEXT_W or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    # Start large, shrink until it fits in MAX_LINES AND every line fits MAX_TEXT_W
    font_size = 104
    while font_size >= 52:
        font = get_font(font_size)
        wrapped_lines = _wrap_to_width(display_text, font)
        # Check: line count OK AND widest line fits
        widest = max(
            (draw.textbbox((0, 0), ln, font=font)[2] - draw.textbbox((0, 0), ln, font=font)[0])
            for ln in wrapped_lines
        )
        if len(wrapped_lines) <= MAX_LINES and widest <= MAX_TEXT_W:
            break
        font_size -= 6

    # Line height scales with chosen font size
    line_h = int(font_size * 1.25)
    total_h = len(wrapped_lines) * line_h
    start_y = (HEIGHT - total_h) // 2

    for i, line in enumerate(wrapped_lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        # Center horizontally; clamp x so it can never go negative (off-frame left)
        x = max(SIDE_MARGIN, (WIDTH - tw) // 2)
        y = start_y + i * line_h
        # Heavy shadow / outline
        for ox in range(-3, 4):
            for oy in range(-3, 4):
                if ox * ox + oy * oy <= 9:
                    draw.text((x + ox, y + oy), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    # Subtle brand watermark at bottom
    canvas = _draw_watermark(canvas.convert("RGB")).convert("RGBA")

    canvas.convert("RGB").save(output_path, "PNG")


def compose_video(script_data, image_paths, audio_path, subtitle_path, music_path, cta_line=None):
    """
    Compositor: clean background panels + ASS word-by-word subtitle animation.
    Text appears word-by-word in sync with narration via ffmpeg subtitles filter.

    NEW (2026-05-26): Prepends a 2.5s 'hook card' to every video — bold
    centered text from the script's first line. Goal: stop the scroll in
    the first second. Voice is delayed by HOOK_DURATION so subtitles still
    sync with narration.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    duration = get_audio_duration(audio_path)
    # Use the SAME narrated-line set as generate_audio (CTA lines are not
    # narrated, so they have no timing and must not be grouped into panels).
    try:
        from generate_audio import _is_cta_line as _is_cta
    except Exception:
        def _is_cta(_t):
            return False
    all_script_lines = [l.strip() for l in script_data["script"].split("\n") if l.strip()]
    lines = [l for l in all_script_lines if not _is_cta(l)]
    num_panels = len(image_paths)
    num_lines = len(lines)

    # Group 2 lines per panel
    line_groups = []
    gi = 0
    while gi < num_lines:
        line_groups.append(lines[gi:min(gi + 2, num_lines)])
        gi += 2
    num_groups = len(line_groups)

    XFADE = 0.6    # crossfade between panels
    TAIL_PAD = 4.0 # tail after last word

    # ── Panel timing from REAL per-line timing (line_timings.json) ────────────
    # generate_audio now records the whole script in one call and writes the
    # actual start/end time of each narrated line. We time the panels to those
    # real boundaries so images change exactly in sync with the narration.
    line_timings = None
    lt_path = os.path.join(OUTPUT_DIR, "line_timings.json")
    if os.path.exists(lt_path):
        try:
            with open(lt_path) as f:
                line_timings = json.load(f)
        except Exception:
            line_timings = None

    seg_durations = None
    if line_timings and len(line_timings) == num_lines:
        starts = [lt["start_ms"] / 1000.0 for lt in line_timings]
        ends = [lt["end_ms"] / 1000.0 for lt in line_timings]
        speech_end = ends[-1]
        seg_durations = []
        li = 0
        for g_i, group in enumerate(line_groups):
            is_last = g_i == num_groups - 1
            g_first = li
            g_start = starts[g_first]
            if is_last:
                g_end = speech_end + TAIL_PAD
            else:
                # group ends when the NEXT group's first line begins
                g_end = starts[li + len(group)]
            seg = g_end - g_start
            if not is_last:
                seg += XFADE  # compensate xfade overlap so images don't drift
            seg_durations.append(max(seg, 1.0))
            li += len(group)
        print(f"[video] Panel timing from line_timings.json ({num_groups} panels): "
              f"{[f'{d:.1f}s' for d in seg_durations]}")

    if seg_durations is None:
        # Fallback: even split across audio duration
        print("[video] line_timings unavailable/mismatched — even-splitting panels")
        per_seg = duration / max(num_groups, 1)
        seg_durations = [per_seg] * num_groups
        seg_durations[-1] = per_seg + TAIL_PAD

    total_video = sum(seg_durations)
    print(f"[video] Audio: {duration:.1f}s, Video (panels): {total_video:.1f}s, {num_groups} panels")

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

        # NO dark overlay — keep images clean. Subtitle text uses outline for readability.

        frame = img.convert("RGB")

        # Bake fixed UI elements.
        # Last panel: CTA text (no follow line — see _draw_cta_overlay).
        # Follow button REMOVED — user wanted only ONE branding. The single
        # "@Quietlyy" watermark (now at the bottom) is the only brand mark.
        if g_i == num_groups - 1:
            frame = _draw_cta_overlay(frame, cta_line=cta_line)

        # The ONE branding: @Quietlyy watermark at the bottom, every panel
        frame = _draw_watermark(frame)

        frame_path = os.path.join(OUTPUT_DIR, f"_panel_{g_i}.png")
        frame.save(frame_path, "PNG")

        clip_path = os.path.join(OUTPUT_DIR, f"_clip_{g_i}.mp4")
        _ffmpeg(
            "ffmpeg", "-y",
            "-loop", "1", "-i", frame_path,
            "-t", f"{seg_durations[g_i]:.3f}",
            "-vf", f"fps={FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            clip_path,
        )

        panel_videos.append(clip_path)
        lines_label = " | ".join(f'"{l[:18]}…"' if len(l) > 18 else f'"{l}"' for l in group)
        print(f"[video]   Panel {g_i+1}/{num_groups} ({seg_durations[g_i]:.1f}s): {lines_label}")

    # ── Step 1b: PREPEND hook card (scroll-stopper for first 2.5s) ─────────────
    hook_text = lines[0] if lines else "Some things deserve to be said."
    hook_card_png = os.path.join(OUTPUT_DIR, "_hook_card.png")
    hook_card_mp4 = os.path.join(OUTPUT_DIR, "_hook_card.mp4")
    bg_for_hook = image_paths[0] if image_paths else None
    _render_hook_card(hook_text, bg_for_hook, hook_card_png)
    _ffmpeg(
        "ffmpeg", "-y",
        "-loop", "1", "-i", hook_card_png,
        "-t", f"{HOOK_DURATION:.3f}",
        "-vf", f"fps={FPS},format=yuv420p",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        hook_card_mp4,
    )
    panel_videos.insert(0, hook_card_mp4)
    seg_durations.insert(0, HOOK_DURATION)
    total_video += HOOK_DURATION
    print(f"[video]   Hook card prepended ({HOOK_DURATION}s): '{hook_text[:50]}'")

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

        _ffmpeg(
            "ffmpeg", "-y", *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p",
            output_no_audio,
        )

    # ── Step 2b: PROBE the actual rendered video length ────────────────────────
    # xfade crossfades OVERLAP panels, so the real video is shorter than
    # sum(seg_durations) by (num_panels-1)*XFADE. Rather than re-derive the math
    # (error-prone — caused a 4.2s audio overrun in audit 2026-06), just measure
    # the concatenated file and pad/fade audio to THIS exact value.
    actual_video_len = get_audio_duration(output_no_audio)
    print(f"[video] Actual rendered video length: {actual_video_len:.2f}s "
          f"(sum-of-segments was {total_video:.2f}s; xfade overlap accounts for the diff)")

    # ── Step 3: Generate ASS word-by-word subtitle file ────────────────────────
    # All subtitle timestamps are shifted by HOOK_DURATION so they sync with the
    # delayed voice (voice is offset by HOOK_DURATION in the audio mix below).
    ass_path = None
    if subtitle_path and os.path.exists(subtitle_path):
        try:
            with open(subtitle_path) as f:
                subtitles = json.load(f)
            # Shift every subtitle event by HOOK_DURATION (in ms)
            for sub in subtitles:
                sub["offset_ms"] = sub.get("offset_ms", 0) + HOOK_DURATION_MS
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
        # Include fontsdir so ffmpeg/libass can find the Kalam cursive font
        fonts_dir = os.path.join(ASSETS_DIR, "fonts")
        fonts_dir_esc = _escape_filter_path(fonts_dir)
        video_filter = f"subtitles='{_escape_filter_path(ass_path)}':fontsdir='{fonts_dir_esc}'"
    else:
        video_filter = "null"  # pass-through filter when no subtitles

    if music_path:
        print(f"[video] Mixing voice + music (with ducking) — {os.path.basename(music_path)}")
        # ── Whisprs-matched audio ducking ─────────────────────────────────────
        # Whisprs profile (measured from their actual videos at -14.5 LUFS total mix):
        #   • Voice alone:  ~-11 LUFS (clearly present, foreground)
        #   • Music alone (pauses):  ~-17 LUFS (audible, fills the silence)
        #   • Music ducked (speech): ~-28 LUFS (barely there, just texture)
        #   • Swing depth:  ~11dB drop when voice enters
        #   • Recovery:     music fully swells back during 1.5s breath gap
        #
        # The duck must be:
        #   1) PRESENT — voice always perceptible above music
        #   2) GRADUAL — slow attack so duck onset isn't audible
        #   3) SMOOTH — soft knee, no pumping artifact
        #   4) STAY DOWN — slow release so music doesn't yo-yo in 1.5s gaps
        #
        # USER FEEDBACK 2026-05-17: Previous duck was 'too aggressive — music
        # suddenly rises high and gets too low quickly, very noticeable'.
        # MEASURED from 3 real Whisprs MP4s (2026-06): total mix -14.5 LUFS,
        # TP -0.5 dBTP, and crucially LRA 3.2-4.4 LU — a VERY TIGHT/EVEN mix.
        # Low LRA means Whisprs BARELY ducks: music sits at a gentle constant
        # level under a steady voice. This confirms the earlier 'ducking too
        # noticeable' complaint. So: even gentler duck (ratio 3) + a FINAL
        # loudnorm to -14.5 LUFS / LRA 4 to match their broadcast-tight profile.
        _ffmpeg(
            "ffmpeg", "-y",
            "-i", output_no_audio,
            "-i", audio_path,
            "-stream_loop", "-1", "-i", music_path,
            "-filter_complex",
            # Voice: delayed by HOOK_DURATION so hook card is silent, then padded
            # to the EXACT total video length (whole_dur) so the mixed audio runs
            # the full video — music fills the silent tail instead of cutting out.
            # (Audit 2026-06: amix duration=first was ending audio ~8s early.)
            f"[1:a]adelay={HOOK_DURATION_MS}|{HOOK_DURATION_MS},loudnorm=I=-12:LRA=5:TP=-1,apad=whole_dur={actual_video_len:.3f},asplit=2[voice_out][voice_sc];"
            # Music: -19 LUFS base (was -21 — user: music too light/quiet). With
            # the gentle ratio-3 duck and final -14.5 normalize, -19 makes the
            # music clearly present under the voice without overpowering it.
            # Fade in at start, fade out over the LAST 4s of the ACTUAL rendered
            # video length (post-xfade) so audio length exactly equals video.
            f"[2:a]loudnorm=I=-24:LRA=7:TP=-2,"
            f"afade=t=in:d=3,afade=t=out:st={max(0, actual_video_len - 4):.2f}:d=4[music_norm];"
            # Sidechain duck — TINY swing (user: pause swell was too loud).
            # Music now sits quietly at -24 LUFS THROUGHOUT; the duck only dips
            # it ~1-2dB more when the narrator speaks, so the pause level is just
            # a hair above the speaking level (not a big bloom). Quiet, constant
            # background with a subtle lift in the gaps.
            #   ratio=2       → very shallow (~1-2dB) swing
            #   attack=300ms  → smooth onset
            #   release=1200ms → gentle, no big recovery jump
            #   knee=6        → very soft, no pumping
            f"[music_norm][voice_sc]sidechaincompress=threshold=0.03:ratio=2:attack=300:release=1200:knee=6:makeup=1[music_ducked];"
            # Mix, then FINAL loudnorm to Whisprs' exact measured profile
            # (-14.5 LUFS, LRA 4, TP -1) → tight, even, broadcast-consistent.
            f"[0:v]{video_filter}[vout];"
            f"[voice_out][music_ducked]amix=inputs=2:duration=first:normalize=0,"
            f"loudnorm=I=-14.5:LRA=4:TP=-1[aout]",
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        )
    else:
        _ffmpeg(
            "ffmpeg", "-y",
            "-i", output_no_audio,
            "-i", audio_path,
            "-filter_complex",
            f"[0:v]{video_filter}[vout];"
            # adelay shifts voice by HOOK_DURATION so the hook card is silent
            f"[1:a]adelay={HOOK_DURATION_MS}|{HOOK_DURATION_MS},loudnorm=I=-11:LRA=7:TP=-0.5,apad=pad_dur=1[voice]",
            "-map", "[vout]", "-map", "[voice]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        )

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
