"""
Quietlyy — Facebook Token Tester
Quick pre-flight: verifies FB_PAGE_ACCESS_TOKEN and FB_PAGE_ID are working.
Run: python scripts/test_facebook_token.py
"""

import os
import sys
import requests

GRAPH_API = "https://graph.facebook.com/v22.0"


def test_token():
    page_id = os.environ.get("FB_PAGE_ID")
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN")

    if not page_id or not token:
        print("ERROR: FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN must be set")
        print("  export FB_PAGE_ID=your_page_id")
        print("  export FB_PAGE_ACCESS_TOKEN=your_token")
        sys.exit(1)

    print(f"Testing Facebook credentials...")
    print(f"  Page ID: {page_id}")
    print(f"  Token: {token[:20]}...{token[-6:]}")
    print()

    # 1. Check token validity
    resp = requests.get(
        f"{GRAPH_API}/me",
        params={"access_token": token, "fields": "name,id,type"},
        timeout=10,
    )
    data = resp.json()
    if resp.status_code != 200 or "error" in data:
        err = data.get("error", {})
        print(f"FAIL: Token invalid")
        print(f"  Code: {err.get('code')} / Subcode: {err.get('error_subcode')}")
        print(f"  Message: {err.get('message')}")
        if err.get('error_subcode') == 467:
            print()
            print("  FIX: Token expired because you logged out of Facebook.")
            print("  Get a new token at: developers.facebook.com/tools/explorer")
            print("  1. Select 'User Token' → Generate Access Token")
            print("  2. Call GET /me/accounts → copy your page's access_token")
            print("  3. Extend at: developers.facebook.com/tools/debug/accesstoken")
        sys.exit(1)

    print(f"OK: Token valid — {data.get('name')} (type: {data.get('type', 'user')})")

    # 2. Check page access
    resp2 = requests.get(
        f"{GRAPH_API}/{page_id}",
        params={"access_token": token, "fields": "name,id,fan_count,category"},
        timeout=10,
    )
    data2 = resp2.json()
    if resp2.status_code != 200 or "error" in data2:
        err = data2.get("error", {})
        print(f"FAIL: Cannot access page {page_id}")
        print(f"  {err.get('message')}")
        print()
        print("  FIX: Make sure FB_PAGE_ID is the numeric Page ID.")
        print("  Get it from: GET /me/accounts (look for your page in the list)")
        sys.exit(1)

    print(f"OK: Page found — '{data2.get('name')}' ({data2.get('fan_count', 0):,} followers, {data2.get('category', '?')})")

    # 3. Check video_reels permission
    resp3 = requests.get(
        f"{GRAPH_API}/me/permissions",
        params={"access_token": token},
        timeout=10,
    )
    perms_data = resp3.json().get("data", [])
    granted = {p["permission"] for p in perms_data if p.get("status") == "granted"}
    needed = {"pages_manage_posts", "pages_read_engagement"}
    missing = needed - granted

    if missing:
        print(f"WARN: Missing permissions: {', '.join(missing)}")
        print("  Re-generate the token with these permissions checked.")
    else:
        print(f"OK: Permissions granted — {', '.join(sorted(granted))}")

    # 4. Token expiry
    debug_resp = requests.get(
        f"{GRAPH_API}/debug_token",
        params={"input_token": token, "access_token": token},
        timeout=10,
    )
    debug = debug_resp.json().get("data", {})
    expires_at = debug.get("expires_at", 0)
    if expires_at == 0:
        print("OK: Token never expires (permanent / System User token)")
    elif expires_at > 0:
        import datetime
        exp = datetime.datetime.fromtimestamp(expires_at)
        days_left = (exp - datetime.datetime.now()).days
        if days_left < 7:
            print(f"WARN: Token expires in {days_left} days ({exp.strftime('%Y-%m-%d')})")
            print("  Extend at: developers.facebook.com/tools/debug/accesstoken")
        else:
            print(f"OK: Token valid for {days_left} more days (expires {exp.strftime('%Y-%m-%d')})")

    print()
    print("All checks passed! Facebook posting should work.")


if __name__ == "__main__":
    test_token()
