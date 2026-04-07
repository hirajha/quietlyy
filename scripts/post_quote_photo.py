"""
Quietlyy — Quote Photo Poster

Posts a static quote image to:
  1. Facebook Page (photo post — highest save/share rate for this format)
  2. Instagram (via Graph API — two-step container + publish)
"""

import os
import json
import random
import requests

GRAPH_API = "https://graph.facebook.com/v22.0"

# ── Caption builders ──────────────────────────────────────────────────────────

FACEBOOK_CAPTION_TEMPLATES = [
    "{quote}\n\n📩 Send this to someone who needs to hear it today.\n💾 Save this — you might need it later.\n\n#deepthoughts #lifequotes #emotionalhealing #wordsthatheal #quietlyy",
    "{quote}\n\n❤️ Tag someone this speaks to.\n\nSome truths are worth saving. 💾\n\n#lifelesson #healingquotes #wordsofwisdom #soulquotes #quietlyy",
    "{quote}\n\n📩 Share this with someone you're thinking of right now.\n\n#deepquotes #reallife #emotionalquotes #lifequotes #quietlyy",
    "{quote}\n\n💙 Who needed to read this today?\nTag them or send it in a DM.\n\n#wordsthatheal #mentalhealth #selfworth #quotestoliveby #quietlyy",
    "{quote}\n\nRead it twice. 💫\n📩 Someone in your life needs this right now.\n\n#deepthoughts #soulquotes #healingjourney #lifequotes #quietlyy",
]

INSTAGRAM_CAPTION_TEMPLATES = [
    "{quote}\n\n📩 Send this to someone who needs it.\n💾 Save for when you forget.\n\n#emotionalhealing #deepquotes #lifequotes #wordsthatheal #quotestagram #healingjourney #soulquotes #selflove #deepthoughts #quietlyy",
    "{quote}\n\n❤️ Tag someone this is for.\n\n#lifelesson #deepwords #emotionalquotes #instaquote #wordsofwisdom #healingquotes #quotestoliveby #mentalhealth #quietlyy",
    "{quote}\n\nSave this. You'll need it one day. 💾\n📩 Share it with someone carrying too much.\n\n#deepthoughts #realtalk #soulquotes #lifequotes #selfworth #healingvibes #quotestagram #quietlyy",
]



def _build_caption(quote, platform, templates):
    template = random.choice(templates)
    return template.format(quote=quote)


# ── Credentials ───────────────────────────────────────────────────────────────

def _get_fb_credentials():
    page_id = os.environ.get("FB_PAGE_ID")
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not page_id or not token:
        raise ValueError("FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN must be set")
    return page_id, token


def _get_page_token(page_id, token):
    resp = requests.get(
        f"{GRAPH_API}/{page_id}",
        params={"access_token": token, "fields": "access_token"},
        timeout=10,
    )
    if resp.status_code == 200:
        page_token = resp.json().get("access_token")
        if page_token and page_token != token:
            return page_token
    return token


# ── Facebook Photo Post ───────────────────────────────────────────────────────

def post_to_facebook(image_path, quote):
    """Post quote image as Facebook photo post. Returns (success, result_dict)."""
    try:
        page_id, raw_token = _get_fb_credentials()
        token = _get_page_token(page_id, raw_token)
        caption = _build_caption(quote, "facebook", FACEBOOK_CAPTION_TEMPLATES)

        print(f"[quote_photo] Posting photo to Facebook page {page_id}...")
        with open(image_path, "rb") as f:
            resp = requests.post(
                f"{GRAPH_API}/{page_id}/photos",
                params={"access_token": token},
                files={"source": ("quote_image.jpg", f, "image/jpeg")},
                data={"message": caption},
                timeout=60,
            )

        if resp.status_code == 200:
            result = resp.json()
            post_id = result.get("id", "unknown")
            print(f"[quote_photo] Facebook photo posted! ID: {post_id}")
            return True, {"platform": "facebook", "post_id": post_id, "status": "posted"}
        else:
            print(f"[quote_photo] Facebook photo post failed: {resp.status_code} {resp.text[:300]}")
            return False, {"platform": "facebook", "status": "failed", "error": resp.text[:300]}

    except Exception as e:
        print(f"[quote_photo] Facebook post error: {e}")
        return False, {"platform": "facebook", "status": "error", "error": str(e)}


