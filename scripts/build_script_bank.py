"""
Quietlyy — Script Bank Builder

Generates a pool of N unique scripts in bulk and stores them in
assets/script_bank.json. The pipeline reads from this bank instead of
generating scripts at video-creation time:

  ✓ Zero duplicate videos (each bank entry used exactly once)
  ✓ Pipeline runs faster (no AI call for script)
  ✓ Quality controlled at build time (review gate runs once per script)
  ✓ Free-tier-friendly: spreads generation across days/providers

USAGE:
    python scripts/build_script_bank.py --target 5000
    python scripts/build_script_bank.py --target 100 --resume     # append to existing
    python scripts/build_script_bank.py --rebuild                  # wipe and start fresh

When the bank exhausts (pipeline reaches the last entry), re-run with --rebuild
to generate the NEXT 5000 and replace the old set.

Storage layout:
  assets/script_bank.json       — array of scripts (the actual content)
  assets/script_bank_state.json — { "next_index": N, "total": N, "version": N }
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

# Reuse the existing generator + quality gate
from generate_script import (
    build_prompt, _generate_raw, load_templates, _OPENING_PATTERNS,
    pick_style_and_topic, save_used_script,
)
from review_script import review_script

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
BANK_PATH = os.path.join(ASSETS_DIR, "script_bank.json")
STATE_PATH = os.path.join(ASSETS_DIR, "script_bank_state.json")

# Style distribution — matches the natural mix the pipeline rotates through.
# love + emotional are the daily majority; nostalgic/poetic/wisdom are added
# for variety. Adjust ratios here to bias bank composition.
_STYLE_WEIGHTS = {
    "emotional": 40,
    "love":      30,
    "nostalgic": 15,
    "poetic":    10,
    "wisdom":     5,
}


def _load_bank():
    """Return list of existing bank entries (or empty list)."""
    if not os.path.exists(BANK_PATH):
        return []
    try:
        with open(BANK_PATH) as f:
            return json.load(f).get("scripts", [])
    except Exception:
        return []


def _save_bank(scripts):
    """Atomic write of bank file."""
    os.makedirs(ASSETS_DIR, exist_ok=True)
    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(scripts),
        "scripts": scripts,
    }
    tmp = BANK_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, BANK_PATH)


def _save_state(next_index, total):
    state = {
        "next_index": next_index,
        "total": total,
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _fingerprint(script_text):
    """Short hash of normalized first-100-chars — catches near-duplicates."""
    norm = " ".join(script_text.lower().strip().split())[:100]
    return hashlib.md5(norm.encode()).hexdigest()[:16]


def _pick_weighted_style():
    """Pick a style according to _STYLE_WEIGHTS distribution."""
    choices, weights = zip(*_STYLE_WEIGHTS.items())
    return random.choices(choices, weights=weights, k=1)[0]


def _generate_one(templates, examples, style):
    """Generate ONE bank-quality script. Returns dict or None.

    Reuses the existing _generate_raw + review_script pipeline but doesn't
    save to used_scripts (we save AT PICK time, not generate time).
    """
    # Topic picker uses random pool — we override style explicitly
    _, topic = pick_style_and_topic(templates, theme_hints=None)
    prompt = build_prompt(topic, examples, style=style)
    result, reason = _generate_raw(prompt, style)
    if not result or "script" not in result:
        return None, reason or "no_result"

    script_text = result["script"]
    approved, why, score = review_script(script_text, topic, style, examples)
    if not approved:
        return None, f"gate_failed: {why}"

    return {
        "id": None,  # filled by caller
        "style": style,
        "topic": topic,
        "script": script_text,
        "visual_keywords": result.get("visual_keywords", []),
        "quality_score": score,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": _fingerprint(script_text),
    }, "ok"


def build_bank(target=5000, resume=False, rebuild=False, batch_save=25):
    """Generate `target` unique scripts and save to the bank.

    resume=True  → append to existing bank
    rebuild=True → wipe existing and start fresh (replaces after exhaustion)
    """
    if rebuild and os.path.exists(BANK_PATH):
        os.remove(BANK_PATH)
        if os.path.exists(STATE_PATH):
            os.remove(STATE_PATH)
        print(f"[bank] Rebuild — cleared existing bank")

    existing = _load_bank() if resume else []
    existing_fps = {s.get("fingerprint") for s in existing if s.get("fingerprint")}
    print(f"[bank] Starting with {len(existing)} existing scripts (target: {target})")

    templates = load_templates()
    examples = templates["example_scripts"]

    scripts = existing[:]
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 30  # bail if 30 in a row fail (likely API down)

    start_time = time.time()
    last_save_count = len(scripts)

    while len(scripts) < target:
        style = _pick_weighted_style()
        result, status = _generate_one(templates, examples, style)

        if result is None:
            consecutive_failures += 1
            elapsed = time.time() - start_time
            print(f"[bank] [{len(scripts)}/{target}] FAIL ({status}) — {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES} consecutive — elapsed {elapsed/60:.1f}min")
            if status == "all_rate_limited":
                backoff = min(120, 30 + consecutive_failures * 10)
                print(f"[bank] All providers rate-limited — sleeping {backoff}s")
                time.sleep(backoff)
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"[bank] Hit {MAX_CONSECUTIVE_FAILURES} consecutive failures — aborting")
                print(f"[bank] Saved {len(scripts)} so far. Re-run with --resume to continue.")
                break
            continue

        # Dedup check
        if result["fingerprint"] in existing_fps:
            consecutive_failures += 1
            print(f"[bank] [{len(scripts)}/{target}] DUPLICATE — skipping (fp={result['fingerprint']})")
            continue

        consecutive_failures = 0
        result["id"] = len(scripts)
        scripts.append(result)
        existing_fps.add(result["fingerprint"])

        elapsed = time.time() - start_time
        rate = (len(scripts) - len(existing)) / max(elapsed, 1)
        eta_min = (target - len(scripts)) / max(rate * 60, 0.01)
        print(f"[bank] [{len(scripts)}/{target}] OK ({result['style']}: {result['topic'][:50]}) — {rate*60:.1f}/min, ETA {eta_min:.0f}min")

        # Checkpoint save every batch_save scripts
        if len(scripts) - last_save_count >= batch_save:
            _save_bank(scripts)
            _save_state(next_index=0, total=len(scripts))
            last_save_count = len(scripts)
            print(f"[bank] 💾 Checkpoint saved at {len(scripts)} scripts")

    # Final save
    _save_bank(scripts)
    _save_state(next_index=0, total=len(scripts))
    total_min = (time.time() - start_time) / 60
    print(f"[bank] ✅ DONE — {len(scripts)} scripts in bank ({total_min:.1f}min total)")
    return len(scripts)


def main():
    parser = argparse.ArgumentParser(description="Build the Quietlyy script bank")
    parser.add_argument("--target", type=int, default=5000,
                        help="Total number of scripts to have in the bank")
    parser.add_argument("--resume", action="store_true",
                        help="Append to existing bank instead of replacing")
    parser.add_argument("--rebuild", action="store_true",
                        help="Wipe existing bank and start fresh")
    parser.add_argument("--batch-save", type=int, default=25,
                        help="Save checkpoint every N successful generations")
    args = parser.parse_args()

    if args.rebuild and args.resume:
        print("ERROR: --rebuild and --resume are mutually exclusive")
        sys.exit(1)

    final_count = build_bank(
        target=args.target,
        resume=args.resume,
        rebuild=args.rebuild,
        batch_save=args.batch_save,
    )
    print(f"[bank] Final count: {final_count}")
    sys.exit(0 if final_count >= args.target else 1)


if __name__ == "__main__":
    main()
