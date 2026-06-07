# Quietlyy — Project Memory

## ✅ APPROVED VOICE BASELINE — "approved-voice-v1"

**Status:** Approved by Hira on 2026-06-07 — *"today's 2nd video was actually
all good including the pause."*

- **Git tag:** `approved-voice-v1`
- **Commit:** `0819346` — "Edge-TTS: pause between thoughts instead of rushing one long paragraph"
- **Produced by:** GitHub Actions run `27091576908`
- **What it sounds like:** Free Edge-TTS voice (`en-US-AvaNeural`, rate `-10%`),
  script synthesized segment-by-segment with REAL silence spliced between
  segments. Pause lengths:
  - sentence end (`. ! ?`) → **1.8s**
  - clause (`, ; : —`) → **0.6s**
  - enjambed / phrase boundary → **0.35s** breath
  (Segmentation in this version splits on the director's `<break>` tags.)

### How to switch BACK to the approved version (if a newer change is worse)
Restore just the audio script from the approved tag, then commit + push:
```bash
cd /Users/home/Desktop/quietlyy
git checkout approved-voice-v1 -- scripts/generate_audio.py
git commit -m "Revert voice to approved-voice-v1 (Hira-approved pacing)"
git push
```
To inspect the difference first:
```bash
git diff approved-voice-v1 HEAD -- scripts/generate_audio.py
```

### Versions AFTER the baseline (under evaluation)
- `56ced96` "Edge-TTS pauses: read like a book" (run `27092020527`) — line-based
  segmentation: merges enjambed lines into one continuous phrase (no mid-phrase
  pause), pauses 1.3s sentence / 1.5s ellipsis / 0.45s clause. **Pending Hira's
  verdict** — if good, keep; else revert to `approved-voice-v1` above.

---

## Voice tunables (env vars / GitHub repo secrets — no code change needed)
- `EDGE_PAUSE_SENTENCE`, `EDGE_PAUSE_CLAUSE`, `EDGE_PAUSE_ELLIPSIS` — pause seconds
- `EDGE_TTS_RATE` (default `-10%`; more negative = slower)
- `EDGE_TTS_VOICE` (default `en-US-AvaNeural`)
- `VOICE_PROVIDER=edge` — force the free Edge voice, skip ElevenLabs entirely

## Pipeline resilience (all free, self-healing)
- **Voice:** ElevenLabs v3 when key present → else free Edge-TTS fallback.
- **Music:** rotates the free `assets/music_gallery/` library (source label
  `gallery_library`, whitelisted in copyright_check).
- **Images:** Cloudflare FLUX (free, 10k neurons/day) + gallery reuse — only
  `FRESH_PER_VIDEO=2` generated fresh per video once the gallery has ≥12 images
  (`scripts/build_image_library.py` can pre-stock it).
- **Quality gate:** audio checked by DURATION (≥6s), not byte size (Edge-TTS is
  lower-bitrate than ElevenLabs).
