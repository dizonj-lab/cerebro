#!/usr/bin/env bash
# Example PreToolUse hook: block commits that would include obvious secrets.
#
# Not wired up by default. To enable, add to .claude/settings.json:
#
#   "hooks": {
#     "PreToolUse": [
#       {
#         "matcher": "Bash",
#         "hooks": [
#           { "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/pre-commit-guard.sh" }
#         ]
#       }
#     ]
#   }
#
# Contract: reads the tool call as JSON on stdin. Exit 0 to allow, exit 2 to
# block and send stderr back to Claude as feedback.
set -euo pipefail

payload=$(cat)
command=$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))')

case "$command" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

if git diff --cached --name-only | grep -Eq '(^|/)\.env($|\.)|(^|/)secrets/'; then
  echo "Blocked: staged changes include an .env file or something under secrets/." >&2
  echo "Unstage it before committing." >&2
  exit 2
fi

exit 0
