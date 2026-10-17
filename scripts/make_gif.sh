#!/usr/bin/env bash
# The README's demo GIF from the Playwright recording of `make screens` (Mrs Tan, English, live).
# Usage: scripts/make_gif.sh <recording.webm> <out.gif> [speed, default 1.5]
# The analysis wait is real; the whole clip plays at 1.5× (the README caption says so).
set -euo pipefail
in="$1"; out="$2"; speed="${3:-1.5}"
test -f "$in" || { echo "no recording at '$in'"; exit 1; }
pal="$(mktemp -t palette).png"
filters="setpts=PTS/${speed},fps=12,scale=320:-1:flags=lanczos"
ffmpeg -v error -y -i "$in" -vf "${filters},palettegen=stats_mode=diff" "$pal"
ffmpeg -v error -y -i "$in" -i "$pal" -lavfi "${filters} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" "$out"
rm -f "$pal"
echo "✔ $out ($(du -h "$out" | cut -f1))"
