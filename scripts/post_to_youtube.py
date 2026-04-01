"""
Quietlyy — YouTube Shorts Poster
Uploads the generated video as a YouTube Short via YouTube Data API v3.
Uses OAuth2 refresh token for headless/automated posting.

Compliance:
- containsSyntheticMedia: true  (YouTube AI/synthetic content policy)
- selfDeclaredMadeForKids: false
- AI disclosure text in description (via generate_seo.py)
"""

import os
import json
import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"


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
    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def build_fallback_snippet(topic, script_text):
    """Fallback metadata if SEO module not available."""
    lines = [l.strip() for l in script_text.split("\n") if l.strip()]
    title = (lines[0][:90] + " #Shorts") if lines else f"{topic} #Shorts"
    description = (
        "\n".join(lines) + "\n\n"
        "— Quietlyy\n\n"
        "🤖 AI Disclosure: This video was created using AI tools for script writing, "
        "voice synthesis, and image generation, as required by YouTube's Creator "
        "Responsibility & Synthetic Media policies.\n\n"
        f"#Shorts #Quietlyy #{topic.replace(' ', '')} #nostalgia #deepthoughts "
        "#lifequotes #reflection #AIGenerated #AIcontent"
    )
    tags = ["Shorts", "Quietlyy", topic, "nostalgia", "deepthoughts",
            "lifequotes", "reflection", "AIgenerated", "AIcontent",
            "emotionalquotes", "viral", "youtubeshorts", "relatable",
            "motivation", "feelings"]
    return title[:100], description, tags


def upload_video(video_path, access_token, title, description, tags):
    """Resumable upload to YouTube with full compliance metadata."""
    file_size = os.path.getsize(video_path)

    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            # Required: disclose AI/synthetic content per YouTube policy
            "containsSyntheticMedia": True,
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
    upload_resp.raise_for_status()
    return upload_resp.json()["id"]


def post(video_path, topic, script_text, seo_metadata=None):
    """Main entry: upload video as a YouTube Short.
    seo_metadata: dict from generate_seo.generate_seo() — uses youtube fields if provided.
    """
    print("[youtube] Authenticating...")
    client_id, client_secret, refresh_token = get_credentials()
    access_token = get_access_token(client_id, client_secret, refresh_token)

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
    return {"video_id": video_id, "url": url}


if __name__ == "__main__":
    print("YouTube Shorts poster ready. Run via pipeline.py")
    print("Required env vars: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN")
