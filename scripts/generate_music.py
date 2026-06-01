"""
Quietlyy — Emotion-Based Background Music Generator

Music matches the emotional tone of the script:
  emotional  → contemplative piano/strings, 65-90 BPM
  nostalgic  → warm piano + subtle nature sounds (birds/wind), 85-110 BPM
  poetic     → melancholic piano/cello + rain/wind ambience, 60-80 BPM
  love       → tender piano + soft violin, 70-90 BPM (heartbeat tempo)
  motivational → building piano/strings, morning nature sounds, 90-120 BPM

Key principle: Emotional congruence between music and script creates the
strongest viewer connection — makes them stop scrolling and feel something.
"""

import json
import os
import random
import requests

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# Music gallery — every successfully generated ElevenLabs track is saved here
# so future runs can reuse them. Saves quota and provides offline fallback.
# Subdirs by mood: assets/music_gallery/heartbreak/, /longing/, etc.
# After 20 different tracks have been used for a mood, repetition is allowed.
MUSIC_GALLERY_DIR = os.path.join(ASSETS_DIR, "music_gallery")
GALLERY_RECENT_LIMIT = 20  # Don't replay any of the last 20 used tracks

FREESOUND_API_KEY = os.environ.get("FREESOUND_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
SONAUTO_API_KEY = os.environ.get("SONAUTO_API_KEY", "")

# Lyria 3 daily quota is very small (~5-10 calls/day on free tier). After a
# 429, skip it for this many hours instead of wasting an API call every run.
LYRIA_COOLDOWN_HOURS = 12

# ── MusicGen prompts per mood ─────────────────────────────────────────────────
# Engineered for Whisprs-style emotional instrumentals: piano + strings + soft
# texture, slow tempo, no vocals. These prompts are specific enough that
# MusicGen reliably produces the right vibe (vs vague terms like "sad music").
# Tested patterns: name instruments + tempo BPM + "instrumental" + "no vocals"
_MUSICGEN_PROMPTS = {
    "heartbreak": "Soft sad piano with deep cello, melancholic heartbreak ballad, slow tempo 60 BPM, cinematic instrumental, gentle strings, no drums, no vocals",
    "longing":    "Wistful piano with cello and violin, nostalgic longing melody, slow tempo 65 BPM, sparse emotional cinematic instrumental, no vocals",
    "melancholy": "Dark melancholy piano and cello, sad emotional atmosphere, slow tempo 60 BPM, cinematic instrumental, ambient strings, no vocals",
    "love":       "Tender romantic piano with soft violin, gentle love ballad, slow tempo 70 BPM, intimate emotional instrumental, no vocals",
    "hope":       "Hopeful piano with rising strings, emotional cinematic build, slow tempo 72 BPM, uplifting instrumental, no vocals",
}


def _generate_lyria_music(mood, output_path, duration_sec=30):
    """Generate music via Google Lyria 3 (DeepMind) through the Gemini API.

    Launched 2026-04-18 alongside Google Flow Music. Available via
    generativelanguage.googleapis.com using the existing GEMINI_API_KEY —
    same key as our script generator. Free tier through Gemini API.

    Models:
      - lyria-3-clip-preview : 30-second clips (what we want)
      - lyria-3-pro-preview  : full-length songs (not needed)

    Response is base64-encoded audio inside the standard Gemini response
    structure: candidates[0].content.parts[i].inline_data.data
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return False

    # Skip if recently 429'd — saves a wasted API call (~1s + log noise)
    if _is_lyria_in_cooldown():
        print(f"[music] ⏱  Lyria in cooldown (429'd within last {LYRIA_COOLDOWN_HOURS}h) — skipping to next provider")
        return False

    prompt = _MUSICGEN_PROMPTS.get(mood, _MUSICGEN_PROMPTS["melancholy"])
    # Lyria understands natural language — be explicit about duration + no vocals
    full_prompt = (
        f"{prompt}. "
        f"Generate a {duration_sec}-second instrumental piece. "
        f"Instrumental only, no vocals, no singing, no lyrics."
    )

    try:
        print(f"[music] ▶ Trying Google Lyria 3 (Gemini): '{prompt[:60]}...' ({duration_sec}s)")
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/lyria-3-clip-preview:generateContent",
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {"responseModalities": ["AUDIO"]},
            },
            timeout=180,  # Music gen can take 30-90s
        )

        if resp.status_code == 200:
            data = resp.json()
            # Walk response → find audio inline_data part
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    inline = part.get("inline_data") or part.get("inlineData")
                    if not inline or "data" not in inline:
                        continue
                    import base64
                    audio_bytes = base64.b64decode(inline["data"])
                    mime = inline.get("mime_type") or inline.get("mimeType", "audio/mpeg")

                    # If WAV/FLAC, convert via ffmpeg; otherwise write directly (MP3)
                    if "wav" in mime.lower() or "flac" in mime.lower() or "pcm" in mime.lower():
                        tmp = output_path + ".lyria.raw"
                        with open(tmp, "wb") as f:
                            f.write(audio_bytes)
                        import subprocess
                        result = subprocess.run(
                            ["ffmpeg", "-y", "-i", tmp, "-b:a", "192k", output_path],
                            capture_output=True,
                        )
                        try: os.remove(tmp)
                        except OSError: pass
                        if result.returncode != 0:
                            print(f"[music]   ❌ Lyria ffmpeg convert failed: {result.stderr.decode(errors='replace')[-200:]}")
                            continue
                    else:
                        with open(output_path, "wb") as f:
                            f.write(audio_bytes)

                    if os.path.getsize(output_path) > 10_000:
                        size_kb = os.path.getsize(output_path) // 1024
                        print(f"[music]   ✅ Lyria 3 generated {duration_sec}s ({size_kb}KB) — FREE via Gemini API")
                        return True

            print(f"[music]   ❌ Lyria response had no usable audio part: {str(data)[:300]}")
            return False

        # Categorized error reporting
        body = resp.text[:300]
        if resp.status_code == 401:
            print(f"[music]   ⚙️  Lyria 401: GEMINI_API_KEY invalid: {body}")
        elif resp.status_code == 403:
            print(f"[music]   ⚙️  Lyria 403: model not enabled on this project — check AI Studio access: {body}")
        elif resp.status_code == 404:
            print(f"[music]   ⚙️  Lyria 404: 'lyria-3-clip-preview' not found — preview may be over or renamed: {body}")
        elif resp.status_code == 429:
            print(f"[music]   ⏳ Lyria 429: free-tier daily quota exhausted: {body}")
            _record_lyria_429()
            print(f"[music]   ⏱  Lyria entered {LYRIA_COOLDOWN_HOURS}h cooldown — will retry after that")
        elif resp.status_code == 400:
            print(f"[music]   ⚙️  Lyria 400: bad request body schema: {body}")
        else:
            print(f"[music]   ❌ Lyria status={resp.status_code}: {body}")
    except Exception as e:
        print(f"[music]   ❌ Lyria error: {type(e).__name__}: {str(e)[:200]}")

    return False


def _generate_sonauto_music(mood, output_path, duration_sec=30):
    """Generate music via Sonauto Melodia v3 — 1,500 free credits on signup.

    Sonauto offers an unlimited free AI music generator (web UI) and an API
    with 1,500 free credits on signup, no credit card required. Sign up at
    sonauto.ai/developers and set SONAUTO_API_KEY in GitHub secrets.

    API is ASYNC — submit returns task_id, poll /status/{task_id} until SUCCESS,
    then download song_paths[0] URL. Generation typically takes 30-90 seconds.
    """
    if not SONAUTO_API_KEY:
        return False

    prompt = _MUSICGEN_PROMPTS.get(mood, _MUSICGEN_PROMPTS["melancholy"])
    headers = {
        "Authorization": f"Bearer {SONAUTO_API_KEY}",
        "Content-Type": "application/json",
    }

    # Step 1: Submit generation request
    try:
        print(f"[music] ▶ Trying Sonauto Melodia v3: '{prompt[:60]}...' ({duration_sec}s)")
        submit = requests.post(
            "https://api.sonauto.ai/v1/generations/v3",
            headers=headers,
            json={
                "prompt": prompt,
                "instrumental": True,         # No vocals/lyrics
                "output_format": "mp3",
                # Sonauto constraint: AT MOST ONE of prompt_strength/style_scale > 1.0
                # We use prompt (not tags), so favor prompt_strength
                "prompt_strength": 2.5,       # Strong prompt adherence
                "style_scale": 1.0,           # Min (we're not using tags)
            },
            timeout=30,
        )

        if submit.status_code == 401:
            print(f"[music]   ⚙️  Sonauto 401: SONAUTO_API_KEY invalid: {submit.text[:200]}")
            return False
        if submit.status_code == 402:
            print(f"[music]   ⏳ Sonauto 402: credits exhausted (free tier = 1500 credits): {submit.text[:200]}")
            return False
        if submit.status_code == 429:
            print(f"[music]   ⏳ Sonauto 429: rate-limited: {submit.text[:200]}")
            return False
        if submit.status_code != 200:
            print(f"[music]   ❌ Sonauto submit status={submit.status_code}: {submit.text[:200]}")
            return False

        task_id = submit.json().get("task_id")
        if not task_id:
            print(f"[music]   ❌ Sonauto returned no task_id: {submit.text[:200]}")
            return False
        print(f"[music]   ⏳ Sonauto job submitted (task_id={task_id[:12]}...), polling for completion")

        # Step 2: Poll for completion (max ~6 minutes — was 3 but kept timing
        # out under load; Sonauto generation often takes 4-5 min for the v3
        # model). Real runs caught timing out: 25956206851, 25953138913.
        import time
        status_url = f"https://api.sonauto.ai/v1/generations/status/{task_id}"
        full_url = f"https://api.sonauto.ai/v1/generations/{task_id}"

        for attempt in range(72):  # 72 * 5s = 360s = 6 min max
            time.sleep(5)
            try:
                poll = requests.get(status_url, headers=headers, timeout=15)
            except Exception:
                continue
            if poll.status_code != 200:
                continue
            try:
                data = poll.json()
            except Exception:
                continue

            # Defensive parse — Sonauto returns string OR dict
            if isinstance(data, str):
                state = data
                song_paths = []
            elif isinstance(data, dict):
                state = data.get("status", "")
                song_paths = data.get("song_paths", []) or []
            else:
                continue

            if state == "SUCCESS":
                # If status endpoint only returned the string, fetch full record
                if not song_paths:
                    try:
                        full = requests.get(full_url, headers=headers, timeout=15)
                        if full.status_code == 200:
                            full_data = full.json()
                            if isinstance(full_data, dict):
                                song_paths = full_data.get("song_paths", []) or []
                    except Exception:
                        pass

                if not song_paths:
                    print(f"[music]   ❌ Sonauto SUCCESS but no song_paths in either endpoint")
                    return False

                # Step 3: Download the audio
                try:
                    audio_resp = requests.get(song_paths[0], timeout=60)
                    if audio_resp.status_code == 200 and len(audio_resp.content) > 50_000:
                        with open(output_path, "wb") as f:
                            f.write(audio_resp.content)
                        print(f"[music]   ✅ Sonauto generated {len(audio_resp.content)//1024}KB — FREE (1500 credits/signup)")
                        return True
                    print(f"[music]   ❌ Sonauto audio download failed: status={audio_resp.status_code}, len={len(audio_resp.content)}")
                except Exception as e:
                    print(f"[music]   ❌ Sonauto audio download error: {e}")
                return False

            if state in ("FAILED", "ERROR", "CANCELLED"):
                print(f"[music]   ❌ Sonauto generation failed: state={state}")
                return False
            # else PENDING/PROCESSING/QUEUED — keep polling

        print(f"[music]   ⏱  Sonauto timed out after 6min waiting for SUCCESS")
    except Exception as e:
        print(f"[music]   ❌ Sonauto error: {type(e).__name__}: {str(e)[:200]}")

    return False


def _generate_elevenlabs_music(mood, output_path, duration_sec=30):
    """Generate music via ElevenLabs Music API — uses the existing ELEVENLABS_API_KEY.

    ElevenLabs Music produces full song-like instrumentals (piano + strings +
    soft beat) much closer to commercial library quality than MusicGen-small.
    Generation takes ~30-90s. Cost: ~1000 chars equivalent per 30s clip
    (counted against your ElevenLabs plan quota).

    Returns True on success. On failure, logs the categorized error so we know
    if it's a plan/auth issue vs transient failure.

    Common failure modes:
      403 → plan doesn't include music generation
      401 → API key invalid
      429 → monthly quota exhausted
      422 → bad request format
    """
    if not ELEVENLABS_API_KEY:
        return False

    prompt = _MUSICGEN_PROMPTS.get(mood, _MUSICGEN_PROMPTS["melancholy"])
    duration_ms = int(min(max(duration_sec, 10), 60) * 1000)

    try:
        print(f"[music] ▶ Trying ElevenLabs Music: '{prompt[:60]}...' ({duration_sec}s)")
        resp = requests.post(
            "https://api.elevenlabs.io/v1/music",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "prompt": prompt,
                "music_length_ms": duration_ms,
            },
            timeout=180,  # Music gen can take 30-90s
        )

        if resp.status_code == 200 and len(resp.content) > 50_000:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            print(f"[music]   ✅ ElevenLabs Music generated {duration_sec}s ({len(resp.content)//1024}KB)")
            return True

        # Categorized error handling — diagnostic clarity for next debug
        if resp.status_code == 403:
            print(f"[music]   ⚙️  ElevenLabs 403: plan does not include music generation. Use CC0 fallback or upgrade.")
        elif resp.status_code == 401:
            print(f"[music]   ⚙️  ElevenLabs 401: API key invalid or expired")
        elif resp.status_code == 429:
            print(f"[music]   ⏳ ElevenLabs 429: monthly quota exhausted")
        elif resp.status_code == 422:
            print(f"[music]   ⚙️  ElevenLabs 422: invalid request: {resp.text[:200]}")
        elif resp.status_code == 404:
            print(f"[music]   ⚙️  ElevenLabs 404: /v1/music endpoint not found — API URL may have changed")
        else:
            print(f"[music]   ❌ ElevenLabs status={resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[music]   ❌ ElevenLabs Music error: {type(e).__name__}: {str(e)[:200]}")

    return False


def _extract_audio_path(result):
    """Pull an audio file path out of a gradio Client result (varies per Space)."""
    if isinstance(result, str):
        return result if os.path.exists(result) else None
    if isinstance(result, (list, tuple)):
        for item in result:
            if isinstance(item, str) and item.lower().endswith((".wav", ".mp3", ".flac", ".ogg", ".m4a")):
                if os.path.exists(item):
                    return item
            if isinstance(item, dict):
                p = item.get("path") or item.get("audio")
                if p and os.path.exists(p):
                    return p
    if isinstance(result, dict):
        p = result.get("path") or result.get("audio")
        if p and os.path.exists(p):
            return p
    return None


def _try_hf_space(space_id, api_name, build_args, prompt, duration, output_path):
    """Try a single HF Space. Returns ('ok'|'down'|'config'|'queued'|'empty', detail).

    Categorizes failures so we can distinguish:
      - 'down'   : Space unreachable / 5xx / timeout (server-side, transient)
      - 'config' : Our api_name or arg shape is wrong (our code bug)
      - 'queued' : Space is busy / rate-limited (transient, try later)
      - 'empty'  : Call succeeded but didn't return a usable audio file
      - 'ok'     : Generated and saved successfully
    """
    try:
        from gradio_client import Client
    except ImportError:
        return "config", "gradio_client not installed"

    # ── Step 1: Connect to the Space ──────────────────────────────────────────
    # Run 25885325300 hit 401 Client Error on multimodalart/stable-audio-open
    # and facebook/MusicGen-Continuation. ZeroGPU Spaces now require auth even
    # for "public" access. gradio_client doesn't accept hf_token kwarg in some
    # versions, but it WILL read from HF_TOKEN / HUGGING_FACE_HUB_TOKEN env
    # vars on import. Set both before connecting (belt and braces).
    if HF_TOKEN:
        os.environ["HF_TOKEN"] = HF_TOKEN
        os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN
    try:
        client = Client(space_id)
    except Exception as e:
        msg = str(e).lower()
        if "401" in msg or "unauthorized" in msg:
            return "config", f"Auth required (401) — HF_TOKEN may lack ZeroGPU access: {str(e)[:200]}"
        if any(s in msg for s in ("connection", "unreachable", "name or service", "timed out", "timeout", "503", "502", "504")):
            return "down", f"{type(e).__name__}: {str(e)[:200]}"
        if "404" in msg or "not found" in msg:
            return "config", f"Space ID '{space_id}' not found: {str(e)[:200]}"
        return "down", f"{type(e).__name__}: {str(e)[:200]}"

    # ── Step 2: Introspect available API endpoints (catches wrong api_name) ──
    detected_apis = []
    try:
        api_info = client.view_api(return_format="dict")
        detected_apis = list(api_info.get("named_endpoints", {}).keys())
        if api_name not in detected_apis:
            # Auto-recover: pick the first available endpoint
            if detected_apis:
                print(f"[music]   ⚙️  api_name '{api_name}' not on Space — falling back to detected '{detected_apis[0]}'")
                api_name = detected_apis[0]
            else:
                return "config", f"Space has NO named endpoints. Our api_name '{api_name}' won't work."
    except Exception as e:
        # Introspection failed but we can still try the call blind
        print(f"[music]   ⚠️  view_api failed ({type(e).__name__}: {str(e)[:80]}) — calling blind")

    # ── Step 3: Make the prediction call ──────────────────────────────────────
    try:
        args = build_args(prompt, duration)
        print(f"[music]   📞 calling {api_name} with {len(args)} args (apis seen: {detected_apis[:3]})")
        result = client.predict(*args, api_name=api_name)
    except Exception as e:
        msg = str(e).lower()
        if any(s in msg for s in ("queue", "queued", "rate limit", "too many requests", "429")):
            return "queued", f"{type(e).__name__}: {str(e)[:200]}"
        if any(s in msg for s in ("405", "method not allowed", "400", "validation error", "argument", "type error", "missing", "expected")):
            return "config", f"{type(e).__name__}: {str(e)[:300]}"
        if any(s in msg for s in ("timeout", "timed out", "503", "502", "504", "connection")):
            return "down", f"{type(e).__name__}: {str(e)[:200]}"
        if "500" in msg or "internal" in msg:
            return "down", f"Space internal error: {str(e)[:200]}"
        # Unknown — assume our config is wrong since most Space errors are network/queue ones
        return "config", f"{type(e).__name__}: {str(e)[:300]}"

    # ── Step 4: Extract audio file from result ───────────────────────────────
    audio_src = _extract_audio_path(result)
    if not audio_src:
        return "empty", f"No audio file in result: {str(result)[:200]}"

    # ── Step 5: Convert WAV/FLAC → MP3 ───────────────────────────────────────
    import subprocess
    conv = subprocess.run(
        ["ffmpeg", "-y", "-i", audio_src, "-b:a", "192k", output_path],
        capture_output=True,
    )
    if conv.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10_000:
        return "ok", f"{os.path.getsize(output_path) // 1024}KB"
    return "empty", f"ffmpeg convert failed: {conv.stderr.decode(errors='replace')[-200:]}"


def _generate_musicgen(mood, output_path, duration=30):
    """Generate Whisprs-style instrumental music via Hugging Face SPACES (free).

    Uses gradio_client to call public HF Spaces running on free ZeroGPU.
    No per-call cost, no credit cap. Queue waits in busy hours.

    Tries each Space and CLASSIFIES its failure mode so we can debug:
      ✅ ok      → generated audio
      🌐 down    → Space offline / 5xx / timeout (their problem, retry later)
      ⚙️  config → our api_name / args don't match this Space (our bug)
      ⏳ queued  → Space busy / rate-limited (transient)
      ❓ empty   → call succeeded but result had no audio
    """
    prompt = _MUSICGEN_PROMPTS.get(mood, _MUSICGEN_PROMPTS["melancholy"])
    duration = min(max(duration, 5), 30)

    spaces = [
        # Stable Audio Open — Stability AI, music-focused, best quality
        ("multimodalart/stable-audio-open", "/predict",
         lambda p, d: [p, "", d, 0.8, 100, 50]),
        # Facebook MusicGen Continuation — official, stereo-medium model
        ("facebook/MusicGen-Continuation", "/predict_full",
         lambda p, d: [p, None, "facebook/musicgen-stereo-medium", d]),
        # Facebook MusicGen — original, most reliable
        ("facebook/MusicGen", "/predict_full",
         lambda p, d: [p, None, "facebook/musicgen-stereo-medium", d]),
    ]

    summary = []  # collect outcomes for final diagnostic line
    for space_id, api_name, build_args in spaces:
        print(f"[music] ▶ Trying HF Space: {space_id}")
        status, detail = _try_hf_space(space_id, api_name, build_args, prompt, duration, output_path)
        icons = {"ok": "✅", "down": "🌐", "config": "⚙️ ", "queued": "⏳", "empty": "❓"}
        icon = icons.get(status, "❌")
        print(f"[music]   {icon} {status.upper()}: {detail}")
        summary.append(f"{space_id}={status}")
        if status == "ok":
            return True

    # All Spaces failed — print a single-line summary that tells us EXACTLY
    # which failure modes hit, so the next debug session is obvious.
    print(f"[music] ❌ All HF Spaces failed → {' | '.join(summary)}")
    print(f"[music]    Interpretation:")
    print(f"[music]      • If most are 'down' → HF infra issue, will recover on its own")
    print(f"[music]      • If most are 'config' → our api_name/args are wrong, code fix needed")
    print(f"[music]      • If most are 'queued' → free ZeroGPU is saturated, try off-peak")
    print(f"[music]      • If most are 'empty' → Space returned unexpected result shape")
    return False

# ── Per-style music palettes ─────────────────────────────────────────────────
# Each style has: queries, BPM range, reject keywords

STYLE_PROFILES = {
    # BPM 60-75 = resting heart rate sync — body relaxes into music subconsciously
    # Piano + cello is the #1 formula for viral emotional content:
    # cello frequency range (65-1000Hz) matches the human voice in distress.
    "emotional": {
        "bpm": "bpm:[58 TO 76]",
        "queries": [
            "sad piano cello cinematic slow",
            "piano cello grief melancholic",
            "neoclassical piano cello emotional",
            "piano cello longing cinematic ambient",
            "melancholic piano strings cello slow",
            "bittersweet piano cello film score",
            "piano cello heartbreak slow ambient",
            "quiet sad piano cello night",
            "cinematic piano strings sadness slow",
            "piano minor cello ambient contemplative",
        ],
    },
    "nostalgic": {
        "bpm": "bpm:[62 TO 80]",
        "queries": [
            "nostalgic piano cello warm slow",
            "piano strings memory wistful slow",
            "childhood memory piano cello gentle",
            "nostalgic piano strings cinematic",
            "piano cello sentimental memory slow",
            "wistful piano strings longing slow",
            "gentle piano cello nostalgia warm",
            "piano violin nostalgia ambient slow",
        ],
    },
    "poetic": {
        "bpm": "bpm:[55 TO 72]",
        "queries": [
            "sparse piano cello dark contemplative",
            "cello solo melancholic slow ambient",
            "piano cello poetic dark cinematic",
            "neoclassical cello piano slow",
            "intimate piano cello minor slow",
            "haunting piano cello ambient",
            "piano cello introspective dark",
            "solo cello ambient melancholic slow",
        ],
    },
    "love": {
        "bpm": "bpm:[60 TO 75]",
        "queries": [
            "tender piano cello romantic slow",
            "piano cello intimate love cinematic",
            "romantic piano strings gentle slow",
            "soft piano cello love melancholic",
            "piano cello longing tender",
            "intimate piano strings romantic ambient",
            "bittersweet love piano cello slow",
            "piano cello heartache gentle",
        ],
    },
    "motivational": {
        "bpm": "bpm:[68 TO 88]",
        "queries": [
            "hopeful piano strings cinematic building",
            "piano cello hope gentle slow build",
            "cinematic piano strings understated hope",
            "peaceful piano strings ambient gentle",
            "piano cello resilience slow",
        ],
    },
    "wisdom": {
        "bpm": "bpm:[58 TO 74]",
        "queries": [
            "contemplative piano cello slow deep",
            "piano strings reflective cinematic slow",
            "neoclassical piano cello meditative",
            "philosophical piano strings ambient",
            "piano cello ancient contemplative slow",
            "solo piano minor contemplative",
            "deep cello piano ambient slow",
        ],
    },
}

# Fallback — used if style not recognized
STYLE_PROFILES["default"] = STYLE_PROFILES["emotional"]

# Words that indicate wrong vibe — always reject these
REJECT_KEYWORDS = [
    "happy", "cheerful", "upbeat", "comedy", "funny", "fun",
    "energetic", "dance", "party", "bright", "joyful",
    "children", "kids", "cartoon",
    # Electronic / wrong genre
    "disco", "techno", "house", "electronic", "edm", "beat", "drum",
    "trap", "hip hop", "hip-hop", "pop", "synth pop",
    # Ethnic / belly dance / world music
    "belly", "belly dance", "bellydance",
    "arabic", "arabian", "arab", "middle east", "middle eastern",
    "oriental", "oud", "darbuka", "doumbek", "tabla", "sitar",
    "tribal", "ethnic", "folk dance",
    "bollywood", "indian dance", "bhangra", "dhol",
    "wedding", "celebration", "festival", "carnival",
    "flute dance", "world music", "latin",
    "turkish", "greek dance", "balkan dance",
    # Wrong emotional register (meditation = different algorithm bucket)
    "meditation", "spa", "yoga", "binaural", "healing meditation",
    "sleep music", "study music", "focus music",
    "bouncy", "quirky", "playful", "whimsical",
    # Nature SFX
    "rain sounds", "thunder", "storm sounds", "nature sounds",
    "rainfall", "rainstorm", "thunderstorm",
    # TOO BIG / too cinematic — Whisprs style needs intimate solo piano, not full orchestra
    "orchestra", "orchestral", "choir", "chorus", "choral", "surround",
    "atmo", "epic", "trailer", "blockbuster", "dramatic",
    "full orchestra", "big band", "brass",
]

# Base Freesound filter — CC0 LICENSE ONLY (prevents Meta/YouTube muting)
# CC0 = Creative Commons Zero — public domain, no restrictions, safe for commercial use
# NOTE: No tag filters here — they're too restrictive and cause zero results.
# The search query itself describes the content (piano, ambient, etc.)
FREESOUND_BASE_FILTER = (
    'duration:[30 TO 180] '
    'license:"Creative Commons 0"'
)


def _is_wrong_vibe(track, style):
    """Return True if track doesn't fit the intended style."""
    name = track.get("name", "").lower()
    tags = " ".join(track.get("tags", [])).lower() if "tags" in track else ""
    combined = name + " " + tags

    # Always reject certain keywords
    if any(kw in combined for kw in REJECT_KEYWORDS):
        return True

    # For non-motivational styles, also reject uplifting/inspiring
    if style not in ("motivational",):
        if any(kw in combined for kw in ["uplifting", "inspiring", "motivational", "epic"]):
            return True

    return False


def _search_freesound(query, style):
    """Search Freesound for a track matching the style's BPM range.
    Tries BPM-filtered search first, falls back to no BPM filter."""
    if not FREESOUND_API_KEY:
        return None, None

    profile = STYLE_PROFILES.get(style, STYLE_PROFILES["default"])
    bpm_filter = FREESOUND_BASE_FILTER + " " + profile["bpm"]

    for filt, label in [(bpm_filter, "BPM-filtered"), (FREESOUND_BASE_FILTER, "no BPM filter")]:
        try:
            resp = requests.get(
                "https://freesound.org/apiv2/search/text/",
                params={
                    "query": query,
                    "filter": filt,
                    "fields": "id,name,duration,previews,tags",
                    "page_size": 15,
                    "sort": "score",
                    "token": FREESOUND_API_KEY,
                },
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

            good = [t for t in results if not _is_wrong_vibe(t, style)]
            if not good:
                print(f"[music] All {len(results)} results rejected by vibe filter — trying next query")
                continue

            pool = good[:8] if len(good) >= 8 else good
            track = random.choice(pool)
            preview_url = track.get("previews", {}).get("preview-hq-mp3")
            if preview_url:
                print(f"[music] Found ({label}): {track['name'][:60]} ({track['duration']:.0f}s)")
                return preview_url, track["name"]
        except Exception as e:
            print(f"[music] Freesound search failed: {e}")

    return None, None


def _download_preview(url, output_path):
    """Download a Freesound preview MP3.
    Tries token-in-URL first (more reliable for CDN), falls back to header."""
    for attempt_url, method in [
        (f"{url}?token={FREESOUND_API_KEY}" if "?" not in url else url, "token-in-URL"),
        (url, "auth-header"),
    ]:
        try:
            resp = requests.get(
                attempt_url,
                headers={"Authorization": f"Token {FREESOUND_API_KEY}"},
                timeout=30,
            )
            if resp.status_code == 200 and len(resp.content) >= 5000:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                print(f"[music] Downloaded {len(resp.content)//1024}KB via {method}")
                return True
            print(f"[music] Download attempt ({method}): status={resp.status_code} size={len(resp.content)}")
        except Exception as e:
            print(f"[music] Download failed ({method}): {e}")
    return False


PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")

# Script-level mood detection: read the actual text to pick the right music feel.
# This goes deeper than just "style" — a love script can be heartbreak or warm romance.
_MOOD_KEYWORDS = {
    "heartbreak": [
        "heartbreak", "broke", "broken", "shattered", "hurt", "pain",
        "lost you", "goodbye", "leave", "left", "tears", "cry", "cried",
        "walked away", "never came back", "ending", "over",
    ],
    "longing": [
        "miss", "missing", "remember", "used to", "once", "long ago",
        "distance", "far away", "gone", "wish you were", "still think",
        "somewhere", "fading", "drift",
    ],
    "love": [
        "love", "loved", "loving", "hold", "arms", "safe", "warm",
        "together", "close", "home in you", "gentle", "stays",
    ],
    "nostalgia": [
        "childhood", "young", "remember when", "back then", "used to",
        "grandmother", "grandfather", "school", "old house", "simpler time",
        "growing up", "those days", "years ago",
    ],
    "melancholy": [
        "alone", "lonely", "empty", "silence", "dark", "heavy", "weight",
        "no one", "invisible", "quiet pain", "numb",
    ],
    "hope": [
        "hope", "someday", "will be", "better", "rise", "strength",
        "begin again", "worth it", "keep going", "brighter", "survive",
    ],
}

# Safe mood map — ALL moods are remapped to dark/sad equivalents for background music.
# "hope" → "inspiring" on Pixabay was causing upbeat/dance tracks to appear.
# The Quietlyy brand is ALWAYS contemplative/melancholic — even hopeful scripts
# use sad ambient music underneath. This is non-negotiable.
_SAFE_MOOD_MAP = {
    "heartbreak": "heartbreak",
    "longing":    "longing",
    "melancholy": "melancholy",
    "nostalgia":  "longing",    # nostalgia → tender longing (dark)
    "love":       "longing",    # love → longing (never cheerful)
    "hope":       "melancholy", # hope → melancholy (NEVER inspiring/upbeat)
}

# Pixabay mood/genre — ALL mapped to sad/dark only
_MOOD_TO_PIXABAY = {
    "heartbreak": {"mood": "sad",  "genre": "cinematic"},
    "longing":    {"mood": "sad",  "genre": "ambient"},
    "melancholy": {"mood": "dark", "genre": "ambient"},
}

# Freesound queries per safe mood — strictly sad/melancholic only
_MOOD_TO_FREESOUND = {
    "heartbreak": [
        "heartbreak piano slow cinematic", "sad piano longing ambient",
        "piano grief melancholic slow", "bittersweet piano strings",
    ],
    "longing": [
        "longing piano ambient slow", "wistful piano missing someone",
        "distant piano melancholic", "nostalgic piano strings slow",
    ],
    "melancholy": [
        "melancholic piano ambient cinematic", "sad piano minor slow",
        "dark ambient piano introspective", "lonely piano slow ambient",
    ],
}


def detect_script_mood(script_text):
    """Analyse script text and return the dominant emotional mood.
    Returns one of: heartbreak / longing / love / nostalgia / melancholy / hope."""
    text = script_text.lower()
    scores = {mood: sum(1 for kw in kws if kw in text)
              for mood, kws in _MOOD_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "melancholy"  # default when nothing matches
    print(f"[music] Script mood detected: {best} (scores: {scores})")
    return best


def _search_pixabay_music(mood):
    """Search Pixabay Music API for a track matching the script's emotional mood.
    Returns (download_url, track_name) or (None, None)."""
    if not PIXABAY_API_KEY:
        return None, None
    profile = _MOOD_TO_PIXABAY.get(mood, {"mood": "sad", "genre": "cinematic"})
    try:
        for params in [
            {"key": PIXABAY_API_KEY, "mood": profile["mood"], "genre": profile["genre"], "per_page": 50},
            {"key": PIXABAY_API_KEY, "mood": profile["mood"], "per_page": 50},
            {"key": PIXABAY_API_KEY, "per_page": 50},
        ]:
            resp = requests.get("https://pixabay.com/api/music/", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", [])
            if not hits:
                continue
            # Log first hit's keys once so we can see the real field names
            print(f"[music] Pixabay hit fields: {list(hits[0].keys())}")
            track = random.choice(hits[:20])
            # Try every possible audio URL field — API field name varies by version
            url = (track.get("download_url")   # most likely — matches Pixabay convention
                   or track.get("audio_download")
                   or track.get("audio")
                   or track.get("previewURL")
                   or track.get("preview_url"))
            name = track.get("title") or track.get("name") or "Pixabay track"
            if url:
                print(f"[music] Pixabay found ({mood}): {name[:60]}")
                return url, name
            print(f"[music] Pixabay hit had no playable URL. Keys: {list(track.keys())}")
    except Exception as e:
        print(f"[music] Pixabay music search failed: {e}")
    return None, None


def _download_pixabay(url, output_path):
    """Download a Pixabay music track."""
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200 and len(resp.content) > 10_000:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return True
    except Exception as e:
        print(f"[music] Pixabay download failed: {e}")
    return False


# ── CC0/CC-BY fallback tracks ─────────────────────────────────────────────────
# Used when Pixabay is unavailable. Kevin MacLeod (incompetech.com) CC-BY 3.0.
# Piano-only and more generic-sounding than Pixabay song-style tracks.
# Kept as reliable fallback — they always download and are always mood-safe.
#
# mood → list of (url, label) — tried in shuffled order until one downloads
# CC0 Kevin MacLeod tracks — every track here is VERIFIED genuinely sad/melancholic.
# "Wish Background" (whimsical/magical) REMOVED — was being mocked by subscribers.
# Each mood pool has 5+ tracks so even with recently-used filtering we don't run dry.
_INCOMPETECH_BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree"
_CC0_TRACKS = {
    "heartbreak": [
        (f"{_INCOMPETECH_BASE}/Heartbreaking.mp3",       "Kevin MacLeod - Heartbreaking"),
        (f"{_INCOMPETECH_BASE}/Sad%20Trio.mp3",          "Kevin MacLeod - Sad Trio"),
        (f"{_INCOMPETECH_BASE}/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        (f"{_INCOMPETECH_BASE}/Dreamy%20Flashback.mp3",  "Kevin MacLeod - Dreamy Flashback"),
        (f"{_INCOMPETECH_BASE}/Aftermath.mp3",           "Kevin MacLeod - Aftermath"),
        (f"{_INCOMPETECH_BASE}/Lightless%20Dawn.mp3",    "Kevin MacLeod - Lightless Dawn"),
        (f"{_INCOMPETECH_BASE}/Anguish.mp3",             "Kevin MacLeod - Anguish"),
    ],
    "longing": [
        (f"{_INCOMPETECH_BASE}/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        (f"{_INCOMPETECH_BASE}/Piano%20Moment.mp3",      "Kevin MacLeod - Piano Moment"),
        (f"{_INCOMPETECH_BASE}/Dreamy%20Flashback.mp3",  "Kevin MacLeod - Dreamy Flashback"),
        (f"{_INCOMPETECH_BASE}/Heartbreaking.mp3",       "Kevin MacLeod - Heartbreaking"),
        (f"{_INCOMPETECH_BASE}/Lightless%20Dawn.mp3",    "Kevin MacLeod - Lightless Dawn"),
        (f"{_INCOMPETECH_BASE}/Long%20Note%20Two.mp3",   "Kevin MacLeod - Long Note Two"),
    ],
    "love": [
        (f"{_INCOMPETECH_BASE}/Touching%20Moments.mp3",  "Kevin MacLeod - Touching Moments"),
        (f"{_INCOMPETECH_BASE}/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        (f"{_INCOMPETECH_BASE}/Dreamy%20Flashback.mp3",  "Kevin MacLeod - Dreamy Flashback"),
        (f"{_INCOMPETECH_BASE}/Piano%20Moment.mp3",      "Kevin MacLeod - Piano Moment"),
        (f"{_INCOMPETECH_BASE}/Bittersweet.mp3",         "Kevin MacLeod - Bittersweet"),
        (f"{_INCOMPETECH_BASE}/Healing.mp3",             "Kevin MacLeod - Healing"),
    ],
    "nostalgia": [
        (f"{_INCOMPETECH_BASE}/Dreamy%20Flashback.mp3",  "Kevin MacLeod - Dreamy Flashback"),
        (f"{_INCOMPETECH_BASE}/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        (f"{_INCOMPETECH_BASE}/Piano%20Moment.mp3",      "Kevin MacLeod - Piano Moment"),
        (f"{_INCOMPETECH_BASE}/Bittersweet.mp3",         "Kevin MacLeod - Bittersweet"),
        (f"{_INCOMPETECH_BASE}/Long%20Note%20Two.mp3",   "Kevin MacLeod - Long Note Two"),
        (f"{_INCOMPETECH_BASE}/Touching%20Moments.mp3",  "Kevin MacLeod - Touching Moments"),
    ],
    "melancholy": [
        (f"{_INCOMPETECH_BASE}/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        (f"{_INCOMPETECH_BASE}/Heartbreaking.mp3",       "Kevin MacLeod - Heartbreaking"),
        (f"{_INCOMPETECH_BASE}/Sad%20Trio.mp3",          "Kevin MacLeod - Sad Trio"),
        (f"{_INCOMPETECH_BASE}/Piano%20Moment.mp3",      "Kevin MacLeod - Piano Moment"),
        (f"{_INCOMPETECH_BASE}/Lightless%20Dawn.mp3",    "Kevin MacLeod - Lightless Dawn"),
        (f"{_INCOMPETECH_BASE}/Aftermath.mp3",           "Kevin MacLeod - Aftermath"),
        (f"{_INCOMPETECH_BASE}/Long%20Note%20Two.mp3",   "Kevin MacLeod - Long Note Two"),
    ],
    "hope": [
        (f"{_INCOMPETECH_BASE}/A%20Quiet%20Thought.mp3", "Kevin MacLeod - A Quiet Thought"),
        (f"{_INCOMPETECH_BASE}/Healing.mp3",             "Kevin MacLeod - Healing"),
        (f"{_INCOMPETECH_BASE}/Piano%20Moment.mp3",      "Kevin MacLeod - Piano Moment"),
        (f"{_INCOMPETECH_BASE}/Dreamy%20Flashback.mp3",  "Kevin MacLeod - Dreamy Flashback"),
        (f"{_INCOMPETECH_BASE}/Touching%20Moments.mp3",  "Kevin MacLeod - Touching Moments"),
    ],
}

# Recently-used CC0 tracks — persisted to assets/used_topics.json. We avoid the
# last N picks to prevent the same track appearing across multiple consecutive
# videos (the bug that made subscribers mock the music repetition).
_RECENT_CC0_LIMIT = 4  # remember last 4 picks; pool sizes are 5-7 so still has room
_USED_STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "used_topics.json")


def _load_state():
    """Load the persisted state dict (recently-used tracks etc.)."""
    if os.path.exists(_USED_STATE_PATH):
        try:
            with open(_USED_STATE_PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_state(state):
    """Persist the state dict."""
    os.makedirs(os.path.dirname(_USED_STATE_PATH), exist_ok=True)
    with open(_USED_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _load_recent_cc0():
    return _load_state().get("recent_cc0_tracks", [])


def _is_lyria_in_cooldown():
    """Return True if Lyria 429'd recently and we should skip the call."""
    from datetime import datetime, timedelta, timezone
    last_429 = _load_state().get("lyria_last_429")
    if not last_429:
        return False
    try:
        last = datetime.fromisoformat(last_429)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last) < timedelta(hours=LYRIA_COOLDOWN_HOURS)
    except Exception:
        return False


def _record_lyria_429():
    """Mark Lyria as 429'd now — pipeline will skip Lyria for LYRIA_COOLDOWN_HOURS."""
    from datetime import datetime, timezone
    state = _load_state()
    state["lyria_last_429"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)


def _save_recent_cc0(track_name):
    """Append track_name to the recently-used CC0 list, capped at _RECENT_CC0_LIMIT."""
    state = _load_state()
    recent = state.get("recent_cc0_tracks", [])
    recent.append(track_name)
    state["recent_cc0_tracks"] = recent[-_RECENT_CC0_LIMIT:]
    _save_state(state)


# ── Music gallery — persistent library of ElevenLabs-generated tracks ────────
# Every successful ElevenLabs generation is saved to assets/music_gallery/<mood>/
# so future runs can reuse them. This both saves ElevenLabs quota and provides
# an offline fallback if their API fails.
#
# Repetition rule: don't reuse any of the last GALLERY_RECENT_LIMIT (=20) tracks.
# Once 20 different tracks have been used, oldest entries are eligible again.


def _gallery_dir_for(mood):
    """Ensure mood-specific gallery dir exists and return its path."""
    path = os.path.join(MUSIC_GALLERY_DIR, mood)
    os.makedirs(path, exist_ok=True)
    return path


def _save_to_music_gallery(mood, mp3_path, prompt_used=""):
    """Copy a freshly generated MP3 into the persistent music gallery.

    Filename format: YYYY-MM-DD_HHMMSS_<6charhash>.mp3
    Returns the gallery file path (or None on failure).
    """
    import shutil
    import hashlib
    from datetime import datetime, timezone

    try:
        gallery_dir = _gallery_dir_for(mood)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        h = hashlib.md5((prompt_used + str(os.path.getsize(mp3_path))).encode()).hexdigest()[:6]
        dest_filename = f"{ts}_{h}.mp3"
        dest_path = os.path.join(gallery_dir, dest_filename)
        shutil.copy(mp3_path, dest_path)
        # Track count for visibility
        total = len([f for f in os.listdir(gallery_dir) if f.endswith(".mp3")])
        print(f"[music] 💾 Saved to gallery: {mood}/{dest_filename} (mood total: {total})")
        return dest_path
    except Exception as e:
        print(f"[music] Gallery save failed: {e}")
        return None


def _load_recent_gallery():
    """List of the last GALLERY_RECENT_LIMIT gallery filenames used."""
    return _load_state().get("recent_gallery_tracks", [])


def _save_recent_gallery(filename):
    """Append a gallery filename to the recently-used list."""
    state = _load_state()
    recent = state.get("recent_gallery_tracks", [])
    recent.append(filename)
    state["recent_gallery_tracks"] = recent[-GALLERY_RECENT_LIMIT:]
    _save_state(state)


def _pick_from_music_gallery(mood, output_path, min_pool_size=3):
    """Reuse a track from the music gallery (skipping last 20 used).

    Returns True if a usable track was found and copied. Returns False if:
      - Gallery dir doesn't exist or is empty
      - Gallery has FEWER than min_pool_size tracks AND every track is in
        the recent-used list (prevents the 'same track reused every video'
        bug seen when gallery is sparse — better to fall through to CC0
        which rotates between 6+ different sad tracks per mood)
      - Gallery has >= min_pool_size tracks but anti-repetition wrap-around
        is needed (relaxed filter kicks in)

    The min_pool_size guard is critical: with only 1-2 tracks per mood,
    subscribers hear the same Sonauto track in 2+ consecutive videos which
    they perceive as repetition. Better to fall through to varied CC0 than
    repeat the same gallery track.
    """
    import shutil

    gallery_dir = os.path.join(MUSIC_GALLERY_DIR, mood)
    if not os.path.isdir(gallery_dir):
        return False
    all_tracks = sorted([f for f in os.listdir(gallery_dir) if f.endswith(".mp3")])
    if not all_tracks:
        return False

    recent_list = _load_recent_gallery()
    recent_set = set(recent_list)

    # Step 1: try fresh tracks (never used or used >20 ago)
    fresh = [t for t in all_tracks if t not in recent_set]

    # Step 2: ANTI-SPARSE-REPETITION GUARD
    # If gallery is too small AND all tracks are in recent-used → fall through.
    # Better to use CC0 rotation than replay same Sonauto track 2nd time in a row.
    if not fresh and len(all_tracks) < min_pool_size:
        print(f"[music] 🚫 Gallery too sparse ({len(all_tracks)} tracks for '{mood}', all recently used) — falling through to CC0 for variety")
        return False

    # Step 3: Gallery is rich enough (>= min_pool_size) but wrap-around needed.
    # Allow oldest 1/3 of recent list back in (least-recently used reuse).
    if not fresh:
        if len(recent_list) > 0:
            cutoff = max(1, len(recent_list) // 3)
            allowed_back = set(recent_list[cutoff:])  # drop oldest 1/3
            fresh = [t for t in all_tracks if t in allowed_back or t not in recent_set]
        if not fresh:
            fresh = all_tracks  # full reset — every track eligible
        print(f"[music] 🔄 Gallery wrap-around (>{GALLERY_RECENT_LIMIT} tracks used) — relaxing filter")

    picked = random.choice(fresh)
    try:
        shutil.copy(os.path.join(gallery_dir, picked), output_path)
        _save_recent_gallery(picked)
        print(f"[music] 🎵 Reused from gallery: {mood}/{picked} (pool: {len(all_tracks)}, fresh: {len(fresh)})")
        return True
    except Exception as e:
        print(f"[music] Gallery copy failed: {e}")
        return False


# ── Pixabay query-based search — mood-targeted text queries for SONG-style instrumentals ──
# These queries are tuned to return full-production tracks (piano + strings + bass +
# soft drums) rather than generic ambient piano. The terms "instrumental", "cinematic",
# and "song" push Pixabay's algorithm toward Whisprs-style tracks: real song
# arrangements with vocals removed, not stripped-down ambient piano.
_MOOD_TO_PIXABAY_QUERIES = {
    "heartbreak": [
        "emotional heartbreak cinematic instrumental",
        "sad piano strings song instrumental",
        "melancholic emotional song background",
        "heartbreak emotional cinematic music",
        "sad emotional ballad instrumental",
    ],
    "longing": [
        "longing emotional cinematic instrumental",
        "nostalgic piano strings song",
        "wistful emotional instrumental music",
        "missing someone cinematic instrumental",
        "longing romantic emotional background",
    ],
    "melancholy": [
        "melancholy cinematic emotional instrumental",
        "sad emotional song background music",
        "dark emotional piano cinematic",
        "melancholic ambient cinematic instrumental",
        "sad piano strings emotional song",
    ],
    "love": [
        "romantic emotional instrumental cinematic",
        "tender love song instrumental",
        "emotional love ballad instrumental",
        "romantic piano strings cinematic",
        "love emotional song background music",
    ],
    "hope": [
        "emotional cinematic uplifting instrumental",
        "hopeful cinematic emotional music",
        "inspiring emotional piano cinematic",
        "emotional cinematic song instrumental",
        "hopeful piano strings cinematic",
    ],
}


def _search_pixabay_by_query(mood, output_path):
    """Search Pixabay Music by mood-targeted text query for song-like instrumentals.

    This bypasses Pixabay's mood/genre params (unreliable) and uses direct text
    search. Queries include 'instrumental', 'cinematic', 'song' to push toward
    full-production tracks rather than ambient piano. Returns True if a track
    was downloaded successfully.
    """
    if not PIXABAY_API_KEY:
        return False

    queries = list(_MOOD_TO_PIXABAY_QUERIES.get(mood, _MOOD_TO_PIXABAY_QUERIES["melancholy"]))
    random.shuffle(queries)

    for q in queries[:4]:
        try:
            resp = requests.get(
                "https://pixabay.com/api/music/",
                params={"key": PIXABAY_API_KEY, "q": q, "per_page": 50},
                timeout=15,
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            if not hits:
                continue

            # Filter by combined name + tags against REJECT_KEYWORDS
            def _good(t):
                tags_raw = t.get("tags", "")
                tags_str = " ".join(tags_raw.split(",")) if isinstance(tags_raw, str) else " ".join(tags_raw)
                combined = (
                    (t.get("title", "") or "").lower() + " " +
                    (t.get("name", "") or "").lower() + " " +
                    tags_str.lower()
                )
                return not any(kw in combined for kw in REJECT_KEYWORDS)

            good = [h for h in hits if _good(h)]
            if not good:
                continue

            track = random.choice(good[:15])
            url = (
                track.get("audio")
                or track.get("download_url")
                or track.get("previewURL")
                or track.get("audio_download")
            )
            name = track.get("title") or track.get("name") or "Pixabay track"
            if url and _download_pixabay(url, output_path):
                print(f"[music] Pixabay query '{q}' → {name[:60]}")
                return True
        except Exception as e:
            print(f"[music] Pixabay query '{q}' failed: {e}")
    return False


def _download_cc0_track(mood, output_path):
    """Download a mood-matched CC0 piano track. No API key needed.

    Anti-repetition: filters out tracks used in the last N videos, then shuffles
    what remains. After successful download, persists the choice so the next
    video avoids it. Prevents the 'same track every video' problem that made
    subscribers mock the channel.
    """
    pool = list(_CC0_TRACKS.get(mood, _CC0_TRACKS["melancholy"]))
    recent = set(_load_recent_cc0())

    # Filter out recently-used tracks. If filter would empty the pool, drop the
    # oldest half of the 'recent' constraint so we still have something to try.
    fresh = [t for t in pool if t[1] not in recent]
    if not fresh:
        # All tracks in this mood pool have been used recently — keep only the
        # 2 most-recent in the blocklist, allowing older ones back in
        recent_oldest_kept = list(_load_recent_cc0())[-2:]
        fresh = [t for t in pool if t[1] not in set(recent_oldest_kept)]
        print(f"[music]   Pool exhausted by recent-used filter — softened to last 2 only")
    random.shuffle(fresh)

    if recent:
        print(f"[music]   Skipping recently-used: {sorted(recent)}")

    for url, name in fresh:
        try:
            print(f"[music] Trying CC0 track: {name}")
            resp = requests.get(url, timeout=45)
            if resp.status_code == 200 and len(resp.content) > 50_000:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                _save_recent_cc0(name)
                print(f"[music] CC0 track downloaded: {name}")
                return True
        except Exception as e:
            print(f"[music] CC0 download failed ({name}): {e}")
    return False


def _get_bundled_music():
    """Pick a random track from assets/music/ for variety."""
    music_dir = os.path.join(ASSETS_DIR, "music")
    if not os.path.exists(music_dir):
        return None
    tracks = sorted([
        os.path.join(music_dir, f)
        for f in os.listdir(music_dir)
        if f.lower().endswith((".mp3", ".wav", ".ogg")) and not f.startswith(".")
    ])
    if not tracks:
        return None
    chosen = random.choice(tracks)
    print(f"[music] Bundled fallback: {os.path.basename(chosen)} ({len(tracks)} track(s) available)")
    return chosen


def generate_music(topic, script_text="", style="emotional"):
    """Fetch background music matched to the Quietlyy brand voice.

    ALWAYS uses sad/melancholic/contemplative music regardless of script content.
    "hope" and "love" moods are remapped to dark equivalents via _SAFE_MOOD_MAP
    to prevent upbeat/dance/inspiring tracks from slipping through.

    Fallback order:
      1. Google Lyria 3 (Gemini API)  ← FREE, uses existing GEMINI_API_KEY
      2. Sonauto Melodia v3           ← 1500 free credits on signup
      3. ElevenLabs Music             ← currently 401 (plan limit)
      4. Gallery reuse                ← saved AI-gen tracks from above
      5. HF Spaces                    ← currently 401 (HF Pro required)
      6. CC0 Kevin MacLeod            ← rotating sad track pool, no API
      7. Freesound CC0                ← if FREESOUND_API_KEY is set
      8. Bundled assets/music/*.mp3   — last resort

    Gallery accumulates AI-generated tracks over time at
    assets/music_gallery/<mood>/. Every Lyria/ElevenLabs success saves a
    copy. After ~20 unique tracks per mood, the pipeline can rotate
    purely from the gallery (saves Lyria quota). Repetition: never replay
    the last GALLERY_RECENT_LIMIT (=20) tracks until wrap-around.

    Returns: (music_path, source) where source is one of:
      "lyria_gemini" / "elevenlabs_music" / "gallery_reuse" /
      "musicgen_hf_space" / "cc0_library" / "freesound_cc0" /
      "bundled" / None
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    music_path = os.path.join(OUTPUT_DIR, "background_music.mp3")

    # Detect raw mood then HARD-LOCK to a safe dark equivalent.
    # "hope" → inspiring was the cause of upbeat/belly-dance tracks appearing.
    raw_mood = detect_script_mood(script_text) if script_text else "melancholy"
    script_mood = _SAFE_MOOD_MAP.get(raw_mood, "melancholy")

    style_map = {"emotional": "emotional", "nostalgic": "nostalgic",
                 "poetic": "poetic", "love": "love", "motivational": "motivational"}
    music_style = style_map.get(style, "emotional")
    bpm_profile = STYLE_PROFILES.get(music_style, STYLE_PROFILES["emotional"])

    print(f"[music] Style: {style} | Raw mood: {raw_mood} → Safe mood: {script_mood}")

    prompt_used = _MUSICGEN_PROMPTS.get(script_mood, "")

    # ── Primary: Google Lyria 3 via Gemini API — FREE, uses existing key ──
    # Launched 2026-04-18 as part of Google Flow Music. Same DeepMind model
    # powering the Flow studio. Uses our existing GEMINI_API_KEY (same key
    # as script generation). Auto-cooldown (12h) after a 429.
    if _generate_lyria_music(script_mood, music_path, duration_sec=30):
        _save_to_music_gallery(script_mood, music_path, prompt_used=prompt_used)
        return music_path, "lyria_gemini"

    # ── Secondary: Sonauto Melodia v3 — 1500 free credits, no CC required ──
    # When Lyria hits daily quota, Sonauto picks up. ~30-90s generation time
    # (async polling). Sign up at sonauto.ai/developers to get SONAUTO_API_KEY.
    if _generate_sonauto_music(script_mood, music_path, duration_sec=30):
        _save_to_music_gallery(script_mood, music_path, prompt_used=prompt_used)
        return music_path, "sonauto_melodia"

    # ── Tertiary: ElevenLabs Music ──
    # Currently 401 (plan doesn't include Music API scope). Kept in case
    # plan is upgraded or Music scope is enabled on the API key.
    if _generate_elevenlabs_music(script_mood, music_path, duration_sec=30):
        _save_to_music_gallery(script_mood, music_path, prompt_used=prompt_used)
        return music_path, "elevenlabs_music"

    # ── Quaternary: CC0 Kevin MacLeod — GUARANTEED soft sad piano, on-mood ──
    # MOVED ABOVE gallery reuse (2026-06): the gallery had polluted Sonauto
    # tracks (some upbeat/dance, wrong mood) that surfaced as background music
    # totally opposite to the emotional script. CC0 Kevin MacLeod tracks are a
    # hand-curated, verified-sad piano set — when fresh AI gen is unavailable
    # (Sonauto out of credits, Lyria paid, ElevenLabs 401), this guarantees
    # on-brand melancholic piano instead of a random gallery track.
    if _download_cc0_track(script_mood, music_path):
        print(f"[music] CC0 library track used (Kevin MacLeod, mood: {script_mood})")
        return music_path, "cc0_library"
    print("[music] CC0 download failed — trying music gallery")

    # ── Quinary: Reuse from music gallery (only if CC0 download fails) ──
    # Last-resort reuse of past AI tracks. Demoted below CC0 because gallery
    # mood can't be verified (see above).
    if _pick_from_music_gallery(script_mood, music_path):
        return music_path, "gallery_reuse"

    # ── HF Spaces — currently 401 (ZeroGPU requires HF Pro) ──
    if _generate_musicgen(script_mood, music_path, duration=30):
        print(f"[music] HF Space generated unique AI track")
        return music_path, "musicgen_hf_space"
    print("[music] All AI + CC0 + gallery failed — trying Freesound")

    # ── Tertiary: Freesound — mood-locked CC0 queries ──
    if FREESOUND_API_KEY:
        mood_queries = list(_MOOD_TO_FREESOUND.get(script_mood, _MOOD_TO_FREESOUND["melancholy"]))
        style_queries = list(bpm_profile["queries"])
        random.shuffle(mood_queries)
        random.shuffle(style_queries)

        for query in (mood_queries + style_queries)[:8]:
            print(f"[music] Searching Freesound: {query}")
            preview_url, track_name = _search_freesound(query, music_style)
            if preview_url and _download_preview(preview_url, music_path):
                print(f"[music] Freesound track: {track_name}")
                return music_path, "freesound_cc0"

        print("[music] All Freesound queries failed — trying bundled")
    else:
        print("[music] No FREESOUND_API_KEY — trying bundled")

    # ── Pixabay Music API: DEPRECATED by Pixabay (returns 404). Removed from chain. ──

    bundled = _get_bundled_music()
    if bundled:
        print(f"[music] Using bundled: {os.path.basename(bundled)}")
        return bundled, "bundled"

    print("[music] WARNING: No background music available")
    return None, None


if __name__ == "__main__":
    for s in ["emotional", "nostalgic", "poetic", "love", "motivational"]:
        print(f"\n=== Testing style: {s} ===")
        path, source = generate_music("test", style=s)
        print(f"Music: {path} (source: {source})")
