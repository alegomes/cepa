#!/bin/sh
# Install the alegomes multi-team plugins into Claude Code AND set up the
# host project for centralized expertise (via symlink).
#
# Usage:
#   ./bin/install.sh                  # install plugins; set up cwd as host project
#   ./bin/install.sh /path/to/project # install plugins; set up given path as host project
#
# Idempotent: safe to re-run after editing the plugin or moving to a new project.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST_PROJECT_INPUT="${1:-$(pwd)}"
HOST_PROJECT="$(cd "${HOST_PROJECT_INPUT}" 2>/dev/null && pwd)" || {
  echo "✗ Host project path does not exist: ${HOST_PROJECT_INPUT}"
  exit 1
}

EXPERTISE_SOURCE="${REPO_DIR}/common/expertise"
EXPERTISE_TARGET="${HOST_PROJECT}/.claude/expertise"

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

# --- Plugin install ---

echo "▶ Registering marketplace from: ${REPO_DIR}"
claude plugin marketplace add "${REPO_DIR}" || {
  echo "  (marketplace may already be registered — continuing)"
}

echo "▶ Installing common@alegomes (5 mindset skills — required)"
claude plugin install common@alegomes

echo "▶ Installing multi-team@alegomes (9-agent topology)"
claude plugin install multi-team@alegomes

echo "▶ Installing solo-pair@alegomes (2-agent topology)"
claude plugin install solo-pair@alegomes

# --- Per-project setup: symlink for centralized expertise ---

echo ""
echo "▶ Setting up host project: ${HOST_PROJECT}"

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

# --- Final summary ---

echo ""
echo "✔ Done."
echo ""
echo "Three plugins installed:"
echo "    common       — 5 mindset skills"
echo "    multi-team   — 9-agent topology + path-lock hook + /plan-build-validate"
echo "    solo-pair    — 2-agent dev/reviewer topology"
echo ""
echo "Host project setup at ${HOST_PROJECT}:"
echo "    .claude/expertise/ → centralized plugin expertise (writes shared across projects)"
echo ""
echo "Final manual step (still needed): copy the topology snippet you want and"
echo "import it from the project's CLAUDE.md."
echo ""
echo "  cp ${REPO_DIR}/multi-team/multi-team-topology.md ${HOST_PROJECT}/.claude/"
echo "  # OR"
echo "  cp ${REPO_DIR}/solo-pair/solo-pair-topology.md ${HOST_PROJECT}/.claude/"
echo ""
echo "  Then add to ${HOST_PROJECT}/CLAUDE.md:"
echo "    @.claude/multi-team-topology.md   (or solo-pair-topology.md)"
