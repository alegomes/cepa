#!/usr/bin/env python3
"""PreToolUse hook: block posting an Implementation Summary that omits the
explicit-null fields.

The structural teeth of the "explicit nulls" discipline (imported from the
Ariad method's cadence rules): an Implementation Summary must STATE its
negatives — "new debt introduced: none", "release needed: no" — instead of
silently skipping the question. For an LLM agent, a silent omission is
undetectable; a missing mandatory field is a string-match away. Same
hook+gate pattern as acceptance-gate.py, one seam earlier: it fires on the
comment post, before the transition.

It also enforces the human-validation asymmetry: every summary carries a
**Human validation route** field — either a real route (command/URL +
expected observation + fail condition) for user-facing behavior, or the
explicit "not applicable (internal substrate)" for plumbing. Automated
tests never silently stand in for the human check on user-facing work, and
the human is never silently drafted to validate internals.

Mechanism:
  - Matches the Atlassian MCP comment tools (any server prefix):
    addCommentToJiraIssue (cloud connector) / jira_add_comment (mcp-atlassian).
  - Only gates comments that ARE an Implementation Summary (a heading line
    matching "Implementation summary", any #-level, case-insensitive).
    Every other comment passes untouched.
  - Requires all four labeled fields (English or pt-BR labels accepted).
    Values are NOT judged — presence is the honest limit of a string gate;
    the labels force the question to be answered somewhere a human reads.

Exit codes:
  0 — allowed
  2 — blocked (stderr reaches the agent so it can self-correct)
"""

import json
import re
import sys

SUMMARY_HEADING_RE = re.compile(
    r"^#{1,4}\s*Implementation summary", re.MULTILINE | re.IGNORECASE
)

# Field label → regex accepting the canonical English label or its pt-BR
# equivalent, as a bold markdown label. Values are free-form on purpose.
REQUIRED_FIELDS = {
    "New debt introduced": re.compile(
        r"\*\*(?:New debt introduced|D[íi]vida nova introduzida)", re.IGNORECASE
    ),
    "Scope captured outside the card": re.compile(
        r"\*\*(?:Scope captured outside the card|Escopo capturado fora do card)",
        re.IGNORECASE,
    ),
    "Release needed": re.compile(
        r"\*\*(?:Release needed|Release necess[áa]ria)", re.IGNORECASE
    ),
    "Human validation route": re.compile(
        r"\*\*(?:Human validation route|Rota de valida[çc][ãa]o humana)",
        re.IGNORECASE,
    ),
}

# Possible field names the MCP comment tools may use for the body.
BODY_FIELDS = ("commentBody", "comment", "body", "text", "commentText")


def extract_body(tool_input: dict) -> str | None:
    for f in BODY_FIELDS:
        v = tool_input.get(f)
        if isinstance(v, str) and v.strip():
            return v
    return None


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[summary-nulls-gate] could not parse hook payload; allowing", file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if "addCommentToJiraIssue" not in tool_name and "jira_add_comment" not in tool_name:
        sys.exit(0)

    body = extract_body(payload.get("tool_input") or {})
    if body is None:
        # Can't see the comment body -> can't gate. Never spuriously block.
        sys.exit(0)

    if not SUMMARY_HEADING_RE.search(body):
        # Not an Implementation Summary (triage note, NOT-A-BUG, block reason,
        # proof verdict...) — none of those carry these fields.
        sys.exit(0)

    missing = [label for label, rx in REQUIRED_FIELDS.items() if not rx.search(body)]
    if not missing:
        sys.exit(0)

    missing_lines = "".join(f"\n    - **{m}:**" for m in missing)
    print(
        f"[summary-nulls-gate] BLOCKED: Implementation Summary is missing explicit-null "
        f"field(s):{missing_lines}\n"
        f"  A summary must answer these questions even when the answer is negative:\n"
        f"    **New debt introduced:** none | <list from review>\n"
        f"    **Scope captured outside the card:** none | <follow-ups captured, not absorbed>\n"
        f"    **Release needed:** no | yes: <what>\n"
        f"    **Human validation route:** not applicable (internal substrate) |\n"
        f"      <command/URL + expected observation + fail condition>\n"
        f"  Silent omission is the failure mode this gate exists to prevent. Add the\n"
        f"  missing field(s) with an honest value and re-post — never delete the heading\n"
        f"  to dodge the gate.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
