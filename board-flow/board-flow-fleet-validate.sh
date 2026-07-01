#!/usr/bin/env bash
#
# board-flow-fleet-validate.sh — validation-first LOCAL read for a board-flow fleet (any repo).
#
# WHY THIS EXISTS
#   board-flow "loop-engineering" routines can run in the cloud (/schedule) ONLY for
#   GitHub-hosted repos the cloud sandbox can clone. For a repo the sandbox can't reach
#   (e.g. Bitbucket-hosted — proven for wego, see docs/loop-engineering.md), the fleet runs
#   LOCALLY via the mcp-atlassian MCP server (static API token). This script is the
#   *validation-first* step: it proves the local auth+read stack works
#   (token -> mcp-atlassian authenticates -> project visible -> To-Do lists) BEFORE any
#   autonomous build is ever unleashed. READ-ONLY: no build, no Jira mutation.
#
# USAGE
#   board-flow-fleet-validate.sh [REPO_PATH]                 # REPO_PATH defaults to $PWD
#
#   # Config-driven (repo has board-flow.yaml): project_key + To-Do status come from it.
#   board-flow-fleet-validate.sh /path/to/board-flow-repo
#
#   # Override mode (repo has NO board-flow.yaml yet, e.g. wego):
#   PROJECT_KEY=WEGO TODO_STATUS='A fazer' board-flow-fleet-validate.sh ~/path/to/wego
#
#   Env knobs: SECRETS_FILE (default ~/.zsecrets), CLAUDE_BIN (default ~/.local/bin/claude),
#              PROJECT_KEY, TODO_STATUS.
#
# NOT scheduled — run by hand. Promote to launchd/cron (running the real /board-flow:drain
# under autonomous-mode) only after this passes. See docs/loop-engineering.md.

set -euo pipefail

REPO_PATH="${1:-$PWD}"
SECRETS_FILE="${SECRETS_FILE:-$HOME/.zsecrets}"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
PROJECT_KEY="${PROJECT_KEY:-}"   # optional override; else resolved from board-flow.yaml
TODO_STATUS="${TODO_STATUS:-}"   # optional override; else resolved from board-flow.yaml

# 1. Load the static token — a launchd/cron job does NOT source ~/.zprofile, so we source
#    the secrets file here. This is the #1 footgun; guard against a silent auth failure.
if [[ -f "$SECRETS_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$SECRETS_FILE"
fi
if [[ -z "${JIRA_API_TOKEN:-}" ]]; then
  echo "BLOCKED: JIRA_API_TOKEN is not set (source $SECRETS_FILE failed or the var is missing)." >&2
  echo "        mcp-atlassian would authenticate with an unresolved token and read zero cards —" >&2
  echo "        that is an AUTH failure, NOT an empty board. Aborting." >&2
  exit 1
fi
export JIRA_API_TOKEN

# 2. Sanity: binary, checkout, and a way to know project_key + To-Do status.
[[ -x "$CLAUDE_BIN" ]] || { echo "BLOCKED: claude not executable at $CLAUDE_BIN (set CLAUDE_BIN)." >&2; exit 1; }
[[ -d "$REPO_PATH"  ]] || { echo "BLOCKED: repo path not found: $REPO_PATH" >&2; exit 1; }

has_config=false
[[ -f "$REPO_PATH/board-flow.yaml" || -f "$REPO_PATH/.claude/board-flow.lifecycle.yaml" ]] && has_config=true
if { [[ -z "$PROJECT_KEY" || -z "$TODO_STATUS" ]]; } && ! $has_config; then
  echo "BLOCKED: no board-flow.yaml in $REPO_PATH and PROJECT_KEY/TODO_STATUS not both set." >&2
  echo "        Add board-flow.yaml (/board-flow:configure), or run with overrides, e.g.:" >&2
  echo "          PROJECT_KEY=WEGO TODO_STATUS='A fazer' $(basename "$0") $REPO_PATH" >&2
  exit 1
fi

cd "$REPO_PATH"

if [[ -n "$PROJECT_KEY" && -n "$TODO_STATUS" ]]; then
  CONFIG_LINE="Use project_key=\"$PROJECT_KEY\" and To-Do status=\"$TODO_STATUS\" (provided explicitly; do NOT read board-flow.yaml)."
else
  CONFIG_LINE="Read board-flow.yaml at the repo root (or .claude/board-flow.lifecycle.yaml) and resolve defaults.project_key and defaults.status_map.to_do from it."
fi

PROMPT="VALIDATION-FIRST board read (READ-ONLY — do NOT build, run tests, git, or transition/edit any Jira issue).

$CONFIG_LINE

Use the mcp-atlassian MCP tools ONLY (mcp__mcp-atlassian__*):
1. PREFLIGHT: call jira_get_all_projects and confirm the project_key is present. If the call errors, returns no projects, or the key is absent, reply EXACTLY:
   \"BLOCKED: mcp-atlassian preflight failed — <verbatim error / project not visible>. This is an AUTH/connection failure, NOT an empty board.\" and STOP.
2. If preflight passes, call jira_search with:
     jql   = project = <project_key> AND status = \"<To-Do status>\" ORDER BY priority DESC
     limit = 20
   List each card as: KEY — summary — priority. Report the count (note if more pages exist).
3. End with one line:
   \"VALIDATION PASS: mcp-atlassian authenticated, <project_key> visible, To-Do listed (<N> cards).\"
   or the BLOCKED line from step 1.

Do NOT run any build, test, or git command. Do NOT create/edit/transition/comment any issue."

exec "$CLAUDE_BIN" -p "$PROMPT" \
  --allowedTools "Read" "mcp__mcp-atlassian__jira_get_all_projects" "mcp__mcp-atlassian__jira_search"
