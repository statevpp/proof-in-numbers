#!/usr/bin/env python3
"""
upload_youtube.py — Uploads output/short.mp4 + output/thumbnail.png to
YouTube via the Data API v3, using metadata from data/script.json.

IMPORTANT — this is the one piece that needs a ONE-TIME manual OAuth setup
(a plain API key is not enough for uploads, unlike the Gemini calls above —
YouTube requires an authorized user, not just a project). See SETUP.md for
the exact one-time steps. Once done, this script runs unattended forever.

Required GitHub Actions secrets:
- YOUTUBE_CLIENT_ID
- YOUTUBE_CLIENT_SECRET
- YOUTUBE_REFRESH_TOKEN

Privacy status: uploads as "private" until Google approves the Audit and
Quota Extension request (submitted Day 1 of the plan) — this is a hard
YouTube API restriction for unaudited apps, not a choice made here. Once
approved, change PRIVACY_STATUS below to "public" and the manual weekly
"publish" click disappears entirely.
"""
import json
import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

PRIVACY_STATUS = os.environ.get("YOUTUBE_PRIVACY_STATUS", "private")

# Extra tags per content pillar (see 00_Project_Overview.md) — keeps each
# video's metadata aligned with whichever of the two pillars it belongs to,
# which helps YouTube surface it to the right audience.
PILLAR_TAGS = {
    "money": ["money", "personalfinance", "salary", "costofliving"],
    "life": ["psychology", "lifehacks", "wellbeing", "happiness"],
}


def get_authenticated_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def main():
    with open("data/script.json", "r", encoding="utf-8") as f:
        script = json.load(f)
    with open("data/today_stat.json", "r", encoding="utf-8") as f:
        stat = json.load(f)

    pillar = stat.get("pillar", "money")
    tags = ["shorts", "proofinnumbers", "data", "facts"] + PILLAR_TAGS.get(pillar, [])

    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": script["title"],
            "description": script["description"] + "\n\n#Shorts",
            "tags": tags,
            "categoryId": "27",  # Education
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload("output/short.mp4", chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[upload_youtube] Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"[upload_youtube] Uploaded video id: {video_id} (privacyStatus={PRIVACY_STATUS})")

    # Thumbnail must be set as a separate call, after the video exists.
    youtube.thumbnails().set(
        videoId=video_id, media_body=MediaFileUpload("output/thumbnail.png")
    ).execute()
    print("[upload_youtube] Thumbnail set.")


if __name__ == "__main__":
    main()
