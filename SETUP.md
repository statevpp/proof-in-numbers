# Setup — one-time only (~2-3 hours total, spread across Day 1 and Day 6-7)

Everything below is done ONCE. After this, the daily cron in
`.github/workflows/daily-short.yml` runs with zero manual work (except the
temporary weekly "publish" click until the YouTube audit is approved — see
the main plan doc).

## 1. Create the GitHub repo

Public repo (required for free unlimited Actions minutes). Push this whole
folder's contents to it as-is — the workflow file is already in
`.github/workflows/daily-short.yml`.

## 2. Gemini API key

Already created and tested working: `business-ideas-daily` key from Google
AI Studio (https://aistudio.google.com/apikey). You can reuse it, or create
a new one dedicated to this channel to track spend separately — either
works, both are free tier.

Add it as a repo secret: **Settings → Secrets and variables → Actions →
New repository secret** → name `GEMINI_API_KEY`.

## 3. YouTube channel + OAuth credentials (the one genuinely fiddly part)

Uploading video via the API needs an **authorized user**, not just an API
key — this is a Google restriction, not a design choice here. One-time only:

1. Go to https://console.cloud.google.com/ → create/select a project →
   enable **YouTube Data API v3**.
2. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   → Application type: "Desktop app". Download the client ID + secret.
3. Run this locally ONCE (not in GitHub Actions) to get a refresh token —
   save it as `get_refresh_token.py` and run `python3 get_refresh_token.py`:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)
print("REFRESH TOKEN:", creds.refresh_token)
```

   (needs `pip install google-auth-oauthlib` and the downloaded
   `client_secret.json` from step 2 in the same folder). It opens a browser,
   you log in with the YouTube channel's Google account and approve — the
   refresh token printed at the end never expires unless you revoke it.

4. Add three repo secrets: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`,
   `YOUTUBE_REFRESH_TOKEN`.

## 4. Submit the YouTube API Audit request — DO THIS ON DAY 1, not later

Google Cloud Console → APIs & Services → OAuth consent screen → your app →
**submit for verification / audit** (the "Audit and Quota Extension" form
mentioned in the plan). This typically takes 1-2 weeks for a small app.
Submitting it on Day 1 means the wait overlaps with the 6 remaining days of
building, instead of adding 1-2 weeks AFTER everything else is ready.

Until approved: `upload_youtube.py` uploads as `privacyStatus: "private"`
(already the default in the workflow). Once approved: change
`YOUTUBE_PRIVACY_STATUS` to `"public"` in the workflow file and every future
video publishes itself with zero manual steps.

## 5. Channel branding (Day 7)

Channel name, banner, profile picture — one-time, do it directly in YouTube
Studio. A banner/logo can be generated with any free AI image tool (or
Gemini's image model) if you don't want to design one by hand — this has no
effect on the automated pipeline either way.

## 6. First test run

GitHub → your repo → **Actions** tab → "Daily Data Short" workflow →
**Run workflow** button. Takes a few minutes. Check the **Artifacts**
section of that run to download and review `short.mp4` before it publishes
to YouTube for the first few days, just to sanity-check tone/quality —
after that, trust the automatic self-checks already built into
`generate_script.py` and `assemble_video.sh`.
