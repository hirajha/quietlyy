"""
Quietlyy — Quote Photo Poster

Posts a 3-slide carousel quote post to:
  1. Facebook Page — album/multi-photo post (counts as a Page Post)
  2. Instagram — carousel media (3.1x more engagement than single image)

Carousel format dramatically outperforms single images:
  - 3.1x more engagement than single static posts
  - 109% more engagement per person than Reels
  - Each swipe = additional engagement signal to algorithm
"""

import os
import json
import random
import requests
import time

GRAPH_API = "https://graph.facebook.com/v22.0"


# ── Caption builders ──────────────────────────────────────────────────────────
# Research-backed: question CTAs get 70% more comments; specific CTAs 3x better than generic.
# Short captions (under 125 chars) perform best on Instagram.
# Sends/DM shares weighted 3-5x higher by algorithm than likes.

FACEBOOK_CAPTION_TEMPLATES = [
    "{quote}\n\nSwipe to read the rest. 👉\n\n💙 Who needed to hear this today? Tag them.\n\n#deepquotes #emotionalhealing #lifequotes #wordsthatheal #quietlyy",
    "{quote}\n\nSwipe 👉 There's more.\n\nTag someone this was written for. 💙\n\n#deepthoughts #soulquotes #healingquotes #wordsofwisdom #quietlyy",
    "{quote}\n\nSwipe 👉\n\n📩 Send this to the person you're thinking about right now.\n\n#lifequotes #reallife #emotionalquotes #deepquotes #quietlyy",
    "{quote}\n\nSwipe 👉 You'll feel this one.\n\n💙 Does this hit? Drop a ❤️ if it does.\n\n#wordsthatheal #mentalhealth #selfworth #quotestoliveby #quietlyy",
    "{quote}\n\nSwipe 👉\n\nRead it twice. Some truths take a moment. 💫\n\n#deepthoughts #soulquotes #healingjourney #lifequotes #quietlyy",
]

INSTAGRAM_CAPTION_TEMPLATES = [
    "{quote}\n\nSwipe 👉 for more.\n\n📩 Send this to someone who needs it.\n💾 Save — you'll need it one day.\n\n#emotionalhealing #deepquotes #lifequotes #wordsthatheal #quotestagram #soulquotes #quietlyy",
    "{quote}\n\nSwipe 👉\n\n❤️ Tag who this is for.\n\n#lifelesson #deepwords #emotionalquotes #instaquote #healingquotes #quotestoliveby #quietlyy",
    "{quote}\n\n👉 Swipe — it gets deeper.\n\n💾 Save this. You'll need it one day.\n📩 Share it with someone carrying too much.\n\n#deepthoughts #realtalk #soulquotes #lifequotes #quietlyy",
    "{quote}\n\nSwipe 👉\n\nDoes this hit close? 💙\nDrop a comment — I want to know.\n\n#emotionalhealing #deepquotes #selflove #healingvibes #quotestagram #quietlyy",
]


def _build_caption(quote, templates):
    return random.choice(templates).format(quote=quote)


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


# ── Facebook Multi-Photo (Album) Post ─────────────────────────────────────────

def post_to_facebook(image_paths, quote):
    """
    Post carousel as Facebook multi-photo album post.
    Steps: upload each image as unpublished photo → post feed with attached_media.
    This counts as a Page Post and appears in the Posts section.
    Returns (success, result_dict).
    """
    try:
        page_id, raw_token = _get_fb_credentials()
        token = _get_page_token(page_id, raw_token)
        caption = _build_caption(quote, FACEBOOK_CAPTION_TEMPLATES)

        # Upload each slide as unpublished photo
        photo_ids = []
        for i, img_path in enumerate(image_paths):
            print(f"[quote_photo] Uploading slide {i+1}/{len(image_paths)} to Facebook...")
            with open(img_path, "rb") as f:
                resp = requests.post(
                    f"{GRAPH_API}/{page_id}/photos",
                    params={"access_token": token},
                    files={"source": (os.path.basename(img_path), f, "image/jpeg")},
                    data={"published": "false"},
                    timeout=60,
                )
            if resp.status_code != 200:
                print(f"[quote_photo] Slide {i+1} upload failed: {resp.text[:200]}")
                continue
            photo_ids.append(resp.json().get("id"))

        if not photo_ids:
            return False, {"platform": "facebook", "status": "failed", "error": "no photos uploaded"}

        # Create multi-photo post (album) — appears as a regular post with multiple images
        attached = [{"media_fbid": pid} for pid in photo_ids if pid]
        post_resp = requests.post(
            f"{GRAPH_API}/{page_id}/feed",
            params={"access_token": token},
            data={
                "message": caption,
                "attached_media": json.dumps(attached),
            },
            timeout=30,
        )

        if post_resp.status_code == 200:
            post_id = post_resp.json().get("id", "unknown")
            print(f"[quote_photo] Facebook carousel posted! ID: {post_id} ({len(photo_ids)} slides)")
            return True, {"platform": "facebook", "post_id": post_id, "status": "posted", "slides": len(photo_ids)}
        else:
            print(f"[quote_photo] Facebook post failed: {post_resp.status_code} {post_resp.text[:300]}")
            # Fallback: post first image as single photo
            return _post_facebook_single(image_paths[0], caption, page_id, token)

    except Exception as e:
        print(f"[quote_photo] Facebook post error: {e}")
        return False, {"platform": "facebook", "status": "error", "error": str(e)}


