"""
Quietlyy — YouTube Shorts Poster
Uploads the generated video as a YouTube Short via YouTube Data API v3.
Uses OAuth2 refresh token for headless/automated posting.

Compliance:
- containsSyntheticMedia: true  (YouTube AI/synthetic content policy)
- selfDeclaredMadeForKids: false
- AI disclosure text in description (via generate_seo.py)

Common failures and fixes:
- invalid_grant: refresh token expired or revoked → regenerate at OAuth Playground
- access_not_configured: YouTube Data API v3 not enabled in Google Cloud Console
- forbidden (403): OAuth app still in Testing mode → publish at GCP OAuth consent screen
- insufficientPermissions: token lacks youtube.upload scope → regenerate with correct scope
"""

import io
import os
import json
import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

# Required OAuth scope for uploading
REQUIRED_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def get_credentials():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        missing = [k for k, v in {
            "YOUTUBE_CLIENT_ID": client_id,
            "YOUTUBE_CLIENT_SECRET": client_secret,
            "YOUTUBE_REFRESH_TOKEN": refresh_token,
        }.items() if not v]
        raise ValueError(f"Missing YouTube secrets: {', '.join(missing)}")
    return client_id, client_secret, refresh_token


def get_access_token(client_id, client_secret, refresh_token):
    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, timeout=15)

    if not resp.ok:
        body = resp.text[:600]
        # Map common errors to actionable messages
        if "invalid_grant" in body:
            hint = (
                "YOUTUBE FIX: Refresh token is invalid or expired.\n"
                "  1. Go to https://developers.google.com/oauthplayground\n"
                "  2. Click gear icon → enter your Client ID + Secret\n"
                "  3. In Step 1 enter: https://www.googleapis.com/auth/youtube.upload\n"
                "  4. Click Authorize → Exchange code for tokens\n"
                "  5. Copy Refresh Token → update YOUTUBE_REFRESH_TOKEN secret in GitHub"
            )
        elif "unauthorized_client" in body or "403" in body:
            hint = (
                "YOUTUBE FIX: OAuth app is in Testing mode — tokens expire after 7 days.\n"
                "  1. Go to Google Cloud Console → APIs & Services → OAuth consent screen\n"
                "  2. Click 'Publish App' → Confirm\n"
                "  3. Regenerate your refresh token at https://developers.google.com/oauthplayground"
            )
        elif "invalid_client" in body:
            hint = (
                "YOUTUBE FIX: Client ID or Client Secret is wrong.\n"
                "  Verify YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in GitHub Secrets."
            )
        else:
            hint = (
                "Check that YOUTUBE_REFRESH_TOKEN is valid and the OAuth app is Published.\n"
                "  Regenerate at https://developers.google.com/oauthplayground\n"
                "  Required scope: https://www.googleapis.com/auth/youtube.upload"
            )
        raise ValueError(
            f"YouTube token refresh failed ({resp.status_code}): {body}\n{hint}"
        )

    data = resp.json()
    if "access_token" not in data:
        raise ValueError(f"No access_token in response: {data}")
    return data["access_token"]


def build_fallback_snippet(topic, script_text):
    """Fallback metadata if SEO module not available."""
    lines = [l.strip() for l in script_text.split("\n") if l.strip()]
    title = (lines[0][:90] + " #Shorts") if lines else f"{topic} #Shorts"
    description = (
        "\n".join(lines[:2]) + "\n\n"
        "— Quietlyy\n\n"
        f"#Shorts #Quietlyy #{topic.replace(' ', '')} #nostalgia #deepthoughts "
        "#lifequotes #reflection #viral #emotionalquotes\n\n"
        "Made with AI tools."
    )
    tags = ["Shorts", "Quietlyy", topic, "nostalgia", "deepthoughts",
            "lifequotes", "reflection", "emotionalquotes", "viral",
            "youtubeshorts", "relatable", "motivation", "feelings", "trending"]
    return title[:100], description, tags


