"""
Quietlyy — First-Hour Engagement Booster

Runs every 30 min during post windows. For any FB post that's 20-90 min old
AND has fewer than 3 comments, posts ONE thoughtful follow-up comment from
the page (different vibe from the initial pinned comment to avoid spammy
feel). Seeding the comment thread early triggers the algorithm distribution
boost — first-hour engagement determines 80% of a post's reach (2026 FB
algo research).

Safety:
  - Max 1 follow-up per post (tracked in assets/engagement_seeds.json)
  - Only fires for posts <90 min old (no point seeding old posts)
  - Skips if post already has >=3 comments (algorithm already happy)

Reuses post_engagement_comment() from post_to_facebook.py.
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

import requests

from post_to_facebook import post_engagement_comment, get_credentials, get_page_token

GRAPH_API = "https://graph.facebook.com/v22.0"
SEEDS_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "engagement_seeds.json")

# Window when a follow-up still matters (first-hour algo boost)
MIN_POST_AGE_MIN = 20    # let organic comments breathe first
MAX_POST_AGE_MIN = 90    # past 90 min, algo has already decided

# Trigger if post has fewer than this many comments
COMMENT_THRESHOLD = 3

# Follow-up phrases — different vibe from the initial pinned question.
# These read like the page admin is reflecting again, not seeding.
# Rotation: random per call.
FOLLOWUP_COMMENTS = [
    "This one stayed with me longer than I expected.",
    "I keep coming back to this line. 🤍",
    "Sometimes the simplest words hit the hardest.",
    "Save this for the right moment. You'll know when. 💭",
    "Read it again. It changes the second time.",
    "I wrote this for someone. Maybe it found you too.",
    "Some nights need a reminder like this. 🌙",
    "This is the version of love we don't talk about enough.",
    "Quiet truths land different.",
    "If this hit, share it with one person. That's enough. 🤍",
    "Some of us needed to read this today.",
    "The kind of words you don't want to scroll past.",
]


def _load_seeds():
    if not os.path.exists(SEEDS_PATH):
        return {"seeded_posts": [], "last_run": None}
    try:
        with open(SEEDS_PATH) as f:
            return json.load(f)
    except Exception:
        return {"seeded_posts": [], "last_run": None}


def _save_seeds(state):
    os.makedirs(os.path.dirname(SEEDS_PATH), exist_ok=True)
    with open(SEEDS_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _age_minutes(iso_time_str):
    if not iso_time_str:
        return 99999
    try:
        ts = iso_time_str.replace("+0000", "+00:00")
        dt = datetime.fromisoformat(ts)
        age = datetime.now(timezone.utc) - dt
        return age.total_seconds() / 60
    except Exception:
        return 99999


def fetch_recent_posts(page_id, token, limit=10):
    """Get recent posts with comment counts."""
    resp = requests.get(
        f"{GRAPH_API}/{page_id}/posts",
        params={
            "access_token": token,
            "limit": limit,
            "fields": "id,created_time,comments.summary(true).limit(0)",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        print(f"[seed-engagement] Failed to fetch posts: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
        return []
    return resp.json().get("data", [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Identify posts that need seeding but don't actually comment")
    args = parser.parse_args()

    state = _load_seeds()
    seeded_ids = set(state.get("seeded_posts", []))

    page_id, raw_token = get_credentials()
    token = get_page_token(page_id, raw_token)

    posts = fetch_recent_posts(page_id, token, limit=10)
    if not posts:
        print("[seed-engagement] No posts returned")
        sys.exit(0)

    now_utc = datetime.now(timezone.utc).isoformat()
    state["last_run"] = now_utc

    candidates = []
    for post in posts:
        post_id = post["id"]
        age = _age_minutes(post.get("created_time"))
        comments = post.get("comments", {}).get("summary", {}).get("total_count", 0)

        if post_id in seeded_ids:
            continue
        if age < MIN_POST_AGE_MIN or age > MAX_POST_AGE_MIN:
            continue
        if comments >= COMMENT_THRESHOLD:
            continue

        candidates.append({"id": post_id, "age_min": age, "comments": comments})

    if not candidates:
        print(f"[seed-engagement] No candidates (checked {len(posts)} posts; "
              f"all are too new, too old, already seeded, or already have ≥{COMMENT_THRESHOLD} comments)")
        _save_seeds(state)
        sys.exit(0)

    # Seed the OLDEST candidate first (closest to losing first-hour boost)
    candidates.sort(key=lambda c: c["age_min"], reverse=True)
    target = candidates[0]

    comment = random.choice(FOLLOWUP_COMMENTS)
    print(f"[seed-engagement] Target: post {target['id']} "
          f"(age={int(target['age_min'])}min, comments={target['comments']})")
    print(f"[seed-engagement] Will comment: \"{comment}\"")

    if args.dry_run:
        print("[seed-engagement] (Dry run — not actually commenting)")
        sys.exit(0)

    ok = post_engagement_comment(target["id"], comment)
    if ok:
        state["seeded_posts"].append(target["id"])
        # Keep last 100 only (storage hygiene)
        state["seeded_posts"] = state["seeded_posts"][-100:]
        _save_seeds(state)
        print(f"[seed-engagement] ✅ Follow-up comment posted to {target['id']}")
    else:
        print(f"[seed-engagement] ❌ Failed to post follow-up")
        sys.exit(1)


if __name__ == "__main__":
    main()
