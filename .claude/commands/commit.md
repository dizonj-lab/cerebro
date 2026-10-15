---
description: Stage and commit the current changes with a descriptive message
argument-hint: "[optional message hint]"
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git add:*), Bash(git commit:*)
---

Current state:

- Status: !`git status --short`
- Staged diff: !`git diff --cached --stat`
- Unstaged diff: !`git diff --stat`
- Recent commits: !`git log --oneline -10`

Review the actual diff, then stage the files that belong in one logical commit
and write a message that matches the style of the recent commits above.

Message hint from the user: $ARGUMENTS

Rules:

- One logical change per commit. If the working tree holds unrelated changes,
  say so and commit only the coherent subset.
- Describe *why* the change was made, not a restatement of the diff.
- Never commit files matched by .gitignore, secrets, or build output.
- Do not push.
