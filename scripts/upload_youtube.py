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
import sys
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

PRIVACY_STATUS = os.environ.get("YOUTUBE_PRIVACY_STATUS", "private")

# Marker written after a successful upload, inside data/ — the SAME directory
# the workflow's actions/cache step already restores from, keyed by
# date+pillar+slot (see .github/workflows/daily-short.yml). This is what was
# missing: the cache correctly stops fetch_stat.py / generate_script.py /
# generate_voice.py from re-billing Gemini on a same-day retry or a second
# manual "Run workflow", but nothing stopped THIS script from re-uploading
# the same already-cached video as a brand new one. Confirmed in production
# on 2026-09-04: a same-day re-run re-uploaded 3 of that day's 4 videos as
# exact duplicates. This marker closes that gap using the existing cache —
# no new secrets or infra needed.
UPLOAD_MARKER_PATH = "data/uploaded_video_id.json"


def already_uploaded_today():
    if not os.path.exists(UPLOAD_MARKER_PATH):
        return None
    with open(UPLOAD_MARKER_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

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
    prior = already_uploaded_today()
    if prior:
        print(
            f"[upload_youtube] SKIPPING upload — this pillar/slot's video was already "
            f"published today as video id {prior['video_id']} ({prior['title']!r}) at "
            f"{prior['uploaded_at']}. This run's cache-restored data/audio/assets are "
            f"identical to that earlier run's, so re-uploading would just create a "
            f"duplicate video (this is exactly the bug fixed on 2026-09-04 — see the "
            f"comment above UPLOAD_MARKER_PATH). If you genuinely want a fresh video for "
            f"this pillar/slot today, delete {UPLOAD_MARKER_PATH} first."
        )
        return

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

    # Write the marker BEFORE the (best-effort, allowed-to-fail) thumbnail
    # call below, so a thumbnail hiccup never leaves this run looking
    # "unfinished" and re-uploadable on a retry — the video itself is what
    # must never be duplicated; the thumbnail can safely be retried alone.
    with open(UPLOAD_MARKER_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "video_id": video_id,
                "title": script["title"],
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            },
            f,
            indent=2,
        )

    # Thumbnail must be set as a separate call, after the video exists. This
    # is allowed to fail without failing the whole run: custom thumbnails
    # require a phone-verified YouTube channel, and even right after
    # verifying, Google can take a while to propagate that permission to the
    # API. The video itself has already been published successfully at this
    # point, so a thumbnail hiccup should never block the daily pipeline —
    # worst case, that day's video keeps YouTube's auto-generated thumbnail
    # and a later run's thumbnail call succeeds once permissions catch up.
    try:
        youtube.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload("output/thumbnail.png")
        ).execute()
        print("[upload_youtube] Thumbnail set.")
    except HttpError as exc:
        print(
            f"[upload_youtube] WARNING: could not set custom thumbnail "
            f"(video {video_id} was still published successfully): {exc}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
