#!/usr/bin/env python3
"""PostToolUse hook: mark .claude/last-build.json as STALE after source edits.

Fires after Edit / Write / MultiEdit on production code (source files,
build/dependency files, migrations). Records the path + timestamp + the
previous known-good status (if any). The /common:green-or-revert skill
reads this file and the PreToolUse gate-advance hook blocks "wrap-up"
operations until verify confirms green.

Never blocks. Failures are stderr-only.

What counts as source:
  - JVM/JS/Python/Go/Rust/etc. by extension (allowlist below).
  - Build/dependency manifests (pom.xml, build.gradle, package.json, ...).
  - Database migrations under db/, migrations/, **/V*__*.sql.

What does NOT count:
  - Docs (.md, .rst, .txt).
  - Spec files under specs/, spec/.
  - .claude/** plumbing.
  - Test sources (changes there don't invalidate "is the production code
    working" — they extend coverage. We could gate this differently if
    needed; for v1, conservative skip.)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


SOURCE_EXTENSIONS = {
    # JVM
    ".java", ".kt", ".kts", ".scala", ".groovy", ".clj",
    # JavaScript / TypeScript
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    # Python
    ".py", ".pyx",
    # Go / Rust
    ".go", ".rs",
    # Ruby / PHP / C# / Swift / ObjC
    ".rb", ".php", ".cs", ".swift", ".m", ".mm",
    # C / C++
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hxx",
    # Elixir
    ".ex", ".exs",
    # SQL (treated as source — migrations affect runtime behavior)
    ".sql",
}

BUILD_FILES = {
    "pom.xml",
    "build.gradle", "build.gradle.kts",
    "settings.gradle", "settings.gradle.kts",
    "package.json", "package-lock.json",
    "yarn.lock", "pnpm-lock.yaml",
    "Cargo.toml", "Cargo.lock",
    "go.mod", "go.sum",
    "requirements.txt", "Pipfile", "Pipfile.lock",
    "pyproject.toml", "poetry.lock",
    "Gemfile", "Gemfile.lock",
}

EXCLUDED_PATH_FRAGMENTS = (
    ".claude/",
    "docs/",
    "/spec/", "/specs/",
    "/src/test/", "/test/", "/tests/", "/__tests__/",
)


def is_source(file_path: str) -> bool:
    """Heuristic: does editing this file invalidate 'is the build green?'."""
    p = Path(file_path)
    posix = str(p).replace(os.sep, "/")

    for fragment in EXCLUDED_PATH_FRAGMENTS:
        if fragment in posix:
            return False

    if p.name in BUILD_FILES:
        return True

    if p.suffix.lower() in SOURCE_EXTENSIONS:
        return True

    return False


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[mark-build-stale] could not parse hook payload; skipping", file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if tool_name not in {"Edit", "Write", "MultiEdit"}:
        sys.exit(0)

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path or not is_source(file_path):
        sys.exit(0)

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()

    edited = Path(file_path)
    if edited.is_absolute():
        try:
            rel = str(edited.resolve().relative_to(cwd))
        except ValueError:
            # Edit landed OUTSIDE the session tree — e.g. a proof worktree
            # perturbation in /tmp. It does not invalidate THIS project's
            # build; marking the main baseline STALE for it poisons the
            # advance gate (and the bare relative_to() used to crash here).
            sys.exit(0)
    else:
        rel = file_path

    state_path = cwd / ".claude" / "last-build.json"

    previous = {}
    if state_path.exists():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}

    new_state = {
        "status": "STALE",
        "since": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "after_edit_to": rel,
        "last_known_status": previous.get("status", "UNKNOWN"),
        "last_known_at": previous.get("at"),
        "last_known_command": previous.get("command"),
    }

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"[mark-build-stale] could not write {state_path}: {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
