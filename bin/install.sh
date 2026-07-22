#!/bin/sh
# Install the Cepa marketplace plugins into Claude Code AND set up the
# host project for centralized expertise (via symlink).
#
# Usage:
#   ./bin/install.sh [--clean] [--rollback] [--topology=NAME] [/path/to/host-project]
#
# Without arguments: installs plugins (idempotent), sets up cwd as host project.
# With --clean: also uninstalls existing plugins and SETS ASIDE the marketplace
#   plugin cache before reinstalling. Use this when you've edited plugin
#   source without bumping versions and want CC to pick up the changes. The
#   previous cache is preserved (not deleted) so --rollback can restore it.
# With --rollback: restore the cache set aside by the last --clean and exit.
#   The recovery route for an install that made things worse — or one that
#   died halfway and left the harness in a state nobody chose.
# With --topology=NAME (build-team | build-solo | build-hex | discovery | docs): also copies
#   that topology's snippet into the host project's .claude/ and appends the
#   matching @-import line to CLAUDE.md (idempotent, creates CLAUDE.md if
#   missing). Skip this flag if you want to wire CLAUDE.md yourself.
# With a path argument: sets up the given path as the host project instead of cwd.
#
# Examples:
#   cd ~/test-build-team && ~/.../bin/install.sh
#   ~/.../bin/install.sh ~/some-other-project
#   ~/.../bin/install.sh --clean              # force-refresh everything
#   ~/.../bin/install.sh --rollback           # undo the last --clean
#   ~/.../bin/install.sh --topology=build-hex ~/foo
#   ~/.../bin/install.sh --clean --topology=build-team ~/foo

set -e

# --- Argument parsing ---

CLEAN=0
ROLLBACK=0
TOPOLOGY=""
HOST_PROJECT_INPUT=""

for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    --rollback) ROLLBACK=1 ;;
    --topology=*) TOPOLOGY="${arg#--topology=}" ;;
    --help|-h)
      # Print the whole header block, however long it grows. A hardcoded line
      # count silently truncated the examples the moment a flag was documented.
      sed -n '2,/^$/{/^#/!q; s/^# \{0,1\}//; p;}' "$0"
      exit 0
      ;;
    -*)
      echo "✗ Unknown flag: $arg"
      exit 1
      ;;
    *) HOST_PROJECT_INPUT="$arg" ;;
  esac
done

case "${TOPOLOGY}" in
  ""|build-team|build-solo|build-hex|discovery|docs) ;;
  *)
    echo "✗ Unknown --topology: ${TOPOLOGY}. Use build-team, build-solo, build-hex, discovery, or docs."
    exit 1
    ;;
esac

# Map topology NAME → source directory. They match for every topology except
# `docs`, whose source lives in docs-topology/ (the repo's own docs/ holds the
# marketplace documentation, so the plugin can't share that path).
case "${TOPOLOGY}" in
  docs) TOPOLOGY_DIR="docs-topology" ;;
  *)    TOPOLOGY_DIR="${TOPOLOGY}" ;;
esac

HOST_PROJECT_INPUT="${HOST_PROJECT_INPUT:-$(pwd)}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST_PROJECT="$(cd "${HOST_PROJECT_INPUT}" 2>/dev/null && pwd)" || {
  echo "✗ Host project path does not exist: ${HOST_PROJECT_INPUT}"
  exit 1
}

MARKETPLACE_NAME="cepa"
EXPERTISE_SOURCE="${REPO_DIR}/common/expertise"
EXPERTISE_TARGET="${HOST_PROJECT}/.claude/expertise"
CACHE_DIR="${HOME}/.claude/plugins/cache/${MARKETPLACE_NAME}"
PREV_CACHE_DIR="${CACHE_DIR}.prev"
OPS_DIR="${HOME}/.claude/ops"
OPS_FILE="${OPS_DIR}/last-install.json"

# --- Operational record -----------------------------------------------------
# Changing hooks/bin/settings is an OPERATIONAL update: it changes the surface
# the NEXT agent runs on, and it is invisible from inside a session. The
# minimum route for one is state → target → rollback → validation. This file
# is the state+target half; --rollback is the recovery half; /common:doctor
# reads the record and is the validation half.
#
# It lives under ~/.claude (not the project) because the plugin cache it
# describes is global — one machine, one live harness, whatever repo you
# happen to be standing in.

