# CEREBRO — Decisions

Decisions taken during the Experience Foundation work package. Each one became
a contract because no prior baseline existed to inherit.

## D1 — Argon2id for password hashing

`argon2-cffi` with library defaults (m=65536, t=3, p=4), which follow the OWASP
recommendation. Rehashing on login is handled when parameters change.

## D2 — JWT in an httpOnly cookie, not `localStorage`

The session must survive a page refresh and be readable during server rendering,
and logout must be a real endpoint. A cookie satisfies all three; `localStorage`
satisfies none of them cleanly and exposes the token to any script on the page.
`SameSite=Lax` is the default; `CEREBRO_COOKIE_SECURE=true` should be set
wherever HTTPS terminates.

A `Bearer` fallback is accepted so the API stays usable outside a browser.

## D3 — Two-layer route protection

The Next proxy checks only that a cookie exists; the `/construct` server layout
validates it against `/api/auth/me`. The proxy prevents a flash of protected UI;
the layout is the authority. Relying on the proxy alone would accept a forged
cookie.

## D4 — Single origin everywhere, via a Next.js rewrite

Next.js proxies `/api/:path*` to `INTERNAL_API_BASE_URL`, so the browser only
ever talks to the origin that served the page.

This replaced an earlier design where the browser called the API directly and an
ingress was responsible for presenting one host. That version had three problems:
it needed CORS configured correctly, it made the session cookie's first-party
status depend on deployment topology, and it silently broke when the app was
opened on `127.0.0.1` rather than `localhost` — a different cookie host *and* a
different CORS origin.

With the proxy, all three disappear. Verified by running the full end-to-end
suite against both `localhost:3000` and `127.0.0.1:3000`: 31/31 on each, where
the latter previously failed outright. The ingress became optional — a plain
`kubectl port-forward` to the web service is now a complete deployment.

## D5 — One light theme, no dark mode

The design contract calls for a single consistent visual language across four
pages. A half-considered dark variant would work against that. Tokens are
structured so a dark theme can be added later by redefining them in one place.

## D6 — Account enumeration resistance

Login returns one message, `Invalid email or password`, for both an unknown
address and a wrong password, and hashes a dummy value on the miss path so the
two cases take comparable time. Signup necessarily reveals that an address is
taken — that is the accepted trade-off for a usable registration form.

## D7 — Colour tokens validated, not eyeballed

Every text token is checked against every surface it can appear on. This caught
a real failure: the original `ink-subtle` passed on white (4.71:1) but failed on
the sidebar's subtle surface (4.43:1). The token was darkened to `#636c7a`,
which passes on all three surfaces.

## D8 — Kubernetes manifests written but unapplied

The development container has no Docker daemon and no cluster, so the manifests
under `k8s/` are YAML-validated only. This is recorded as BLOCKED rather than
reported as a deployment.

## D9 — Brand copy follows the logo, not the original work package

The supplied logo carries the tagline *Adaptive Knowledge and Reasoning Digital
Twin* and the pillars *Learn · Connect · Reason · Recall*. The Experience
Foundation work package specified *Digital Knowledge Twin* and *Capture →
Connect → Reason → Recall*. The logo wins, by the product owner's decision.

Consequences: the landing eyebrow, pillar list, page metadata, auth subtitles
and the Construct welcome line were updated, along with the tests asserting
them. `Capture` became `Learn`.

Name, tagline and pillars now live in one `BRAND` constant
(`src/components/brand/Logo.tsx`) so a future wording change is one edit, not a
search across pages.

## D10 — Wordmark set in type, not baked into the artwork

The supplied logo is a lockup (mark + wordmark + tagline + pillar strip). Only
the mark is used as an image; the wordmark, tagline and pillars are rendered as
text. This keeps them crisp at every size, lets them inherit the ink colour
token, keeps them selectable and searchable, and means the header can show a
compact mark + wordmark where the full lockup would be illegible at 64px.

## D11 — `NEXT_PUBLIC_API_BASE_URL` must be empty in container images

`NEXT_PUBLIC_*` values are inlined into the browser bundle when the image is
built; they are not read at runtime. An earlier version of the web Deployment
set it as a runtime environment variable, which did nothing, and the Dockerfile
defaulted it to `/`, which produced `//api/auth/login` — a protocol-relative URL
that a browser resolves to a host literally named `api`.

The default is now empty (same origin), and `src/lib/api.ts` strips trailing
slashes so no configured value can reproduce the bug. Verified by building with
the variable empty and grepping the emitted bundle for the inlined path.
