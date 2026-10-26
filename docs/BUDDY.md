# CEREBRO on the home server (Buddy)

Runs CEREBRO with Docker Compose on Buddy (Ubuntu, `192.168.1.25`), next to MealSenseAI and the
architecture site, without touching either. It is a separate Compose project named `cerebro`, with
its own database and upload volumes.

| Address | What |
| --- | --- |
| `http://192.168.1.25:3100` | CEREBRO, from any device on the home network |
| `127.0.0.1:18000` | API, from Buddy only (the app does not need it) |
| `127.0.0.1:15432` | PostgreSQL, from Buddy only |

## Install

```bash
cd ~/development/cerebro-mvp
git fetch origin
git checkout deploy/buddy
./scripts/buddy-up.sh
```

The script:

1. works out Buddy's LAN address (or takes `CEREBRO_BIND=…`) and refuses `0.0.0.0`;
2. checks the ports are free (web `3100`, or `CEREBRO_WEB=…`), and that no other Compose project
   is already called `cerebro`;
3. generates a session secret once and keeps it in `.env` (mode 600, never committed);
4. builds and starts PostgreSQL, the migrations, the API and the web app, all restarting with the
   machine;
5. reports which Ollama models the API container can see, and pins the embedding provider.

Open the address it prints and create your account. Accounts on your laptop's CEREBRO are not
copied; this is a fresh library.

## Update

```bash
cd ~/development/cerebro-mvp && git pull && ./scripts/buddy-up.sh
```

The database and uploads are kept; only the images are rebuilt.

## Stop, start, logs

```bash
docker compose stop          # stop, keeping everything
docker compose start
docker compose ps
docker compose logs --tail 80 api web
```

**Never run `make compose-down` or `docker compose down -v` here.** Both delete the database and
every uploaded document.

## Local AI

CEREBRO works without a model: deterministic enrichment, keyword-style search and cited passages.
With Ollama it adds semantic search (`mxbai-embed-large`), written answers and title suggestions
(`qwen3`). It looks for Ollama at `http://host.docker.internal:11434`, which is Buddy itself.

`buddy-up.sh` prints what it found. If it says **not reachable**, Ollama is either running inside
MealSenseAI's Compose project on its internal network, or installed on Buddy but listening on
`127.0.0.1` only. Both are deliberate MealSenseAI settings, so the script changes neither; decide
first, then run the script again.

**Decide before uploading documents.** The script pins the embedding provider on its first run
(`hashing` without Ollama, `ollama` when `mxbai-embed-large` is visible). Changing it later hides
every document already stored until each is re-registered, because vectors from different providers
are never compared.

To change it on purpose: edit `CEREBRO_EMBEDDING_PROVIDER` in `.env`, then run `./scripts/buddy-up.sh`.

## Who can reach it

The web app is bound to the LAN address, so devices at home can open it and nothing outside can: no
router port is forwarded and it is not on the Cloudflare Tunnel. The API and database are bound to
`127.0.0.1`. The database keeps the development password from `docker-compose.yml`, which is why it
is never published beyond Buddy itself.

To use CEREBRO away from home, add a hostname to the existing tunnel behind Cloudflare Access
(email login). Do not publish it without Access, and set `CEREBRO_COOKIE_SECURE=true` once it is
served over HTTPS.
