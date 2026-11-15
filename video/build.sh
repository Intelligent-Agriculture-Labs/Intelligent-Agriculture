#!/usr/bin/env bash
# Build the 30 s IA (Intelligent Agriculture) film: fetch imagery -> compose score -> render frames -> mux
#   -> media/ia-demo-30s.mp4 and the poster media/film-poster.jpg (title frame)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=backend/.venv/bin/python
[ -f video/assets/levels.json ] || $PY video/fetch_assets.py
$PY video/score.py
node video/render.mjs
ffmpeg -loglevel error -y -i video/build/film_video.mp4 -i video/build/score.wav -map 0:v -map 1:a \
  -c:v libx264 -preset slow -crf 19 -pix_fmt yuv420p -af "loudnorm=I=-14:TP=-1.5:LRA=11" -ar 48000 -c:a aac -b:a 256k \
  -shortest -movflags +faststart media/ia-demo-30s.mp4
ffmpeg -loglevel error -y -ss 7.3 -i media/ia-demo-30s.mp4 -frames:v 1 -q:v 3 media/film-poster.jpg
echo "wrote media/ia-demo-30s.mp4, media/film-poster.jpg"
