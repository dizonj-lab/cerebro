# CLAUDE.md

Project guidance for Claude Code. Keep this file short and factual — it is
loaded into context on every session.

## Project

**CEREBRO** — an Adaptive Knowledge and Reasoning Digital Twin. It turns
personal knowledge and experiences into a connected, private, searchable store:
Learn · Connect · Reason · Recall.

- Frontend: Next.js 16 (App Router), React 19, TypeScript, Tailwind v4 — `frontend/`
- Backend: FastAPI, SQLAlchemy 2, Alembic, Python 3.11 — `backend/`
- Database: PostgreSQL 16
- Deployment: Kubernetes, namespace `cerebro` — `k8s/`

React never connects to PostgreSQL directly. All data access goes through the API.

## Commands

| Purpose       | Command                                                    |
| ------------- | ---------------------------------------------------------- |
| Backend deps  | `cd backend && uv pip install -e ".[dev]"`                 |
| Migrate       | `cd backend && alembic upgrade head`                       |
| Run API       | `cd backend && uvicorn app.main:app --reload --port 8000`  |
| Backend tests | `cd backend && pytest -q`                                  |
| Frontend deps | `cd frontend && npm install`                               |
| Run web       | `cd frontend && npm run dev`                               |
| Whole stack   | `make up` (Kubernetes) or `make compose-up` (Docker)       |
| Port in use   | Append `WEB_PORT=3100` to any of the above                 |
| Validate k8s  | `make validate`                                            |
| Typecheck     | `cd frontend && npm run typecheck`                         |
| Lint          | `cd frontend && npm run lint`                              |
| Build         | `cd frontend && npm run build`                             |
| E2E tests     | `cd frontend && npm run test:e2e` (both servers must be up) |

## Layout

```
backend/app/{api,core,db,models,schemas,services}   FastAPI application
backend/alembic/                                    migrations
backend/tests/                                      pytest, real PostgreSQL
frontend/src/app/                                   routes: /, /login, /signup, /construct
frontend/src/components/{ui,brand,auth,construct}/  primitives → components
frontend/src/lib/                                   api client, server session, cn
frontend/e2e/                                       Playwright journey + UI suites
k8s/                                                manifests, namespace cerebro
docs/                                               architecture, contracts, state
```

## Conventions

- Design tokens live in `frontend/src/app/globals.css`. Never hard-code a colour
  in a component; add or use a token. The dark theme re-points the same tokens,
  so a hard-coded colour breaks it — `text-white` on the accent became
  `text-accent-ink` for exactly this reason. Appearance is a user preference
  (`system` | `light` | `dark`), mirrored to localStorage so the first paint
  does not flash.
- Components layer strictly: tokens → `components/ui` primitives → CEREBRO
  components → pages. Do not style a page independently.
- Auth logic stays out of presentation components — use `lib/api.ts` (browser)
  or `lib/session.ts` (server).
- Backend: HTTP concerns in `app/api`, business logic in `app/services`,
  reusable primitives in `app/core`. Services take a `Session`, not a `Request`.
- Tests run against real PostgreSQL and a real browser. Do not introduce mocks
  for either.

## Things to know

- The browser only ever calls the **web origin**. `src/app/api/[...path]/route.ts`
  proxies `/api` to the backend, so the session cookie is always first-party and
  no CORS is involved. Do not point the browser at the API directly.
- **Never proxy `/api` with `rewrites()`.** Rewrite destinations resolve at build
  time and are written into the standalone server bundle, so a container ignores
  the runtime environment and proxies to the wrong host. This shipped once and
  broke signup in Docker. `npm run check:runtime-config` fails the image build if
  it returns.
- `INTERNAL_API_BASE_URL` is the proxy and server-render target, read at runtime.
  `NEXT_PUBLIC_API_BASE_URL` is inlined at **build** time and must stay empty for
  containers — setting it in a Deployment does nothing.
- The session is a JWT in an **httpOnly** cookie (`cerebro_session`). It is not
  readable from JavaScript by design — do not add a client-side token store.
- `/construct` is protected twice: `src/proxy.ts` checks the cookie exists,
  `src/app/construct/layout.tsx` validates it against the API. The layout is the
  authority; the proxy only prevents a flash of protected UI.
- Email uniqueness is enforced by the unique index, and duplicates are caught
  via `IntegrityError` — never by a prior `SELECT`, which races.
- Login returns one message for unknown-email and wrong-password. Keep it that
  way; it is deliberate anti-enumeration behaviour with a test asserting it.
- The API refuses to start outside development unless `CEREBRO_JWT_SECRET` is
  set to 32+ characters.
- Sidebar items other than Dashboard are inert placeholders for future work
  packages. Do not wire them up without an explicit work package.
- Enrichment **proposes**, it never establishes. Every field carries its
  method in `field_methods`, and only approval sets `human_confirmed`.
  `created_date` may come **only** from the document's own metadata. `author`
  may come from that or from a **byline the document prints on its own first
  page** — a line carrying an honorific or an introducer like "Presented by",
  taken verbatim and marked `extracted_byline`. No model may propose either,
  and a name in the body is never an author: being mentioned is not evidence
  of having written it. A model's suggested topics and tags are dropped
  unless they appear in the document verbatim.
- A title the authoring tool wrote is not the document's title. "PowerPoint
  Presentation" and "Microsoft Word - Document1" are dropped so a better
  candidate can through; a real title behind a tool prefix is kept.
- There is **no cloud AI engine**. A failing local engine falls back to
  deterministic enrichment, never to a remote service. Say "CEREBRO
  environment", not "your device", and never claim data never leaves it.
- Inside a container, `localhost:11434` is the container, not the host. Ollama
  is reached at `host.docker.internal`, with `extra_hosts: host-gateway` for
  Linux parity. See `docs/DEVELOPMENT.md`.
- Switching embedding provider **orphans existing vectors**: provider, model
  and dimensions are stored per vector and search filters on all three, so
  artifacts must be re-registered under the new provider to be found. The
  model, width, context limit, chunk size and overlap are per-user settings
  (null = deployment default), resolved via `services/ingest_settings.py` at
  both write and read time — a query must be embedded by the same model its
  vectors were. Their combination is validated on the merged preferences row,
  never field by field: a chunk target and a context limit are each valid
  alone and impossible together.
- Extracted text is a **derived object** in the object store, keyed
  `<storage_key>.extraction.json`; the artifact row holds only a summary in
  `extraction`. Never put document text on the row — a library query would
  then carry megabytes of it. The original bytes are stored verbatim so
  registration re-verifies the checksum against the source, never the derived
  text.
- A container image that writes to a mounted volume must **create and chown the
  directory itself**. A volume mounted over a path absent from the image is
  created owned by root, and the API runs as uid 10001 — uploads then fail with
  a `PermissionError`. FastAPI returns plain text for an unhandled exception, so
  the browser shows only "Something went wrong." This cost a full debugging
  cycle; see `backend/Dockerfile`.
- Run the e2e suite against the **compose containers**, not a locally started
  `next start`. The two differ: upload is the only multipart request and the
  only write to a volume, and it was broken in containers while green locally.
- An upload is refused when the bytes contradict the extension, and when a PDF
  has no text layer. Both are deliberate: the filename is a claim and the bytes
  are the evidence, and an artifact with no retrievable content must not enter
  the library.
- Brand name, tagline and pillars come from the `BRAND` constant in
  `src/components/brand/Logo.tsx`. Do not retype them in a page.
- The brand mark is the supplied artwork at `public/brand/cerebro-mark.png`.
  The wordmark and tagline are set in type, not baked into the image — see
  `frontend/public/brand/README.md` before changing either.
