# CEREBRO — API Contract

Base URL: `/api`. All request and response bodies are JSON.

Authentication is a JWT carried in the `cerebro_session` cookie
(httpOnly, `SameSite=Lax`, `Path=/`). An `Authorization: Bearer <token>`
header is accepted as an alternative.

## POST /api/auth/signup

Register an account and open a session.

Request:

```json
{ "display_name": "Ada Lovelace", "email": "ada@example.com", "password": "at-least-10-chars-1" }
```

Rules: `display_name` 1–100 characters after trimming; `email` a valid address,
stored lowercased, unique; `password` 10–128 characters containing at least one
letter and one digit.

| Status | Meaning                                    |
| ------ | ------------------------------------------ |
| 201    | Created. Sets `cerebro_session`.           |
| 409    | `An account with that email already exists` |
| 422    | Validation failure, per-field detail        |

Response body (201) is a User object. The password hash is never returned.

## POST /api/auth/login

```json
{ "email": "ada@example.com", "password": "at-least-10-chars-1" }
```

| Status | Meaning                                             |
| ------ | --------------------------------------------------- |
| 200    | Authenticated. Sets `cerebro_session`. Body: User.  |
| 401    | `Invalid email or password`                         |

The 401 message is identical for an unknown email and a wrong password, and the
endpoint spends comparable time on both, so accounts cannot be enumerated.

## GET /api/auth/me

| Status | Meaning                       |
| ------ | ----------------------------- |
| 200    | Body: the authenticated User. |
| 401    | Missing, invalid or expired token, or the account no longer exists. |

## POST /api/auth/logout

Clears `cerebro_session`. Always 200 — logging out of a dead session is not an
error and no valid token is required.

```json
{ "message": "Signed out" }
```

## GET /api/health

```json
{ "status": "ok", "database": "up" }
```

`status` is `degraded` and `database` is `down` when PostgreSQL is unreachable.
Used as the readiness and liveness probe.

## User object

```json
{
  "id": "a63dae33-7608-48ed-a834-c80381d13a96",
  "display_name": "Ada Lovelace",
  "email": "ada@example.com",
  "created_at": "2026-09-17T10:03:04.788367Z"
}
```

## Phase 1.5 — profile, preferences, account

All of these resolve the user from the session. None accepts a user id in its
path, query or body, so a client cannot address another user's record.

| Method | Path                    | Notes                                            |
| ------ | ----------------------- | ------------------------------------------------ |
| GET    | `/api/profile`          | Creates an empty profile on first access         |
| PATCH  | `/api/profile`          | Full replacement of editable fields              |
| GET    | `/api/preferences`      | Defaults: local AI, private knowledge, no consent |
| PATCH  | `/api/preferences`      | Partial; omitted fields are left untouched       |
| GET    | `/api/account`          | Safe fields only — never the hash or a token     |
| POST   | `/api/account/password` | Requires the current password                    |

`completion_percent` is derived on every read from a fixed list of twelve
profile fields; it is never stored, so it cannot drift from the data.

Cloud AI processing requires `cloud_ai_consent`. Setting
`ai_processing_mode: "cloud"` without it leaves the mode at `local`, and
withdrawing consent returns the mode to `local`. The consent timestamp is
server-set. No API credentials are stored on these records.

### The embedding and chunking budget

Five further preference fields decide how a document is cut up and embedded:
`embedding_model`, `embedding_dimensions`, `embedding_context_limit`,
`chunk_target_tokens` and `chunk_overlap_tokens`. They were compiled-in
constants until a slide-deck chunk overran the embedding model's context and
failed a whole registration with nothing on screen to say why.

`null` means "inherit whatever this deployment is configured with", so an
untouched account behaves exactly as before and a change to the deployment
default still reaches everyone who has not overridden it. Sending an explicit
`null` clears an override; omitting a field leaves it alone.