# ── Instagram Photo Post ──────────────────────────────────────────────────────

def post_to_instagram(image_path, quote):
    """
    Post quote image to Instagram via Graph API.
    Step 1: Upload image to Facebook CDN (unpublished photo) → get URL
    Step 2: Create IG media container with that URL
    Step 3: Publish container
    Returns (success, result_dict).
    """
    ig_user_id = os.environ.get("INSTAGRAM_USER_ID")
    if not ig_user_id:
        print("[quote_photo] INSTAGRAM_USER_ID not set — skipping Instagram")
        return False, {"platform": "instagram", "status": "skipped", "reason": "no credentials"}

    try:
        page_id, raw_token = _get_fb_credentials()
        token = _get_page_token(page_id, raw_token)
        caption = _build_caption(quote, "instagram", INSTAGRAM_CAPTION_TEMPLATES)

        # Step 1: Upload to Facebook as unpublished photo to get CDN URL
        print("[quote_photo] Uploading image to Facebook CDN for Instagram...")
        with open(image_path, "rb") as f:
            fb_resp = requests.post(
                f"{GRAPH_API}/{page_id}/photos",
                params={"access_token": token},
                files={"source": ("quote_image.jpg", f, "image/jpeg")},
                data={"published": "false"},  # unpublished — just to get URL
                timeout=60,
            )

        if fb_resp.status_code != 200:
            print(f"[quote_photo] Could not upload to Facebook CDN: {fb_resp.text[:200]}")
            return False, {"platform": "instagram", "status": "failed", "error": "cdn_upload_failed"}

        photo_id = fb_resp.json().get("id")

        # Get the CDN URL of the uploaded photo
        url_resp = requests.get(
            f"{GRAPH_API}/{photo_id}",
            params={"access_token": token, "fields": "images"},
            timeout=15,
        )
        images = url_resp.json().get("images", [])
        if not images:
            print("[quote_photo] Could not get Facebook CDN URL for Instagram")
            return False, {"platform": "instagram", "status": "failed", "error": "no_cdn_url"}

        # Use the largest available image
        image_url = sorted(images, key=lambda x: x.get("width", 0), reverse=True)[0]["source"]
        print(f"[quote_photo] Got CDN URL for Instagram posting")

        # Step 2: Create Instagram media container
        container_resp = requests.post(
            f"{GRAPH_API}/{ig_user_id}/media",
            params={"access_token": token},
            data={"image_url": image_url, "caption": caption},
            timeout=30,
        )

        if container_resp.status_code != 200:
            print(f"[quote_photo] IG container creation failed: {container_resp.text[:200]}")
            return False, {"platform": "instagram", "status": "failed", "error": container_resp.text[:200]}

        container_id = container_resp.json().get("id")

        # Step 3: Publish
        import time
        time.sleep(3)  # Brief pause before publishing
        publish_resp = requests.post(
            f"{GRAPH_API}/{ig_user_id}/media_publish",
            params={"access_token": token},
            data={"creation_id": container_id},
            timeout=30,
        )

        if publish_resp.status_code == 200:
            ig_id = publish_resp.json().get("id", "unknown")
            print(f"[quote_photo] Instagram photo posted! ID: {ig_id}")
            return True, {"platform": "instagram", "post_id": ig_id, "status": "posted"}
        else:
            print(f"[quote_photo] IG publish failed: {publish_resp.text[:200]}")
            return False, {"platform": "instagram", "status": "failed", "error": publish_resp.text[:200]}

    except Exception as e:
        print(f"[quote_photo] Instagram post error: {e}")
        return False, {"platform": "instagram", "status": "error", "error": str(e)}


# ── Main entry ────────────────────────────────────────────────────────────────

def post(image_path, quote, skip_post=False):
    """
    Post quote image to Facebook and Instagram.
    Returns dict of results per platform.
    """
    results = {}

    if skip_post:
        print("[quote_photo] skip_post=True — skipping social posting")
        return results

    # Facebook
    fb_ok, fb_result = post_to_facebook(image_path, quote)
    results["facebook"] = fb_result

    # Instagram
    ig_ok, ig_result = post_to_instagram(image_path, quote)
    results["instagram"] = ig_result

    return results
