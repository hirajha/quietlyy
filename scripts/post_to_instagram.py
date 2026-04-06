"""
Quietlyy — Instagram Reels Poster
Posts directly to Instagram via Graph API resumable upload.
No public video URL needed — uploads bytes directly like Facebook.

Uses: INSTAGRAM_USER_ID + FB_PAGE_ACCESS_TOKEN (System User token)
"""

import os
import time
import requests

GRAPH_API = "https://graph.facebook.com/v22.0"


def get_credentials():
    ig_user_id = os.environ.get("INSTAGRAM_USER_ID")
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not ig_user_id or not token:
        raise ValueError("INSTAGRAM_USER_ID and FB_PAGE_ACCESS_TOKEN must be set")
    return ig_user_id, token


def post(video_path, caption):
    """Post a Reel directly to Instagram via resumable upload."""
    ig_user_id, token = get_credentials()

    print(f"[instagram] Starting Reel upload (ig_user_id={ig_user_id})...")

    # Step 1: Create media container (resumable)
    init_resp = requests.post(
        f"{GRAPH_API}/{ig_user_id}/media",
        params={"access_token": token},
        json={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
        },
        timeout=30,
    )
    _raise_with_body(init_resp)
    init_data = init_resp.json()
    container_id = init_data.get("id")
    upload_uri = init_data.get("uri")

    if not container_id or not upload_uri:
        raise ValueError(f"Instagram did not return container id/uri: {init_data}")

    print(f"[instagram] Container created: {container_id}")

    # Step 2: Upload video bytes to rupload URI
    file_size = os.path.getsize(video_path)
    print(f"[instagram] Uploading {file_size // 1024} KB...")
    with open(video_path, "rb") as f:
        upload_resp = requests.post(
            upload_uri,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "video/mp4",
            },
            data=f,
            timeout=300,
        )
    _raise_with_body(upload_resp)
    print("[instagram] Upload complete — waiting for processing...")

    # Step 3: Poll until container status = FINISHED (max 3 min)
    for attempt in range(18):  # 18 x 10s = 3 min
        time.sleep(10)
        status_resp = requests.get(
            f"{GRAPH_API}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=15,
        )
        status_data = status_resp.json()
        status_code = status_data.get("status_code", "")
        print(f"[instagram] Status ({attempt + 1}/18): {status_code}")

        if status_code == "FINISHED":
            break
        elif status_code == "ERROR":
            raise ValueError(f"Instagram container processing failed: {status_data}")
    else:
        raise TimeoutError("Instagram container processing timed out after 3 minutes")

    # Step 4: Publish
    print("[instagram] Publishing Reel...")
    pub_resp = requests.post(
        f"{GRAPH_API}/{ig_user_id}/media_publish",
        params={"access_token": token},
        json={"creation_id": container_id},
        timeout=30,
    )
    _raise_with_body(pub_resp)
    result = pub_resp.json()
    media_id = result.get("id", container_id)
    print(f"[instagram] Reel published! Media ID: {media_id}")
    return {"id": media_id, "platform": "instagram"}


def _raise_with_body(resp):
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise requests.HTTPError(
            f"{e} | API response: {resp.text[:500]}", response=resp
        ) from e