A `GET` or `PATCH` also returns an `effective` object — the five values
actually in force once the nulls are resolved, plus `chunk_target_chars` and
an `overridden` list naming which the user chose rather than inherited. It is
derived on every read and never stored, so it cannot drift from the defaults
it is merged with.

The combination is validated on the **merged** row rather than on the request,
because a `PATCH` carries only what changed: a 900-token chunk target is valid
alone and impossible against a stored 512-token limit, so checking the request
alone would admit the pair one field at a time. A rejected combination is a
422 naming the conflict, and nothing is stored. The rules are:

- a stated width must match what the model publishes, where CEREBRO knows it;
- a stated context limit may be **lower** than the model's published context
  but never higher — overrunning it is the failure the setting exists to
  prevent;
- the chunk target must fit inside the effective context limit;
- the overlap must be smaller than the chunk it overlaps.

Changing `embedding_model` or `embedding_dimensions` **orphans existing
vectors**: provider, model and width travel with every vector and search
filters on all three, so documents registered under the old model stay in the
library and stay findable by keyword, but drop out of semantic search until
re-registered. The settings screen warns before saving either. The chunking
fields only affect the next registration; fragments already written keep the
size they were cut at.

Every one of these is resolved from the session's own user, at both write time
(registration) and read time (search and recall), so one account's budget
never reaches another's.

### The context and the payload limit are not the same number

A wordpiece model wraps every input in `[CLS] … [SEP]`. Those are tokens the
daemon counts and the text does not contain, so the text's share of the
context is smaller than the context. `tokens.payload_limit()` is that share —
the context less the special tokens and a small safety margin — and it is what
chunks are cut to, what the guard measures against, and what `/api/ml/status`
reports as `payload_limit` beside `context_limit`.

Measuring against the context instead is what allowed a 1280-character chunk
through: estimated at exactly 512 tokens against a 512-token context, it
passed every check and the daemon refused it as `input length exceeds the
context length`. Two characters decided it.

Two guarantees follow, and both are tested:

- **Nothing oversized is ever sent.** The check sits immediately before the
  request, inside the one function that posts to the daemon, so it covers
  every path — registration, enrichment, search and recall queries, the width
  probe, and anything added later.
- **An oversized input is split, never truncated or dropped.** The pieces are
  embedded and recombined into one vector by a length-weighted mean, so one
  input still yields one vector and no content is lost. A split is recorded in
  telemetry as `embeddings.split`, because a pooled vector is not quite the
  same object as one the model produced in a single pass.

An embedding failure mid-document rolls the whole attempt back: the artifact
stays unregistered and no fragments are written. Registering content that
retrieval cannot reach would show it in the library as trusted evidence no
query can find, and a half-written fragment set is worse than none. The upload
survives, so a retry needs no re-upload.

## Phase 2 — artifacts

Ownership always comes from the session. No route accepts an owner id, and
every lookup is scoped to the authenticated user, so a guessed artifact id
returns 404 rather than another person's document.

| Method | Path                    | Notes                                              |
| ------ | ----------------------- | -------------------------------------------------- |
| POST   | `/api/artifacts`        | multipart upload. Inspects, stores, drafts metadata |
| GET    | `/api/artifacts`        | The owner's library                                 |
| GET    | `/api/artifacts/{id}`   | Detail, including a text preview                    |
| PATCH  | `/api/artifacts/{id}`   | Save reviewed metadata; `approve: true` registers   |
| DELETE | `/api/artifacts/{id}`   | Removes the row and the stored bytes                |

Upload is refused (400) for an empty file, a file over the limit, or any
modality other than text in this phase. Re-uploading bytes already in the
library returns 409 — uniqueness is on `(owner_id, sha256)`.

Registration fails closed. It requires human review, explicit approval, and a
checksum that still matches the stored bytes; if the bytes have drifted since
inspection the artifact stays unregistered and the endpoint returns 409.
`provenance.ai_enrichment` is `null` throughout this phase.
