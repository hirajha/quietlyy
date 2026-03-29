# Quietlyy

Automated pipeline for generating and posting nostalgic 30-second videos to the **Quietlyy** Facebook page.

## What It Does

Every day (or on manual trigger), this pipeline:
1. **Generates a script** — AI creates a nostalgic "There was a time…" voiceover script
2. **Creates voiceover** — Deep, exhausted male voice via edge-tts (free)
3. **Generates images** — AI-created anime-style atmospheric panels via Gemini
4. **Composites video** — 30s vertical (9:16) video with Ken Burns effect, text overlays, snow particles, @Quietlyy watermark
5. **Posts to Facebook** — Uploads as Reel to the Quietlyy page

## Setup (One-Time)

### 1. Get API Keys (all free)

| Service | Purpose | Get Key |
|---------|---------|---------|
| **Groq** | Script generation | [console.groq.com](https://console.groq.com) |
| **Google Gemini** | Image generation | [aistudio.google.com](https://aistudio.google.com/apikey) |
| **Pexels** | Fallback stock images | [pexels.com/api](https://www.pexels.com/api/) |
| **Facebook** | Video posting | See below |

### 2. Facebook Page Access Token

1. Go to [developers.facebook.com](https://developers.facebook.com) → My Apps → Create App
2. Add **Pages API** product
3. Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
4. Select your app, add permissions: `pages_manage_posts`, `pages_read_engagement`, `publish_video`
5. Generate User Token → Get Page Access Token via: `GET /me/accounts`
6. Copy your Page's `id` and `access_token`
7. Exchange for long-lived token (60-day): `GET /oauth/access_token?grant_type=fb_exchange_token&client_id={APP_ID}&client_secret={APP_SECRET}&fb_exchange_token={SHORT_TOKEN}`

### 3. Add GitHub Secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret:

- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `PEXELS_API_KEY` (optional fallback)
- `FB_PAGE_ID`
- `FB_PAGE_ACCESS_TOKEN`

### 4. Enable GitHub Actions

The workflow runs automatically daily at **10:00 AM IST**.

## Usage from Android Tablet

### Manual Trigger
1. Open GitHub in browser → go to this repo
2. Click **Actions** tab → **Quietlyy — Generate & Post Video**
3. Click **Run workflow** → optionally set a custom topic → Run
4. Watch the logs, download the video artifact if needed

### Check Results
- Each run saves the video as a downloadable **artifact** (kept 30 days)
- The `script.json` artifact shows what script was generated

## Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GROQ_API_KEY=your_key
export GEMINI_API_KEY=your_key

# Run without posting to Facebook
python scripts/pipeline.py --skip-post
```

## Customization

### Add New Topics
Edit `templates/scripts.json` → add to `topics_pool` array.

### Change Voice
Set env vars: `VOICE=en-US-ChristopherNeural`, `PITCH=-40Hz`, `RATE=-20%`

### Change Schedule
Edit `.github/workflows/generate-and-post.yml` → change the cron expression.

## Architecture

```
scripts/
  generate_script.py   → AI script generation (Groq → Gemini fallback)
  generate_audio.py    → Text-to-speech (edge-tts, free)
  generate_images.py   → Panel images (Gemini → Pexels → gradient fallback)
  compose_video.py     → ffmpeg + Pillow video compositor
  post_to_facebook.py  → Facebook Graph API posting
  pipeline.py          → Orchestrator
templates/
  scripts.json         → Example scripts + topic pool
```
