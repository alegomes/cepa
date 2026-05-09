#!/bin/sh
# Install the alegomes multi-team plugins into Claude Code AND set up the
# host project for centralized expertise (via symlink).
#
# Usage:
#   ./bin/install.sh [--clean] [--topology=NAME] [/path/to/host-project]
#
# Without arguments: installs plugins (idempotent), sets up cwd as host project.
# With --clean: also uninstalls existing plugins and nukes the marketplace
#   plugin cache before reinstalling. Use this when you've edited plugin
#   source without bumping versions and want CC to pick up the changes.
# With --topology=NAME (multi-team | solo-pair | hex-backend | book): also copies
#   that topology's snippet into the host project's .claude/ and appends the
#   matching @-import line to CLAUDE.md (idempotent, creates CLAUDE.md if
#   missing). Skip this flag if you want to wire CLAUDE.md yourself.
# With a path argument: sets up the given path as the host project instead of cwd.
#
# Examples:
#   cd ~/test-multi-team && ~/.../bin/install.sh
#   ~/.../bin/install.sh ~/some-other-project
#   ~/.../bin/install.sh --clean              # force-refresh everything
#   ~/.../bin/install.sh --topology=hex-backend ~/foo
#   ~/.../bin/install.sh --clean --topology=multi-team ~/foo

set -e

# --- Argument parsing ---

CLEAN=0
TOPOLOGY=""
HOST_PROJECT_INPUT=""

for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    --topology=*) TOPOLOGY="${arg#--topology=}" ;;
    --help|-h)
      head -n 24 "$0" | sed -n '2,24p' | sed 's/^# \{0,1\}//'
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
  ""|multi-team|solo-pair|hex-backend|discovery|book) ;;
  *)
    echo "✗ Unknown --topology: ${TOPOLOGY}. Use multi-team, solo-pair, hex-backend, discovery, or book."
    exit 1
    ;;
esac

HOST_PROJECT_INPUT="${HOST_PROJECT_INPUT:-$(pwd)}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST_PROJECT="$(cd "${HOST_PROJECT_INPUT}" 2>/dev/null && pwd)" || {
  echo "✗ Host project path does not exist: ${HOST_PROJECT_INPUT}"
  exit 1
}

MARKETPLACE_NAME="alegomes"
EXPERTISE_SOURCE="${REPO_DIR}/common/expertise"
EXPERTISE_TARGET="${HOST_PROJECT}/.claude/expertise"
CACHE_DIR="${HOME}/.claude/plugins/cache/${MARKETPLACE_NAME}"

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

# --- Optional: --clean teardown ---

if [ "${CLEAN}" -eq 1 ]; then
  echo "▶ --clean: uninstalling existing plugins (errors ignored)"
  claude plugin uninstall "common@${MARKETPLACE_NAME}" 2>/dev/null || true
  claude plugin uninstall "multi-team@${MARKETPLACE_NAME}" 2>/dev/null || true
  claude plugin uninstall "solo-pair@${MARKETPLACE_NAME}" 2>/dev/null || true
  claude plugin uninstall "hex-backend@${MARKETPLACE_NAME}" 2>/dev/null || true
  claude plugin uninstall "discovery@${MARKETPLACE_NAME}" 2>/dev/null || true
  claude plugin uninstall "jira-flow@${MARKETPLACE_NAME}" 2>/dev/null || true
  claude plugin uninstall "book@${MARKETPLACE_NAME}" 2>/dev/null || true

  if [ -d "${CACHE_DIR}" ]; then
    echo "▶ --clean: removing plugin cache at ${CACHE_DIR}"
    rm -rf "${CACHE_DIR}"
  fi
fi

# --- Marketplace re-registration (always: cheap, refreshes metadata) ---

echo "▶ Refreshing marketplace registration: ${MARKETPLACE_NAME}"
claude plugin marketplace remove "${MARKETPLACE_NAME}" 2>/dev/null || true
claude plugin marketplace add "${REPO_DIR}"

# --- Plugin install ---

echo "▶ Installing common@alegomes (8 mindset skills — required)"
claude plugin install common@alegomes

echo "▶ Installing multi-team@alegomes (9-agent generic topology)"
claude plugin install multi-team@alegomes

echo "▶ Installing solo-pair@alegomes (2-agent dev/reviewer topology)"
claude plugin install solo-pair@alegomes

echo "▶ Installing hex-backend@alegomes (13-agent hexagonal-architecture topology)"
claude plugin install hex-backend@alegomes

echo "▶ Installing discovery@alegomes (6-agent continuous product-discovery topology)"
claude plugin install discovery@alegomes

echo "▶ Installing jira-flow@alegomes (Jira lifecycle layer)"
claude plugin install jira-flow@alegomes

echo "▶ Installing book@alegomes (10-agent book-writing topology)"
claude plugin install book@alegomes

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

# --- Per-project setup: topology snippet + CLAUDE.md @-import ---

