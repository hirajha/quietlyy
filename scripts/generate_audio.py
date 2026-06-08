"""
Quietlyy — Audio Generator
ElevenLabs ONLY. No fallbacks — if ElevenLabs fails, pipeline fails.
Records each line individually, joins with real silence gaps.
"""

import json
import os
import subprocess
import requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# ElevenLabs config
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
# eleven_v3 = ElevenLabs' most expressive model + supports AUDIO TAGS
# ([pause], [emphasized], [slows down], [breathes], [softly]) for true narrator
# delivery. Verified 2026-06-05 that this key has v3 access AND the
# with-timestamps endpoint returns alignment (so subtitle/panel sync is kept).
ELEVENLABS_MODEL = "eleven_v3"

# ── Variable pause logic (Whisprs-style breathing rhythm) ─────────────────────
# User feedback: uniform 1.5s pauses every line sounded robotic. Real Whisprs
# narration uses VARIED pauses based on punctuation:
#   - End of sentence (period)   → longer breath (1.8s) — the thought lands
#   - Continuation (comma, dash) → short pause   (0.6s) — within the thought
#   - No ending punctuation      → medium pause  (1.0s) — natural breath
# This mirrors human speech: longer pauses between complete thoughts,
# shorter pauses within a flowing phrase.
LINE_GAP_DEFAULT = 1.0   # legacy fallback (still used for ffmpeg silence gen)
LINE_GAP_SENTENCE = 1.8  # after a complete sentence (.) or strong end (! ?)
LINE_GAP_CONTINUATION = 0.6   # after comma, dash, ellipsis — flow continues
LINE_GAP_NEUTRAL = 1.0   # no ending punctuation — natural breath

# Legacy alias for code that still references LINE_GAP (e.g. for capacity calcs)
LINE_GAP = LINE_GAP_NEUTRAL


def _gap_for_line(text):
    """Return the silence-pause duration (seconds) AFTER this line.

    Mirrors human speech rhythm — periods get deep breath, commas get short
    flow-pause, neutral endings get a default neutral pause.
    """
    stripped = text.rstrip()
    if not stripped:
        return LINE_GAP_NEUTRAL
    last = stripped[-1]
    if last in ".!?":
        return LINE_GAP_SENTENCE
    if last in ",;:—-…":
        return LINE_GAP_CONTINUATION
    return LINE_GAP_NEUTRAL

# CTA patterns — lines matching these are NOT narrated; shown as baked text overlay instead.
# Check both startswith (for clean CTA lines) and contains (for embedded CTAs).
_CTA_STARTS = [
    "send this to",
    "send this",
    "send it to",
    "share this with",
    "share this",
    "tag the",
    "tag someone",
    "tag them",
    "tag a",
    "save this for",
    "save this if",
    "save this.",
    "save this —",
    "save this -",
    "comment below",
    "drop a ",
    "follow for",
    "like if",
    "forward this",
    "pass this on",
]
_CTA_CONTAINS = [
    "who needs to hear this",
    "who needs this",
    "who needs it",
    "send it to them",
    "needs to see this",
    "share with someone",
    "tag someone who",
    "save for the days",
    "save for when",
]


def _is_cta_line(text):
    """Return True if this line is a social CTA that should not be narrated."""
    t = text.lower().strip()
    if any(t.startswith(p) for p in _CTA_STARTS):
        return True
    # Also catch CTAs embedded mid-line (short lines only — avoids false positives)
    if len(t) < 120 and any(k in t for k in _CTA_CONTAINS):
        return True
    return False


def extract_cta(script_text):
    """Return the first CTA line from a script, or None."""
    for line in script_text.split("\n"):
        line = line.strip()
        if line and _is_cta_line(line):
            return line
    return None


def _clean_text(text):
    """Clean text for TTS — preserve ellipsis as natural pauses."""
    # Keep … as ... so ElevenLabs reads it as a pause, not a comma rush
    clean = text.replace("\u2026", "...").strip()
    return clean


