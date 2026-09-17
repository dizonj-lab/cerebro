# CEREBRO — Architecture

Scope: the Experience Foundation work package. Only what exists today is
described here.

## Components

```
Browser
   │
   │  HTTP (same origin in Kubernetes, via ingress)
   ▼
cerebro-web ──────────────► cerebro-api ──────────────► PostgreSQL
Next.js 16 (App Router)     FastAPI                     users table
React 19, Tailwind v4       Argon2id + JWT              UUID primary keys
```

React never touches PostgreSQL. All data access is through the API.

## Request paths

There are two distinct callers of the API, and they authenticate the same way:

1. **Browser → API.** Client components call `src/lib/api.ts`, which sends
   `credentials: "include"` so the session cookie travels with the request.
2. **Next.js server → API.** `src/lib/session.ts` reads the cookie via
   `next/headers` and forwards it to `/api/auth/me`. This is what the protected
   layout uses, and it is the authoritative check.

In Kubernetes both paths resolve to the same host through the ingress, so the
session cookie stays first-party. In local development the API is on port 8000
and the app on port 3000; cookies ignore ports, so a cookie set by
`localhost:8000` is sent to `localhost:3000`. Use `localhost` consistently —
`127.0.0.1` is a different cookie host and a different CORS origin.

## Access control

Two layers, deliberately:

| Layer                        | Checks                       | Purpose                |
| ---------------------------- | ---------------------------- | ---------------------- |
| `src/proxy.ts` (Next proxy)  | Cookie is present            | Cheap redirect, no flash of protected UI |
| `src/app/construct/layout.tsx` | Cookie is **valid**, via API | The real authority     |

The proxy alone is not sufficient — a forged cookie would pass it. The layout
validates the token against the API on every request and redirects to `/login`
if it does not resolve to a user.

## Authentication

- Passwords hashed with **Argon2id** (`argon2-cffi` defaults, OWASP-aligned).
- Session is a **JWT in an httpOnly cookie**, `SameSite=Lax`, `Path=/`.
  httpOnly keeps the token out of reach of page scripts; a cookie (rather than
  `localStorage`) is what allows the session to survive a refresh and be read
  during server rendering.
- A `Bearer` token is accepted as a fallback so non-browser clients can use the
  same endpoints.
- The API refuses to start outside development if `CEREBRO_JWT_SECRET` is still
  the development default or shorter than 32 characters.

## Frontend layering

```
Design tokens         src/app/globals.css  (@theme)
      ↓
UI primitives         src/components/ui/
      ↓
CEREBRO components    src/components/{brand,auth,construct}/
      ↓
Pages                 src/app/{page,login,signup}
      ↓
The Construct         src/app/construct/
```

No page hard-codes a colour; every value comes from a token.
