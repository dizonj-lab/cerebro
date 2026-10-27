#!/usr/bin/env bash
# Record the CEREBRO demo on Buddy.
#
#   ./demo/run.sh            start the demo stack, load the Larkspur library, record the tour
#   ./demo/run.sh record     record again (stack already up and seeded)
#   ./demo/run.sh down       stop the demo stack (its data is kept)
#
# Everything runs in the separate Compose project "cerebro-demo": the live
# CEREBRO, its database, uploads and Ollama are not touched. The result is a
# folder ~/cerebro-demo-<time>/ with the silent video, the scene timings and
# the narration; copy it to a Mac and run voice_mac.sh there to add the voice.
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
COMPOSE=(docker compose -f docker-compose.demo.yml)
PORT="${DEMO_WEB_PORT:-3300}"
BASE="http://127.0.0.1:$PORT"
PLAYWRIGHT="${PLAYWRIGHT_VERSION:-1.63.0}"
THEME="${THEME:-light}"

case "${1:-all}" in
  down)
    "${COMPOSE[@]}" down
    echo "Stopped. Its data is kept; to delete the demo's own database and uploads as well:"
    echo "  docker volume rm cerebro-demo_postgres-data cerebro-demo_artifact-data"
    exit 0 ;;
  all|record) ;;
  *) echo "usage: $0 [all|record|down]"; exit 1 ;;
esac

if [ "${1:-all}" = all ]; then
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

echo "==> Recording (about 5 minutes; the browser runs in a container)"
rm -rf "$HERE/out"
docker run --rm --network host --ipc=host -v "$HERE:/demo" -w /demo \
  -e BASE="$BASE" -e OUT=/demo/out -e THEME="$THEME" \
  "mcr.microsoft.com/playwright:v$PLAYWRIGHT-noble" \
  bash -c "npm install --no-save --silent playwright@$PLAYWRIGHT >/dev/null && node record.mjs; chown -R $(id -u):$(id -g) /demo/out /demo/node_modules 2>/dev/null || true"

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$HOME/cerebro-demo-$STAMP"
mkdir -p "$DEST"
cp "$HERE/out/demo.webm" "$HERE/out/scenes.json" "$HERE/narration.json" "$HERE/voice.py" "$HERE/voice_mac.sh" "$DEST/"
tar -czf "$DEST.tar.gz" -C "$HOME" "$(basename "$DEST")"
echo
echo "==> Done: $DEST.tar.gz ($(du -h "$DEST.tar.gz" | cut -f1))"
echo "    On your Mac:  scp 'admin@<buddy>:$DEST.tar.gz' ~/Downloads/ && cd ~/Downloads"
echo "                  tar -xzf $(basename "$DEST").tar.gz && cd $(basename "$DEST") && ./voice_mac.sh"