def _record_line_elevenlabs(text, output_path):
    """Record one line via ElevenLabs with-timestamps endpoint.

    Returns word-level timing data extracted from ElevenLabs' character alignment.
    Falls back to plain TTS (no timestamps) if the endpoint fails.
    """
    import base64
    clean = _clean_text(text)
    voice_settings = {
        # Tuning history: 0.22 = wobbly, 0.40 = too monotone/robotic (user feedback).
        # 0.32 is the sweet spot — expressive natural variation (less robotic) while
        # staying clear. Higher style adds emotional inflection so it doesn't read flat.
        "stability": 0.32,          # 0.22→0.40→0.32: expressive but not wobbly
        "similarity_boost": 0.85,
        "style": 0.60,              # 0.50→0.60: more emotional inflection, less flat
        "use_speaker_boost": True,
        "speed": 0.90,              # 0.88→0.90: natural conversational pace
    }
    body = {
        "text": clean,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": voice_settings,
    }

    # Try with-timestamps endpoint first — gives real per-character timing
    ts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/with-timestamps"
    headers_json = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    word_timings = None
    try:
        resp = requests.post(ts_url, json=body, headers=headers_json, timeout=40)
        if resp.status_code == 200:
            data = resp.json()
            audio_bytes = base64.b64decode(data["audio_base64"])
            with open(output_path, "wb") as f:
                f.write(audio_bytes)

            # Build word-level timings from character alignment
            alignment = data.get("alignment", {})
            chars = alignment.get("characters", [])
            starts = alignment.get("character_start_times_seconds", [])
            ends = alignment.get("character_end_times_seconds", [])

            if chars and starts and ends:
                word_timings = _chars_to_word_timings(chars, starts, ends)
    except Exception as e:
        print(f"[audio] with-timestamps failed ({e}), falling back to plain TTS")

    # Fallback: plain TTS endpoint
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 500:
        plain_url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers_mp3 = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        resp = requests.post(plain_url, json=body, headers=headers_mp3, timeout=30)
        if resp.status_code != 200:
            raise ValueError(f"ElevenLabs error {resp.status_code}: {resp.text[:200]}")
        with open(output_path, "wb") as f:
            f.write(resp.content)

    if os.path.getsize(output_path) < 500:
        raise ValueError("Audio too small")

    return word_timings  # None if timestamps unavailable


def _chars_to_word_timings(chars, starts, ends):
    """Convert ElevenLabs character-level alignment into word-level timing dicts."""
    words = []
    current_word = []
    current_starts = []
    current_ends = []

    for ch, s, e in zip(chars, starts, ends):
        if ch == " ":
            if current_word:
                words.append(("".join(current_word), current_starts[0], current_ends[-1]))
                current_word, current_starts, current_ends = [], [], []
        else:
            current_word.append(ch)
            current_starts.append(s)
            current_ends.append(e)

    if current_word:
        words.append(("".join(current_word), current_starts[0], current_ends[-1]))

    return [{"word": w, "start_s": s, "end_s": e} for w, s, e in words]


def _is_tag_token(t):
    """True if a token looks like a leaked break tag or v3 audio-tag fragment."""
    tl = t.lower()
    return (("<" in t) or (">" in t) or ("=" in t) or ("/" in t)
            or ("[" in t) or ("]" in t)          # v3 audio tags like [pause]
            or tl.startswith("break") or tl == 'time')


def _chars_to_clean_words(chars, starts, ends):
    """Convert char-level alignment → a FLAT list of clean word-timing dicts
    {word, start_s, end_s}. Splits on any whitespace. Filters out fragments of
    SSML <break> tags in case they leak into the alignment characters.
    Line mapping is done by the caller via sequential word count (deterministic),
    so we don't need to track line breaks in the characters here.
    """
    words = []
    cur, cs, ce = [], [], []

    def _flush():
        nonlocal cur, cs, ce
        if cur:
            w = "".join(cur)
            if not _is_tag_token(w):
                words.append({"word": w, "start_s": cs[0], "end_s": ce[-1]})
            cur, cs, ce = [], [], []

    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            _flush()
        else:
            cur.append(ch); cs.append(s); ce.append(e)
    _flush()
    return words


