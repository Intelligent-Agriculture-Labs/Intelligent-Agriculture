#!/usr/bin/env bash
# Build the 30 s FieldShift film: fetch imagery -> compose score -> render frames -> mux -> media/fieldshift-demo-30s.mp4
set -euo pipefail
cd "$(dirname "$0")/.."
PY=backend/.venv/bin/python
[ -f video/assets/levels.json ] || $PY video/fetch_assets.py
$PY video/score.py
node video/render.mjs
ffmpeg -loglevel error -y -i video/build/film_video.mp4 -i video/build/score.wav -map 0:v -map 1:a \
  -c:v libx264 -preset slow -crf 19 -pix_fmt yuv420p -af "loudnorm=I=-14:TP=-1.5:LRA=11" -ar 48000 -c:a aac -b:a 256k \
  -shortest -movflags +faststart media/fieldshift-demo-30s.mp4
echo "wrote media/fieldshift-demo-30s.mp4"
