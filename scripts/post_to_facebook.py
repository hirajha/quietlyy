"""
Quietlyy — Facebook/Instagram Poster
3-layer fallback: Facebook Reel → Facebook Video → Instagram Reel
Since FB and IG are linked, posting to one auto-posts to both.
Uses whichever works first.
"""

import os
import json
import requests

GRAPH_API = "https://graph.facebook.com/v22.0"


def get_credentials():
    page_id = os.environ.get("FB_PAGE_ID")
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not page_id or not token:
        raise ValueError("FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN must be set")
    return page_id, token


def build_description(topic, script_text):
    """Build the post description/caption."""
    lines = [line.strip() for line in script_text.split("\n") if line.strip()]
    caption = "\n".join(lines)

    return (
        f"{caption}\n\n"
        f"— Quietlyy\n\n"
        f"#Quietlyy #{topic.replace(' ', '')} #nostalgia #memories "
        f"#deepthoughts #lifequotes #reflection #lostmoments"
    )


# ── Layer 1: Facebook Reel (best reach) ──
def post_as_reel(video_path, description):
    page_id, token = get_credentials()

    # Step 1: Initialize
    print("[facebook] Layer 1: Initializing Reel upload...")
    init_resp = requests.post(
        f"{GRAPH_API}/{page_id}/video_reels",
        params={"access_token": token},
        json={"upload_phase": "start"},
    )
    init_resp.raise_for_status()
    video_id = init_resp.json()["video_id"]

    # Step 2: Upload
    print(f"[facebook] Uploading video (ID: {video_id})...")
    file_size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        upload_resp = requests.post(
            f"{GRAPH_API}/{video_id}",
            params={"access_token": token},
            headers={"offset": "0", "file_size": str(file_size)},
            data=f,
        )
    upload_resp.raise_for_status()

    # Step 3: Publish (optionally cross-post to Instagram simultaneously)
    print("[facebook] Publishing Reel...")
    publish_payload = {
        "upload_phase": "finish",
        "video_id": video_id,
        "title": "Quietlyy",
        "description": description,
    }
    ig_user_id = os.environ.get("INSTAGRAM_USER_ID")
    if ig_user_id:
        publish_payload["instagram_user_id"] = ig_user_id
        print("[facebook] Cross-posting to Instagram...")

    publish_resp = requests.post(
        f"{GRAPH_API}/{page_id}/video_reels",
        params={"access_token": token},
        json=publish_payload,
    )
    publish_resp.raise_for_status()
    result = publish_resp.json()
    if ig_user_id:
        print(f"[facebook] Reel posted to Facebook + Instagram! ID: {result.get('id', video_id)}")
    else:
        print(f"[facebook] Reel posted to Facebook! ID: {result.get('id', video_id)}")
    return result


# ── Layer 2: Facebook Page Video (uses pages_manage_posts, no publish_video needed) ──
def post_as_video(video_path, description):
    page_id, token = get_credentials()

    print("[facebook] Layer 2: Uploading as Page video...")
    with open(video_path, "rb") as f:
        resp = requests.post(
            f"{GRAPH_API}/{page_id}/videos",
            params={"access_token": token},
            files={"source": ("quietlyy.mp4", f, "video/mp4")},
            data={"description": description, "title": "Quietlyy"},
            timeout=120,
        )
    resp.raise_for_status()
    result = resp.json()
    print(f"[facebook] Video posted! ID: {result.get('id', 'unknown')}")
    return result


# ── Layer 3: Save for manual upload ──
def save_for_manual(video_path, description):
    """If all API methods fail, save the caption for manual upload."""
    output_dir = os.path.dirname(video_path)
    caption_path = os.path.join(output_dir, "manual_caption.txt")
    with open(caption_path, "w") as f:
        f.write(description)
    print(f"[facebook] Layer 3: Saved for manual upload")
    print(f"[facebook] Video: {video_path}")
    print(f"[facebook] Caption: {caption_path}")
    return {"status": "manual", "video": video_path, "caption": caption_path}


def post(video_path, topic, script_text):
    """Main entry: post video with 3-layer fallback."""
    description = build_description(topic, script_text)

    layers = [
        (post_as_reel, "Facebook Reel"),
        (post_as_video, "Facebook Video"),
    ]

    for layer_fn, name in layers:
        try:
            return layer_fn(video_path, description)
        except Exception as e:
            print(f"[facebook] {name} failed: {e}")

    # Layer 3: always works
    return save_for_manual(video_path, description)


if __name__ == "__main__":
    print("Facebook poster ready. Run via pipeline.py")
    print("Required env vars: FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN")