ops_versions() {  # dir → {"plugin": "version"} for the newest version present
  python3 - "$1" <<'PYOPS'
import json, os, re, sys
root = sys.argv[1]
def sv(v):
    try: return tuple(int(x) for x in re.findall(r"\d+", v)[:3])
    except Exception: return (0,)
out = {}
if os.path.isdir(root):
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        vs = sorted((x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))), key=sv)
        if vs:
            out[name] = vs[-1]
print(json.dumps(out))
PYOPS
}

ops_write() {  # $1 = status, $2 = optional note
  mkdir -p "${OPS_DIR}"
  STATUS="$1" NOTE="${2:-}" \
  FROM="${OPS_FROM:-{\}}" TO="${OPS_TO:-{\}}" \
  REPO="${REPO_DIR}" HOSTP="${HOST_PROJECT:-}" \
  CACHE="${CACHE_DIR}" PREV="${PREV_CACHE_DIR}" \
  OPSF="${OPS_FILE}" STARTED="${OPS_STARTED:-}" \
  python3 - <<'PYOPS'
import json, os
from datetime import datetime, timezone
now = datetime.now(timezone.utc).isoformat()
rec = {
    "status": os.environ["STATUS"],          # in_progress | ok | rolled_back
    "started_at": os.environ.get("STARTED") or now,
    "finished_at": None if os.environ["STATUS"] == "in_progress" else now,
    "repo_dir": os.environ["REPO"],
    "host_project": os.environ.get("HOSTP") or None,
    "cache_dir": os.environ["CACHE"],
    "previous_cache_dir": os.environ["PREV"],
    "versions_before": json.loads(os.environ["FROM"] or "{}"),
    "versions_target": json.loads(os.environ["TO"] or "{}"),
    "note": os.environ.get("NOTE") or None,
}
with open(os.environ["OPSF"], "w") as f:
    json.dump(rec, f, indent=2, ensure_ascii=False)
    f.write("\n")
PYOPS
}

# --- Sanity checks ---

if ! command -v claude > /dev/null 2>&1; then
  echo "✗ The 'claude' CLI is not installed. Install Claude Code first:"
  echo "  https://docs.anthropic.com/en/docs/claude-code"
  exit 1
fi

if [ ! -d "${EXPERTISE_SOURCE}" ]; then
  echo "✗ Expertise source directory not found: ${EXPERTISE_SOURCE}"
  echo "  This script must be run from a complete clone of the marketplace repo."
  exit 1
fi

# --- --rollback: restore and exit (before anything else touches state) ------

if [ "${ROLLBACK}" -eq 1 ]; then
  if [ ! -d "${PREV_CACHE_DIR}" ]; then
    echo "✗ Nothing to roll back to: ${PREV_CACHE_DIR} does not exist."
    echo "  A rollback point is created by --clean (it sets the old cache aside"
    echo "  instead of deleting it). If you have never run --clean since this"
    echo "  feature landed, there is no previous state to restore."
    exit 1
  fi
  echo "▶ --rollback: restoring the cache set aside by the last --clean"
  echo "    from: ${PREV_CACHE_DIR}"
  echo "      to: ${CACHE_DIR}"
  BROKEN_CACHE_DIR="${CACHE_DIR}.rolledback"
  rm -rf "${BROKEN_CACHE_DIR}"
  [ -d "${CACHE_DIR}" ] && mv "${CACHE_DIR}" "${BROKEN_CACHE_DIR}"
  mv "${PREV_CACHE_DIR}" "${CACHE_DIR}"
  OPS_FROM="$(ops_versions "${BROKEN_CACHE_DIR}")"
  OPS_TO="$(ops_versions "${CACHE_DIR}")"
  ops_write "rolled_back" "restored from ${PREV_CACHE_DIR}; the cache being replaced was kept at ${BROKEN_CACHE_DIR}"
  echo "✓ Cache restored. The replaced cache was kept at ${BROKEN_CACHE_DIR}"
  echo "  ⚠ Restart Claude Code — a running session holds the OLD hooks in memory."
  exit 0
fi

# --- Plugin list: derived from marketplace.json (single source of truth) ---
# The install/uninstall lists used to be hardcoded here and drifted from the
# marketplace (the maestro plugin was registered there but forgotten here, so
# --clean reported success while silently not installing it). The marketplace
# manifest is what plugin authors already maintain — derive from it.

MARKETPLACE_JSON="${REPO_DIR}/.claude-plugin/marketplace.json"
PLUGINS="$(python3 -c '
import json, sys
print("\n".join(p["name"] for p in json.load(open(sys.argv[1]))["plugins"]))
' "${MARKETPLACE_JSON}")" || {
  echo "✗ Could not read plugin list from ${MARKETPLACE_JSON}"
  exit 1
}