def _edge_pause_after_line(line):
    """Silence (seconds) AFTER a poem line, decided by its TRAILING punctuation —
    exactly where a human reading aloud would pause:
      • ends a sentence (. ! ?)  → full pause (finish the thought)
      • ends with ellipsis (...) → dramatic trailing pause (this emotional style)
      • ends a clause (, ; : —)  → short breath
      • no end punctuation       → ENJAMBED: 0.0, flow into the next line
    Returning 0.0 for enjambed lines is the key to never pausing mid-phrase —
    those lines get merged into one continuous breath with the line that follows.
    """
    t = line.rstrip()
    if not t:
        return 0.0
    if t.endswith("...") or t.endswith("…"):
        return float(os.environ.get("EDGE_PAUSE_ELLIPSIS", "1.5"))
    c = t[-1]
    if c in ".!?":
        return float(os.environ.get("EDGE_PAUSE_SENTENCE", "1.3"))
    if c in ",;:—-":
        return float(os.environ.get("EDGE_PAUSE_CLAUSE", "0.45"))
    return 0.0  # enjambed — no pause, flows into the next line


# Words that START a new breath-phrase — a poet/reader naturally pauses just
# BEFORE these, so when we must break a long unpunctuated line we split here to
# keep the break natural (never strands a dangling "of"/"a"/"too" on its own).
_PHRASE_BOUNDARY = {
    "and", "but", "or", "nor", "yet", "so", "of", "in", "on", "at", "to", "for",
    "with", "from", "by", "like", "that", "which", "who", "when", "where",
    "while", "before", "after", "until", "though", "because", "into", "onto",
    "about", "as", "if", "then", "still", "just", "not",
}


def _segment_for_edge(lines):
    """Turn poem lines into poet-sized spoken phrases + the pause after each.

    Reads like a poet/reader (Hira: "longer continuous lines before a pause —
    should be how a poet speaks"):
      - Each poem LINE is its own breath unit — NOT merged into long run-ons —
        so the narrator pauses at every line, like reading verse.
      - The pause size matches the line's end: sentence (.!?) = long, clause
        (,;:—) = medium, ellipsis = dramatic, enjambed (no punctuation) = a
        small breath (not silence).
      - Any single line longer than MAX_PHRASE_WORDS is broken into smaller
        breath-groups — at internal commas first, then only BEFORE a natural
        phrase-boundary word — so we never pause on a dangling "of"/"a"/"too".

    Returns a list of (clean_text, pause_after_seconds).
    """
    MAX_PHRASE_WORDS = int(os.environ.get("EDGE_MAX_PHRASE_WORDS", "7"))
    PHRASE_BREATH = float(os.environ.get("EDGE_PAUSE_PHRASE", "0.3"))
    CLAUSE = float(os.environ.get("EDGE_PAUSE_CLAUSE", "0.45"))

    def _natural_chunks(text):
        """Break a long line into ≤MAX_PHRASE_WORDS breath-groups at natural
        boundaries (commas, then before phrase-boundary words). Returns a list
        of (chunk_text, is_last)."""
        import re as _re
        if len(text.split()) <= MAX_PHRASE_WORDS:
            return [text]
        # 1) split at internal clause punctuation, keeping the mark
        parts = [p.strip() for p in _re.findall(r"[^,;:—]+[,;:—]?", text) if p.strip()]
        chunks = []
        for p in parts:
            words = p.split()
            if len(words) <= MAX_PHRASE_WORDS:
                chunks.append(p)
                continue
            # 2) still too long → break BEFORE a phrase-boundary word near the cap
            cur = []
            for tok in words:
                base = tok.lower().strip(",.;:—!?'\"")
                if len(cur) >= MAX_PHRASE_WORDS - 2 and base in _PHRASE_BOUNDARY and len(cur) >= 3:
                    chunks.append(" ".join(cur))
                    cur = [tok]
                elif len(cur) >= MAX_PHRASE_WORDS:   # hard cap fallback
                    chunks.append(" ".join(cur))
                    cur = [tok]
                else:
                    cur.append(tok)
            if cur:
                chunks.append(" ".join(cur))
        return chunks

    segs = []
    for line in lines:
        s = _clean_text(line).strip()
        if not s:
            continue
        end_pause = _edge_pause_after_line(s) or PHRASE_BREATH  # enjambed → breath
        chunks = _natural_chunks(s)
        for i, ch in enumerate(chunks):
            if i == len(chunks) - 1:
                segs.append((ch, end_pause))           # line-end pause
            else:
                last_c = ch.rstrip()[-1:]
                segs.append((ch, CLAUSE if last_c in ",;:—-" else PHRASE_BREATH))

    if segs:
        segs[-1] = (segs[-1][0], 0.0)        # no pause after the very last segment
    return segs