def upload_video(video_path, access_token, title, description, tags):
    """Resumable upload to YouTube. Tries with AI disclosure first, falls back without."""
    file_size = os.path.getsize(video_path)

    # Try with containsSyntheticMedia (required by YouTube AI policy).
    # Fall back without it if the field causes a 400 error (older API versions).
    for attempt, include_synthetic in enumerate([(True,), (False,)], 1):
        include_synthetic = include_synthetic[0]

        status_body = {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        }
        if include_synthetic:
            status_body["containsSyntheticMedia"] = True

        metadata = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags[:500],  # YouTube tag list limit
                "categoryId": "22",  # People & Blogs
            },
            "status": status_body,
        }

        # Step 1: initiate resumable session
        init_resp = requests.post(
            UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(file_size),
            },
            json=metadata,
            timeout=30,
        )

        if init_resp.status_code == 400 and include_synthetic and attempt == 1:
            print(f"[youtube] Upload init 400 with containsSyntheticMedia — retrying without it")
            continue

        if not init_resp.ok:
            body = init_resp.text[:600]
            if "insufficientPermissions" in body or "forbidden" in body.lower():
                raise ValueError(
                    f"YouTube upload denied ({init_resp.status_code}): {body}\n"
                    "YOUTUBE FIX: The OAuth token lacks youtube.upload scope.\n"
                    "  Regenerate refresh token at https://developers.google.com/oauthplayground\n"
                    "  In Step 1 add scope: https://www.googleapis.com/auth/youtube.upload"
                )
            raise ValueError(f"YouTube upload init failed ({init_resp.status_code}): {body}")

        upload_uri = init_resp.headers.get("Location")
        if not upload_uri:
            raise ValueError(f"YouTube upload init returned no Location header. Response: {init_resp.text[:200]}")

        # Step 2: upload file bytes
        print(f"[youtube] Uploading {file_size // 1024 // 1024} MB...")
        with open(video_path, "rb") as f:
            upload_resp = requests.put(
                upload_uri,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(file_size),
                },
                data=f,
                timeout=300,
            )

        if not upload_resp.ok:
            raise ValueError(
                f"YouTube upload failed ({upload_resp.status_code}): {upload_resp.text[:400]}"
            )
        data = upload_resp.json()
        if "id" not in data:
            raise ValueError(f"Upload response has no video id: {data}")
        return data["id"]

    raise ValueError("YouTube upload failed after all retries")


def pin_comment(video_id, access_token, topic):
    """Post an engaging question comment to drive replies."""
    import random
    questions = [
        "Which line hit you the hardest? 👇",
        "Who in your life needs to hear this? Tag them below 💙",
        "Save this for the days it gets heavy 💾 What did this remind you of?",
        "Does this feel familiar? Drop a 🤍 if it hit home.",
        "Comment the name of someone you're thinking of right now 👇",
        "Which word from this stayed with you? 💬",
    ]
    comment_text = random.choice(questions)

    try:
        resp = requests.post(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            params={"part": "snippet"},
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": comment_text}
                    }
                }
            },
            timeout=15,
        )
        if resp.status_code == 200:
            print(f"[youtube] Pinned comment: \"{comment_text}\"")
        else:
            print(f"[youtube] Comment post failed (non-critical): {resp.text[:100]}")
    except Exception as e:
        print(f"[youtube] Comment failed (non-critical): {e}")


def post(video_path, topic, script_text, seo_metadata=None):
    """Main entry: upload video as a YouTube Short.
    seo_metadata: dict from generate_seo.generate_seo() — uses youtube fields if provided.
    """
    print("[youtube] Authenticating...")
    client_id, client_secret, refresh_token = get_credentials()
    access_token = get_access_token(client_id, client_secret, refresh_token)
    print("[youtube] Auth OK")

    if seo_metadata and "youtube" in seo_metadata:
        yt = seo_metadata["youtube"]
        title = yt["title"]
        description = yt["description"]
        tags = yt["tags"]
        print("[youtube] Using AI-optimised SEO metadata")
    else:
        title, description, tags = build_fallback_snippet(topic, script_text)

    print(f"[youtube] Uploading Short: {title}")
    video_id = upload_video(video_path, access_token, title, description, tags)

    url = f"https://www.youtube.com/shorts/{video_id}"
    print(f"[youtube] Short posted! {url}")

    # Pin an engaging question comment to drive replies
    pin_comment(video_id, access_token, topic)

    return {"video_id": video_id, "url": url}


if __name__ == "__main__":
    print("YouTube Shorts poster ready. Run via pipeline.py")
    print("Required env vars: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN")
    print(f"Required OAuth scope: {REQUIRED_SCOPE}")
