#!/usr/bin/env bash
#
# board-flow-fleet-validate.sh — validation-first LOCAL read for a board-flow fleet (any repo).
#
# WHY THIS EXISTS
#   board-flow "loop-engineering" routines can run in the cloud (/schedule) ONLY for
#   GitHub-hosted repos the cloud sandbox can clone. For a repo the sandbox can't reach
#   (e.g. Bitbucket-hosted — proven for wego, see docs/loop-engineering.md), the fleet runs
#   LOCALLY, and locally the atlassian-expert reaches Jira through the `twg` CLI (OAuth,
#   ~/.config/twg/auth.conf). This script is the *validation-first* step: it proves that
#   exact path works (twg authenticates -> project visible -> To-Do lists) BEFORE any
#   autonomous build is ever unleashed. READ-ONLY: no build, no Jira mutation.
#
#   Until 2026-09 this script ran `claude -p` restricted to the mcp-atlassian MCP server
#   (static JIRA_API_TOKEN). The agent stopped using that server, so a PASS proved a path
#   no run takes, and a broken twg went unnoticed. It now calls twg directly — no claude,
#   no token.
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
#   Env knobs: TWG_BIN (default: twg on PATH), PROJECT_KEY, TODO_STATUS, LIMIT (default 20).
#
# EXIT
#   0  VALIDATION PASS
#   1  BLOCKED (auth/connection, project not visible, config missing) — never an empty board
#
# NOT scheduled — run by hand. Promote to launchd/cron (running the real /board-flow:drain
# under autonomous-mode) only after this passes. See docs/loop-engineering.md.

set -euo pipefail

REPO_PATH="${1:-$PWD}"
TWG_BIN="${TWG_BIN:-$(command -v twg || true)}"
PROJECT_KEY="${PROJECT_KEY:-}"   # optional override; else resolved from board-flow.yaml
TODO_STATUS="${TODO_STATUS:-}"   # optional override; else resolved from board-flow.yaml
LIMIT="${LIMIT:-20}"

blocked() { echo "BLOCKED: $*" >&2; exit 1; }

# 1. Sanity: binary and checkout.
[[ -n "$TWG_BIN" && -x "$TWG_BIN" ]] || blocked "twg not found (install it, or set TWG_BIN)."
[[ -d "$REPO_PATH" ]] || blocked "repo path not found: $REPO_PATH"

# 2. project_key + To-Do status: overrides win, else board-flow.yaml.
if [[ -z "$PROJECT_KEY" || -z "$TODO_STATUS" ]]; then
  cfg=""
  for c in "$REPO_PATH/board-flow.yaml" "$REPO_PATH/.claude/board-flow.lifecycle.yaml"; do
    [[ -f "$c" ]] && { cfg="$c"; break; }
  done
  if [[ -z "$cfg" ]]; then
    echo "BLOCKED: no board-flow.yaml in $REPO_PATH and PROJECT_KEY/TODO_STATUS not both set." >&2
    echo "        Add board-flow.yaml (/board-flow:configure), or run with overrides, e.g.:" >&2
    echo "          PROJECT_KEY=WEGO TODO_STATUS='A fazer' $(basename "$0") $REPO_PATH" >&2
    exit 1
  fi
  resolved="$(python3 - "$cfg" <<'PY'
import sys
try:
    import yaml
except ImportError:
    sys.exit("PyYAML missing: cannot read board-flow.yaml (pip install pyyaml, or pass PROJECT_KEY/TODO_STATUS)")
try:
    d = (yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}).get("defaults") or {}
except Exception as e:
    sys.exit(f"{sys.argv[1]} unreadable: {e}")
print(d.get("project_key") or "")
print((d.get("status_map") or {}).get("to_do") or "")
PY
)" || blocked "could not read $cfg"
  [[ -n "$PROJECT_KEY" ]] || PROJECT_KEY="$(sed -n 1p <<<"$resolved")"
  [[ -n "$TODO_STATUS" ]] || TODO_STATUS="$(sed -n 2p <<<"$resolved")"
  [[ -n "$PROJECT_KEY" && -n "$TODO_STATUS" ]] \
    || blocked "$cfg has no defaults.project_key and/or defaults.status_map.to_do."
fi

twg_json() { "$TWG_BIN" "$@" -o json --output-summary none; }

# 3. PREFLIGHT — twg authenticates. A failure here is AUTH/connection, NOT an empty board.
doctor="$(twg_json doctor 2>&1)" || true
conn="$(python3 -c '
import json, sys
try:
    c = (json.loads(sys.stdin.read()).get("data") or {}).get("connectivity") or {}
except ValueError:
    print("unparseable twg doctor output"); sys.exit()
print("ok" if c.get("ok") is True else (c.get("message") or "connectivity not ok"))
' <<<"$doctor")"
[[ "$conn" == "ok" ]] \
  || blocked "twg preflight failed — $conn. This is an AUTH/connection failure, NOT an empty board. (twg auth login)"

# 4. The project is visible to this account.
space="$(twg_json jira space get "$PROJECT_KEY" 2>&1)" \
  || blocked "project $PROJECT_KEY not visible via twg — $(head -c 300 <<<"$space")"

# 5. List the To-Do column.
JQL="project = $PROJECT_KEY AND status = \"$TODO_STATUS\" ORDER BY priority DESC"
query="$(twg_json jira workitem query "$JQL" --first "$LIMIT" 2>&1)" \
  || blocked "To-Do query failed — $(head -c 300 <<<"$query")"

python3 -c '
import json, sys
key, status = sys.argv[1], sys.argv[2]
try:
    issues = (json.loads(sys.stdin.read()).get("data") or {}).get("issues")
except ValueError:
    issues = None
if not isinstance(issues, list):
    print("BLOCKED: unexpected twg query output (no data.issues).", file=sys.stderr); sys.exit(1)
for i in issues:
    pr = i.get("priority")
    pr = pr.get("name", "-") if isinstance(pr, dict) else (pr or "-")
    print(" — ".join((str(i.get("key")), str(i.get("summary")), str(pr))))
print("VALIDATION PASS: twg authenticated, %s visible, To-Do \"%s\" listed (%d cards)." % (key, status, len(issues)))
' "$PROJECT_KEY" "$TODO_STATUS" <<<"$query"
