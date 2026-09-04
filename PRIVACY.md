# Privacy Policy — Proof in Numbers

Last updated: 2026-09-04

"Proof in Numbers" is an automated YouTube Shorts channel. This project (a set of scripts running on GitHub Actions) uses YouTube API Services to publish our own videos, and does not collect, store, or process any personal data from viewers or from any third party.

By using YouTube API Services, this application is bound by the [YouTube Terms of Service](https://www.youtube.com/t/terms) and incorporates the [Google Privacy Policy](https://policies.google.com/privacy).

## What we do

- We generate short video scripts from publicly available statistics (e.g. World Bank, Our World in Data).
- We use the YouTube Data API v3 solely to upload our own videos to our own YouTube channel (Proof in Numbers) and to optionally set a custom thumbnail for those videos.
- We do not read, collect, or store any data belonging to YouTube viewers or other channels.

## Data we hold

- The only credentials used are our own OAuth tokens (client ID/secret and refresh token) for our own YouTube channel, stored as encrypted GitHub Actions secrets, used exclusively to authenticate our own channel's video uploads.
- No viewer data, comments, analytics, or personal information is accessed, collected or shared with any third party.

## Data deletion

Because we do not collect or store any viewer or third-party data, there is no such data to delete. The only data we hold is our own OAuth authorization for our own channel. This authorization can be revoked at any time from the Google Account permissions page: https://myaccount.google.com/permissions — revoking access immediately and permanently deletes our application's ability to act on the channel, and deletes the associated refresh token from our systems (a GitHub Actions secret) within 24 hours of revocation being noticed.

## Contact

Questions about this policy can be sent to statev.petrov@gmail.com.
