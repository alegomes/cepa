#!/usr/bin/env python3
"""PreToolUse hook: block "wrap-up" operations when build is STALE or FAILED.

Hard gate. Reads .claude/last-build.json (maintained by mark-build-stale
and capture-build-result hooks). When the orchestrator tries to commit,
push, open a PR, or do anything else that signals "I'm done" — and the
build state is STALE or FAILURE — refuses with a clear message.

Exit codes:
  0 — allowed
  2 — blocked (stderr reaches the agent so it can self-correct)

What gets gated, in two tiers:

  LOCAL operations — fail-OPEN when no baseline exists (with a loud
  warning). Recoverable with `git reset` if the commit was a mistake.
    - git commit

  SHARING operations — fail-CLOSED when no baseline exists. Broadcasts
  unverified code to others; the friction of forcing a baseline is
  worth it.
    - git push
    - gh pr create / merge / approve, gh release
    - kubectl apply, terraform apply
    - docker push
    - aws/gcloud/az deploy or push

  Both tiers fail-CLOSED when state is STALE or FAILURE (existing
  build context says "broken"; no exceptions).

What does NOT get gated:
  - Read-only Bash (status, log, diff, ls, etc.)
  - Test/build invocations themselves (./mvnw, gradle, pytest, npm test).
    These are how you fix STALE/FAILURE — gating them would be a deadlock.
  - ANY project that declares it has no build, via a `.claude/no-build`
    marker file. Explicit, human-placed opt-out for docs-only / build-less
    repos where a build baseline can never exist.
  - A project with NO recognizable build manifest at its root (no pom.xml,
    mvnw, gradlew, package.json, pyproject.toml, Cargo.toml, go.mod,
    Makefile...): sharing ops are allowed with a loud warning instead of
    blocked. There is nothing to baseline in such a repo, so fail-closed
    only produces a dead end (seen in practice: `git push` blocked on a
    browser-extension repo that has no build at all). The warning still
    asks for the `.claude/no-build` marker to make the opt-out explicit.

UNKNOWN status (state file present but unrecognized) is treated as
FAILURE (something's off; don't proceed).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# Local operations: commit. Recoverable with git reset; missing baseline
# falls open with a loud warning (H1).
LOCAL_PATTERNS = [
    re.compile(r"(?:^|\s|&&\s|;\s)git\s+commit\b"),
]

# Sharing operations: push code to others / deploy. Missing baseline
# fails CLOSED (H2). Once your work crosses the boundary out of your
# machine, it's unrecoverable — the gate forces a baseline first.
SHARING_PATTERNS = [
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


# Root-level files that indicate the project HAS a build/test toolchain.
# Absence of all of them means there is nothing to baseline.
BUILD_MANIFESTS = [
    "pom.xml", "mvnw", "build.gradle", "build.gradle.kts", "gradlew",
    "package.json", "pyproject.toml", "setup.py", "Cargo.toml", "go.mod",
    "Makefile", "CMakeLists.txt", "mix.exs", "Gemfile",
]


def has_build_manifest(cwd: Path) -> bool:
    return any((cwd / m).exists() for m in BUILD_MANIFESTS)


def baseline_age_days(state: dict) -> float | None:
    """Best-effort age of the baseline in days, from its timestamp fields."""
    for key in ("at", "since"):
        raw = state.get(key)
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 86400
    return None


def classify(command: str) -> str:
    """Return one of: 'local', 'sharing', 'exempt-only', 'unrelated'."""
    matches_local = any(p.search(command) for p in LOCAL_PATTERNS)
    matches_sharing = any(p.search(command) for p in SHARING_PATTERNS)
    matches_exempt = any(p.search(command) for p in EXEMPT_PATTERNS)

    # When the command mixes exempt + gated portions, the gated portion
    # still matters. The strictest tier wins: sharing > local > exempt.
    if matches_sharing:
        return "sharing"
    if matches_local:
        return "local"
    if matches_exempt:
        return "exempt-only"
    return "unrelated"


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
    if not command:
        sys.exit(0)

    tier = classify(command)
    if tier in ("unrelated", "exempt-only"):
        sys.exit(0)

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()

    # Explicit opt-out. A project with no build to verify declares it by
    # creating `.claude/no-build`. The gate has nothing to baseline here,
    # so it does not apply — to EITHER tier. This is a deliberate,
    # human-placed marker, never auto-detection: the gate does not open
    # a door by guessing a repo is build-less. (Commit the marker if the
    # opt-out should hold for teammates / CI too.)
    if (cwd / ".claude" / "no-build").exists():
        print(
            "[gate-advance] .claude/no-build present — this project opts out of "
            "build-baseline gating (no build to verify); allowing.",
            file=sys.stderr,
        )
        sys.exit(0)

    state_path = cwd / ".claude" / "last-build.json"

    # ─── Missing baseline ─────────────────────────────────────────────
    if not state_path.exists():
        if tier == "local":
            # H1: fail-OPEN for local commits, but make the warning
            # impossible to ignore. The user can `git reset` if they
            # later realize this commit slipped a broken build through.
            warning = (
                "\n"
                "╔══════════════════════════════════════════════════════════════════════╗\n"
                "║              ⚠  COMMIT WITHOUT BUILD VERIFICATION  ⚠               ║\n"
                "╠══════════════════════════════════════════════════════════════════════╣\n"
                "║  No .claude/last-build.json found at this project.                  ║\n"
                "║  No build has been verified yet — this commit is UNVERIFIED.        ║\n"
                "║                                                                      ║\n"
                "║  RECOMMENDED: run your project's verify command FIRST to establish  ║\n"
                "║    a baseline (e.g., `./mvnw verify`, `npm test`, `pytest`).        ║\n"
                "║                                                                      ║\n"
                "║  ALLOWED because this is a LOCAL commit (recoverable via            ║\n"
                "║    `git reset`). Pushes / PRs / deploys will be BLOCKED until       ║\n"
                "║    a SUCCESS baseline is recorded.                                  ║\n"
                "╚══════════════════════════════════════════════════════════════════════╝\n"
            )
            print(warning, file=sys.stderr)
            sys.exit(0)
        elif not has_build_manifest(cwd):
            # Build-less repo (no recognizable build manifest at root):
            # there is nothing to baseline, so blocking is a dead end.
            # Allow with a loud warning and ask for the explicit marker.
            print(
                "[gate-advance] ⚠ ALLOWED WITH WARNING: sharing operation in a repo "
                "with no recognizable build manifest (no pom.xml/package.json/etc.) "
                "and no build baseline. Nothing to verify here.\n"
                "  If this repo genuinely has no build, make the opt-out explicit:\n"
                "    mkdir -p .claude && touch .claude/no-build   (commit it)\n"
                "  If it DOES have a build under a non-root path, run its verify "
                "command from that path first to record a baseline.",
                file=sys.stderr,
            )
            sys.exit(0)
        else:
            # H2: fail-CLOSED for sharing operations.
            print(
                f"[gate-advance] BLOCKED: sharing operation requires a build baseline.\n"
                f"  Command: {command[:200]}\n"
                f"  No .claude/last-build.json found — no build has been verified at\n"
                f"  this project yet. Sharing unverified code is the failure mode this\n"
                f"  gate exists to prevent.\n"
                f"  Suggestion: run your project's verify command (e.g. `./mvnw verify`,\n"
                f"  `npm test`, `pytest`) to establish a SUCCESS baseline, then retry.\n"
                f"  If your project uses a build tool not recognized by capture-build-\n"
                f"  result.py, extend its PATTERNS list rather than faking the state file.\n"
                f"  If this project genuinely has NO build (e.g. docs-only), opt out\n"
                f"  honestly: create `.claude/no-build` (commit it to apply for the team).",
                file=sys.stderr,
            )
            sys.exit(2)

    # ─── Baseline exists — read and gate on status ─────────────────────
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[gate-advance] could not read {state_path}: {e}; allowing", file=sys.stderr)
        sys.exit(0)

    status = state.get("status", "UNKNOWN")
    if status == "SUCCESS":
        sys.exit(0)

    age = baseline_age_days(state)
    age_note = ""
    if age is not None:
        age_note = f" ({age:.0f} day(s) ago)"
        if age > 7:
            age_note += (
                " — this baseline is OLD and may describe a state that no longer "
                "exists (e.g. recorded by another session/worktree); re-running "
                "the verify command is the fastest way to find out"
            )

    # STALE or FAILURE → block (regardless of tier).
    if status == "STALE":
        reason = f"build is STALE since edit to {state.get('after_edit_to', '<unknown path>')} at {state.get('since', '<unknown time>')}{age_note}"
        suggestion = "Run your project's verify command (e.g. `./mvnw <scope> verify`) before this operation. The hook will clear STALE on a green run."
    elif status == "FAILURE":
        reason = f"build is FAILURE since {state.get('at', '<unknown time>')}{age_note} (command: `{state.get('command', '<unknown>')}`)"
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
