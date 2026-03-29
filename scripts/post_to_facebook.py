"""
Quietlyy — Facebook Poster
Posts video as a Reel to the Quietlyy Facebook Page via Graph API.
"""

import os
import json
import time
import requests

GRAPH_API = "https://graph.facebook.com/v22.0"


def get_credentials():
    page_id = os.environ.get("FB_PAGE_ID")
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not page_id or not token:
        raise ValueError("FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN must be set")
    return page_id, token


def post_reel(video_path, description):
    """
    Post a video as a Facebook Reel (3-step process):
    1. Initialize upload
    2. Upload video file
    3. Publish
    """
    page_id, token = get_credentials()

    # Step 1: Initialize upload
    print("[facebook] Initializing Reel upload...")
    init_resp = requests.post(
        f"{GRAPH_API}/{page_id}/video_reels",
        params={"access_token": token},
        json={"upload_phase": "start"},
    )
    init_resp.raise_for_status()
    video_id = init_resp.json()["video_id"]
    print(f"[facebook] Video ID: {video_id}")

    # Step 2: Upload video file
    print("[facebook] Uploading video...")
    file_size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        upload_resp = requests.post(
            f"{GRAPH_API}/{video_id}",
            params={"access_token": token},
            headers={
                "offset": "0",
                "file_size": str(file_size),
            },
            data=f,
        )
    upload_resp.raise_for_status()
    print("[facebook] Upload complete")

    # Step 3: Publish
    print("[facebook] Publishing Reel...")
    publish_resp = requests.post(
        f"{GRAPH_API}/{page_id}/video_reels",
        params={"access_token": token},
        json={
            "upload_phase": "finish",
            "video_id": video_id,
            "title": "Quietlyy",
            "description": description,
        },
    )
    publish_resp.raise_for_status()
    result = publish_resp.json()
    print(f"[facebook] Published! Post ID: {result.get('id', 'unknown')}")
    return result


def post_video(video_path, description):
    """
    Alternative: Post as a regular Page video (simpler, more reliable).
    Falls back to this if Reel posting fails.
    """
    page_id, token = get_credentials()

    print("[facebook] Uploading as Page video...")
    with open(video_path, "rb") as f:
        resp = requests.post(
            f"{GRAPH_API}/{page_id}/videos",
            params={"access_token": token},
            files={"source": ("quietlyy.mp4", f, "video/mp4")},
            data={
                "description": description,
                "title": "Quietlyy",
            },
            timeout=120,
        )
    resp.raise_for_status()
    result = resp.json()
    print(f"[facebook] Posted! Video ID: {result.get('id', 'unknown')}")
    return result


def build_description(topic, script_text):
    """Build the Facebook post description."""
    # Clean up script for caption
    lines = [line.strip() for line in script_text.split("\n") if line.strip()]
    caption = "\n".join(lines)

    return (
        f"{caption}\n\n"
        f"— Quietlyy\n\n"
        f"#Quietlyy #{topic.replace(' ', '')} #nostalgia #memories "
        f"#deepthoughts #lifequotes #reflection"
    )


def post(video_path, topic, script_text):
    """Main entry: post video to Facebook, trying Reel first then regular video."""
    description = build_description(topic, script_text)

    # Try Reel first
    try:
        return post_reel(video_path, description)
    except Exception as e:
        print(f"[facebook] Reel posting failed: {e}")
        print("[facebook] Falling back to regular video post...")

    # Fallback to regular video
    return post_video(video_path, description)


if __name__ == "__main__":
    print("Facebook poster ready. Run via pipeline.py")
    print("Required env vars: FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN")