def _post_facebook_single(image_path, caption, page_id, token):
    """Fallback: single photo post if multi-photo fails."""
    try:
        with open(image_path, "rb") as f:
            resp = requests.post(
                f"{GRAPH_API}/{page_id}/photos",
                params={"access_token": token},
                files={"source": ("quote_image.jpg", f, "image/jpeg")},
                data={"message": caption},
                timeout=60,
            )
        if resp.status_code == 200:
            post_id = resp.json().get("id", "unknown")
            print(f"[quote_photo] Facebook single photo posted (fallback)! ID: {post_id}")
            return True, {"platform": "facebook", "post_id": post_id, "status": "posted_single"}
        return False, {"platform": "facebook", "status": "failed", "error": resp.text[:200]}
    except Exception as e:
        return False, {"platform": "facebook", "status": "error", "error": str(e)}


# ── Instagram Carousel Post ───────────────────────────────────────────────────

def _upload_to_fb_cdn(image_path, page_id, token):
    """Upload image as unpublished Facebook photo and return its CDN URL."""
    with open(image_path, "rb") as f:
        resp = requests.post(
            f"{GRAPH_API}/{page_id}/photos",
            params={"access_token": token},
            files={"source": (os.path.basename(image_path), f, "image/jpeg")},
            data={"published": "false"},
            timeout=60,
        )
    if resp.status_code != 200:
        return None
    photo_id = resp.json().get("id")
    url_resp = requests.get(
        f"{GRAPH_API}/{photo_id}",
        params={"access_token": token, "fields": "images"},
        timeout=15,
    )
    images = url_resp.json().get("images", [])
    if not images:
        return None
    return sorted(images, key=lambda x: x.get("width", 0), reverse=True)[0]["source"]


def post_to_instagram(image_paths, quote):
    """
    Post quote carousel to Instagram via Graph API.
    Steps: upload slides to FB CDN → create IG carousel container → publish.
    Returns (success, result_dict).
    """
    ig_user_id = os.environ.get("INSTAGRAM_USER_ID")
    if not ig_user_id:
        print("[quote_photo] INSTAGRAM_USER_ID not set — skipping Instagram")
        return False, {"platform": "instagram", "status": "skipped", "reason": "no credentials"}

    try:
        page_id, raw_token = _get_fb_credentials()
        token = _get_page_token(page_id, raw_token)
        caption = _build_caption(quote, INSTAGRAM_CAPTION_TEMPLATES)

        # Step 1: Upload each slide to Facebook CDN to get public URLs
        image_urls = []
        for i, img_path in enumerate(image_paths):
            print(f"[quote_photo] Getting CDN URL for slide {i+1}...")
            url = _upload_to_fb_cdn(img_path, page_id, token)
            if url:
                image_urls.append(url)

        if not image_urls:
            return False, {"platform": "instagram", "status": "failed", "error": "cdn_upload_failed"}

        # Step 2: Create carousel child containers
        child_ids = []
        for i, img_url in enumerate(image_urls):
            child_resp = requests.post(
                f"{GRAPH_API}/{ig_user_id}/media",
                params={"access_token": token},
                data={"image_url": img_url, "is_carousel_item": "true"},
                timeout=30,
            )
            if child_resp.status_code == 200:
                child_ids.append(child_resp.json().get("id"))
            else:
                print(f"[quote_photo] IG child {i+1} creation failed: {child_resp.text[:150]}")

        if not child_ids:
            return False, {"platform": "instagram", "status": "failed", "error": "no_carousel_children"}

        # Step 3: Create carousel container
        carousel_resp = requests.post(
            f"{GRAPH_API}/{ig_user_id}/media",
            params={"access_token": token},
            data={
                "media_type": "CAROUSEL",
                "children": ",".join(child_ids),
                "caption": caption,
            },
            timeout=30,
        )
        if carousel_resp.status_code != 200:
            print(f"[quote_photo] IG carousel container failed: {carousel_resp.text[:200]}")
            return False, {"platform": "instagram", "status": "failed", "error": carousel_resp.text[:200]}

        container_id = carousel_resp.json().get("id")

        # Step 4: Publish
        time.sleep(3)
        publish_resp = requests.post(
            f"{GRAPH_API}/{ig_user_id}/media_publish",
            params={"access_token": token},
            data={"creation_id": container_id},
            timeout=30,
        )

        if publish_resp.status_code == 200:
            ig_id = publish_resp.json().get("id", "unknown")
            print(f"[quote_photo] Instagram carousel posted! ID: {ig_id} ({len(child_ids)} slides)")
            return True, {"platform": "instagram", "post_id": ig_id, "status": "posted", "slides": len(child_ids)}
        else:
            print(f"[quote_photo] IG publish failed: {publish_resp.text[:200]}")
            return False, {"platform": "instagram", "status": "failed", "error": publish_resp.text[:200]}

    except Exception as e:
        print(f"[quote_photo] Instagram post error: {e}")
        return False, {"platform": "instagram", "status": "error", "error": str(e)}


# ── Main entry ────────────────────────────────────────────────────────────────

def post(image_paths, quote, skip_post=False):
    """
    Post quote carousel to Facebook and Instagram.
    image_paths: list of slide image paths (3 slides).
                 Also accepts a single string path for backwards compat.
    Returns dict of results per platform.
    """
    if isinstance(image_paths, str):
        image_paths = [image_paths]

    results = {}

    if skip_post:
        print("[quote_photo] skip_post=True — skipping social posting")
        return results

    fb_ok, fb_result = post_to_facebook(image_paths, quote)
    results["facebook"] = fb_result

    ig_ok, ig_result = post_to_instagram(image_paths, quote)
    results["instagram"] = ig_result

    return results
