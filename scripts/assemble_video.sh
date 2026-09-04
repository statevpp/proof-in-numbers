#!/usr/bin/env bash
# assemble_video.sh — Combines audio/voice.wav + assets/chart.png + burned-in
# captions into the final vertical Short (1080x1920, <60s), plus a YouTube
# thumbnail. Adapted from the proven Lumaris assemble-youtube-video.sh
# pattern (same repo family, same known ffmpeg gotchas — see notes below).
#
# Also burns in a small pillar badge ("MONEY IN YOUR LIFE" / "YOUR LIFE BY
# THE NUMBERS") above the hook, read from data/today_stat.json's "pillar"
# field — this is what makes the channel's two content pillars visually
# recognizable as a consistent series, not two unrelated video styles.
#
# Usage: ./assemble_video.sh <workdir>
# Expects inside <workdir>: audio/voice.wav, assets/chart.png,
#   data/script.json, data/today_stat.json
# Produces: output/short.mp4, output/thumbnail.png

set -euo pipefail

WORKDIR="${1:-.}"
cd "$WORKDIR"

mkdir -p output

VOICE="audio/voice.wav"
CHART="assets/chart.png"
SCRIPT_JSON="data/script.json"
STAT_JSON="data/today_stat.json"

if [[ ! -f "$VOICE" || ! -f "$CHART" || ! -f "$SCRIPT_JSON" || ! -f "$STAT_JSON" ]]; then
  echo "[assemble_video] Missing required input file(s). Aborting." >&2
  exit 1
fi

DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VOICE")
echo "[assemble_video] Voice duration: ${DURATION}s"

# Sanity floor/ceiling — a broken TTS call sometimes returns near-silent or
# absurdly long audio. Fail loud instead of publishing garbage (this is the
# "technical self-check" from the plan, no human review needed).
python3 - "$DURATION" <<'PY'
import sys
d = float(sys.argv[1])
if d < 8 or d > 75:
    print(f"[assemble_video] Voice duration {d}s outside sane 8-75s range — failing.", file=sys.stderr)
    sys.exit(1)
PY

# Burn the hook + title as an overlay caption over the chart, letterboxed to
# 1080x1920. Text is sanitized (not escaped) before reaching drawtext —
# ffmpeg's drawtext silently drops the ENTIRE overlay on stray `%` characters
# (confirmed failure mode in the Lumaris pipeline, 18.07.2026), so we strip
# risky characters here rather than trust escaping.
HOOK=$(python3 - "$SCRIPT_JSON" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.load(f)
text = d["hook"]
for bad, good in [("'", ""), (":", " -"), ("%", " PCT"), ('"', "")]:
    text = text.replace(bad, good)
print(text)
PY
)

# Pillar badge text — derived from a fixed 2-item map (never external/free
# text), so it needs no sanitization the way HOOK/THUMB_TEXT do.
PILLAR_LABEL=$(python3 - "$STAT_JSON" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.load(f)
pillar = d.get("pillar", "money")
print("YOUR LIFE BY THE NUMBERS" if pillar == "life" else "MONEY IN YOUR LIFE")
PY
)

ffmpeg -y \
  -loop 1 -i "$CHART" \
  -i "$VOICE" \
  -filter_complex "\
    [0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,\
    drawtext=text='${PILLAR_LABEL}':fontcolor=#e0b04a:fontsize=34:box=1:boxcolor=black@0.55:boxborderw=14:\
    x=(w-text_w)/2:y=60,\
    drawtext=text='${HOOK}':fontcolor=white:fontsize=64:box=1:boxcolor=black@0.55:boxborderw=20:\
    x=(w-text_w)/2:y=175:line_spacing=10[v]" \
  -map "[v]" -map 1:a \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 192k \
  -shortest -t "$DURATION" \
  output/short.mp4

# Thumbnail: reuse the chart image (zero extra Gemini cost), burn the
# thumbnail_text on top, output at YouTube's recommended 1280x720.
THUMB_TEXT=$(python3 - "$SCRIPT_JSON" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.load(f)
text = d["thumbnail_text"]
for bad, good in [("'", ""), (":", " -"), ("%", " PCT"), ('"', "")]:
    text = text.replace(bad, good)
print(text)
PY
)

ffmpeg -y -i "$CHART" \
  -vf "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,\
  drawtext=text='${THUMB_TEXT}':fontcolor=white:fontsize=72:box=1:boxcolor=black@0.6:boxborderw=24:\
  x=(w-text_w)/2:y=(h-text_h)/2" \
  output/thumbnail.png

echo "[assemble_video] Done. Verifying output..."
ffprobe -v error -show_entries stream=width,height,codec_type,duration -of default=noprint_wrappers=1 output/short.mp4
echo "[assemble_video] output/short.mp4 and output/thumbnail.png ready."
