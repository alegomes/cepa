#!/bin/sh
# Install the alegomes multi-team plugin marketplace and its three plugins into Claude Code.
#
# Default usage (registers this repo as the marketplace):
#   ./bin/install.sh
#
# Override with an explicit local repo path:
#   ./bin/install.sh /path/to/claude-multi-team-plugin

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MARKETPLACE="${1:-${REPO_DIR}}"

if ! command -v claude > /dev/null 2>&1; then
  echo "✗ The 'claude' CLI is not installed. Install Claude Code first:"
  echo "  https://docs.anthropic.com/en/docs/claude-code"
  exit 1
fi

echo "▶ Registering marketplace from: ${MARKETPLACE}"
claude plugin marketplace add "${MARKETPLACE}" || {
  echo "  (marketplace may already be registered — continuing)"
}

echo "▶ Installing common@alegomes (5 mindset skills — required)"
claude plugin install common@alegomes

echo "▶ Installing multi-team@alegomes (9-agent topology)"
claude plugin install multi-team@alegomes

echo "▶ Installing solo-pair@alegomes (2-agent topology)"
claude plugin install solo-pair@alegomes

echo ""
echo "✔ Done. Three plugins installed:"
echo "    common       — 5 mindset skills"
echo "    multi-team   — 9-agent topology + path-lock hook + /plan-build-validate"
echo "    solo-pair    — 2-agent dev/reviewer topology"
echo ""
echo "Next: in any host project where you want orchestrator behavior, copy a"
echo "topology snippet to .claude/ and import it from CLAUDE.md. See the"
echo "'Per host project' section of README.md for details."
