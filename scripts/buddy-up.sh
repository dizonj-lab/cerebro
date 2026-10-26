#!/usr/bin/env bash
# Install or update CEREBRO on the home server (Buddy). Safe to run again: it rebuilds the images,
# keeps the database and uploads, and reuses the settings saved in .env.
#
#   ./scripts/buddy-up.sh                                 # first time, and after every git pull
#   CEREBRO_BIND=192.168.1.25 CEREBRO_WEB=3100 ./scripts/buddy-up.sh
#
# Never run `make compose-down` here: it is `docker compose down -v`, which deletes the database
# and every uploaded document. `docker compose stop` stops CEREBRO and keeps everything.
set -euo pipefail
cd "$(dirname "$0")/.."
touch .env && chmod 600 .env
setkv() { grep -q "^$1=" .env && sed -i "s#^$1=.*#$1=$2#" .env || echo "$1=$2" >> .env; }
getkv() { sed -n "s/^$1=//p" .env | tail -1; }
in_use() { ss -ltnH "( sport = :$1 )" | grep -q .; }

# The LAN address: an explicit value wins, then the saved one, then the default route's source.
lan_ip="$(ip -o -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' || true)"
saved="$(getkv CEREBRO_WEB_PORT)"
BIND="${CEREBRO_BIND:-${saved%:*}}"; BIND="${BIND:-$lan_ip}"
WEB="${CEREBRO_WEB:-${saved##*:}}"; WEB="${WEB:-3100}"
API="$(getkv CEREBRO_API_PORT)"; API="${API##*:}"; API="${API:-18000}"
DB="$(getkv CEREBRO_DB_PORT)"; DB="${DB##*:}"; DB="${DB:-15432}"
[ -n "$BIND" ] || { echo "Could not work out the LAN address; run again with CEREBRO_BIND=192.168.x.y"; exit 1; }
case "$BIND" in 0.0.0.0|::) echo "Refusing to publish on every interface; use the LAN address."; exit 1;; esac

# Another Compose project already called "cerebro" (from a different folder) would share its
# volumes with this one. Stop rather than mix two databases.
other="$(docker compose ls -a --format json 2>/dev/null | python3 -c "
import json, os, sys
for p in json.load(sys.stdin):
    if p['Name'] == 'cerebro' and os.path.realpath(os.getcwd()) not in p.get('ConfigFiles', ''):
        print(p['ConfigFiles'])" || true)"
if [ -n "$other" ]; then
  echo "A Compose project named 'cerebro' already exists from another folder: $other"
  echo "Run this script from that folder instead, or stop that project first. Nothing was changed."
  exit 1
fi

# A port another service holds would make a container fail to start; say so up front. Ports this
# project already publishes are fine: the containers are simply being replaced.
mine="$(docker compose -p cerebro ps -q 2>/dev/null || true)"
if [ -z "$mine" ]; then
  for p in "$WEB" "$API" "$DB"; do
    if in_use "$p"; then echo "Port $p is already in use:"; ss -ltnp "( sport = :$p )" || true
      echo "Pick others with CEREBRO_WEB=…, or edit CEREBRO_API_PORT / CEREBRO_DB_PORT in .env."; exit 1; fi
  done
fi

# A session secret, generated once and kept: changing it later signs everyone out.
if [ -z "$(getkv CEREBRO_JWT_SECRET)" ]; then
  setkv CEREBRO_JWT_SECRET "$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  echo "==> Generated a session secret (stored in .env, readable by you only)"
fi
setkv COMPOSE_PROJECT_NAME cerebro
setkv COMPOSE_FILE docker-compose.yml:docker-compose.buddy.yml
setkv CEREBRO_WEB_PORT "$BIND:$WEB"
setkv CEREBRO_API_PORT "127.0.0.1:$API"
setkv CEREBRO_DB_PORT "127.0.0.1:$DB"

echo "==> Building and starting CEREBRO (the first build takes a few minutes)"
docker compose up -d --build

echo "==> Waiting for the web app"
for _ in $(seq 1 90); do
  curl -fsS -o /dev/null "http://$BIND:$WEB/" && break
  sleep 2
done
curl -fsS -o /dev/null "http://$BIND:$WEB/" || { echo "!! The web app did not answer. See: docker compose logs --tail 80 api web"; exit 1; }

# Local AI. CEREBRO looks for Ollama at CEREBRO_OLLAMA_BASE_URL (default: the host, port 11434)
# and uses what it finds. Report what the API container can actually see.
echo "==> Checking local AI (Ollama) from inside the API container"
models="$(docker compose exec -T api python -c "
import json, os, urllib.request
url = os.environ.get('CEREBRO_OLLAMA_BASE_URL', '')
try:
    tags = json.load(urllib.request.urlopen(url + '/api/tags', timeout=5))
    print(' '.join(m['name'] for m in tags.get('models', [])) or '(none)')
except Exception as e:
    print('UNREACHABLE', url, type(e).__name__)
" 2>&1 | tail -1)"
case "$models" in
  UNREACHABLE*) echo "-- Ollama is not reachable: ${models#UNREACHABLE }"
                echo "   CEREBRO runs without local AI: keyword search, passages instead of written answers."
                echo "   See docs/BUDDY.md, 'Local AI', before uploading documents." ;;
  *)            echo "   Ollama models visible: $models" ;;
esac

# Pin the embedding provider on the first run, so it cannot change later on its own: vectors from
# two providers are never compared, and a silent switch would hide every document already stored.
if [ -z "$(getkv CEREBRO_EMBEDDING_PROVIDER)" ]; then
  case "$models" in
    *mxbai-embed-large*) provider=ollama ;;
    *)                   provider=hashing ;;
  esac
  setkv CEREBRO_EMBEDDING_PROVIDER "$provider"
  echo "==> Embedding provider pinned to '$provider'"
  docker compose up -d api >/dev/null
fi

echo "==> CEREBRO: http://$BIND:$WEB/   (LAN only; create your account there)"
