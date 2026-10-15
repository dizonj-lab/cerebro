# .claude/

Project-level configuration for [Claude Code](https://code.claude.com/docs).
Everything here is committed and shared with the team, except
`settings.local.json`, which is gitignored.

```
.claude/
├── README.md              # this file
├── settings.json          # shared settings: permissions, env, hooks
├── settings.local.json    # personal overrides — gitignored, never committed
├── commands/              # slash commands  -> /check, /commit
├── agents/                # subagents       -> code-reviewer
├── skills/                # skills          -> repo-conventions/SKILL.md
└── hooks/                 # hook scripts referenced by settings.json
```

`CLAUDE.md` lives at the repo root, not here — it is the project memory file
and is read into context automatically at the start of every session.

## settings.json

Shared project settings. Precedence, lowest to highest: user settings
(`~/.claude/settings.json`) → this file → `settings.local.json` → enterprise
policy. The `permissions` block controls which tool calls run without a
prompt (`allow`), which always prompt (`ask`), and which are refused outright
(`deny`).

Put anything machine-specific — a local API base URL, your own extra
allowances — in `settings.local.json` instead. It is already in `.gitignore`.

## commands/

Each `.md` file becomes a slash command named after the file: `check.md` →
`/check`. Frontmatter takes `description`, `argument-hint` and
`allowed-tools`. In the body, `$ARGUMENTS` expands to everything the user
typed, `$1`/`$2` to positional arguments, `@path` inlines a file, and
`` !`cmd` `` inlines the output of a shell command at invocation time.

Subdirectories namespace the command: `commands/db/migrate.md` → `/db:migrate`.

## agents/

Subagents run in their own context window with their own tool allowance, so a
long investigation does not crowd the main conversation. Frontmatter takes
`name`, `description` (this is what decides when Claude delegates to it),
`tools` and `model` (`inherit` follows the main session).

## skills/

Each skill is a directory containing `SKILL.md` with `name` and `description`
frontmatter. Claude loads a skill's body only when the description matches the
task at hand, which makes skills the right home for procedural knowledge that
is too long or too situational for `CLAUDE.md`. Supporting files can sit
alongside `SKILL.md` and be referenced by relative path.

## hooks/

Shell scripts invoked at fixed points in the agent loop (`PreToolUse`,
`PostToolUse`, `SessionStart`, `Stop`, and others), wired up in the `hooks`
block of `settings.json`. A hook receives the event as JSON on stdin; for
`PreToolUse`, exit code `2` blocks the tool call and returns stderr to Claude
as feedback.

`hooks/pre-commit-guard.sh` is a working example — it blocks a `git commit`
that would include an `.env` file or anything under `secrets/`. It is not
enabled by default; the script's header comment has the settings snippet that
turns it on.

## Adding to this

Keep `CLAUDE.md` short — it is in context on every turn. Anything long,
optional or task-specific belongs in a skill or a command instead.
