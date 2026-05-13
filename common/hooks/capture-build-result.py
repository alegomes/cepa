#!/usr/bin/env python3
"""PostToolUse hook: capture build/test results to .claude/last-build.json.

Fires after Bash invocations of common build/test commands. Parses the
tool result for SUCCESS / FAILURE markers and writes the canonical state
file the /common:green-or-revert skill and gate-advance hook consult.

Out-of-band: orchestrator can claim "build is green" only by reading this
file; it cannot fabricate the entry. Hook owns the write.

Patterns detected (v1):
  - Maven: ./mvnw or mvn  → BUILD SUCCESS / BUILD FAILURE
  - Gradle: ./gradlew or gradle  → BUILD SUCCESSFUL / BUILD FAILED
  - npm/yarn/pnpm test → exit code is the signal
  - pytest → exit code is the signal

If the command isn't one we know how to parse, we skip — better to leave
stale than mis-classify.

Never blocks. Failures are stderr-only.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# (regex on command, kind, success-marker, failure-marker)
# When markers are None, we fall back to exit_code from tool_response.
PATTERNS = [
    (re.compile(r"(?:^|\s)(?:\./)?mvnw?\b.*\b(?:verify|test|package|install)\b"),
     "maven", "BUILD SUCCESS", "BUILD FAILURE"),
    (re.compile(r"(?:^|\s)(?:\./)?gradlew?\b.*\b(?:build|test|check|verify)\b"),
     "gradle", "BUILD SUCCESSFUL", "BUILD FAILED"),
    (re.compile(r"(?:^|\s)npm\b.*\b(?:test|run\s+test|run\s+build)\b"),
     "npm", None, None),
    (re.compile(r"(?:^|\s)(?:yarn|pnpm)\b.*\b(?:test|build)\b"),
     "yarn", None, None),
    (re.compile(r"(?:^|\s)pytest\b"),
     "pytest", None, None),
    (re.compile(r"(?:^|\s)cargo\b.*\b(?:test|build|check)\b"),
     "cargo", None, None),
    (re.compile(r"(?:^|\s)go\s+test\b"),
     "go-test", None, None),
]


def extract_text(tool_response) -> str:
    """tool_response shape varies; try to flatten to a single string."""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        # Common keys
        for key in ("stdout", "output", "result", "content"):
            value = tool_response.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                parts = []
                for item in value:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    else:
                        parts.append(str(item))
                return "\n".join(parts)
        # stderr too
        stderr = tool_response.get("stderr", "")
        if isinstance(stderr, str) and stderr:
            return stderr
    return ""


def tail(text: str, lines: int = 12) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def classify(command: str, response_text: str, exit_code) -> tuple[str | None, str | None]:
    """Return (status, kind) or (None, None) if we don't know how to read it."""
    for pattern, kind, success_marker, failure_marker in PATTERNS:
        if not pattern.search(command):
            continue
        if success_marker is not None and success_marker in response_text:
            return "SUCCESS", kind
        if failure_marker is not None and failure_marker in response_text:
            return "FAILURE", kind
        # Marker-less or marker-missing — fall back to exit code if available.
        if exit_code == 0:
            return "SUCCESS", kind
        if isinstance(exit_code, int) and exit_code != 0:
            return "FAILURE", kind
        return None, kind  # Couldn't tell.
    return None, None


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[capture-build-result] could not parse hook payload; skipping", file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    tool_response = payload.get("tool_response") or {}
    response_text = extract_text(tool_response)
    exit_code = None
    if isinstance(tool_response, dict):
        for key in ("exit_code", "exitCode", "returncode", "returnCode"):
            if key in tool_response and isinstance(tool_response[key], int):
                exit_code = tool_response[key]
                break
        if tool_response.get("is_error") and exit_code is None:
            exit_code = 1

    status, kind = classify(command, response_text, exit_code)
    if status is None:
        sys.exit(0)  # Not a build command we recognize, or result was ambiguous.

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    state_path = cwd / ".claude" / "last-build.json"

    new_state = {
        "status": status,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": command[:200],
        "kind": kind,
        "tail": tail(response_text),
    }

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"[capture-build-result] could not write {state_path}: {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
