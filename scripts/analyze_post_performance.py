"""
Quietlyy — Post Performance Analyzer

Queries the Facebook Graph API to pull engagement metrics for recent posts.
Used by recommend_boost.py to identify boost candidates (over-performing
organic posts where paid promotion will have highest ROI).

Requires:
  FB_PAGE_ID            (already configured)
  FB_PAGE_ACCESS_TOKEN  (already configured; needs pages_read_engagement scope)

Metrics pulled per post:
  - impressions (organic reach)
  - reactions (likes + loves + etc)
  - comments
  - shares
  - engagement_rate = (reactions + comments + shares) / impressions

USAGE:
  python scripts/analyze_post_performance.py            # last 30 days
  python scripts/analyze_post_performance.py --days 7   # last 7 days
  python scripts/analyze_post_performance.py --json     # machine-readable
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

GRAPH_API = "https://graph.facebook.com/v22.0"


def get_page_token():
    """Exchange user token for a page access token (required for Insights)."""
    page_id = os.environ.get("FB_PAGE_ID")
    raw = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not page_id or not raw:
        print("ERROR: FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN must be set", file=sys.stderr)
        sys.exit(1)

    # Try to exchange for a page token (the access_token field on the page)
    resp = requests.get(
        f"{GRAPH_API}/{page_id}",
        params={"access_token": raw, "fields": "access_token,name,id"},
        timeout=10,
    )
    if resp.status_code == 200:
        data = resp.json()
        page_token = data.get("access_token")
        if page_token:
            return page_id, page_token
    return page_id, raw  # fall back to user token if exchange fails


def fetch_recent_posts(page_id, token, days=30, limit=100):
    """Pull all posts from the page in the last N days."""
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    resp = requests.get(
        f"{GRAPH_API}/{page_id}/posts",
        params={
            "access_token": token,
            "since": since,
            "limit": limit,
            "fields": "id,created_time,message,permalink_url,attachments{media_type,title}",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"ERROR fetching posts: {resp.status_code} — {resp.text[:300]}", file=sys.stderr)
        return []
    return resp.json().get("data", [])


_INSIGHTS_PERMISSION_WARNED = False  # only warn once per run


def fetch_post_metrics(post_id, token):
    """Pull engagement metrics for a single post.

    Tries Insights API first (needs read_insights permission). If denied,
    falls back to basic post fields (likes, comments, shares) which work
    with pages_read_engagement. Returns dict with whatever data we got.
    """
    global _INSIGHTS_PERMISSION_WARNED
    result = {}

    # ── Try Insights API (rich metrics, but needs read_insights) ────────────
    metrics = [
        "post_impressions",
        "post_impressions_unique",
        "post_engaged_users",
        "post_reactions_by_type_total",
        "post_video_views",
    ]
    resp = requests.get(
        f"{GRAPH_API}/{post_id}/insights",
        params={"access_token": token, "metric": ",".join(metrics)},
        timeout=15,
    )
    if resp.status_code == 200:
        for entry in resp.json().get("data", []):
            name = entry.get("name")
            values = entry.get("values", [])
            if not values:
                continue
            val = values[0].get("value", 0)
            if name == "post_reactions_by_type_total" and isinstance(val, dict):
                result["reactions_total"] = sum(val.values())
            else:
                result[name] = val
    else:
        if not _INSIGHTS_PERMISSION_WARNED:
            err = resp.json().get("error", {})
            print(f"[analyze] ⚠️  Insights API failed (status {resp.status_code}): "
                  f"{err.get('message', resp.text[:200])}", file=sys.stderr)
            print(f"[analyze] ⚠️  Need read_insights permission on FB_PAGE_ACCESS_TOKEN.", file=sys.stderr)
            print(f"[analyze] ⚠️  Falling back to basic post fields (likes/comments/shares).", file=sys.stderr)
            _INSIGHTS_PERMISSION_WARNED = True

    # ── Fallback: basic post fields (always work with pages_read_engagement) ──
    resp2 = requests.get(
        f"{GRAPH_API}/{post_id}",
        params={
            "access_token": token,
            "fields": "shares,comments.summary(true).limit(0),"
                      "likes.summary(true).limit(0),"
                      "reactions.summary(true).limit(0)",
        },
        timeout=15,
    )
    if resp2.status_code == 200:
        d = resp2.json()
        result["shares"] = d.get("shares", {}).get("count", 0)
        result["comments"] = d.get("comments", {}).get("summary", {}).get("total_count", 0)
        # If Insights gave us reactions_total, prefer that; otherwise use this
        if "reactions_total" not in result:
            result["reactions_total"] = d.get("reactions", {}).get("summary", {}).get("total_count", 0)
        # Use likes count as proxy for impressions when insights is denied
        if "post_impressions" not in result:
            result["likes_count"] = d.get("likes", {}).get("summary", {}).get("total_count", 0)

    # Always return a dict (even if minimal) — caller decides if it's enough
    return result if result else None


def analyze(days=30):
    """Pull + analyze. Returns list of dicts with metrics + engagement_rate."""
    page_id, token = get_page_token()
    print(f"[analyze] Pulling posts for page {page_id} (last {days} days)...", file=sys.stderr)

    posts = fetch_recent_posts(page_id, token, days=days)
    print(f"[analyze] Found {len(posts)} posts", file=sys.stderr)

    results = []
    for i, post in enumerate(posts, 1):
        post_id = post["id"]
        print(f"[analyze] [{i}/{len(posts)}] Fetching metrics for {post_id}...", file=sys.stderr)
        metrics = fetch_post_metrics(post_id, token)
        if not metrics:
            continue

        impressions = metrics.get("post_impressions", 0)
        reactions = metrics.get("reactions_total", 0)
        comments = metrics.get("comments", 0)
        shares = metrics.get("shares", 0)
        total_eng = reactions + comments + shares
        # If Insights gave us impressions, compute proper engagement rate.
        # Otherwise rank by weighted absolute engagement (shares matter most).
        if impressions > 0:
            eng_rate = total_eng / impressions * 100
        else:
            # Weighted engagement score as proxy (shares 5x > comments 2x > reactions 1x)
            eng_rate = (shares * 5 + comments * 2 + reactions) / 10.0

        results.append({
            "id": post_id,
            "created_time": post.get("created_time"),
            "permalink": post.get("permalink_url"),
            "message_preview": (post.get("message") or "")[:80].replace("\n", " "),
            "impressions": impressions,
            "video_views": metrics.get("post_video_views", 0),
            "reactions": reactions,
            "comments": comments,
            "shares": shares,
            "total_engagement": total_eng,
            "engagement_rate_pct": round(eng_rate, 2),
            "has_insights": impressions > 0,
        })

    # Sort by engagement rate descending (or proxy score if no Insights)
    results.sort(key=lambda r: r["engagement_rate_pct"], reverse=True)
    return results


def print_human(results, top_n=15):
    if not results:
        print("\nNo posts found with metrics.")
        return

    avg_eng_rate = sum(r["engagement_rate_pct"] for r in results) / len(results)
    avg_impressions = sum(r["impressions"] for r in results) / len(results)

    print(f"\n=== POST PERFORMANCE REPORT ===")
    print(f"Posts analyzed: {len(results)}")
    print(f"Avg engagement rate: {avg_eng_rate:.2f}%")
    print(f"Avg impressions: {avg_impressions:.0f}")
    print()
    print(f"{'#':<3} {'ER%':<6} {'Impr':<7} {'Reach':<7} {'React':<6} {'Cmts':<5} {'Shr':<5} {'Preview':<60}")
    print("-" * 110)
    for i, r in enumerate(results[:top_n], 1):
        marker = " 🚀" if r["engagement_rate_pct"] > avg_eng_rate * 1.5 and r["impressions"] > 100 else ""
        print(f"{i:<3} {r['engagement_rate_pct']:<6.2f} {r['impressions']:<7} "
              f"{r.get('post_impressions_unique', 0):<7} "
              f"{r['reactions']:<6} {r['comments']:<5} {r['shares']:<5} "
              f"{r['message_preview'][:55]}{marker}")
    print()
    print("🚀 = strong boost candidate (engagement rate 1.5x+ average, >100 impressions)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30, help="Lookback window")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    parser.add_argument("--top", type=int, default=15, help="How many top posts to show")
    args = parser.parse_args()

    results = analyze(days=args.days)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_human(results, top_n=args.top)


if __name__ == "__main__":
    main()