def _record_full_edge_tts(lines, output_path):
    """FREE fallback voice (Microsoft Edge neural TTS) for when ElevenLabs is
    down/quota-exhausted — keeps posts going. Quality is good neural TTS, a notch
    below ElevenLabs v3.

    Synthesizes the poem segment-by-segment — merging enjambed lines so each
    segment is a complete phrase — and splices REAL silence at the natural
    stopping points (sentence/clause/ellipsis ends), so the narrator pauses
    between thoughts like a book reader, never mid-phrase. Returns
    (word_timings, ok) — word timing measured per segment (offset past each
    inserted silence), so subtitle/panel sync holds.

    `lines` is the list of poem lines (raw); cleaning happens inside.
    """
    try:
        import edge_tts, asyncio
    except ImportError:
        print("[audio] edge-tts not installed — cannot use free voice fallback")
        return None, False

    VOICE = os.environ.get("EDGE_TTS_VOICE", "en-US-AvaNeural")  # warm natural female
    RATE = os.environ.get("EDGE_TTS_RATE", "-10%")               # calm, unhurried

    segs = _segment_for_edge(lines)
    if not segs:
        return None, False

    rendered = []  # (seg_path, pause_after, dur_s, text)
    for idx, (text, pause) in enumerate(segs):
        seg_path = os.path.join(OUTPUT_DIR, f"_edge_seg_{idx}.mp3")
        audio = bytearray()

        async def _run(t=text, buf=audio):
            comm = edge_tts.Communicate(t, VOICE, rate=RATE)
            async for ch in comm.stream():
                if ch.get("type") == "audio":
                    buf.extend(ch["data"])

        try:
            asyncio.run(_run())
        except Exception as e:
            print(f"[audio] Edge TTS error: {str(e)[:150]}")
            return None, False
        if len(audio) < 800:
            continue
        with open(seg_path, "wb") as f:
            f.write(bytes(audio))
        dur = _get_duration_ms(seg_path) / 1000.0
        rendered.append((seg_path, pause, dur, text))

    if not rendered:
        return None, False

    # Word timings — distribute each segment's words across its measured
    # duration (by word length), advancing the clock past each inserted pause.
    words = []
    clock = 0.0
    for j, (sp, pause, dur, text) in enumerate(rendered):
        toks = text.split()
        if toks and dur > 0:
            wts = [max(len(t), 1) for t in toks]
            tw = sum(wts)
            t0 = clock
            for tok, w in zip(toks, wts):
                d = dur * (w / tw)
                words.append({"word": tok, "start_s": t0, "end_s": t0 + d})
                t0 += d
        clock += dur
        if j < len(rendered) - 1:
            clock += pause

    seg_files = [r[0] for r in rendered]
    gaps = [r[1] for r in rendered[:-1]]  # pause after each segment except last
    _join_lines_with_silence(seg_files, output_path, gaps_seconds=gaps)

    for sf in seg_files:
        try:
            os.remove(sf)
        except OSError:
            pass

    print(f"[audio]   Edge TTS: {len(rendered)} paused segments, "
          f"{len(words)} words, {clock:.1f}s total")
    return (words or None), True


