#!/usr/bin/env python3
"""PreToolUse hook: block "wrap-up" operations when build is STALE or FAILED.

Hard gate. Reads .claude/last-build.json (maintained by mark-build-stale
and capture-build-result hooks). When the orchestrator tries to commit,
push, open a PR, or do anything else that signals "I'm done" — and the
build state is STALE or FAILURE — refuses with a clear message.

Exit codes:
  0 — allowed
  2 — blocked (stderr reaches the agent so it can self-correct)

What gets gated:
  - Bash:  git commit, git push, gh pr create, gh pr merge, gh release
  - Bash:  deploy commands (heuristic: kubectl apply, terraform apply,
           docker push, aws/gcloud/az deploy)

What does NOT get gated:
  - Read-only Bash (status, log, diff, ls, etc.)
  - Test/build invocations themselves (./mvnw, gradle, pytest, npm test).
    These are how you fix STALE/FAILURE — gating them would be a deadlock.

UNKNOWN status (no state file yet) is allowed — we can't gate when we
have no prior data. The skill instructs the agent to establish a baseline.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# Commands that mean "I'm done, push it out" — gate these.
ADVANCE_PATTERNS = [
    re.compile(r"(?:^|\s|&&\s|;\s)git\s+commit\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)git\s+push\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)gh\s+pr\s+(?:create|merge|review\s+--approve)\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)gh\s+release\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)kubectl\s+apply\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)terraform\s+apply\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)docker\s+push\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)(?:aws|gcloud|az)\s+(?:.*\b)?(?:deploy|push)\b"),
]

# Test/build invocations should NEVER be gated — they're how you clear
# STALE/FAILURE. Allowlist explicitly.
EXEMPT_PATTERNS = [
    re.compile(r"(?:^|\s|&&\s|;\s)(?:\./)?mvnw?\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)(?:\./)?gradlew?\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)gradle\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)npm\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)(?:yarn|pnpm)\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)pytest\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)cargo\s+(?:test|build|check)\b"),
    re.compile(r"(?:^|\s|&&\s|;\s)go\s+test\b"),
    # Allow git operations that don't push state out
    re.compile(r"(?:^|\s|&&\s|;\s)git\s+(?:status|log|diff|show|stash|checkout|restore|reset|add|rm|mv|fetch|pull|merge|rebase|branch|tag|worktree|config|remote)\b"),
]


def is_gated(command: str) -> bool:
    """True if this Bash command needs gating against build state."""
    if any(p.search(command) for p in EXEMPT_PATTERNS):
        # If command mixes exempt + gated patterns, the gated portion still
        # matters. Check that there's no advance pattern in the same line.
        if not any(p.search(command) for p in ADVANCE_PATTERNS):
            return False
    return any(p.search(command) for p in ADVANCE_PATTERNS)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[gate-advance] could not parse hook payload; allowing", file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command or not is_gated(command):
        sys.exit(0)

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    state_path = cwd / ".claude" / "last-build.json"

    if not state_path.exists():
        # No baseline. Can't gate; let it through but emit a soft warning
        # to stderr so the user sees that no verification was on file.
        print(
            "[gate-advance] no .claude/last-build.json — no build verification "
            "recorded yet this session. Consider running ./mvnw verify (or "
            "equivalent) before this commit / push to establish a baseline.",
            file=sys.stderr,
        )
        sys.exit(0)

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[gate-advance] could not read {state_path}: {e}; allowing", file=sys.stderr)
        sys.exit(0)

    status = state.get("status", "UNKNOWN")
    if status == "SUCCESS":
        sys.exit(0)

    # STALE or FAILURE → block.
    if status == "STALE":
        reason = f"build is STALE since edit to {state.get('after_edit_to', '<unknown path>')} at {state.get('since', '<unknown time>')}"
        suggestion = "Run your project's verify command (e.g. `./mvnw <scope> verify`) before this operation. The hook will clear STALE on a green run."
    elif status == "FAILURE":
        reason = f"build is FAILURE since {state.get('at', '<unknown time>')} (command: `{state.get('command', '<unknown>')}`)"
        suggestion = "Fix the failing tests / build errors, re-run the verify command, and try again. Don't proceed with broken state."
    else:
        reason = f"build status is {status!r} — unrecognized"
        suggestion = "Run your project's verify command to establish a known-good baseline."

    print(
        f"[gate-advance] BLOCKED: cannot run advancement command — {reason}.\n"
        f"  Command: {command[:200]}\n"
        f"  Suggestion: {suggestion}\n"
        f"  State file: {state_path}\n"
        f"  Override by re-establishing green build, not by editing the state file.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
