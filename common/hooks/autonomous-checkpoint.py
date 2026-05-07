#!/usr/bin/env python3
"""PostToolUse hook: append a state-file entry after every subagent call.

Activates only when CLAUDE_AUTONOMOUS_RUN_ID is set in the environment.
Outside autonomous mode, this hook is a no-op.

When active:
  1. Read the JSON payload from stdin (PostToolUse format).
  2. If the tool is `Task` (subagent invocation), parse out who was called
     and what came back.
  3. Append a YAML entry to docs/autonomous/<run-id>/state.yaml's `log` list.

Hook never blocks (always exit 0). Failures are logged to stderr but don't
break the workflow — the orchestrator must always be able to keep working
even if checkpointing fails.

Run-id resolution:
  - $CLAUDE_AUTONOMOUS_RUN_ID (env, set by /common:autonomous-start)
  - else: no-op exit 0.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


MAX_TEXT_LEN = 200  # Truncate prompt + result text to keep state.yaml readable.


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def truncate(text: str, n: int = MAX_TEXT_LEN) -> str:
    """One-line, length-capped representation of free-form text."""
    if not isinstance(text, str):
        text = str(text)
    text = text.replace("\n", " ").replace("\r", " ").strip()
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


def yaml_escape(s: str) -> str:
    """Minimal YAML string escaping: wrap in double quotes, escape \\ and \"."""
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def append_log_entry(state_path: Path, entry: dict) -> None:
    """Append a YAML list item to the `log:` list at the end of state.yaml.

    We don't fully parse the YAML — that would require PyYAML, which we don't
    want to depend on. Instead we trust that the file ends with a `log:` list
    (created by /common:autonomous-start) and append a new item to it.
    """
    if not state_path.exists():
        # Don't create the file from scratch; that's autonomous-start's job.
        # But emit a warning so it surfaces in --debug.
        print(
            f"[autonomous-checkpoint] state file not found: {state_path}; "
            f"skipping. (Was the run started via /common:autonomous-start?)",
            file=sys.stderr,
        )
        return

    lines = []
    lines.append(f"  - timestamp: {entry['timestamp']}")
    lines.append(f"    subagent: {yaml_escape(entry['subagent'])}")
    lines.append(f"    prompt_summary: {yaml_escape(entry['prompt_summary'])}")
    lines.append(f"    result_summary: {yaml_escape(entry['result_summary'])}")
    lines.append(f"    exit_status: {yaml_escape(entry['exit_status'])}")

    block = "\n".join(lines) + "\n"

    # Append. If the file doesn't end with a newline, add one.
    with state_path.open("r+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            f.seek(f.tell() - 1)
            last = f.read(1)
            if last != "\n":
                f.write("\n")
        f.write(block)


def extract_subagent_call(payload: dict) -> dict | None:
    """If this PostToolUse fires for a Task (subagent) call, build an entry.

    Otherwise return None — we only checkpoint subagent invocations, not every
    Read/Bash/Edit. (For PreToolUse-style coverage of all tools, this hook
    would need to be wired differently.)
    """
    tool_name = payload.get("tool_name", "")
    if tool_name != "Task":
        return None

    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}

    subagent_type = tool_input.get("subagent_type") or tool_input.get("agent_type") or "unknown"
    description = tool_input.get("description") or ""
    prompt = tool_input.get("prompt") or ""
    prompt_summary = description if description else prompt

    # tool_response shape varies; try a few likely fields.
    result_text = ""
    if isinstance(tool_response, dict):
        result_text = (
            tool_response.get("content")
            or tool_response.get("result")
            or tool_response.get("output")
            or ""
        )
        if isinstance(result_text, list):
            # CC sometimes returns content as a list of {type, text} blocks.
            parts = []
            for item in result_text:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(str(item))
            result_text = " ".join(parts)
    elif isinstance(tool_response, str):
        result_text = tool_response

    exit_status = "ok"
    if isinstance(tool_response, dict) and tool_response.get("is_error"):
        exit_status = "error"

    return {
        "timestamp": now_iso(),
        "subagent": truncate(str(subagent_type), 80),
        "prompt_summary": truncate(prompt_summary),
        "result_summary": truncate(result_text),
        "exit_status": exit_status,
    }


def main():
    run_id = os.environ.get("CLAUDE_AUTONOMOUS_RUN_ID")
    if not run_id:
        # Not in autonomous mode — fast no-op.
        sys.exit(0)

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(
            "[autonomous-checkpoint] could not parse hook payload; skipping",
            file=sys.stderr,
        )
        sys.exit(0)

    entry = extract_subagent_call(payload)
    if entry is None:
        sys.exit(0)

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    state_path = cwd / "docs" / "autonomous" / run_id / "state.yaml"

    try:
        append_log_entry(state_path, entry)
    except OSError as e:
        print(
            f"[autonomous-checkpoint] could not append to {state_path}: {e}; continuing",
            file=sys.stderr,
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
