# CLAUDE.md

Project guidance for Claude Code. Keep this file short and factual — it is
loaded into context on every session, so it costs tokens on every turn.

> This file was scaffolded before the codebase existed. Fill in the `TODO`
> markers as the project takes shape, and delete anything that stops being true.

## Project

**cerebro** — TODO: one or two sentences on what this project is and who uses it.

- Language / runtime: TODO
- Package manager: TODO
- Entry point: TODO

## Commands

Replace these with the real ones once tooling is in place. Claude prefers
commands listed here over guessing.

| Purpose      | Command |
| ------------ | ------- |
| Install deps | `TODO`  |
| Run locally  | `TODO`  |
| Test         | `TODO`  |
| Test (single)| `TODO`  |
| Lint         | `TODO`  |
| Format       | `TODO`  |
| Typecheck    | `TODO`  |
| Build        | `TODO`  |

## Layout

```
.
├── CLAUDE.md          # this file
├── .claude/           # Claude Code project config (see .claude/README.md)
└── readme.md
```

TODO: describe the real source directories as they are added.

## Conventions

- TODO: naming, module boundaries, error handling, logging.
- TODO: test layout and what must be covered.
- Commit messages: TODO (e.g. Conventional Commits).

## Things to know

Non-obvious constraints that are easy to get wrong — migrations that must run in
order, a service that must be up for tests, a generated file that must never be
hand-edited. Add them here as you hit them.

- TODO
