"""
Quietlyy — YouTube Shorts Poster
Uploads the generated video as a YouTube Short via YouTube Data API v3.
Uses OAuth2 refresh token for headless/automated posting.
"""

import os
import json
import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
UPDATE_URL = "https://www.googleapis.com/youtube/v3/videos"


def get_credentials():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN must be set"
        )
    return client_id, client_secret, refresh_token


def get_access_token(client_id, client_secret, refresh_token):
    """Exchange refresh token for a short-lived access token."""
    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def build_snippet(topic, script_text):
    """Build YouTube video title, description and tags."""
    lines = [line.strip() for line in script_text.split("\n") if line.strip()]
    description = (
        "\n".join(lines) + "\n\n"
        "— Quietlyy\n\n"
        f"#Shorts #Quietlyy #{topic.replace(' ', '')} "
        "#nostalgia #memories #deepthoughts #lifequotes #reflection"
    )
    title = f"{topic} #Shorts"[:100]  # YouTube title max 100 chars
    tags = ["Shorts", "Quietlyy", topic, "nostalgia", "memories",
            "deepthoughts", "lifequotes", "reflection"]
    return title, description, tags


def upload_video(video_path, access_token, title, description, tags):
    """
    Resumable upload to YouTube.
    Step 1: Initialize upload session → get upload URI.
    Step 2: Upload file bytes.
    Returns the new video ID.
    """
    file_size = os.path.getsize(video_path)

    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",   # People & Blogs
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
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
    )
    init_resp.raise_for_status()
    upload_uri = init_resp.headers["Location"]

    # Step 2: upload the file
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
    upload_resp.raise_for_status()
    video_id = upload_resp.json()["id"]
    return video_id


def post(video_path, topic, script_text):
    """Main entry: upload video as a YouTube Short."""
    print("[youtube] Authenticating...")
    client_id, client_secret, refresh_token = get_credentials()
    access_token = get_access_token(client_id, client_secret, refresh_token)

    title, description, tags = build_snippet(topic, script_text)

    print(f"[youtube] Uploading Short: {title}")
    video_id = upload_video(video_path, access_token, title, description, tags)

    url = f"https://www.youtube.com/shorts/{video_id}"
    print(f"[youtube] Short posted! {url}")
    return {"video_id": video_id, "url": url}


if __name__ == "__main__":
    print("YouTube Shorts poster ready. Run via pipeline.py")
    print("Required env vars: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN")
