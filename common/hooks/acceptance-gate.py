#!/usr/bin/env python3
"""PreToolUse hook: block the In-Review Jira transition when the acceptance
audit is incomplete.

The structural teeth of the `acceptance-completeness` discipline — the same
hook+state+gate pattern as `gate-advance.py`, but the state is per-card
acceptance evidence instead of build greenness.

Mechanism (why this needs no knowledge of WHICH status is being targeted):

  The `completion-auditor` writes `.claude/acceptance/<KEY>.yaml` only AFTER
  implementation, right before the flow tries to move the card to In Review.
  So:
    - Earlier transitions (To Do -> In Progress) happen with NO artifact on
      disk -> this gate fails OPEN (nothing to enforce yet).
    - The In-Review transition happens with the artifact present -> this gate
      reads its `status` and BLOCKS unless it is `complete`.
  The artifact's temporal existence is the signal; we never have to decode the
  numeric transition id.

Matches the Atlassian MCP transition tool (any server prefix). Extracts the
issue key from the tool input, looks for `.claude/acceptance/<KEY>.yaml`:

  - absent                       -> allow (audit hasn't run; not gated)
  - present, status: complete    -> allow
  - present, status: <anything>  -> BLOCK (incomplete / malformed audit)
  - key not extractable          -> allow (can't gate meaningfully; never
                                    spuriously block a Jira transition)

Exit codes:
  0 — allowed
  2 — blocked (stderr reaches the agent so it can self-correct)
"""

import json
import os
import re
import sys
from pathlib import Path

STATUS_RE = re.compile(r"^status:\s*([A-Za-z_-]+)", re.MULTILINE)
GAP_RE = re.compile(r"^\s*gap:\s*(?!null\b)(?!~\s*$)[\"']?(.+?)[\"']?\s*$", re.MULTILINE)
# Possible field names the MCP tool may use for the issue key.
KEY_FIELDS = ("issueIdOrKey", "issueKey", "issueId", "issue", "key")


def extract_key(tool_input: dict) -> str | None:
    for f in KEY_FIELDS:
        v = tool_input.get(f)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[acceptance-gate] could not parse hook payload; allowing", file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if "transitionJiraIssue" not in tool_name:
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    key = extract_key(tool_input)
    if not key:
        # Can't identify the card -> can't gate. Never spuriously block.
        sys.exit(0)

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    artifact = cwd / ".claude" / "acceptance" / f"{key}.yaml"

    if not artifact.exists():
        # No audit on disk yet (e.g. the To Do -> In Progress transition).
        # Nothing to enforce. The completion-auditor writes this file right
        # before the In-Review transition; that's when teeth appear.
        sys.exit(0)

    try:
        text = artifact.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[acceptance-gate] could not read {artifact}: {e}; allowing", file=sys.stderr)
        sys.exit(0)

    m = STATUS_RE.search(text)
    status = (m.group(1).lower() if m else "unparseable")

    if status == "complete":
        sys.exit(0)

    # Present but not complete -> BLOCK. Surface the gaps so the agent can route
    # the fix instead of guessing.
    gaps = GAP_RE.findall(text)
    gap_lines = "".join(f"\n    - {g.strip()}" for g in gaps[:8]) or "\n    - (see the artifact for per-criterion gaps)"

    print(
        f"[acceptance-gate] BLOCKED: cannot move {key} to review — acceptance audit is "
        f"'{status}', not 'complete'.\n"
        f"  Artifact: {artifact}\n"
        f"  Open gaps (criterion not demonstrated at its stated altitude):{gap_lines}\n"
        f"  An acceptance criterion is only 'complete' when a test exercises its literal\n"
        f"  surface end-to-end and was run green — not when the parts are covered in\n"
        f"  isolation. Close the gap (add the missing altitude test), re-run the\n"
        f"  completion-auditor, and retry. Override by demonstrating the criterion, not\n"
        f"  by editing the artifact.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