# --- Optional: --clean teardown ---

# Record the operational state BEFORE anything is torn down: what is live now,
# what we are aiming at. A run that dies between here and the final ops_write
# leaves status=in_progress on disk — which is exactly what /common:doctor
# reports as "last install did not finish", instead of the harness silently
# sitting in a state nobody chose.
OPS_STARTED="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
OPS_FROM="$(ops_versions "${CACHE_DIR}")"
OPS_TO="$(python3 - "${REPO_DIR}" <<'PYOPS'
import glob, json, os, sys
out = {}
for pj in sorted(glob.glob(os.path.join(sys.argv[1], "*", ".claude-plugin", "plugin.json"))):
    try:
        m = json.load(open(pj))
        out[m.get("name") or os.path.basename(os.path.dirname(os.path.dirname(pj)))] = m.get("version", "0")
    except Exception:
        pass
print(json.dumps(out))
PYOPS
)"
ops_write "in_progress"

if [ "${CLEAN}" -eq 1 ]; then
  echo "▶ --clean: uninstalling existing plugins (errors ignored)"
  for PLUGIN in ${PLUGINS}; do
    claude plugin uninstall "${PLUGIN}@${MARKETPLACE_NAME}" 2>/dev/null || true
  done

  if [ -d "${CACHE_DIR}" ]; then
    # Set aside, don't delete: an install with no way back is an operational
    # change without a recovery route, and the absence of one is a fact the
    # human should see BEFORE it matters, not after.
    echo "▶ --clean: setting the current cache aside at ${PREV_CACHE_DIR}"
    echo "    (restore it with: bin/install.sh --rollback)"
    rm -rf "${PREV_CACHE_DIR}"
    mv "${CACHE_DIR}" "${PREV_CACHE_DIR}"
  fi
fi

# --- Marketplace re-registration (always: cheap, refreshes metadata) ---

echo "▶ Refreshing marketplace registration: ${MARKETPLACE_NAME}"
claude plugin marketplace remove "${MARKETPLACE_NAME}" 2>/dev/null || true
claude plugin marketplace add "${REPO_DIR}"

# --- Plugin install (order = marketplace.json order; common comes first) ---

for PLUGIN in ${PLUGINS}; do
  echo "▶ Installing ${PLUGIN}@${MARKETPLACE_NAME}"
  claude plugin install "${PLUGIN}@${MARKETPLACE_NAME}"
done

# --- Per-project setup: symlink for centralized expertise ---

echo ""
echo "▶ Setting up host project: ${HOST_PROJECT}"

if [ "${HOST_PROJECT}" = "${REPO_DIR}" ]; then
  echo "  ⚠ Skipping symlink setup: host project IS the plugin repo itself."
  echo "    Re-run with a different host project path to set up a symlink."
else
  mkdir -p "${HOST_PROJECT}/.claude"

  if [ -L "${EXPERTISE_TARGET}" ]; then
    EXISTING_TARGET="$(readlink "${EXPERTISE_TARGET}")"
    if [ "${EXISTING_TARGET}" = "${EXPERTISE_SOURCE}" ]; then
      echo "  ✔ ${EXPERTISE_TARGET} already symlinks to ${EXPERTISE_SOURCE}"
    else
      echo "  ⚠ ${EXPERTISE_TARGET} is a symlink pointing elsewhere:"
      echo "     -> ${EXISTING_TARGET}"
      echo "  Remove it manually if you want to re-link to the plugin source."
    fi
  elif [ -e "${EXPERTISE_TARGET}" ]; then
    echo "  ⚠ ${EXPERTISE_TARGET} exists and is NOT a symlink. Refusing to clobber."
    echo "  Move or rename it, then re-run this script."
  else
    ln -s "${EXPERTISE_SOURCE}" "${EXPERTISE_TARGET}"
    echo "  ✔ Created symlink: ${EXPERTISE_TARGET}"
    echo "                  -> ${EXPERTISE_SOURCE}"
  fi
fi

# --- Launcher: ccw (auto-isolating claude) ---

