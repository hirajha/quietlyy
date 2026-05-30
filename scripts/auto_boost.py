"""
Quietlyy — Automated Post Boosting

Reads the boost brief, identifies the top candidate, and creates a Facebook
ad campaign to boost that post — WITHOUT manual intervention.

═══ SAFETY CAPS (hard-coded, cannot be exceeded) ═══
  AD_ACCOUNT_CURRENCY  = INR (user funded the 'Quietlyy' ad account in INR)
  DAILY_BUDGET_CAP     = ₹500 per day, total across all boosts
  DAILY_BOOST_LIMIT    = 1    boost per day max
  PER_BOOST_BUDGET     = ₹500 default per boost (= the daily cap → never doubled up)
  PER_BOOST_DURATION   = 1    day per boost
  → Funded with ₹1,000 = 2 boosts before fund exhaustion. No surprise charges.

All boosts logged to assets/boost_history.json with date+amount+ad_id+status.
If today's spend already hit the cap, this script does nothing.

═══ REQUIRED SETUP (one-time) ═══
  1. FB_AD_ACCOUNT_ID secret  — your ad account ID (format: "act_123456789")
     Find at: https://business.facebook.com/settings/ad-accounts
  2. FB_PAGE_ACCESS_TOKEN     — already configured; needs ads_management scope
  3. Payment method attached to the ad account (cannot be set via API)

═══ HOW IT WORKS ═══
  1. Read assets/boost_brief.md for the top candidate
  2. Check assets/boost_history.json — if already boosted today, exit
  3. Create FB Marketing API objects:
        Campaign (objective: POST_ENGAGEMENT)
            └── AdSet ($7 daily budget, 24h duration, smart audience)
                └── Ad (creative = your existing post)
  4. Record success/failure to history file
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

GRAPH_API = "https://graph.facebook.com/v22.0"

# ═══ HARD SAFETY CAPS ═══
# Currency: INR (user funded the 'Quietlyy' ad account with ₹1,000 in INR).
# FB Marketing API uses minor units → 1 INR = 100 paise, so budget × 100 below.
AD_CURRENCY = "INR"
DAILY_BUDGET_CAP = 500           # ₹500 per day max, period
DAILY_BOOST_LIMIT = 1            # max 1 new boost per day
PER_BOOST_BUDGET = 500           # ₹500 default per boost (= daily cap)
PER_BOOST_DURATION_DAYS = 1      # each boost runs for 24 hours
AD_ACCOUNT_NAME = "Quietlyy"     # used by auto-detect when FB_AD_ACCOUNT_ID not set

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
BRIEF_PATH = os.path.join(ASSETS_DIR, "boost_brief.md")
HISTORY_PATH = os.path.join(ASSETS_DIR, "boost_history.json")


def _load_history():
    if not os.path.exists(HISTORY_PATH):
        return {"boosts": []}
    try:
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except Exception:
        return {"boosts": []}


def _save_history(history):
    os.makedirs(ASSETS_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


def _today_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _today_spent(history):
    """Sum boost amounts created today (UTC) in AD_CURRENCY. Used for the daily cap."""
    today = _today_utc()
    # Backwards-compat: read either new "budget" or legacy "budget_usd"
    return sum(b.get("budget", b.get("budget_usd", 0)) for b in history.get("boosts", [])
               if b.get("date") == today and b.get("status") == "ok")


def _today_boost_count(history):
    today = _today_utc()
    return sum(1 for b in history.get("boosts", [])
               if b.get("date") == today and b.get("status") == "ok")


def _parse_top_candidate_from_brief():
    """Pull the #1 boost candidate out of assets/boost_brief.md.

    Returns dict with at least: post_id, message_preview, suggested_budget
    Returns None if no candidate.
    """
    if not os.path.exists(BRIEF_PATH):
        return None
    with open(BRIEF_PATH) as f:
        brief = f.read()

    # Look for the "boost candidate" section
    if "No boost candidates today" in brief:
        return None

    # The brief contains lines like "fb_post_id=1000158716521208_122112464132914386"
    # The post_id is what we boost.
    m = re.search(r"fb_post_id=(\S+?)\)", brief)
    if not m:
        return None
    post_id = m.group(1)

    # Suggested budget — line like "Suggested boost: `$7`"
    budget_m = re.search(r"Suggested boost:\s*`\$(\d+)`", brief)
    # Brief still uses $ as suggested-budget display unit (it's currency-agnostic
    # market data). Take the dollar number and treat as INR (since our ad
    # account is INR). Multiplied by ~80 would over-spend — instead we use
    # the brief's number as a relative-strength signal capped at PER_BOOST_BUDGET.
    suggested = int(budget_m.group(1)) if budget_m else PER_BOOST_BUDGET
    # Scale: brief's $7 → ₹350, $14 → ₹500 (rough INR equivalent intent)
    budget = min(suggested * 50, PER_BOOST_BUDGET)

    # Message preview — line after "### 1."
    preview_m = re.search(r"### 1\. (.+)", brief)
    preview = preview_m.group(1).strip() if preview_m else "(unknown)"

    return {
        "post_id": post_id,
        "message_preview": preview,
        "suggested_budget": min(budget, PER_BOOST_BUDGET),  # never exceed cap
    }


def _get_page_token():
    page_id = os.environ.get("FB_PAGE_ID")
    raw = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not page_id or not raw:
        return None, None
    resp = requests.get(
        f"{GRAPH_API}/{page_id}",
        params={"access_token": raw, "fields": "access_token,id"},
        timeout=10,
    )
    if resp.status_code == 200:
        token = resp.json().get("access_token", raw)
        return page_id, token
    return page_id, raw


def _autodetect_ad_account(token):
    """If FB_AD_ACCOUNT_ID isn't set, find the ad account.

    Priority:
      1. Single active ad account → use it
      2. Multiple active → prefer the one named AD_ACCOUNT_NAME ("Quietlyy")
      3. Multiple active, no name match → ask user to set FB_AD_ACCOUNT_ID
    """
    resp = requests.get(
        f"{GRAPH_API}/me/adaccounts",
        params={"access_token": token, "fields": "id,name,account_status,currency"},
        timeout=10,
    )
    if resp.status_code != 200:
        return None, resp.text[:300]
    accounts = resp.json().get("data", [])
    active = [a for a in accounts if a.get("account_status") == 1]

    if len(active) == 1:
        a = active[0]
        if a.get("currency") and a["currency"] != AD_CURRENCY:
            print(f"[auto-boost] ⚠️  Ad account currency is {a['currency']}, expected {AD_CURRENCY}. "
                  f"Caps assume {AD_CURRENCY} — verify your budget settings.", file=sys.stderr)
        return a["id"], None

    if len(active) > 1:
        # Try to match by name first
        name_match = [a for a in active if a.get("name", "").lower() == AD_ACCOUNT_NAME.lower()]
        if len(name_match) == 1:
            return name_match[0]["id"], None
        names = [f"{a['id']} ({a.get('name')}, {a.get('currency')})" for a in active]
        return None, f"Multiple ad accounts and none named '{AD_ACCOUNT_NAME}'. Set FB_AD_ACCOUNT_ID. Options: {names}"

    return None, f"No active ad accounts found. {len(accounts)} total, 0 active."


def create_boost(post_id, page_id, ad_account_id, token, budget, days, dry_run=False):
    """Create campaign + ad set + ad to boost an existing post.

    `budget` is in AD_CURRENCY (₹ for INR account). FB Marketing API uses
    minor units → multiplied by 100 below (1 INR = 100 paise).

    Returns dict with keys: status ('ok'|'error'), ad_id, error, breakdown.
    """
    daily_budget_minor = budget * 100  # ₹500 → 50000 paise

    if dry_run:
        return {
            "status": "ok",
            "ad_id": "DRY_RUN_NO_AD_CREATED",
            "campaign_id": "DRY_RUN",
            "adset_id": "DRY_RUN",
            "breakdown": f"Dry run — would have boosted post for ₹{budget}/{days}d",
        }

    # Step 1: Create campaign (objective: POST_ENGAGEMENT)
    camp_resp = requests.post(
        f"{GRAPH_API}/{ad_account_id}/campaigns",
        params={"access_token": token},
        data={
            "name": f"Auto-boost {post_id[-8:]} {_today_utc()}",
            "objective": "OUTCOME_ENGAGEMENT",  # 2026 modern objective name
            "status": "ACTIVE",
            "special_ad_categories": "[]",
        },
        timeout=20,
    )
    if camp_resp.status_code != 200:
        return {
            "status": "error",
            "ad_id": None,
            "error": f"Campaign create failed: {camp_resp.status_code} — {camp_resp.text[:300]}",
        }
    campaign_id = camp_resp.json()["id"]

    # Step 2: Create ad set (the budget/audience layer)
    # Smart Audience uses Meta's auto-targeting based on page engagement
    # End time = now + days
    from datetime import timedelta
    end_time = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    adset_resp = requests.post(
        f"{GRAPH_API}/{ad_account_id}/adsets",
        params={"access_token": token},
        data={
            "name": f"Auto-boost AdSet {post_id[-8:]}",
            "campaign_id": campaign_id,
            "daily_budget": daily_budget_minor,
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "POST_ENGAGEMENT",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "targeting": json.dumps({
                # Smart Audience — let Meta auto-target based on page engagement
                "geo_locations": {"countries": ["US", "GB", "CA", "AU", "IN"]},
                "age_min": 18,
                "age_max": 65,
            }),
            "status": "ACTIVE",
            "end_time": end_time,
        },
        timeout=20,
    )
    if adset_resp.status_code != 200:
        return {
            "status": "error",
            "ad_id": None,
            "campaign_id": campaign_id,
            "error": f"AdSet create failed: {adset_resp.status_code} — {adset_resp.text[:300]}",
        }
    adset_id = adset_resp.json()["id"]

    # Step 3: Create ad (the creative — pointer to our existing post)
    # object_story_id format: "{page_id}_{post_id_suffix}" — but we already have full
    ad_resp = requests.post(
        f"{GRAPH_API}/{ad_account_id}/ads",
        params={"access_token": token},
        data={
            "name": f"Auto-boost Ad {post_id[-8:]}",
            "adset_id": adset_id,
            "creative": json.dumps({
                "object_story_id": post_id,
            }),
            "status": "ACTIVE",
        },
        timeout=20,
    )
    if ad_resp.status_code != 200:
        return {
            "status": "error",
            "ad_id": None,
            "campaign_id": campaign_id,
            "adset_id": adset_id,
            "error": f"Ad create failed: {ad_resp.status_code} — {ad_resp.text[:300]}",
        }
    ad_id = ad_resp.json()["id"]

    return {
        "status": "ok",
        "ad_id": ad_id,
        "campaign_id": campaign_id,
        "adset_id": adset_id,
        "breakdown": f"Boosted for ₹{budget}/day × {days}d. View in Ads Manager.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't actually create the ad — just log what would happen")
    args = parser.parse_args()

    # ── Load history & enforce daily caps ────────────────────────────────────
    history = _load_history()
    today = _today_utc()
    today_spent = _today_spent(history)
    today_count = _today_boost_count(history)

    if today_spent >= DAILY_BUDGET_CAP:
        print(f"[auto-boost] 🛑 Already spent ₹{today_spent} today (cap: ₹{DAILY_BUDGET_CAP}) — skipping")
        sys.exit(0)
    if today_count >= DAILY_BOOST_LIMIT:
        print(f"[auto-boost] 🛑 Already boosted {today_count} post(s) today (limit: {DAILY_BOOST_LIMIT}) — skipping")
        sys.exit(0)

    # ── Read the top candidate from today's brief ────────────────────────────
    candidate = _parse_top_candidate_from_brief()
    if not candidate:
        print(f"[auto-boost] No candidate in today's brief — nothing to boost")
        sys.exit(0)

    budget = min(candidate["suggested_budget"], DAILY_BUDGET_CAP - today_spent)
    print(f"[auto-boost] Candidate: {candidate['message_preview'][:60]}")
    print(f"[auto-boost] Budget: ₹{budget} (suggested: ₹{candidate['suggested_budget']}, "
          f"cap remaining: ₹{DAILY_BUDGET_CAP - today_spent})")

    # ── Resolve ad account + token ───────────────────────────────────────────
    page_id, token = _get_page_token()
    if not token:
        print(f"[auto-boost] ❌ FB_PAGE_ACCESS_TOKEN missing — cannot proceed")
        sys.exit(1)

    ad_account_id = os.environ.get("FB_AD_ACCOUNT_ID")
    if not ad_account_id:
        detected, err = _autodetect_ad_account(token)
        if detected:
            ad_account_id = detected
            print(f"[auto-boost] Auto-detected ad account: {ad_account_id}")
        else:
            print(f"[auto-boost] ❌ FB_AD_ACCOUNT_ID not set and couldn't auto-detect: {err}")
            print(f"[auto-boost]    Find your ad account at https://business.facebook.com/settings/ad-accounts")
            print(f"[auto-boost]    Then: gh secret set FB_AD_ACCOUNT_ID -b 'act_XXXXXXXXX'")
            sys.exit(1)
    elif not ad_account_id.startswith("act_"):
        ad_account_id = f"act_{ad_account_id}"

    # ── Create the boost ────────────────────────────────────────────────────
    print(f"[auto-boost] Creating boost on ad account {ad_account_id}...")
    result = create_boost(
        post_id=candidate["post_id"],
        page_id=page_id,
        ad_account_id=ad_account_id,
        token=token,
        budget=budget,
        days=PER_BOOST_DURATION_DAYS,
        dry_run=args.dry_run,
    )

    # ── Record in history ────────────────────────────────────────────────────
    entry = {
        "date": today,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "post_id": candidate["post_id"],
        "message_preview": candidate["message_preview"][:80],
        "budget": budget if result["status"] == "ok" else 0,
        "currency": AD_CURRENCY,
        "status": result["status"],
        "ad_id": result.get("ad_id"),
        "campaign_id": result.get("campaign_id"),
        "adset_id": result.get("adset_id"),
        "error": result.get("error"),
        "dry_run": args.dry_run,
    }
    history["boosts"].append(entry)
    history["boosts"] = history["boosts"][-100:]  # keep last 100
    _save_history(history)

    # ── Final report ─────────────────────────────────────────────────────────
    if result["status"] == "ok":
        print(f"[auto-boost] ✅ Boost created. Ad ID: {result['ad_id']}")
        print(f"[auto-boost]    Today's spend: ₹{today_spent + budget} / ₹{DAILY_BUDGET_CAP}")
        print(f"[auto-boost]    View: https://www.facebook.com/ads/manager/")
    else:
        print(f"[auto-boost] ❌ Boost failed: {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
