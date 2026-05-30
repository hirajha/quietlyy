"""
Quietlyy — Cross-Promotion Page Finder

The ONE big lever Whisprs has that we don't: cross-page network amplification.
Sri Lankan content agencies typically run 10-50 emotional-content pages and
have them share each other's posts. Each share is a free traffic injection.

We can't BUILD a network from scratch, but we can FIND existing small pages
in our niche and propose mutual content swaps. This script:

  1. Queries FB Graph Page Search for emotional-content keywords
  2. Filters to pages with 500-15,000 followers (peer tier — they'll say yes)
  3. Skips pages that are too big (won't bother with us) or too small (no value)
  4. Outputs assets/cross_promo_pages.md with:
        - Page name + link + follower count
        - Pre-written DM template to send them
        - Tracking notes for who you've already contacted

Manual step required: YOU send the DMs (15 min/week, ~5 contacts).
Realistic conversion: 1-2 of 5 will reciprocate → 1-2 new shares per week
from established small pages → exposure to 1K-30K new eyes per share.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests

GRAPH_API = "https://graph.facebook.com/v22.0"

# Niche keywords — emotional content space we want peers in
SEARCH_KEYWORDS = [
    "deep feelings",
    "emotional quotes",
    "heart broken",
    "soul whispers",
    "unspoken words",
    "midnight thoughts",
    "feelings quotes",
    "broken hearts",
    "love quotes",
    "lonely thoughts",
    "missing you quotes",
    "soft quotes",
]

# Peer tier — pages in this range are likely to reciprocate
MIN_FOLLOWERS = 500
MAX_FOLLOWERS = 15_000


def _get_page_token():
    page_id = os.environ.get("FB_PAGE_ID")
    raw = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not page_id or not raw:
        return None, None
    resp = requests.get(
        f"{GRAPH_API}/{page_id}",
        params={"access_token": raw, "fields": "access_token"},
        timeout=10,
    )
    if resp.status_code == 200:
        return page_id, resp.json().get("access_token", raw)
    return page_id, raw


def search_pages(keyword, token, limit=20):
    """Search FB Pages by keyword. Returns list of {id, name, follower_count}."""
    resp = requests.get(
        f"{GRAPH_API}/pages/search",
        params={
            "access_token": token,
            "q": keyword,
            "fields": "id,name,fan_count,follower_count,link,category",
            "limit": limit,
        },
        timeout=20,
    )
    if resp.status_code != 200:
        # /pages/search requires Pages Public Content Access permission
        # which is gated and hard to get. Log and skip.
        print(f"[cross-promo] /pages/search failed for '{keyword}': {resp.status_code} "
              f"{resp.text[:200]}", file=sys.stderr)
        return []
    return resp.json().get("data", [])


def find_pages():
    """Aggregate page search across all keywords. Dedupe + filter by follower range."""
    page_id, token = _get_page_token()
    if not token:
        print("[cross-promo] FB credentials missing", file=sys.stderr)
        return []

    seen_ids = set()
    candidates = []

    for kw in SEARCH_KEYWORDS:
        print(f"[cross-promo] Searching: '{kw}'", file=sys.stderr)
        pages = search_pages(kw, token)
        for p in pages:
            pid = p.get("id")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            followers = p.get("follower_count") or p.get("fan_count") or 0
            if followers < MIN_FOLLOWERS or followers > MAX_FOLLOWERS:
                continue
            # Don't propose to ourselves
            if pid == page_id:
                continue

            candidates.append({
                "id": pid,
                "name": p.get("name"),
                "followers": followers,
                "link": p.get("link") or f"https://www.facebook.com/{pid}",
                "category": p.get("category"),
                "matched_keyword": kw,
            })

    # Sort by follower count descending (bigger peer = more value)
    candidates.sort(key=lambda p: p["followers"], reverse=True)
    return candidates


def build_brief(candidates, max_pages=10):
    """Generate a markdown brief with the candidates + DM template."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# 🔗 Quietlyy Cross-Promo Outreach Brief",
        f"_Generated: {now_iso}_",
        "",
        "## What this is",
        "",
        "The biggest lever we lack vs Whisprs is cross-page sharing. We can't build",
        "a network from scratch, but we can FIND small peer pages and propose mutual",
        "content swaps. Below: ~10 candidates from the emotional content niche.",
        "",
        "**Goal:** Send 5 DMs per week. Realistic: 1-2 reciprocate → 1-2 free shares",
        "per week → exposure to 1K-30K new eyes per share.",
        "",
    ]

    if not candidates:
        lines += [
            "## ⚠️ No candidates found this week",
            "",
            "FB's `/pages/search` API requires the `Pages Public Content Access`",
            "permission, which Meta no longer grants to new apps (deprecated 2024).",
            "Without it, we can't programmatically search for peer pages.",
            "",
            "## Manual workaround (5 min)",
            "",
            "1. Open Facebook search → type one of these keywords:",
            "   - `deep feelings`",
            "   - `emotional quotes`",
            "   - `unspoken words`",
            "   - `soul whispers`",
            "   - `midnight thoughts`",
            "2. Filter to **Pages**",
            "3. Look for pages with 500-15,000 followers (sweet spot — they'll reciprocate)",
            "4. Use the DM template at the bottom of this file",
            "",
        ]
    else:
        lines += [
            f"## 📋 Top {min(max_pages, len(candidates))} candidates this week",
            "",
            "| Page | Followers | Niche match | DM link |",
            "|---|---|---|---|",
        ]
        for p in candidates[:max_pages]:
            msg_link = f"https://www.facebook.com/messages/t/{p['id']}"
            lines.append(
                f"| [{p['name']}]({p['link']}) | {p['followers']:,} | "
                f"`{p['matched_keyword']}` | [Send DM →]({msg_link}) |"
            )
        lines.append("")

    lines += [
        "---",
        "## 💬 DM Template (copy/paste)",
        "",
        "> Hey! 👋 I run @Quietlyy — a page sharing similar emotional content to yours.",
        "> Loved your recent posts.",
        ">",
        "> I'd love to do a content swap — I share one of your posts to my audience,",
        "> you share one of mine to yours. No catch, no payment, just two creators",
        "> helping each other reach more people who'd love this kind of content. 🤍",
        ">",
        "> Let me know if you're up for it — happy to start by sharing yours first.",
        ">",
        "> — Hira (Quietlyy)",
        "",
        "## ✅ Outreach tracker",
        "",
        "After sending DMs, mark them in this section so we don't double-DM:",
        "",
        "```",
        f"{today}: Sent to: [page1], [page2], [page3]",
        f"        Replied: ?",
        f"        Reciprocated: ?",
        "```",
        "",
        "_Brief regenerates weekly (Mondays). New candidates appear; previously",
        "contacted ones stay until you mark them as 'replied' or 'rejected'._",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="assets/cross_promo_pages.md")
    parser.add_argument("--max", type=int, default=10)
    args = parser.parse_args()

    candidates = find_pages()
    print(f"[cross-promo] Found {len(candidates)} eligible peer pages")

    brief = build_brief(candidates, max_pages=args.max)

    repo_root = os.path.join(os.path.dirname(__file__), "..")
    out_path = os.path.join(repo_root, args.output)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(brief)
    print(f"[cross-promo] Brief written to {args.output}")


if __name__ == "__main__":
    main()