CCW="${REPO_DIR}/common/bin/ccw"
if [ -f "${CCW}" ]; then
  chmod +x "${CCW}" 2>/dev/null || true
  echo ""
  echo "▶ Worktree launcher available: ${CCW}"
  echo "  Use it instead of 'claude' to auto-isolate parallel sessions into their"
  echo "  own git worktrees (only when another live session shares the tree)."
  echo "  Add to your shell rc (you run the shell yourself):"
  echo ""
  echo "    alias claude='${CCW}'"
  echo ""
  echo "  Aliasing 'claude' is recommended; ccw falls back to the real binary via"
  echo "  CLAUDE_WT_CLAUDE_BIN. Prefer not to override 'claude'? Alias it as 'ccw':"
  echo "    alias ccw='${CCW}'"
fi

# --- Shell completion for ccw (zsh) ---
# Tab-completes `ccw -s <slice>` with existing session/* worktrees, newest first,
# each captioned with its label (the branch's git description). Resume a recent
# worktree without remembering its timestamp name. You run your own shell, so we
# print the line to add rather than editing your rc.

COMPLETIONS_DIR="${REPO_DIR}/common/completions"
if [ -f "${COMPLETIONS_DIR}/_ccw" ]; then
  echo ""
  echo "▶ zsh completion for ccw available: ${COMPLETIONS_DIR}/_ccw"
  echo "  Tab-completes 'ccw -s <slice>' from your recent session/* worktrees."
  echo "  Add to ~/.zshrc BEFORE the 'compinit' line, then restart your shell:"
  echo ""
  echo "    fpath=(${COMPLETIONS_DIR} \$fpath)"
  echo "    autoload -U compinit && compinit"
  echo ""
  echo "  Note: Warp uses its own completion engine and ignores zsh completions,"
  echo "  so Tab won't work there. In ANY terminal (Warp included), run 'ccw -s'"
  echo "  with no name to pick a recent worktree interactively instead."
fi

# --- Per-project setup: topology snippet + CLAUDE.md @-import ---

if [ -n "${TOPOLOGY}" ] && [ "${HOST_PROJECT}" != "${REPO_DIR}" ]; then
  SNIPPET_SRC="${REPO_DIR}/${TOPOLOGY_DIR}/${TOPOLOGY}-topology.md"
  SNIPPET_DST="${HOST_PROJECT}/.claude/${TOPOLOGY}-topology.md"
  CLAUDE_MD="${HOST_PROJECT}/CLAUDE.md"
  IMPORT_LINE="@.claude/${TOPOLOGY}-topology.md"

  if [ ! -f "${SNIPPET_SRC}" ]; then
    echo "  ✗ Topology snippet not found: ${SNIPPET_SRC}"
    exit 1
  fi

  echo ""
  echo "▶ Wiring topology: ${TOPOLOGY}"

  cp "${SNIPPET_SRC}" "${SNIPPET_DST}"
  echo "  ✔ Copied snippet → ${SNIPPET_DST}"

  # Persist active topology for topology-aware common commands
  # (/common:autonomous-start, /common:autonomous-resume, etc.) to read.
  TOPOLOGY_MARKER="${HOST_PROJECT}/.claude/topology"
  printf '%s\n' "${TOPOLOGY}" > "${TOPOLOGY_MARKER}"
  echo "  ✔ Wrote ${TOPOLOGY_MARKER} (active topology: ${TOPOLOGY})"

  if [ -f "${CLAUDE_MD}" ] && grep -qF "${IMPORT_LINE}" "${CLAUDE_MD}"; then
    echo "  ✔ ${CLAUDE_MD} already imports ${IMPORT_LINE}"
  else
    if [ ! -f "${CLAUDE_MD}" ]; then
      printf '# Project instructions\n\n' > "${CLAUDE_MD}"
      echo "  ✔ Created ${CLAUDE_MD}"
    fi
    printf '\n%s\n' "${IMPORT_LINE}" >> "${CLAUDE_MD}"
    echo "  ✔ Appended ${IMPORT_LINE} to ${CLAUDE_MD}"
  fi

  # Sanity warning: board-flow needs leads, build-solo has none.
  if [ "${TOPOLOGY}" = "build-solo" ]; then
    echo "  ⚠ build-solo has no leads. /board-flow:* commands won't work with this topology."
  fi

  # Seed board-flow project config at project root. This is project-team
  # data (your Jira site, project key, board, etc.) — visible at root, not
  # hidden under .claude/. atlassian-expert reads it on every invocation.
  JIRA_FLOW_DST="${HOST_PROJECT}/board-flow.yaml"
  LEGACY_DST="${HOST_PROJECT}/.claude/board-flow.lifecycle.yaml"

  # Backward-compat note: if the legacy file exists at .claude/, leave it
  # alone but tell the user to migrate. Don't auto-move (avoids surprise on
  # a project that may have local edits in flight).
  if [ -f "${LEGACY_DST}" ] && [ ! -f "${JIRA_FLOW_DST}" ]; then
    echo "  ⚠ Legacy ${LEGACY_DST} found. Move it to ${JIRA_FLOW_DST}"
    echo "    (project root) when you can — atlassian-expert and the board-flow"
    echo "    commands prefer the new location."
  fi

  if [ "${TOPOLOGY}" = "discovery" ]; then
    JIRA_FLOW_SRC="${REPO_DIR}/discovery/board-flow.example.yaml"
    if [ -f "${JIRA_FLOW_DST}" ]; then
      echo "  ✔ ${JIRA_FLOW_DST} already exists — leaving untouched"
    elif [ -f "${JIRA_FLOW_SRC}" ]; then
      cp "${JIRA_FLOW_SRC}" "${JIRA_FLOW_DST}"
      echo "  ✔ Seeded ${JIRA_FLOW_DST} from discovery template"
      echo "    Edit it: set defaults.site, defaults.project_key, defaults.board_id,"
      echo "    and the lifecycle status names to match your discovery board."
    fi
  elif [ "${TOPOLOGY}" = "build-hex" ] || [ "${TOPOLOGY}" = "build-team" ] || [ "${TOPOLOGY}" = "docs" ]; then
    if [ -f "${JIRA_FLOW_DST}" ]; then
      echo "  ✔ ${JIRA_FLOW_DST} already exists — leaving untouched"
    else
      cat > "${JIRA_FLOW_DST}" <<EOF