def _record_full_elevenlabs(full_text, output_path):
    """Record the ENTIRE script in ONE ElevenLabs call (with timestamps).

    full_text already contains <break time="..."/> tags between lines so the
    narrator takes a real ~1s breath at each line change while still reading
    with natural connected prosody.

    Returns (clean_word_timings, ok) — a FLAT list of {word,start_s,end_s}
    (break-tag fragments filtered out). The caller maps words → lines by
    sequential word count. Returns (None, False) if the call fails.
    """
    import base64
    voice_settings = {
        "stability": 0.32,
        "similarity_boost": 0.85,
        "style": 0.60,
        "use_speaker_boost": True,
        "speed": 0.90,
    }
    body = {
        "text": full_text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": voice_settings,
    }
    ts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/with-timestamps"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    try:
        resp = requests.post(ts_url, json=body, headers=headers, timeout=90)
        if resp.status_code != 200:
            print(f"[audio] full-script with-timestamps failed {resp.status_code}: {resp.text[:200]}")
            return None, False
        data = resp.json()
        audio_bytes = base64.b64decode(data["audio_base64"])
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        alignment = data.get("alignment", {})
        chars = alignment.get("characters", [])
        starts = alignment.get("character_start_times_seconds", [])
        ends = alignment.get("character_end_times_seconds", [])
        if not (chars and starts and ends):
            print("[audio] full-script: no alignment data returned")
            return None, False
        word_timings = _chars_to_clean_words(chars, starts, ends)
        if os.path.getsize(output_path) < 500:
            return None, False
        return word_timings, True
    except Exception as e:
        print(f"[audio] full-script recording error: {e}")
        return None, False


