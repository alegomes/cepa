#!/bin/sh
# Install the alegomes multi-team plugins into Claude Code AND set up the
# host project for centralized expertise (via symlink).
#
# Usage:
#   ./bin/install.sh [--clean] [/path/to/host-project]
#
# Without arguments: installs plugins (idempotent), sets up cwd as host project.
# With --clean: also uninstalls existing plugins and nukes the marketplace
#   plugin cache before reinstalling. Use this when you've edited plugin
#   source without bumping versions and want CC to pick up the changes.
# With a path argument: sets up the given path as the host project instead of cwd.
#
# Examples:
#   cd ~/test-multi-team && ~/.../bin/install.sh
#   ~/.../bin/install.sh ~/some-other-project
#   ~/.../bin/install.sh --clean              # force-refresh everything
#   ~/.../bin/install.sh --clean ~/foo        # force-refresh and target ~/foo

set -e

# --- Argument parsing ---

CLEAN=0
HOST_PROJECT_INPUT=""

for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    --help|-h)
      head -n 20 "$0" | sed -n '2,20p' | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    -*)
      echo "✗ Unknown flag: $arg"
      exit 1
      ;;
    *) HOST_PROJECT_INPUT="$arg" ;;
  esac
done

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
  claude plugin uninstall "jira-flow@${MARKETPLACE_NAME}" 2>/dev/null || true

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

echo "▶ Installing jira-flow@alegomes (Jira lifecycle layer)"
claude plugin install jira-flow@alegomes

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

# --- Final summary ---

echo ""
echo "✔ Done."
echo ""
echo "Five plugins installed:"
echo "    common       — 8 mindset skills (required by every topology)"
echo "    multi-team   — 9-agent generic topology + /multi-team:plan-build-validate"
echo "    solo-pair    — 2-agent dev/reviewer topology"
echo "    hex-backend  — 13-agent hexagonal-architecture topology + per-Task quality loop"
echo "    jira-flow    — atlassian-expert + Jira-aware commands (pair with multi-team or hex-backend)"
echo ""
if [ "${HOST_PROJECT}" != "${REPO_DIR}" ]; then
  echo "Host project setup at ${HOST_PROJECT}:"
  echo "    .claude/expertise/ → centralized plugin expertise (writes shared across projects)"
  echo ""
  echo "Final manual step (still needed): copy ONE topology snippet and import it"
  echo "from the project's CLAUDE.md."
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
