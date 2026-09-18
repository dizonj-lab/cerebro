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
  in a component; add or use a token.
- Components layer strictly: tokens → `components/ui` primitives → CEREBRO
  components → pages. Do not style a page independently.
- Auth logic stays out of presentation components — use `lib/api.ts` (browser)
  or `lib/session.ts` (server).
- Backend: HTTP concerns in `app/api`, business logic in `app/services`,
  reusable primitives in `app/core`. Services take a `Session`, not a `Request`.
- Tests run against real PostgreSQL and a real browser. Do not introduce mocks
  for either.

## Things to know

- The browser only ever calls the **web origin**. Next.js rewrites `/api` to the
  backend (`next.config.ts`), so the session cookie is always first-party and no
  CORS is involved. Do not point the browser at the API directly.
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
- Brand name, tagline and pillars come from the `BRAND` constant in
  `src/components/brand/Logo.tsx`. Do not retype them in a page.
- The brand mark is the supplied artwork at `public/brand/cerebro-mark.png`.
  The wordmark and tagline are set in type, not baked into the image — see
  `frontend/public/brand/README.md` before changing either.
