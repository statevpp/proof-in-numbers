#!/usr/bin/env python3
"""
generate_voice.py — Turns data/script.json's narration into audio/voice.wav
using Gemini TTS. Response format (raw PCM16 @ 24kHz mono) was verified live
on 2026-09-04 — see google_genai_helper.write_wav() for the header wrapping.
"""
import json
import os

import google_genai_helper as gh


def main():
    # Same ephemeral-runner retry logic as fetch_stat.py / generate_script.py
    # — TTS is the priciest call in this pipeline, so skip it on a same-day
    # retry if the cache already restored a voice file.
    out_path = "audio/voice.wav"
    if os.path.exists(out_path):
        print(f"[generate_voice] {out_path} already exists for today "
              f"(restored from cache) — skipping regeneration.")
        return

    with open("data/script.json", "r", encoding="utf-8") as f:
        script = json.load(f)

    pcm = gh.generate_speech_pcm(script["narration"])

    os.makedirs("audio", exist_ok=True)
    gh.write_wav(pcm, out_path)
    print(f"[generate_voice] Saved {out_path}")


if __name__ == "__main__":
    main()
