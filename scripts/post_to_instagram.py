"""
Quietlyy — Instagram Reels Poster
Posts directly to Instagram via Graph API resumable upload.

SETUP CHECKLIST (both required):
1. developers.facebook.com → Your App → App Review → Permissions and Features
   → Add: instagram_basic, instagram_content_publish (click Request)
2. Meta Business Manager → System Users → Generate New Token
   → Check: instagram_basic, instagram_content_publish
   → Update FB_PAGE_ACCESS_TOKEN secret in GitHub
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


def _check_meta_error(resp_data, context=""):
    """Raise if Meta returned an error inside a 200 OK response body."""
    if isinstance(resp_data, dict) and "error" in resp_data:
        err = resp_data["error"]
        code = err.get("code", "?")
        msg = err.get("message", str(err))
        subcode = err.get("error_subcode", "")
        if code == 190:
            hint = "Token expired — regenerate FB_PAGE_ACCESS_TOKEN in Business Manager"
        elif code == 10:
            hint = (
                "App does not have permission. TWO steps required: "
                "(1) developers.facebook.com → Your App → App Review → Permissions and Features "
                "→ Add 'instagram_content_publish' and 'instagram_basic'. "
                "(2) Business Manager → System Users → Generate New Token with those scopes."
            )
        elif code == 200:
            hint = "Token missing instagram_content_publish scope — regenerate in Business Manager"
        elif code == 100:
            hint = "Check INSTAGRAM_USER_ID — must be an Instagram Business/Creator account numeric ID"
        else:
            hint = ""
        raise ValueError(f"Meta API error [{context}] code={code}{f'.{subcode}' if subcode else ''}: {msg}" + (f" | FIX: {hint}" if hint else ""))


def _verify_token_permissions(token):
    """Log token permissions to help diagnose issues."""
    try:
        resp = requests.get(
            f"{GRAPH_API}/me/permissions",
            params={"access_token": token},
            timeout=10,
        )
        data = resp.json()
        if "error" in data:
            print(f"[instagram] WARNING: Could not read permissions: {data['error'].get('message')}")
            return
        if "data" in data:
            granted = {p["permission"] for p in data["data"] if p.get("status") == "granted"}
            needed = {"instagram_basic", "instagram_content_publish"}
            has = needed & granted
            missing = needed - granted
            print(f"[instagram] Token permissions — have: {has or 'none'}, missing: {missing or 'none'}")
            if missing:
                print(
                    f"[instagram] ACTION NEEDED: Go to developers.facebook.com → App Review → "
                    f"Permissions and Features → add {missing}. Then regenerate token in Business Manager."
                )
    except Exception as e:
        print(f"[instagram] Could not check permissions: {e}")


def post(video_path, caption):
    """Post a Reel directly to Instagram via resumable upload."""
    ig_user_id, token = get_credentials()

    _verify_token_permissions(token)
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
    _check_meta_error(init_data, "create container")

    container_id = init_data.get("id")
    upload_uri = init_data.get("uri")

    if not container_id:
        raise ValueError(f"Instagram did not return container id: {init_data}")
    if not upload_uri:
        raise ValueError(
            f"Instagram did not return upload URI — token likely missing instagram_content_publish. "
            f"Response: {init_data}"
        )

    print(f"[instagram] Container created: {container_id}")

    # Step 2: Upload video bytes to resumable URI
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
    upload_data = upload_resp.json() if upload_resp.content else {}
    _check_meta_error(upload_data, "upload video")
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
        _check_meta_error(status_data, "poll status")
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
    _check_meta_error(result, "publish")
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