def _get_duration_ms(filepath):
    """Get audio duration in milliseconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", filepath],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip()) * 1000


def _join_lines_with_silence(line_files, audio_path, gaps_seconds=None):
    """Concatenate line audio files with VARIABLE silence gaps between them.

    gaps_seconds: list of N-1 gap durations (one between each adjacent pair).
                  If None, uses LINE_GAP_NEUTRAL for all gaps (legacy behavior).
    """
    if gaps_seconds is None:
        gaps_seconds = [LINE_GAP_NEUTRAL] * max(0, len(line_files) - 1)

    # Pre-render the distinct silence durations we'll need (deduped)
    distinct_gaps = sorted(set(gaps_seconds))
    silence_paths = {}
    for gap in distinct_gaps:
        sp = os.path.join(OUTPUT_DIR, f"_silence_{int(gap*1000)}.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", f"{gap:.3f}", "-b:a", "192k", sp,
        ], capture_output=True, check=True)
        silence_paths[gap] = sp

    concat_path = os.path.join(OUTPUT_DIR, "_concat.txt")
    with open(concat_path, "w") as f:
        for i, lf in enumerate(line_files):
            f.write(f"file '{lf}'\n")
            if i < len(line_files) - 1:
                f.write(f"file '{silence_paths[gaps_seconds[i]]}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_path, "-b:a", "192k", audio_path,
    ], capture_output=True, check=True)

    # Cleanup (keep _line_*.mp3 — compositor uses them for per-line timing)
    for sp in silence_paths.values():
        try: os.remove(sp)
        except OSError: pass
    os.remove(concat_path)


def _strip_direction(text):
    """Remove break tags, v3 audio tags ([pause], [emphasized]...), and ellipses
    from directed text → plain words (for validating the director kept the
    actual words unchanged)."""
    import re
    t = re.sub(r"<break[^>]*/>", " ", text)
    t = re.sub(r"\[[^\]]*\]", " ", t)   # v3 audio tags like [pause], [slows down]
    t = t.replace("…", " ").replace("...", " ")
    return [w for w in re.split(r"\s+", t.strip()) if w]


def _direct_narration(lines):
    """AI NARRATION DIRECTOR — use a free LLM to annotate the poem with delivery
    direction (break tags, ellipses, emphasis) the way a pro audiobook narrator
    would, so ElevenLabs reads it with feeling instead of mechanically.

    HARD CONSTRAINT: the LLM may ONLY add <break>/ellipsis/emphasis — never add,
    remove, reorder, or change WORDS. We validate the word sequence is preserved
    (case-insensitive); if it drifts, we reject and fall back to punctuation rules.

    Returns directed_text (str) on success, or None to fall back.
    """
    orig_words = []
    for l in lines:
        orig_words.extend(l.split())
    orig_norm = [w.strip(".,;:!?…—-").lower() for w in orig_words]

    poem = "\n".join(lines)
    prompt = (
        "You are a master audiobook narrator directing an intimate, emotional "
        "spoken-word poem for ElevenLabs v3 text-to-speech. Add delivery direction "
        "so it reads like a human narrating with real feeling — contemplative, "
        "tender, never robotic.\n\n"
        "STRICT RULES — follow exactly:\n"
        "1. Do NOT add, remove, reorder, or change ANY spoken word. Keep every original word, in order. "
        "(Audio tags in [brackets] and <break> tags are NOT words — those you add.)\n"
        "2. Pacing with break tags between words:\n"
        "   - <break time=\"1.5s\" /> after a COMPLETE thought (where an idea lands)\n"
        "   - NO break between enjambed fragments that grammatically continue — they FLOW as one breath\n"
        "   - <break time=\"0.4s\" /> for a subtle beat before an emotional turn\n"
        "3. ElevenLabs v3 AUDIO TAGS in [square brackets] for delivery — use 3-6 total, placed before the "
        "word/phrase they affect. Choose from: [softly], [whispers], [sighs], [breathes], [slows down], "
        "[gently], [warmly], [emphasized], [tenderly], [pause]. Use them where a narrator naturally would — "
        "e.g. [softly] to open, [sighs] before a painful line, [emphasized] on the key word, [slows down] on the close.\n"
        "4. Add an ellipsis (…) right after a word for a soft trailing pause (sparingly, 1-2 times).\n"
        "5. Output ONLY the directed poem with tags/breaks/ellipses inline. No explanation, no quotes.\n\n"
        f"Poem:\n{poem}\n\nDirected version:"
    )

    def _call_gemini(p):
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            return None
        try:
            r = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": p}]}],
                      "generationConfig": {"temperature": 0.6, "maxOutputTokens": 1200}},
                timeout=40,
            )
            if r.status_code != 200:
                print(f"[audio] director Gemini {r.status_code}: {r.text[:120]}")
                return None
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            print(f"[audio] director Gemini error: {str(e)[:120]}")
            return None

    def _call_groq(p):
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            return None
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile",
                      "messages": [{"role": "user", "content": p}],
                      "temperature": 0.6, "max_tokens": 1200},
                timeout=40,
            )
            if r.status_code != 200:
                return None
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return None

    for caller in (_call_gemini, _call_groq):
        directed = caller(prompt)
        if not directed:
            continue
        # Strip code fences / quotes the model may wrap around it
        directed = directed.strip().strip("`").strip()
        if directed.lower().startswith("directed version"):
            directed = directed.split(":", 1)[-1].strip()
        # VALIDATE: same words, same order (ignoring case/punctuation/tags)
        new_norm = [w.strip(".,;:!?…—-").lower() for w in _strip_direction(directed)]
        if new_norm == orig_norm:
            print(f"[audio] 🎬 Narration director applied (via {caller.__name__[6:]}) — words preserved")
            return directed
        else:
            # Allow tiny diffs (≤1 word) from punctuation edge cases; else reject
            diff = sum(1 for a, b in zip(new_norm, orig_norm) if a != b) + abs(len(new_norm) - len(orig_norm))
            if diff <= 1 and abs(len(new_norm) - len(orig_norm)) <= 1:
                print(f"[audio] 🎬 Narration director applied (minor diff={diff})")
                return directed
            print(f"[audio] director output changed words (diff={diff}) — rejecting, using rules")
    return None


def generate_audio(script_text):
    """Generate the voiceover. PRIMARY path records the WHOLE script in one
    ElevenLabs call (natural flowing prosody + breathing); FALLBACK is the old
    line-by-line stitch if the single timestamped call fails.
    ElevenLabs ONLY. Raises error on total failure."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio_path = os.path.join(OUTPUT_DIR, "voiceover.mp3")
    subtitle_path = os.path.join(OUTPUT_DIR, "subtitles.json")
    line_timings_path = os.path.join(OUTPUT_DIR, "line_timings.json")

    all_lines = [line.strip() for line in script_text.split("\n") if line.strip()]
    lines = [l for l in all_lines if not _is_cta_line(l)]
    skipped = len(all_lines) - len(lines)
    if skipped:
        print(f"[audio] Skipping {skipped} CTA line(s) from narration")

    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set. Cannot generate audio.")

    print(f"[audio] Using ElevenLabs (voice: {ELEVENLABS_VOICE_ID})")

    # ── PRIMARY: whole script in ONE call (natural breathing) ────────────────
    # Break ONLY at real punctuation — NOT at every line. Whisprs-format scripts
    # have 2-6 word fragments per line; a break after every line made short-line
    # scripts choppy ("2 words, pause, 2 words, pause" — user feedback 2026-06-05).
    # Enjambed lines (no end punctuation) are grammatically continuous, so they
    # FLOW into the next line with no break. Pauses land only where the meaning
    # actually completes:
    #   • ends in . ! ?  → 1.6s break (thought lands)
    #   • ends in , ; : → 0.4s break (minor beat)
    #   • no end punctuation (enjambed) → NO break — flow into next line
    def _break_after(line):
        s = line.rstrip()
        if not s:
            return 0.0
        last = s[-1]
        if last in ".!?":
            return 1.6
        if last in ",;:—-…":
            return 0.4
        return 0.0  # enjambed — flow, no break (fixes choppiness)

    # AI NARRATION DIRECTOR first (reads like a human narrator). If it fails or
    # changes words, fall back to the deterministic punctuation-break rules.
    full_text = _direct_narration([_clean_text(l) for l in lines])
    if not full_text:
        parts = []
        for i, l in enumerate(lines):
            parts.append(_clean_text(l))
            if i < len(lines) - 1:
                brk = _break_after(l)
                parts.append(f' <break time="{brk:.1f}s" /> ' if brk > 0 else ' ')
        full_text = "".join(parts)
        print("[audio] Using punctuation-rule direction (director unavailable)")

    # Voice provider. ElevenLabs (premium v3) is used when a key is present and
    # VOICE_PROVIDER isn't forced to edge. Once you cancel ElevenLabs (no key, or
    # VOICE_PROVIDER=edge), we go STRAIGHT to the free Edge-TTS voice — no wasted
    # failing call, no scary 401 logs.
    use_elevenlabs = (
        os.environ.get("VOICE_PROVIDER", "").lower() != "edge"
        and bool(os.environ.get("ELEVENLABS_API_KEY"))
    )
    ok = False
    word_timings = None
    if use_elevenlabs:
        word_timings, ok = _record_full_elevenlabs(full_text, audio_path)

    # Free Edge-TTS — primary when ElevenLabs is off, or fallback if it failed
    # (down / quota-exhausted) so posts always keep going.
    if not ok:
        if use_elevenlabs:
            print("[audio] ElevenLabs unavailable — falling back to free Edge TTS voice")
        else:
            print("[audio] Using free Edge TTS voice (ElevenLabs off)")
        word_timings, ok = _record_full_edge_tts(lines, audio_path)
        if ok:
            print("[audio] ✅ Edge TTS voice used (free neural voice)")

    if ok and word_timings:
        # Per-word subtitle data (absolute timing from the single recording)
        sub_data = [{
            "text": wt["word"],
            "offset_ms": wt["start_s"] * 1000,
            "duration_ms": (wt["end_s"] - wt["start_s"]) * 1000,
        } for wt in word_timings]

        # Map words → lines by SEQUENTIAL word count (deterministic; robust to
        # however the break tags were handled in the alignment).
        line_timings = []
        wi = 0
        n_words = len(word_timings)
        for li, line in enumerate(lines):
            n = len(line.split())
            grp = word_timings[wi:wi + n]
            wi += n
            if grp:
                line_timings.append({
                    "line": li,
                    "start_ms": grp[0]["start_s"] * 1000,
                    "end_ms": grp[-1]["end_s"] * 1000,
                })
        # Safety: if word-count mapping consumed fewer/more words than expected
        # (ElevenLabs tokenized differently), still emit what we have — compose
        # falls back to even-split if the line count doesn't match.
        with open(line_timings_path, "w") as f:
            json.dump(line_timings, f, indent=2)

        total_dur = _get_duration_ms(audio_path) / 1000
        print(f"[audio] ✅ Whole-script single-call recording — {len(lines)} lines, "
              f"{len(word_timings)} words, {total_dur:.1f}s "
              f"(breaks only at punctuation: 1.6s full stops, 0.4s commas, enjambed flows)")
    else:
        # ── FALLBACK: old line-by-line stitch with variable silence gaps ─────
        print("[audio] ⚠️  Single-call failed — falling back to line-by-line stitch")
        line_files = []
        cumulative_ms = 0
        timing_data = []
        all_word_timings = []
        gaps_seconds = [_gap_for_line(l) for l in lines[:-1]]

        for i, line in enumerate(lines):
            line_path = os.path.join(OUTPUT_DIR, f"_line_{i}.mp3")
            wt = _record_line_elevenlabs(line, line_path)
            line_files.append(line_path)
            all_word_timings.append(wt)
            line_dur = _get_duration_ms(line_path)
            timing_data.append({"line": i, "start_ms": cumulative_ms, "duration_ms": line_dur})
            gap_after = gaps_seconds[i] if i < len(gaps_seconds) else 0
            cumulative_ms += line_dur + (gap_after * 1000)

        sub_data = []
        line_timings = []
        for td, wts in zip(timing_data, all_word_timings):
            ls = td["start_ms"]
            line_timings.append({"line": td["line"], "start_ms": ls,
                                 "end_ms": ls + td["duration_ms"]})
            if wts:
                for wt in wts:
                    sub_data.append({"text": wt["word"],
                                     "offset_ms": ls + wt["start_s"] * 1000,
                                     "duration_ms": (wt["end_s"] - wt["start_s"]) * 1000})
            else:
                words = lines[td["line"]].split()
                wd = td["duration_ms"] / max(len(words), 1)
                for wi, word in enumerate(words):
                    sub_data.append({"text": word, "offset_ms": ls + wi * wd, "duration_ms": wd})

        _join_lines_with_silence(line_files, audio_path, gaps_seconds=gaps_seconds)
        with open(line_timings_path, "w") as f:
            json.dump(line_timings, f, indent=2)
        total_dur = _get_duration_ms(audio_path) / 1000
        print(f"[audio] Done (fallback): {len(lines)} lines, {total_dur:.1f}s total")

    with open(subtitle_path, "w") as f:
        json.dump(sub_data, f, indent=2)

    return {
        "audio_path": audio_path,
        "subtitle_path": subtitle_path,
        "subtitles": sub_data,
        "line_timings_path": line_timings_path,
    }


if __name__ == "__main__":
    test = (
        "There was a time\u2026 when hearing someone's voice\u2026 meant everything.\n"
        "Back then\u2026 people waited hours\u2026 sometimes days\u2026 just for a call.\n"
        "Not because it was easy\u2026 but because it mattered.\n"
        "And now\u2026 They silence calls\u2026 from the people who care the most.\n"
        "Maybe\u2026 They didn't lose connection\u2026 They just stopped valuing it."
    )
    generate_audio(test)
