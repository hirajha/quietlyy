"""
Quietlyy — Script Bank Cleaner (one-time, heuristic, no AI cost)

The bank had a 1000+ script backlog (~252 days at 4/day), so prompt/gate
improvements would never reach the feed in time. This trims the UNUSED portion
to only emotionally-real scripts:

  - drops broken output (artifact endings like "...Period", dangling filler,
    too-short) via review_script.check_structure
  - drops abstract / generic scripts (nature-poetry with NO concrete human
    anchor — the OPPOSITE of "feels like my real life") via a heuristic

Already-used scripts (bank[:next_index]) are removed from the bank (they're
posted + tracked in used_scripts.json for dedup). The cleaned UNUSED scripts
become the new bank with next_index reset to 0.

Run:  python scripts/clean_script_bank.py            # report + apply
      python scripts/clean_script_bank.py --dry-run  # report only
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from review_script import check_structure

BANK = os.path.join(os.path.dirname(__file__), "..", "assets", "script_bank.json")
STATE = os.path.join(os.path.dirname(__file__), "..", "assets", "script_bank_state.json")
BACKUP = os.path.join(os.path.dirname(__file__), "..", "assets", "script_bank.backup.json")

# CONCRETE objects / moments / times → the signal that a script describes the
# viewer's ACTUAL life ("their number is still saved", "coffee for two", "2am").
# NOTE: pronouns (you/I/my) are deliberately EXCLUDED — they appear in nearly
# every script (abstract ones too), so they're a useless signal. What separates
# "feels like my life" from "generic sad-poetry" is a tangible thing/moment.
_CONCRETE = re.compile(r"\b("
    r"phone|number|text|texts|message|messages|call|calls|voicemail|ringtone|"
    r"contact|screen|inbox|notification|coffee|tea|mug|cup|bed|pillow|sheets|"
    r"blanket|door|doorway|car|keys|key|chair|couch|sofa|table|photo|photos|"
    r"picture|pictures|name|voice|laugh|smile|jacket|hoodie|sweater|shirt|"
    r"clothes|perfume|cologne|song|songs|playlist|radio|"
    r"2am|3am|4am|midnight|noon|morning|tonight|evening|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"birthday|wedding|funeral|airport|station|hospital|kitchen|bedroom|"
    r"kid|kids|child|children|son|daughter|mother|father|mom|dad|grandma|grandpa|"
    r"ring|letter|letters|note|notes|diary|journal|wallet|mirror|window|street|"
    r"scroll\w*|typing|unsent|saved|deleted|delete|unread|seen|left on read"
    r")\b", re.I)


def is_abstract(script):
    concrete = len(_CONCRETE.findall(script))
    # No tangible object/moment anywhere → it's generic feelings/imagery, not
    # the viewer's specific life. That's exactly what we're cutting.
    if concrete == 0:
        return True, "no concrete object/moment (generic, not lived)"
    return False, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bank = json.load(open(BANK))
    scripts = bank.get("scripts", [])
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    ni = state.get("next_index", 0)

    unused = scripts[ni:]
    kept, dropped = [], {"structure": [], "abstract": []}

    for e in unused:
        txt = e.get("script", "")
        ok, why = check_structure(txt)
        if not ok:
            dropped["structure"].append((why, txt.splitlines()[-1] if txt else ""))
            continue
        # wisdom is quote-based, exempt from the abstraction heuristic
        if e.get("style") != "wisdom":
            ab, why = is_abstract(txt)
            if ab:
                dropped["abstract"].append((why, e.get("topic", "")))
                continue
        kept.append(e)

    print(f"Bank: {len(scripts)} total | {ni} already used | {len(unused)} unused")
    print(f"  DROP broken/structure : {len(dropped['structure'])}")
    print(f"  DROP abstract/generic : {len(dropped['abstract'])}")
    print(f"  KEEP (emotionally real): {len(kept)}")
    from collections import Counter
    print("  kept by style:", dict(Counter(e.get('style') for e in kept)))
    print(f"  new backlog at 4/day: ~{len(kept)//4} days")
    print("\n  sample broken drops:", dropped["structure"][:4])
    print("  sample abstract drops:", dropped["abstract"][:5])

    if args.dry_run:
        print("\n[dry-run] no changes written.")
        return

    json.dump(bank, open(BACKUP, "w"))          # backup original
    bank["scripts"] = kept
    json.dump(bank, open(BANK, "w"), indent=2)
    state["next_index"] = 0
    json.dump(state, open(STATE, "w"), indent=2)
    print(f"\n✅ Cleaned. Backup at {os.path.basename(BACKUP)}. next_index reset to 0.")


if __name__ == "__main__":
    main()
