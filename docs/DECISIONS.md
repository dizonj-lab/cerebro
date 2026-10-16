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

## D4 — Single origin everywhere, via a runtime proxy route

`src/app/api/[...path]/route.ts` proxies `/api/*` to `INTERNAL_API_BASE_URL`, so
the browser only ever talks to the origin that served the page.

This was first implemented as a `rewrites()` entry, which was wrong — see D12.

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

## D12 — The API proxy must be a route handler, not a rewrite

Signup failed in Docker with an unhelpful "Something went wrong.", while working
in development. Cause: `rewrites()` destinations are resolved when the app is
built, and under `output: "standalone"` the resolved host is written literally
into `.next/standalone/server.js`. The image was built without
`INTERNAL_API_BASE_URL`, so it baked the `http://127.0.0.1:8000` fallback and
ignored the value the container set at runtime — proxying to port 8000 inside
the web container, where nothing listens. Next returned a plain-text 500, which
the client could not parse as JSON, hence the generic message.

Confirmed by reading the baked destination out of `routes-manifest.json` and
finding the literal host in the standalone bundle.

The proxy is now a route handler that reads `process.env` per request. Proven by
serving one build twice with different `INTERNAL_API_BASE_URL` values and
getting different targets. `npm run check:runtime-config` fails the image build
if an absolute rewrite destination reappears; the check itself was verified by
reintroducing the rewrite and watching it fail.

Two supporting fixes came out of the same bug:

- The proxy returns `{"detail": ...}` JSON when the API is unreachable, so a
  transport failure surfaces a real message instead of an unparseable error page.
- `Set-Cookie` is copied entry by entry via `getSetCookie()`, because iterating a
  `Headers` object folds multiple cookies into one comma-joined value that
  browsers reject.

## D13 — Local models are discovered, not configured

Ask CEREBRO, enrichment and embeddings all had working Ollama paths that were
off unless an environment variable was set: `CEREBRO_RECALL_LLM=ollama`,
`CEREBRO_ENRICHMENT_LLM=ollama`, `CEREBRO_EMBEDDING_PROVIDER=ollama`. Nothing
told the user that, so a running daemon with the right models pulled still
produced passages instead of answers, and a deterministic hash projection
instead of learned vectors. A feature that depends on configuration nobody
set is a feature that is off, and from the outside it is indistinguishable
from one that is broken.

All three now default to `auto`: one client asks the daemon what is installed
(`GET /api/tags`) and picks from what is actually there, preferring small
instruction-following models for answering and purpose-built embedders for
embedding. `off` pins the deterministic path, which is what the test suite
uses so no test depends on whether a daemon happens to be running.

Two details that cost time elsewhere and are handled here:

- Inside a container `localhost:11434` is the container. Discovery tries the
  configured URL, then `host.docker.internal`, then localhost, so compose
  works without the user knowing this.
- An embedding model's width comes from the model. Known models use their
  published width; anything else is measured once by embedding a single word.
  A wrong width is not a smaller vector — it is a provider that refuses every
  embedding.

The risk `auto` introduces is honest and visible: provider, model and width
travel with every vector and retrieval filters on all three, so if the daemon
is down when a document is registered, those fragments are embedded by the
fallback and are not retrievable once the daemon returns. `/api/ml/status`
therefore reports the active provider and how many fragments lack a vector
for it, and `/api/ml/embeddings/backfill` fixes it without deleting the old
vectors — switching back needs no re-embedding.

## D14 — No Qdrant and no Neo4j yet

The Ask CEREBRO work package authorised both. Neither was added, because
neither is what makes the feature work.

Qdrant would replace an exact cosine scan over the owner's `float4[]` vectors.
That scan is behind the `VectorIndex` interface, is exact rather than
approximate, and at a personal library's scale is not the bottleneck — the
local model's generation time is, by two orders of magnitude. Adding a second
datastore buys approximate search CEREBRO does not need, and costs a service
to deploy, secure, back up and keep consistent with the artifacts table.
The honest trigger for revisiting this is measured latency, which
`/api/ml/status` now records.

Neo4j would replace topic co-occurrence edges computed in SQL. The graph is
co-occurrence and nothing more — CEREBRO never claims an inferred semantic
relationship — so there are no traversals a graph database would answer that
SQL cannot. Graph expansion of retrieval is a real idea, but it needs verified
relationships to expand along, and inventing those is exactly what the
provenance rules forbid.

Both decisions are reversible and neither blocks the RAG flow. They are
recorded here so the next person does not read their absence as an oversight.
