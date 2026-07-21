#!/usr/bin/env python3
"""PreToolUse hook: block bouncing a card back without a structured reason.

Sibling of summary-nulls-gate.py, one seam later in the card's life. A card
returned from Review with only "not proven" (or, worse, moved to some
attention-shaped status with no comment at all) forces the next session to
re-derive WHY from the diff. The reason is cheap to write once and expensive
to reconstruct — so the gate makes writing it the only way through.

Mechanism (deliberately the same string-match technique as the nulls gate —
a new mechanism would be a new failure mode):
  - Matches the Atlassian MCP comment tools (any server prefix):
    addCommentToJiraIssue (cloud connector) / jira_add_comment (mcp-atlassian).
  - Only gates comments that ARE a bounce-back: a heading line carrying a
    recognized return marker (UNPROVEN, "returning for rework", "devolvendo",
    "bounce"...). Every other comment passes untouched.
  - Requires a labeled `Reason:` / `Motivo:` field WITH text. Unlike the nulls
    gate, emptiness IS judged here: a bare label carries none of the
    information the field exists to carry.

Anexed discipline, enforced in prose (prove.md / prove-drain.md /
atlassian-expert.md), not here: "Attention" is not a state. Name the real
condition — Blocked / Deferred / Dropped — plus the reason.

Exit codes:
  0 — allowed
  2 — blocked (stderr reaches the agent so it can self-correct)
"""

import json
import re
import sys

# Same structural markers as summary-nulls-gate: Jira comments arrive in wiki
# markup (`h3. Label`) as often as in markdown, and a markdown-only gate is
# blind to the format its own callers naturally use.
MARKER = r"(?:\*\*|__|#{1,6}\s*|h[1-6]\.\s*|[-*+]\s+)"

# A bounce is any comment whose HEADING announces a return. Matching on the
# heading (not anywhere in the body) is what keeps a PROVEN summary that
# merely mentions the word from being gated.
BOUNCE_MARKERS = (
    r"UNPROVEN",
    r"returning\s+for\s+rework",
    r"returning\s+to\b",
    r"sending\s+back",
    r"bounce(?:[-\s]?back)?",
    r"devolv\w*",              # devolvendo / devolvido / devolução
    r"retornando\s+para",
)
BOUNCE_HEADING_RE = re.compile(
    rf"^{MARKER}?[^\n]*?(?:{'|'.join(BOUNCE_MARKERS)})",
    re.MULTILINE | re.IGNORECASE,
)

REASON_LABELS = (r"Reason", r"Motivo", r"Raz[ãa]o")

# Labeled AND followed by text on the same line. The `[^\S\n]*` keeps the
# match on one line: a label whose value lives on the next line is handled
# separately, so we can tell "no value" from "value below the heading".
REASON_INLINE_RE = re.compile(
    rf"{MARKER}\s*(?:{'|'.join(REASON_LABELS)})\s*:?\s*\**[^\S\n]*(?P<value>\S[^\n]*)",
    re.IGNORECASE,
)
# Heading-style: `### Reason` / `h3. Motivo` with the text on following lines.
# The value line must NOT itself start a labeled field — otherwise an empty
# `**Reason:**` followed by `**Artifact:** ...` would read as answered, which
# is exactly the silent-omission shape this gate exists to catch.
REASON_BLOCK_RE = re.compile(
    rf"^{MARKER}\s*(?:{'|'.join(REASON_LABELS)})\s*:?\s*\**\s*$\n+"
    rf"(?!{MARKER})(?P<value>\S[^\n]*)",
    re.MULTILINE | re.IGNORECASE,
)
# No marker at all — used only to distinguish "never answered" from
# "answered in a shape I don't recognize", same as the nulls gate.
REASON_BARE_RE = re.compile(
    rf"(?:{'|'.join(REASON_LABELS)})\s*:\s*(?P<value>\S[^\n]*)", re.IGNORECASE
)

# A value has to carry information. Bold/emphasis leftovers and punctuation
# are stripped before measuring so `**Reason:** **` doesn't read as content.
MIN_REASON_CHARS = 3

BODY_FIELDS = ("commentBody", "comment", "body", "text", "commentText")


def extract_body(tool_input: dict) -> str | None:
    for f in BODY_FIELDS:
        v = tool_input.get(f)
        if isinstance(v, str) and v.strip():
            return v
    return None


def reason_value(body: str) -> str | None:
    """The labeled reason's text, or None when there is no labeled reason."""
    for rx in (REASON_INLINE_RE, REASON_BLOCK_RE):
        m = rx.search(body)
        if m:
            return m.group("value")
    return None


def is_substantive(value: str) -> bool:
    return len(re.sub(r"[\s*_`~.:\-–—]", "", value)) >= MIN_REASON_CHARS


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[bounce-reason-gate] could not parse hook payload; allowing",
              file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if "addCommentToJiraIssue" not in tool_name and "jira_add_comment" not in tool_name:
        sys.exit(0)

    body = extract_body(payload.get("tool_input") or {})
    if body is None:
        # Can't see the comment body -> can't gate. Never spuriously block.
        sys.exit(0)

    if not BOUNCE_HEADING_RE.search(body):
        sys.exit(0)

    value = reason_value(body)
    if value is not None and is_substantive(value):
        sys.exit(0)

    if value is None and REASON_BARE_RE.search(body):
        diagnosis = (
            "[bounce-reason-gate] BLOCKED: the reason is there but NOT in a "
            "recognized format.\n"
            "  Prefix the label with `**bold**`, a heading (`###` or `h3.`), or a\n"
            "  list bullet. Do NOT re-write the reason; only its markup is wrong.\n"
        )
    elif value is None:
        diagnosis = (
            "[bounce-reason-gate] BLOCKED: this comment sends a card back but "
            "carries no **Reason:** / **Motivo:** field.\n"
        )
    else:
        diagnosis = (
            "[bounce-reason-gate] BLOCKED: the **Reason:** label is present but "
            "empty.\n"
            "  A bare label carries none of the information the field exists for.\n"
        )

    print(
        f"{diagnosis}"
        f"  A bounce-back must say WHY, structurally, so the next session does not\n"
        f"  re-derive it from the diff:\n"
        f"    **Reason:** <what is wrong / missing, concretely — file:line or the\n"
        f"      external test that must exist to close it>\n"
        f"  And name the real condition instead of an attention-shaped status:\n"
        f"  Blocked (waiting on X) | Deferred (until Y) | Dropped (because Z).\n"
        f"  'Attention' is not a state. Add the reason and re-post — never delete\n"
        f"  the heading to dodge the gate.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
