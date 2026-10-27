#!/usr/bin/env bash
# Make the CEREBRO demo video on Buddy, start to finish.
#
#   ./demo/run.sh            demo stack + library, voice, recording, finished MP4
#   ./demo/run.sh record     record and build again (stack already up; voice reused)
#   ./demo/run.sh voice      remake the voice (after editing narration.json), then record and build
#   ./demo/run.sh samples    the same line in ten voices, to pick one by ear
#   ./demo/run.sh down       stop the demo stack (its data is kept)
#
#   VOICE=am_michael ./demo/run.sh voice     another Kokoro voice (af_sarah is the default)
#
# Everything runs in the Compose project "cerebro-demo" and in throwaway
# containers: the live CEREBRO, its database, uploads and Ollama are not
# touched. The result is ~/cerebro-demo-<time>/CEREBRO-demo.mp4 (+ .srt).
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
COMPOSE=(docker compose -f docker-compose.demo.yml)
PORT="${DEMO_WEB_PORT:-3300}"
BASE="http://127.0.0.1:$PORT"
PLAYWRIGHT="${PLAYWRIGHT_VERSION:-1.63.0}"
THEME="${THEME:-light}"
VOICE="${VOICE:-af_sarah}"
STEP="${1:-all}"

case "$STEP" in
  down)
    "${COMPOSE[@]}" down
    echo "Stopped. Its data is kept; to delete the demo's own database and uploads as well:"
    echo "  docker volume rm cerebro-demo_postgres-data cerebro-demo_artifact-data"
    exit 0 ;;
  all|record|voice|samples) ;;
  *) echo "usage: $0 [all|record|voice|samples|down]"; exit 1 ;;
esac

voice_image() {
  docker image inspect cerebro-demo-voice >/dev/null 2>&1 || {
    echo "==> Building the voice image (Kokoro, once; a few minutes)"
    docker build -q -t cerebro-demo-voice -f voice.Dockerfile . >/dev/null; }
}
in_voice() {  # run voice.py in the voice container, in folder $1
  docker run --rm -v "$1:/work" -v "$HERE:/demo:ro" -v cerebro-demo-models:/root/.cache \
    -e VOICE="$VOICE" -e ENGINE=kokoro -w /work cerebro-demo-voice python /demo/voice.py "$2"
}

if [ "$STEP" = samples ]; then
  voice_image
  mkdir -p "$HOME/cerebro-voice-samples"
  docker run --rm -v "$HOME/cerebro-voice-samples:/work" -v "$HERE:/demo:ro" -v cerebro-demo-models:/root/.cache \
    -w /work cerebro-demo-voice python /demo/voice.py samples
  echo "==> Samples in ~/cerebro-voice-samples/voice-samples/. Listen, then: VOICE=<name> ./demo/run.sh"
  exit 0
fi

if [ "$STEP" = all ]; then
  for image in "${CEREBRO_API_IMAGE:-cerebro-api}" "${CEREBRO_WEB_IMAGE:-cerebro-web}"; do
    docker image inspect "$image" >/dev/null 2>&1 || {
      echo "Image $image not found. Build the live stack first (cd ~/cerebro && docker compose build),"
      echo "or set CEREBRO_API_IMAGE / CEREBRO_WEB_IMAGE."; exit 1; }
  done
  docker volume inspect cerebro-eval-ollama >/dev/null 2>&1 || docker volume create cerebro-eval-ollama >/dev/null

  echo "==> Starting the demo stack (project cerebro-demo, $BASE)"
  "${COMPOSE[@]}" up -d --wait
  for model in qwen3 mxbai-embed-large; do
    "${COMPOSE[@]}" exec -T ollama ollama list | grep -q "^$model" || {
      echo "==> Pulling $model (once)"; "${COMPOSE[@]}" exec -T ollama ollama pull "$model"; }
  done
  echo "==> Loading the Larkspur library (the local model reads each document; a few minutes)"
  python3 seed.py "$BASE"
fi

# 1. The voice first, so every scene can be timed to its line.
if [ "$STEP" != record ] || [ ! -f "$HERE/clips/durations.json" ]; then
  voice_image
  echo "==> Speaking the narration ($VOICE)"
  rm -rf "$HERE/clips"
  in_voice "$HERE" speak
fi

# 2. The recording, in a browser container.
echo "==> Recording (about 5 minutes)"
rm -rf "$HERE/out"
docker run --rm --network host --ipc=host -v "$HERE:/demo" -w /demo \
  -e BASE="$BASE" -e OUT=/demo/out -e THEME="$THEME" \
  "mcr.microsoft.com/playwright:v$PLAYWRIGHT-noble" \
  bash -c "npm install --no-save --silent playwright@$PLAYWRIGHT >/dev/null && node record.mjs; chown -R $(id -u):$(id -g) /demo/out /demo/node_modules 2>/dev/null || true"

# 3. Assembly: idle stretches tightened, voice, music, subtitles.
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$HOME/cerebro-demo-$STAMP"
mkdir -p "$DEST"
cp -r "$HERE/out/demo.webm" "$HERE/out/scenes.json" "$HERE/narration.json" "$HERE/clips" \
  "$HERE/voice.py" "$HERE/music.py" "$HERE/voice_mac.sh" "$DEST/"
voice_image
echo "==> Building the video"
in_voice "$DEST" build
echo
echo "==> Done: $DEST/CEREBRO-demo.mp4"
echo "    On your Mac:  scp 'admin@<buddy>:$DEST/CEREBRO-demo.mp4' ~/Downloads/"
