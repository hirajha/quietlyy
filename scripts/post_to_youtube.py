"""
Quietlyy — YouTube Shorts Poster
Uploads the generated video as a YouTube Short via YouTube Data API v3.
Uses OAuth2 refresh token for headless/automated posting.

Compliance:
- containsSyntheticMedia: true  (YouTube AI/synthetic content policy)
- selfDeclaredMadeForKids: false
- AI disclosure text in description (via generate_seo.py)
"""

import io
import os
import json
import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
WATERMARK_URL = "https://www.googleapis.com/upload/youtube/v3/watermarks/set"


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
    if not resp.ok:
        raise ValueError(
            f"YouTube token refresh failed ({resp.status_code}): {resp.text[:400]}\n"
            "Check that YOUTUBE_REFRESH_TOKEN is valid and the app is Published "
            "(not in Testing mode). Regenerate at https://developers.google.com/oauthplayground"
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
        "\n".join(lines) + "\n\n"
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
    if not init_resp.ok:
        raise ValueError(
            f"YouTube upload init failed ({init_resp.status_code}): {init_resp.text[:400]}"
        )
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


def pin_comment(video_id, access_token, topic):
    """Post and pin an engaging question comment to drive replies."""
    import random
    questions = [
        f"Which line hit you the hardest? 👇",
        f"Who in your life needs to hear this? Tag them below 💙",
        f"Save this for the days it gets heavy 💾 What did this remind you of?",
        f"Does this feel familiar? Drop a 🤍 if it hit home.",
        f"Comment the name of someone you're thinking of right now 👇",
        f"Which word from this stayed with you? 💬",
    ]
    comment_text = random.choice(questions)

    try:
        resp = requests.post(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            params={"part": "snippet", "access_token": access_token},
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
            comment_id = resp.json()["id"]
            print(f"[youtube] Pinned comment: \"{comment_text}\"")
            # Pin it
            requests.post(
                "https://www.googleapis.com/youtube/v3/comments/setModerationStatus",
                params={
                    "id": comment_id,
                    "moderationStatus": "published",
                    "banAuthor": "false",
                    "access_token": access_token,
                },
                timeout=10,
            )
        else:
            print(f"[youtube] Comment post failed: {resp.text[:100]}")
    except Exception as e:
        print(f"[youtube] Comment failed (non-critical): {e}")


def _make_watermark_image():
    """Generate a small Subscribe button PNG in memory (150x50 px)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        W, H = 150, 50
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Red pill background
        draw.rounded_rectangle([0, 0, W - 1, H - 1], radius=12, fill=(255, 0, 0, 230))
        # White "Subscribe" text
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        except Exception:
            font = ImageFont.load_default()
        text = "Subscribe"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((W - tw) // 2, (H - th) // 2 - bbox[1]), text, font=font, fill=(255, 255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.read()
    except ImportError:
        # Minimal 1x1 transparent PNG fallback (won't show — just prevents crash)
        return (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
                b'\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
                b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
                b'\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')


def setup_channel_watermark(access_token):
    """
    One-time channel setup: add a Subscribe button watermark that
    appears on every uploaded video (bottom-right corner, from 0s).
    Safe to call on every run — YouTube just overwrites the existing watermark.
    """
    try:
        watermark_bytes = _make_watermark_image()
        file_size = len(watermark_bytes)

        # Step 1: initiate resumable upload
        init_resp = requests.post(
            WATERMARK_URL,
            params={"uploadType": "resumable", "part": "watermark",
                    "channelId": ""},  # empty = own channel
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "image/png",
                "X-Upload-Content-Length": str(file_size),
            },
            json={
                "timing": {"type": "offsetFromStart", "offsetMs": 0},
                "position": {"type": "corner", "cornerPosition": "bottomRight"},
                "imageUrl": "",  # ignored for upload, required field
                "targetChannelId": "",  # own channel
            },
            timeout=15,
        )
        if init_resp.status_code not in (200, 307):
            print(f"[youtube] Watermark init failed ({init_resp.status_code}): {init_resp.text[:100]}")
            return

        upload_uri = init_resp.headers.get("Location")
        if not upload_uri:
            print("[youtube] Watermark: no upload URI returned")
            return

        # Step 2: upload image bytes
        up_resp = requests.put(
            upload_uri,
            headers={"Content-Type": "image/png", "Content-Length": str(file_size)},
            data=watermark_bytes,
            timeout=30,
        )
        if up_resp.status_code in (200, 204):
            print("[youtube] Channel Subscribe watermark set ✓ (bottom-right on all videos)")
        else:
            print(f"[youtube] Watermark upload failed ({up_resp.status_code}): {up_resp.text[:100]}")
    except Exception as e:
        print(f"[youtube] Watermark setup failed (non-critical): {e}")


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

    # One-time channel setup: Subscribe watermark on every video (bottom-right)
    setup_channel_watermark(access_token)

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
