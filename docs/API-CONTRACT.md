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