# board-flow project config for the ${TOPOLOGY} topology.
#
# Two roles for atlassian-expert and the board-flow commands:
#
#   defaults — identity values for every Jira call (site, project, board,
#     issue types, custom fields). atlassian-expert is FORBIDDEN to infer
#     these from context; missing values cause BLOCKED, not guesses.
#
#   default_topology — which topology's leads /board-flow:execute and
#     /board-flow:plan-track-build-validate delegate to.
#
# Edit the defaults below before using board-flow commands. Sample values
# shown — replace site, project_key, board_id with YOUR Jira's values.
schema_version: 1

defaults:
  site: example.atlassian.net
  project_key: EXAMPLE
  board_id: 1
  status_map:
    # Literal Jira status names. Backlog is implicit (where new cards land);
    # to_do is "refined and ready for dev" — what /board-flow:drain pulls from.
    to_do:       "To Do"
    in_progress: "In Progress"
    in_review:   "In Review"
    blocked:     "Blocked"          # set to null if your project lacks a Blocked column
  issue_types:
    story: "Story"
    bug: "Bug"
    epic: "Epic"
    task: "Task"
  required_fields: []   # baseline; per-topology overrides go in topologies: below

  # Scope: narrow which cards the *-drain commands sweep. scope.jql is a raw
  # JQL fragment AND-ed into the column query:
  #     status = "<column>" AND (<scope.jql>) ORDER BY priority, rank
  # Leave '' to sweep the whole column. Precedence (first match wins, no merge):
  #   --no-scope  >  --scope "<jql>"  >  scope_overrides.<command>  >
  #   topologies.<active>.scope  >  defaults.scope
  # Command keys for scope_overrides: drain, prove_drain. Single-card commands
  # (execute/prove/fix/advance) only WARN when the named card is out of scope.
  # Worked example: discovery/board-flow.example.yaml.
  scope:
    jql: ''
  scope_overrides:
    drain:       { jql: '' }
    prove_drain: { jql: '' }

default_topology: ${TOPOLOGY}

