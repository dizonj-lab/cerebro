---
description: Run the project's lint, typecheck and test suite, then fix what fails
argument-hint: "[path or test name]"
allowed-tools: Bash, Read, Edit, Glob, Grep
---

Run the checks listed in the Commands table of @CLAUDE.md, in this order:

1. Format / lint
2. Typecheck
3. Tests

Scope: $1 (if empty, run against the whole project).

For each failure: read the failing code, identify the root cause, and fix it.
Do not skip, disable, or weaken a test to make it pass. Re-run the failing
check after each fix to confirm it is green.

Finish by reporting, in a few lines, what failed and what you changed. If a
failure is pre-existing on the base branch, say so instead of fixing it
silently.
