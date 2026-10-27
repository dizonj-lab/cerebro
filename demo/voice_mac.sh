#!/usr/bin/env bash
# Add the narration on a Mac: ./voice_mac.sh   (needs ffmpeg: brew install ffmpeg)
# Pick a voice with VOICE="Zoe (Premium)" ./voice_mac.sh. See voice.py for details.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 voice.py