if [ -n "${TOPOLOGY}" ] && [ "${HOST_PROJECT}" != "${REPO_DIR}" ]; then
  SNIPPET_SRC="${REPO_DIR}/${TOPOLOGY}/${TOPOLOGY}-topology.md"
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

  # Sanity warning: jira-flow needs leads, solo-pair has none.
  if [ "${TOPOLOGY}" = "solo-pair" ]; then
    echo "  ⚠ solo-pair has no leads. /jira-flow:* commands won't work with this topology."
  fi

  # Seed lifecycle yaml with default_topology so jira-flow commands qualify agent names.
  LIFECYCLE_DST="${HOST_PROJECT}/.claude/jira-flow.lifecycle.yaml"
  if [ "${TOPOLOGY}" = "discovery" ]; then
    LIFECYCLE_SRC="${REPO_DIR}/discovery/jira-flow.lifecycle.example.yaml"
    if [ -f "${LIFECYCLE_DST}" ]; then
      echo "  ✔ ${LIFECYCLE_DST} already exists — leaving untouched"
    elif [ -f "${LIFECYCLE_SRC}" ]; then
      cp "${LIFECYCLE_SRC}" "${LIFECYCLE_DST}"
      echo "  ✔ Seeded ${LIFECYCLE_DST} from discovery template"
      echo "    Edit it: set project_key, issue_type, and status names to match your board."
    fi
  elif [ "${TOPOLOGY}" = "hex-backend" ] || [ "${TOPOLOGY}" = "multi-team" ] || [ "${TOPOLOGY}" = "book" ]; then
    if [ -f "${LIFECYCLE_DST}" ]; then
      echo "  ✔ ${LIFECYCLE_DST} already exists — leaving untouched"
    else
      cat > "${LIFECYCLE_DST}" <<EOF
# jira-flow config for ${TOPOLOGY} topology.
# Tells /jira-flow:execute and /jira-flow:plan-track-build-validate which
# topology's leads to delegate to (e.g. ${TOPOLOGY}:engineering-lead).
schema_version: 1
default_topology: ${TOPOLOGY}
EOF
      echo "  ✔ Seeded ${LIFECYCLE_DST} (default_topology: ${TOPOLOGY})"
    fi
  fi
fi

# --- Final summary ---

echo ""
echo "✔ Done."
echo ""
echo "Seven plugins installed:"
echo "    common       — 8 mindset skills (required by every topology)"
echo "    multi-team   — 9-agent generic topology + /multi-team:plan-build-validate"
echo "    solo-pair    — 2-agent dev/reviewer topology"
echo "    hex-backend  — 13-agent hexagonal-architecture topology + per-Task quality loop"
echo "    discovery    — 6-agent continuous product-discovery topology"
echo "    jira-flow    — atlassian-expert + Jira-aware commands (pair with any topology)"
echo "    book         — 10-agent book-writing topology + /book:inception + /book:write-chapter"
echo ""
if [ "${HOST_PROJECT}" != "${REPO_DIR}" ]; then
  echo "Host project setup at ${HOST_PROJECT}:"
  echo "    .claude/expertise/ → centralized plugin expertise (writes shared across projects)"
  if [ -n "${TOPOLOGY}" ]; then
    echo "    .claude/${TOPOLOGY}-topology.md + CLAUDE.md @-import → orchestrator wired"
    echo ""
    echo "You're ready. Open Claude Code in ${HOST_PROJECT} and try:"
    case "${TOPOLOGY}" in
      multi-team)  echo "    /multi-team:plan-build-validate <task>" ;;
      solo-pair)   echo "    /solo-pair:* (or just describe a small task — 2-agent dev/reviewer)" ;;
      hex-backend) echo "    /hex-backend:plan-build-validate <task>" ;;
      discovery)   echo "    /discovery:capture <signal>   (then /jira-flow:advance <KEY> to move forward)" ;;
      book)        echo "    /book:inception \"<book title>\"   (then /book:write-chapter <slug>)" ;;
    esac
  else
    echo ""
    echo "Final manual step: pick ONE topology snippet and import it from CLAUDE.md."
    echo "(Or re-run with --topology=multi-team|solo-pair|hex-backend to automate.)"
    echo ""
    echo "  cp ${REPO_DIR}/hex-backend/hex-backend-topology.md ${HOST_PROJECT}/.claude/"
    echo "  # OR"
    echo "  cp ${REPO_DIR}/multi-team/multi-team-topology.md ${HOST_PROJECT}/.claude/"
    echo "  # OR"
    echo "  cp ${REPO_DIR}/solo-pair/solo-pair-topology.md ${HOST_PROJECT}/.claude/"
    echo ""
    echo "  Then add the matching @-import to ${HOST_PROJECT}/CLAUDE.md:"
    echo "    @.claude/hex-backend-topology.md   (or multi-team-topology.md / solo-pair-topology.md)"
  fi
fi
