#!/usr/bin/env python3
"""
google_genai_helper.py — Tiny shared wrapper around the Gemini API so every
script in this pipeline (fetch_stat.py, generate_script.py, generate_voice.py)
talks to it the same way, with the same error handling.

Requires env var GEMINI_API_KEY (set as a GitHub Actions secret — see
.github/workflows/daily-short.yml). Never hardcode the key in this file.
"""
import base64
import json
import os
import urllib.request
import urllib.error

TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.6-flash")
TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
TTS_VOICE = os.environ.get("GEMINI_TTS_VOICE", "Charon")

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. In GitHub Actions this must come from "
            "Settings -> Secrets and variables -> Actions (repo secrets, NOT "
            "Vercel env vars — different storage even if the name matches)."
        )
    return key


def _post(model: str, body: dict) -> dict:
    url = f"{API_BASE}/{model}:generateContent?key={_api_key()}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini API error {e.code}: {e.read().decode('utf-8', 'ignore')}") from e


def generate_text(prompt: str, temperature: float = 0.8) -> str:
    """Plain text generation. Returns the raw text of the first candidate."""
    resp = _post(
        TEXT_MODEL,
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        },
    )
    parts = resp["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def generate_json(prompt: str, temperature: float = 0.8) -> dict:
    """Same as generate_text but strips markdown fences and parses JSON.
    Raises ValueError if the model didn't return valid JSON (caller decides
    whether to retry once or fail the run)."""
    raw = generate_text(prompt, temperature=temperature).strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def generate_speech_pcm(text: str, voice: str = None) -> bytes:
    """Calls the Gemini TTS model. Returns RAW PCM bytes (16-bit signed
    little-endian, mono, 24000 Hz — confirmed via live test on 2026-09-04).
    This is NOT a playable file by itself — wrap it in a WAV header before
    writing to disk (see write_wav() below)."""
    resp = _post(
        TTS_MODEL,
        {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice or TTS_VOICE}}
                },
            },
        },
    )
    inline = resp["candidates"][0]["content"]["parts"][0]["inlineData"]
    mime = inline.get("mimeType", "")
    if "L16" not in mime:
        raise RuntimeError(f"Unexpected TTS mimeType: {mime} (expected raw PCM L16)")
    return base64.b64decode(inline["data"])


def write_wav(pcm_bytes: bytes, out_path: str, sample_rate: int = 24000,
              channels: int = 1, sample_width: int = 2) -> None:
    """Wraps raw PCM bytes in a standard WAV header. stdlib `wave` module
    handles this correctly — no manual byte-packing needed."""
    import wave

    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