# Per-topology overrides — fields here REPLACE the matching defaults
# field when that topology is active. Common use: different Team
# values per topology (engineering vs product), or different
# project_key when discovery uses a separate Jira project. Lists are
# atomic — the override replaces the default list entirely, not
# merged item-by-item. A topology may also carry its own scope: block
# ({ jql: '...' }) at precedence level 4. Topologies without a block here
# inherit defaults wholesale. See discovery/board-flow.example.yaml for a
# worked example.
topologies: {}
EOF
      echo "  ✔ Seeded ${JIRA_FLOW_DST} (default_topology: ${TOPOLOGY})"
      echo "    EDIT IT: replace defaults.site, defaults.project_key, defaults.board_id"
      echo "    with your Jira's values before running any /board-flow:* command."
    fi
  fi

  # Seed build-hex.yaml (role → module mapping) when wiring build-hex.
  # Only seed if absent; if user already customized, don't overwrite.
  # The plugin is opinionated about hexagonal INVARIANTS, not about
  # module naming — this file maps roles to physical modules.
  if [ "${TOPOLOGY}" = "build-hex" ]; then
    HEX_LAYOUT_SRC="${REPO_DIR}/build-hex/build-hex.example.yaml"
    HEX_LAYOUT_DST="${HOST_PROJECT}/build-hex.yaml"
    if [ -f "${HEX_LAYOUT_DST}" ]; then
      echo "  ✔ ${HEX_LAYOUT_DST} already exists — leaving untouched"
    elif [ -f "${HEX_LAYOUT_SRC}" ]; then
      cp "${HEX_LAYOUT_SRC}" "${HEX_LAYOUT_DST}"
      echo "  ✔ Seeded ${HEX_LAYOUT_DST} (canonical layout)"
      echo "    Edit roles.* if your project uses different module names"
      echo "    (e.g. tenancy-core instead of domain). Delete the file"
      echo "    entirely to use canonical defaults."
    fi
  fi
fi

# --- Close the operational record -------------------------------------------
# Reached only if every step above succeeded (set -e). Until this line runs,
# the record on disk says in_progress, and the doctor treats that as an
# unfinished install rather than a healthy one.

ops_write "ok"

# --- Final summary ---

echo ""
echo "✔ Done."
if [ "${CLEAN}" -eq 1 ] && [ -d "${PREV_CACHE_DIR}" ]; then
  echo "  Rollback point: ${PREV_CACHE_DIR}  (restore with bin/install.sh --rollback)"
fi
echo "  Operational record: ${OPS_FILE}  (checked by /common:doctor)"
echo ""
echo "Nine plugins installed:"
echo "    common       — 8 mindset skills (required by every topology)"
echo "    build-team   — 9-agent generic topology + /build-team:plan-build-validate"
echo "    build-solo    — 2-agent dev/reviewer topology"
echo "    build-hex  — 14-agent hexagonal-architecture topology + per-Task quality loop"
echo "    discovery    — 6-agent continuous product-discovery topology"
echo "    design       — 6-agent product-design topology (brief → build-ready spec)"
echo "    board-flow    — atlassian-expert + Jira-aware commands (pair with any topology)"
echo "    docs         — 9-agent documentation/onboarding topology + /docs:survey ... /docs:finalize"
echo "    review-gate  — pre-merge PR gate (open + merge doors)"
echo ""
if [ "${HOST_PROJECT}" != "${REPO_DIR}" ]; then
  echo "Host project setup at ${HOST_PROJECT}:"
  echo "    .claude/expertise/ → centralized plugin expertise (writes shared across projects)"
  if [ -n "${TOPOLOGY}" ]; then
    echo "    .claude/${TOPOLOGY}-topology.md + CLAUDE.md @-import → orchestrator wired"
    echo ""
    echo "You're ready. Open Claude Code in ${HOST_PROJECT} and try:"
    case "${TOPOLOGY}" in
      build-team)  echo "    /build-team:plan-build-validate <task>" ;;
      build-solo)   echo "    /build-solo:* (or just describe a small task — 2-agent dev/reviewer)" ;;
      build-hex) echo "    /build-hex:plan-build-validate <task>" ;;
      discovery)   echo "    /discovery:capture <signal>   (then /board-flow:advance <KEY> to move forward)" ;;
      docs)        echo "    /docs:survey   (then /docs:declutter → /docs:checkpoint → /docs:author → /docs:finalize)" ;;
    esac
  else
    echo ""
    echo "Final manual step: pick ONE topology snippet and import it from CLAUDE.md."
    echo "(Or re-run with --topology=build-team|build-solo|build-hex to automate.)"
    echo ""
    echo "  cp ${REPO_DIR}/build-hex/build-hex-topology.md ${HOST_PROJECT}/.claude/"
    echo "  # OR"
    echo "  cp ${REPO_DIR}/build-team/build-team-topology.md ${HOST_PROJECT}/.claude/"
    echo "  # OR"
    echo "  cp ${REPO_DIR}/build-solo/build-solo-topology.md ${HOST_PROJECT}/.claude/"
    echo ""
    echo "  Then add the matching @-import to ${HOST_PROJECT}/CLAUDE.md:"
    echo "    @.claude/build-hex-topology.md   (or build-team-topology.md / build-solo-topology.md)"
  fi
fi
