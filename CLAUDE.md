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

## Script quality — "emotional realness" (2026-06-07)
Hira's bar: scripts must feel like they describe the viewer's EXACT life (à la
Whisprs), not generic sad-poetry.
- `generate_script.py` `_REALNESS_BLOCK`: prompts demand ONE concrete lived
  anchor (saved contact, empty side of bed, 2am phone screen), ban abstract
  nature-metaphor. Closing line must end with a "." mark — NEVER the word
  "Period"/"Done" (that bug produced "in my phone. Period").
- `review_script.py`: `check_structure()` hard-rejects artifact/dangling endings;
  AI scorer weights REALNESS most and enforces realness>=6 (wisdom exempt).
- `clean_script_bank.py`: one-time heuristic clean (no AI). Bank trimmed
  1075 → 768 concrete-only scripts, next_index=0. Original at
  `assets/script_bank.backup.json`.
- Bank builder reuses build_prompt + review_script → rebuilds inherit all of it.
- ARCHITECTURE (2026-06-07): generation is now LIVE-FIRST — `generate_best_script`
  generates fresh candidates on-demand (best-of-3) every post so the current
  realness logic always applies; the bank is FALLBACK only (providers down).
  Dedup is independent (used_scripts.json) → use-once-then-forget. Confirmed live:
  YT short sAUdYrVsU0o ("their favorite mug still has your fingerprints").
- FIXED (2026-06-07): engagement predictor wiring — generate_best_script read
  scores from a nested pred["scores"][...] that never existed (predict_engagement
  returns them top-level), so composites were always 0.0. Now reads top-level
  with an "overall" fallback. Best-of-3 genuinely ranks by shareability
  (save+share+hook+rewatch). Confirmed live: candidates scored 6.8 / 7.4 / 7.4,
  best (7.4) selected — YT short tRyiE_k8FwU.
- NOTE: kept 768 are pre-existing concrete scripts (better, visible immediately).
  Scripts written with the NEW realness prompt only appear via a bank rebuild
  (build-script-bank workflow) or live gen when the bank empties.

## ⚠️ LESSON (2026-06-07): realness ≠ naming objects
First realness directive over-pushed "name a concrete object" → model produced
COLD JUNK: "their old keyboard still has your login", "75% of people keep old
accounts alive". Hira (rightly) furious. Real Whisprs quality = EMOTIONAL TRUTH
carried by ONE warm human image (table set for two, a coat on the hook, reaching
for a hand). Corrected `_REALNESS_BLOCK` + gate now BAN: statistics/numbers/data,
cold tech objects (keyboard/login/password/account), and run-on scripts (too few
lines ending in punctuation — which also rushed the voice).
- Voice robustness: `_segment_for_edge` caps enjambed runs at EDGE_MAX_SEG_WORDS
  (9) → always inserts a breath, so a badly-punctuated script can't rush the
  narrator. Confirmed: bad script 3 → 11 segments. Good script example: YT
  cCEcJ3bFReY ("I still set the table for two").
- NEVER reintroduce object-naming or statistics into script prompts.

## Music shuffling (2026-06-07)
- Was replaying the same tracks: GALLERY_RECENT_LIMIT=20 vs ~5-6 tracks/mood +
  a GLOBAL recent list → constant wrap-around → repeats. Fixed `_pick_from_music_gallery`
  to per-mood anti-repetition (avoid only same-mood recents, keep ≥2 fresh, prefer
  never-used). Confirmed: 5 consecutive videos = 5 different tracks.
- DEEPER ISSUE (open): all 17 gallery tracks are from ONE 06-05 batch with the
  same humming-ballad prompt → they SOUND alike even when the file differs. Real
  fix = diversify the library (varied instruments/tempo) via Sonauto batch (costs
  credits) or Pixabay (free, but API reliability unverified). Gallery is PRIMARY
  source (min_pool_size=1) so Pixabay/CC0 variety paths are rarely reached.

## ✅ CURRENT APPROVED VOICE — "approved-voice-v3" = POET PHRASING (2026-06-08)
Hira A/B'd two porch-light videos and chose **#58 "The porch light stays on all
night"** (poet phrasing, per-line pauses, 13 clips) — NOT #59 (natural-merged, 6
clips). So `approved-voice-v3` now points at the POET PHRASING config (restored
from commit 3e44d73): each poem line is its own breath unit, long lines split
only at natural boundaries (commas / before phrase-boundary words), pause sized
by line-end punctuation (sentence 1.3s / clause 0.45s / enjambed 0.3s breath).
NOTE: an earlier "robo" comment was about a LAGGED older video, not #58 — do not
over-correct away from poet phrasing again. The natural-merged version (892016c)
is NOT preferred.

## ⚠️ DO NOT auto-post test videos to the live accounts
Hira (2026-06-08): "don't post continuously — this is live accounts and
subscribers may get angry." Rapid manual `gh workflow run` test-posts spam real
subscribers AND create a confusing feedback loop (Hira commenting on older posts
while newer ones land). RULE: verify voice/script changes LOCALLY (the
segmentation logic runs offline), let the SCHEDULED cron deploy them, and ASK
before triggering any manual post.

## Script uniqueness (2026-06-08)
Hira: "couple of scripts is dupe — same story, few words here and there." Real
cases: porch-light x2 back-to-back, "You're sitting..." x3 in 10 videos. Fixed
in review_script.py with deterministic story-level dedup:
- opener-formula check (first 2 words of line 1, unique in last 25)
- central-image check (lived-anchor object in first 3 lines, unique in last 25)
- prompt avoid-block feeds the AI recent first-lines + central images verbatim
Every video must be a NEW story — never a remix. If dupes still appear, the next
lever is raising the windows (25) or adding an AI same-story judge.

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
