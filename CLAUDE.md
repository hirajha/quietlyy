# Quietlyy — Project Memory

## ✅ CURRENT APPROVED VOICE BASELINE — "approved-voice-v2"

**Status:** Approved by Hira on 2026-06-07 — *"looks good."* This is the
CURRENT live version.

- **Git tag:** `approved-voice-v2`
- **Commit:** `56ced96` — "Edge-TTS pauses: read like a book — flow through phrases, pause at thoughts"
- **Produced by:** GitHub Actions run `27092020527` (YT short R-9Ip431Cg4)
- **What it sounds like:** Free Edge-TTS voice (`en-US-AvaNeural`, rate `-10%`),
  synthesized by poem-line structure. Enjambed lines (no end punctuation) are
  MERGED into one continuous phrase — never pauses mid-phrase. Pauses land only
  at thought-ends:
  - sentence end (`. ! ?`) → **1.3s**
  - ellipsis (`...`) → **1.5s** (dramatic)
  - clause (`, ; : —`) → **0.45s**

### How to switch to a known-good version (if a newer change is worse)
Restore just the audio script from a tag, then commit + push:
```bash
cd /Users/home/Desktop/quietlyy
git checkout approved-voice-v2 -- scripts/generate_audio.py   # or approved-voice-v1
git commit -m "Revert voice to approved-voice-v2 (Hira-approved pacing)"
git push
```
Inspect a difference first: `git diff approved-voice-v2 HEAD -- scripts/generate_audio.py`

### Previous baseline (also good, kept as fallback)
- **`approved-voice-v1`** — commit `0819346`, run `27091576908`. Earlier paced
  version: splits on director `<break>` tags; pauses 1.8s sentence / 0.6s clause
  / 0.35s phrase breath. Superseded by v2 but still a valid revert target.

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
