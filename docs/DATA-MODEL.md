# CEREBRO — Data Model

PostgreSQL 16. Schema is managed by Alembic (`backend/alembic/`); migration
`51f951ae16d7` creates the initial table.

## users

| Column          | Type                       | Constraints                     |
| --------------- | -------------------------- | ------------------------------- |
| `id`            | `uuid`                     | Primary key, generated `uuid4`  |
| `display_name`  | `varchar(100)`             | Not null                        |
| `email`         | `varchar(320)`             | Not null, **unique** (`ix_users_email`), stored lowercased |
| `password_hash` | `varchar(255)`             | Not null, Argon2id encoded hash |
| `created_at`    | `timestamptz`              | Not null, defaults to `now()`   |
| `updated_at`    | `timestamptz`              | Not null, `now()` on insert and update |

Notes:

- Plaintext passwords are never stored or logged. `password_hash` holds an
  Argon2id encoded string (`$argon2id$v=19$m=65536,t=3,p=4$…`).
- Duplicate detection relies on the unique index, not a prior `SELECT`, so two
  concurrent signups for the same address cannot both succeed.
- `email` is normalised (trimmed, lowercased) on write and on lookup, making
  address matching case-insensitive.
