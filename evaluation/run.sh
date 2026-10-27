#!/usr/bin/env bash
# Run CEREBRO's model evaluation on Buddy and pack the evidence.
#
#   ./evaluation/run.sh                    # everything, about an hour on the RTX 5060 Ti
#   ./evaluation/run.sh --only topics      # one experiment
#   OLLAMA_URL=http://127.0.0.1:11434 ./evaluation/run.sh
#
# Reads nothing from CEREBRO's database and writes nothing to it. Keyword
# search is measured in a throwaway PostgreSQL container (no volume, removed
# on exit). The models are the ones the running Ollama already has.
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cu128}"
PG_PORT="${EVAL_PG_PORT:-55432}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$HERE/evidence/$STAMP"

curl -fsS "$OLLAMA_URL/api/tags" >/dev/null || { echo "Ollama is not answering at $OLLAMA_URL (set OLLAMA_URL)."; exit 1; }

# A virtual environment of its own: PyTorch with CUDA, scikit-learn, and
# CEREBRO's backend package so the product's own code is what runs.
if [ ! -x .venv/bin/python ]; then
  echo "==> Creating evaluation/.venv (PyTorch download is about 3 GB, once)"
  if command -v uv >/dev/null; then
    uv venv -q -p 3.12 .venv
    PIP=(uv pip install -q --python .venv/bin/python)
  else
    python3 -m venv .venv
    .venv/bin/pip install -q --upgrade pip
    PIP=(.venv/bin/pip install -q)
  fi
  "${PIP[@]}" --index-url "$TORCH_INDEX" torch
  "${PIP[@]}" -r requirements.txt
  "${PIP[@]}" -e ../backend
fi
.venv/bin/python -c "import torch; print('==> PyTorch', torch.__version__, '· CUDA', torch.cuda.is_available() and torch.cuda.get_device_name(0))"

# The scratch database for keyword search: CEREBRO's ts_rank query, never CEREBRO's data.
PG_NAME="cerebro-eval-pg-$STAMP"
cleanup() { docker rm -f "$PG_NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT
PG_ARGS=()
if command -v docker >/dev/null; then
  echo "==> Starting a throwaway PostgreSQL ($PG_NAME, 127.0.0.1:$PG_PORT)"
  docker run -d --rm --name "$PG_NAME" -p "127.0.0.1:$PG_PORT:5432" \
    -e POSTGRES_USER=eval -e POSTGRES_PASSWORD=eval -e POSTGRES_DB=eval postgres:16-alpine >/dev/null
  for _ in $(seq 60); do docker exec "$PG_NAME" pg_isready -U eval -d eval >/dev/null 2>&1 && break; sleep 1; done
  PG_ARGS=(--pg-url "postgresql+psycopg://eval:eval@127.0.0.1:$PG_PORT/eval")
else
  echo "-- Docker not found: keyword search will not be measured"
fi

PYTHONPATH="$HERE" .venv/bin/python -m cerebro_eval --out "$OUT" --ollama "$OLLAMA_URL" "${PG_ARGS[@]}" "$@"

ARCHIVE="$HOME/cerebro-evidence-$STAMP.tar.gz"
tar -czf "$ARCHIVE" -C "$HERE/evidence" "$STAMP"
echo
echo "==> Evidence: $OUT"
echo "==> Archive:  $ARCHIVE  ($(du -h "$ARCHIVE" | cut -f1))"
echo "    sha256:   $(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
