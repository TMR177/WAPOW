#!/usr/bin/env bash
# wapow_start.sh — extract splash frames (one-time), then run the dash.
#
# Run on the Pi:  ./wapow_start.sh
# (DISPLAY defaults to :0 so it works fine over SSH.)
#
# The dash plays its own boot splash (play_splash() in wapow_dash.py)
# by flipping through JPEG frames in splash_frames/. This script's only
# splash job is to create that folder from the mp4 the first time — after
# that it just execs the dash. No external video player is involved:
# running mpv fullscreen over a fullscreen pygame app froze and crashed
# (two apps fighting over one screen), so the dash owns the screen alone.

set -u
export DISPLAY="${DISPLAY:-:0}"

HERE="$(cd "$(dirname "$0")" && pwd)"
SPLASH="$HERE/wapow_boot_splash.mp4"
FRAMES="$HERE/splash_frames"

# One-time: video -> numbered JPEGs, 25 fps, scaled to 1024 wide (576 tall
# from the 1280x720 source — the dash letterboxes the sliver). Best-effort:
# if this fails the dash simply boots with no splash.
if [ -f "$SPLASH" ] && [ ! -f "$FRAMES/f0001.jpg" ]; then
    echo "extracting splash frames (one-time)..."
    mkdir -p "$FRAMES"
    ffmpeg -loglevel error -y -i "$SPLASH" \
           -vf "fps=25,scale=1024:-2" -q:v 3 "$FRAMES/f%04d.jpg" \
        || echo "frame extraction failed — dash will start without splash"
fi

exec python3 -u "$HERE/wapow_dash.py" > "$HERE/wapow_run.log" 2>&1
