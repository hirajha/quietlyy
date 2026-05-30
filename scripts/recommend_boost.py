"""
Quietlyy — Smart Boost Recommender

Identifies which RECENT posts (last 3 days) are over-performing organically,
calculates ROI estimates, and writes a clear daily brief:
  assets/boost_brief.md

Workflow:
  1. Pull post performance via analyze_post_performance.py
  2. Filter to posts that are: (a) recent enough to still benefit from
     boosting (algorithm pushes posts <72h old), AND (b) hitting at least
     1.5x average engagement rate (signal of organic resonance)
  3. Output ranked recommendations + direct boost URLs + suggested $ amounts

User reads the brief, clicks the boost link, sets the $ amount,
and approves. No automated spend = no surprise charges.

WHY NOT GENERIC PAGE LIKE ADS:
  Generic Page Like campaigns bring low-quality followers (people who tap
  Like once and never engage). Boosting an over-performing organic POST
  attracts followers who already liked your specific content style —
  much higher retention + downstream engagement.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from analyze_post_performance import analyze, get_page_token

# Tunables
MIN_IMPRESSIONS_TO_CONSIDER = 50    # ignore very-low-reach posts (small sample)
MIN_AGE_HOURS = 4                    # let organic signal settle before boosting
MAX_AGE_HOURS = 96                   # 4 days — older posts won't benefit much
ENG_MULTIPLE_TO_RECOMMEND = 1.5      # post must be 1.5x avg engagement rate
DEFAULT_BOOST_USD = 7                # the user said $5-10/day budget — go 7


def _hours_ago(iso_time_str):
    if not iso_time_str:
        return 9999
    try:
        # Parse FB ISO format like "2026-05-26T11:30:45+0000"
        ts = iso_time_str.replace("+0000", "+00:00")
        dt = datetime.fromisoformat(ts)
        age = datetime.now(timezone.utc) - dt
        return age.total_seconds() / 3600
    except Exception:
        return 9999


def _build_boost_url(post_id):
    """Direct deep link into Meta Ads Manager to boost a specific post."""
    # Strip the page-prefix from post_id (FB returns "pageid_postid")
    return f"https://www.facebook.com/ads/manager/?act=boost_post&fb_post_id={post_id}"


def _suggest_budget(eng_rate, avg_eng_rate, impressions):
    """Suggest $ amount based on how strong the signal is.

    Strong signal (3x+ avg, 500+ impressions) → spend more
    Moderate signal (1.5-3x avg) → conservative spend
    """
    ratio = eng_rate / max(avg_eng_rate, 0.1)
    if ratio >= 3 and impressions >= 500:
        return DEFAULT_BOOST_USD * 2     # 14
    if ratio >= 2:
        return DEFAULT_BOOST_USD + 3     # 10
    return DEFAULT_BOOST_USD             # 7


def _estimate_reach(usd_budget):
    """Rough industry estimate: $1 = 100-300 reach for emotional content niche."""
    low = usd_budget * 100
    high = usd_budget * 300
    return f"{low:,}–{high:,}"


def build_brief(days=7, max_recommendations=3):
    page_id, token = get_page_token()
    results = analyze(days=days)

    if not results:
        return "# Boost Brief\n\n**No posts found in the last %d days.**\n" % days

    has_insights = any(r.get("has_insights") for r in results)
    avg_eng_rate = sum(r["engagement_rate_pct"] for r in results) / len(results)
    avg_impressions = sum(r["impressions"] for r in results) / len(results)

    # When Insights API is denied, we can't compute proper engagement rate.
    # Lower the threshold and skip the impressions-based filter so we still
    # produce a useful brief from basic metrics (likes/comments/shares).
    if not has_insights:
        global MIN_IMPRESSIONS_TO_CONSIDER
        MIN_IMPRESSIONS_TO_CONSIDER = 0

    # Filter to BOOST CANDIDATES
    candidates = []
    for r in results:
        age = _hours_ago(r.get("created_time"))
        if r["impressions"] < MIN_IMPRESSIONS_TO_CONSIDER:
            continue
        if age < MIN_AGE_HOURS or age > MAX_AGE_HOURS:
            continue
        if r["engagement_rate_pct"] < avg_eng_rate * ENG_MULTIPLE_TO_RECOMMEND:
            continue
        candidates.append({**r, "_age_hours": age})

    # Sort by engagement rate desc
    candidates.sort(key=lambda c: c["engagement_rate_pct"], reverse=True)
    candidates = candidates[:max_recommendations]

    # Build markdown brief
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# 📊 Quietlyy Boost Brief",
        f"_Generated: {now_iso}_",
        "",
    ]
    if has_insights:
        lines += [
            f"**Avg engagement rate (last {days} days):** `{avg_eng_rate:.2f}%`  ",
            f"**Avg impressions per post:** `{avg_impressions:.0f}`",
            "",
        ]
    else:
        lines += [
            "> ⚠️ **Insights API access not granted on FB token.** Rankings below use only",
            "> reactions/comments/shares (no impressions or engagement rate). To unlock proper",
            "> ranking, grant `read_insights` on FB_PAGE_ACCESS_TOKEN at",
            "> https://developers.facebook.com/tools/explorer/ — pick page → permissions → add `read_insights`.",
            "",
            f"**Avg engagement score (last {days} days):** `{avg_eng_rate:.1f}` (weighted: shares×5 + comments×2 + reactions)",
            "",
        ]

    if not candidates:
        lines += [
            "## No boost candidates today",
            "",
            "No recent posts (4-96h old) are hitting 1.5× average engagement.",
            "This usually means: (a) it's normal to skip a day, (b) all posts performed similarly,",
            "or (c) need to wait longer for organic signal to settle.",
            "",
            f"Next brief regenerates automatically tomorrow.",
        ]
    else:
        lines += [
            f"## 🚀 {len(candidates)} boost candidate{'s' if len(candidates) > 1 else ''}",
            "",
            "These posts are out-performing your average — boosting them now will reach",
            "the audience that already resonates with your content (highest-quality followers).",
            "",
        ]
        for i, c in enumerate(candidates, 1):
            budget = _suggest_budget(c["engagement_rate_pct"], avg_eng_rate, c["impressions"])
            reach = _estimate_reach(budget)
            multiple = c["engagement_rate_pct"] / max(avg_eng_rate, 0.1)
            permalink = c.get("permalink") or f"https://www.facebook.com/{c['id']}"
            boost_url = _build_boost_url(c["id"])
            age_hr = int(c["_age_hours"])
            lines += [
                f"### {i}. {c['message_preview']}",
                f"- **Engagement rate:** `{c['engagement_rate_pct']:.2f}%` ({multiple:.1f}× average)",
                f"- **Stats:** {c['impressions']} impressions · {c['reactions']} reactions · {c['comments']} comments · {c['shares']} shares",
                f"- **Age:** {age_hr}h ({'fresh' if age_hr < 24 else 'still in algorithmic window'})",
                f"- **Suggested boost:** `${budget}` → estimated reach +{reach}",
                f"- 🔗 [View post]({permalink})",
                f"- 🎯 [**Boost in Ads Manager →**]({boost_url})",
                "",
            ]

    lines += [
        "---",
        "## How to use this brief",
        "",
        "1. Click **🎯 Boost in Ads Manager** for any candidate above",
        "2. Set the budget = the suggested amount (e.g. `$7`)",
        "3. Set duration = `1 day` (single-shot boost, then re-evaluate tomorrow)",
        "4. Choose audience = **People who like Quietlyy and similar pages** (Meta's smart default)",
        "5. Submit → boost runs automatically",
        "",
        "**Total daily spend cap (recommended):** `$5–10/day`. Don't boost everything; pick the #1 candidate only.",
        "",
        "_This brief regenerates daily. No automated spend — you approve every boost manually._",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--max", type=int, default=3, help="Max candidates to recommend")
    parser.add_argument("--output", default="assets/boost_brief.md",
                        help="Where to write the brief (relative to repo root)")
    args = parser.parse_args()

    brief = build_brief(days=args.days, max_recommendations=args.max)

    repo_root = os.path.join(os.path.dirname(__file__), "..")
    out_path = os.path.join(repo_root, args.output)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(brief)
    print(f"[boost] Brief written to {args.output}")
    print()
    print(brief)


if __name__ == "__main__":
    main()
