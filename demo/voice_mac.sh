#!/usr/bin/env bash
# Optional: rebuild the video on a Mac with a macOS voice instead of Kokoro.
#   ./voice_mac.sh                      (in a cerebro-demo-<time> folder; needs: brew install ffmpeg)
#   VOICE="Ava (Premium)" ./voice_mac.sh
# The recording's scenes were timed to the Kokoro lines; build speeds up or
# spaces scenes to fit whichever voice speaks.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf clips
ENGINE=say exec python3 "$(dirname "$0")/voice.py" all
