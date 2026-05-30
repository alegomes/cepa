#!/usr/bin/env python3
"""PostToolUse hook: capture build/test results to .claude/last-build.json.

Fires after Bash invocations of common build/test commands. Parses the
tool result for SUCCESS / FAILURE markers and writes the canonical state
file the /common:green-or-revert skill and gate-advance hook consult.

Out-of-band: orchestrator can claim "build is green" only by reading this
file; it cannot fabricate the entry. Hook owns the write.

Patterns detected:
  - Maven: ./mvnw or mvn  → BUILD SUCCESS / BUILD FAILURE
  - Gradle: ./gradlew or gradle  → BUILD SUCCESSFUL / BUILD FAILED
  - npm/yarn/pnpm test → exit code is the signal
  - pytest → exit code is the signal
  - cargo → exit code
  - go test → exit code
  - docker build → exit code (static-site / containerized verify)

If the command isn't one we know how to parse, we skip — better to leave
stale than mis-classify.

Never blocks. Failures are stderr-only.

Debugging: set CAPTURE_BUILD_DEBUG=1 to dump every invocation's
payload + classification details to /tmp/capture-build-debug.log
(or to $CAPTURE_BUILD_DEBUG_LOG if set). Same pattern as
HEX_PATHLOCK_DEBUG.
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
    (re.compile(r"(?:^|\s)docker\s+(?:buildx\s+)?build\b"),
     "docker-build", None, None),
]


# ─── shape extraction ─────────────────────────────────────────────────

def _flatten_content_blocks(value):
    """Common pattern: list of {type: text|tool_result, text|content: ...}."""
    parts = []
    for item in value:
        if isinstance(item, dict):
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif item.get("type") == "tool_result" and "content" in item:
                # Recursive: tool_result block may contain text or another list.
                nested = item["content"]
                if isinstance(nested, str):
                    parts.append(nested)
                elif isinstance(nested, list):
                    parts.append(_flatten_content_blocks(nested))
                else:
                    parts.append(str(nested))
            elif isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item.get("content"), str):
                parts.append(item["content"])
            else:
                parts.append(str(item))
        elif isinstance(item, str):
            parts.append(item)
        else:
            parts.append(str(item))
    return "\n".join(parts)


def extract_text(tool_response) -> str:
    """tool_response shape varies across CC versions and plugin wrappers;
    flatten defensively to a single string. Returns empty string if no
    text-like field is found.

    Shapes covered:
      - str (raw)
      - list (top-level content blocks)
      - dict.stdout / output / result / content / text / data / message (str OR list-of-blocks)
      - dict.output.stdout (nested envelope used by some wrappers)
      - dict.tool_use_result.content (Anthropic SDK envelope)
      - dict.stderr (last-resort fallback)
    """
    if isinstance(tool_response, str):
        return tool_response

    if isinstance(tool_response, list):
        return _flatten_content_blocks(tool_response)

    if not isinstance(tool_response, dict):
        return str(tool_response) if tool_response is not None else ""

    # Direct string-or-list keys at top level.
    for key in ("stdout", "output", "result", "content", "text", "data", "message"):
        value = tool_response.get(key)
        if isinstance(value, str):
            if value:
                return value
        elif isinstance(value, list):
            text = _flatten_content_blocks(value)
            if text:
                return text

    # Nested envelope: dict.output may itself be a dict with stdout inside.
    output = tool_response.get("output")
    if isinstance(output, dict):
        for nested_key in ("stdout", "content", "text", "result"):
            value = output.get(nested_key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list):
                text = _flatten_content_blocks(value)
                if text:
                    return text

    # Anthropic SDK envelope.
    tur = tool_response.get("tool_use_result")
    if isinstance(tur, dict):
        for nested_key in ("content", "text", "output", "result"):
            value = tur.get(nested_key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list):
                text = _flatten_content_blocks(value)
                if text:
                    return text

    # Last resort: stderr alone.
    stderr = tool_response.get("stderr", "")
    if isinstance(stderr, str) and stderr:
        return stderr

    return ""


def extract_exit_code(tool_response):
    """Find an integer exit code in tool_response, regardless of nesting."""
    if not isinstance(tool_response, dict):
        return None

    for key in ("exit_code", "exitCode", "returncode", "returnCode", "status_code"):
        if key in tool_response and isinstance(tool_response[key], int):
            return tool_response[key]

    # Nested envelope
    output = tool_response.get("output")
    if isinstance(output, dict):
        for key in ("exit_code", "exitCode", "returncode", "returnCode"):
            if key in output and isinstance(output[key], int):
                return output[key]

    if tool_response.get("is_error"):
        return 1

    return None


# ─── classification ───────────────────────────────────────────────────

def tail(text: str, lines: int = 12) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def classify(command: str, response_text: str, exit_code):
    """Return (status, kind, reason).

    status: "SUCCESS" | "FAILURE" | None
    kind:   pattern kind that matched (or None if no pattern matched)
    reason: one-line diagnostic string for debug log
    """
    for pattern, kind, success_marker, failure_marker in PATTERNS:
        if not pattern.search(command):
            continue

        # Markers when defined.
        if success_marker is not None and success_marker in response_text:
            return "SUCCESS", kind, f"matched success marker {success_marker!r}"
        if failure_marker is not None and failure_marker in response_text:
            return "FAILURE", kind, f"matched failure marker {failure_marker!r}"

        # Marker-less or marker-missing — fall back to exit code if available.
        if exit_code == 0:
            return "SUCCESS", kind, "fallback: exit_code 0"
        if isinstance(exit_code, int) and exit_code != 0:
            return "FAILURE", kind, f"fallback: exit_code {exit_code}"

        return None, kind, (
            f"matched pattern {kind!r} but could not classify: "
            f"no marker in response_text (len={len(response_text)}), "
            f"no exit_code (exit_code={exit_code!r}). "
            f"Likely a tool_response shape extract_text doesn't cover; "
            f"set CAPTURE_BUILD_DEBUG=1 and rerun."
        )

    return None, None, "no command pattern matched (not a build command)"


# ─── debug logging ────────────────────────────────────────────────────

def debug_log(payload, response_text, exit_code, status, kind, reason):
    """When CAPTURE_BUILD_DEBUG=1, append a JSON line to the debug log
    capturing what the hook saw + how it classified. Default log path
    is /tmp/capture-build-debug.log; override with
    CAPTURE_BUILD_DEBUG_LOG."""
    if os.environ.get("CAPTURE_BUILD_DEBUG") != "1":
        return

    log_path = os.environ.get("CAPTURE_BUILD_DEBUG_LOG", "/tmp/capture-build-debug.log")

    tool_response = payload.get("tool_response")
    response_top_keys = (
        sorted(tool_response.keys())
        if isinstance(tool_response, dict)
        else None
    )
    response_type = type(tool_response).__name__

    # Truncate the raw payload defensively so the log file doesn't explode.
    try:
        payload_preview = json.dumps(payload, default=str)[:4000]
    except (TypeError, ValueError):
        payload_preview = str(payload)[:4000]

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool_name": payload.get("tool_name"),
        "command_preview": (payload.get("tool_input") or {}).get("command", "")[:200],
        "tool_response_type": response_type,
        "tool_response_top_keys": response_top_keys,
        "extracted_text_len": len(response_text),
        "extracted_text_tail": tail(response_text, 4) if response_text else "",
        "exit_code": exit_code,
        "classified_status": status,
        "classified_kind": kind,
        "classification_reason": reason,
        "payload_preview": payload_preview,
    }

    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


# ─── main ─────────────────────────────────────────────────────────────

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
    exit_code = extract_exit_code(tool_response)

    status, kind, reason = classify(command, response_text, exit_code)

    debug_log(payload, response_text, exit_code, status, kind, reason)

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
