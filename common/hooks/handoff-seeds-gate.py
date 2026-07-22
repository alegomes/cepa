#!/usr/bin/env python3
"""PreToolUse hook: block writing a discovery handoff that omits the
forward-carrying fields.

When exploration becomes delivery, two things are routinely lost at the seam:

  1. **Validation seeds** — how we would know this worked, thought up BEFORE
     implementation exists. Written after the fact, they degrade into a
     description of whatever got built; the seed only has value while nobody
     yet knows what the code will look like.
  2. **Carry-forward notes** — the implementation-relevant findings discovery
     stumbled on (a rate limit, a legacy field, a partner's quirk). Discovery
     knows them, engineering needs them, and nothing in the pipeline forces
     the transfer. They are re-discovered later, expensively.

Neither is a value judgment the hook can make. What it CAN do is make the
question impossible to skip silently: an absent label is a string-match away,
while an unanswered question in someone's head is invisible. Same technique
as summary-nulls-gate.py (from which the marker/label handling is borrowed),
one seam earlier in the lifecycle.

Explicit nulls are accepted on purpose. "Validation seeds: none — this is
internal substrate" is a real answer; silence is not.

Mechanism:
  - Fires on Write/Edit/MultiEdit whose target path looks like a discovery
    handoff: docs/discovery/<anything>/handoff.md.
  - Requires both labeled fields (English or pt-BR labels accepted).
  - Values are NOT judged beyond presence — the honest limit of a string gate.

Exit codes:
  0 — allowed
  2 — blocked (stderr reaches the agent so it can self-correct)
"""

import json
import re
import sys

# Structural markers that can introduce a labeled field. handoff.md is
# markdown, but the wiki forms are kept so a brief pasted from/to a Jira
# comment isn't blocked for its markup — the lesson of the 2026-07-21
# summary-nulls-gate false positive, where a formatting slip was reported as
# an omission and taught the agent to treat the gate as noise.
MARKER = r"(?:\*\*|__|#{1,6}\s*|h[1-6]\.\s*|[-*+]\s+)"

# Only these paths are gated. A handoff lives at docs/discovery/<key>/handoff.md;
# anything else (framing, research, a handoff in another topology) is none of
# this gate's business.
HANDOFF_PATH_RE = re.compile(
    r"(?:^|/)docs/discovery/[^/]+/handoff\.md$", re.IGNORECASE
)

# Field label → accepted spellings. English is canonical; pt-BR is accepted
# because the harness mandates pt-BR prose. Word order is deliberately loose —
# the gate proves the QUESTION was answered, not how it was phrased.
FIELD_LABELS = {
    "Validation seeds": (
        r"Validation seeds?",
        r"Sementes? de valida[çc][ãa]o",
    ),
    "Carry-forward notes": (
        r"Carry[- ]forward notes?",
        r"Notas? de carry[- ]forward",
        r"Achados? a carregar",
        r"Notas? a carregar",
    ),
}

REQUIRED_FIELDS = {
    label: re.compile(rf"{MARKER}\s*(?:{'|'.join(spellings)})", re.IGNORECASE)
    for label, spellings in FIELD_LABELS.items()
}

# Matched WITHOUT a marker — separates "never answered" from "answered in a
# shape I don't recognize". Reporting the second as the first is how a
# formatting slip gets mistaken for an omission.
BARE_FIELDS = {
    label: re.compile(rf"(?:{'|'.join(spellings)})", re.IGNORECASE)
    for label, spellings in FIELD_LABELS.items()
}

GATED_TOOLS = ("Write", "Edit", "MultiEdit")


def extract_path(tool_input: dict) -> str:
    for f in ("file_path", "filePath", "path", "notebook_path"):
        v = tool_input.get(f)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def extract_content(tool_input: dict) -> str | None:
    """The prospective file content, across the tool shapes that carry it.

    Edit/MultiEdit only carry a fragment, so their content is a partial view;
    the gate treats an absent view as "can't see, don't block" rather than
    guessing. Write is the tool the epic-briefer actually uses.
    """
    v = tool_input.get("content")
    if isinstance(v, str):
        return v
    v = tool_input.get("new_string")
    if isinstance(v, str):
        return v
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        parts = [e.get("new_string", "") for e in edits if isinstance(e, dict)]
        if parts:
            return "\n".join(p for p in parts if isinstance(p, str))
    return None


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[handoff-seeds-gate] could not parse hook payload; allowing",
              file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if not any(t in tool_name for t in GATED_TOOLS):
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    if not HANDOFF_PATH_RE.search(extract_path(tool_input).replace("\\", "/")):
        sys.exit(0)

    content = extract_content(tool_input)
    if content is None:
        # Can't see what's being written -> can't gate. Never spuriously block.
        sys.exit(0)

    missing = [label for label, rx in REQUIRED_FIELDS.items()
               if not rx.search(content)]
    if not missing:
        sys.exit(0)

    absent = [m for m in missing if not BARE_FIELDS[m].search(content)]
    unlabeled = [m for m in missing if m not in absent]

    detail = ""
    if absent:
        lines = "".join(f"\n    - **{m}:**" for m in absent)
        detail += (
            f"[handoff-seeds-gate] BLOCKED: the delivery brief is missing "
            f"required field(s):{lines}\n"
        )
    if unlabeled:
        lines = "".join(f"\n    - **{m}:**" for m in unlabeled)
        detail += (
            f"[handoff-seeds-gate] BLOCKED: field(s) present but NOT in a "
            f"recognized format:{lines}\n"
            f"  The text is there — the label just isn't marked up. Prefix it "
            f"with `**bold**`, a heading (`###`), or a list bullet. Do NOT "
            f"re-write the answer; only the label's markup is wrong.\n"
        )

    print(
        f"{detail}"
        f"  A handoff carries what only discovery can know:\n"
        f"    **Validation seeds:** none — <why> | <how we'd know this worked,\n"
        f"      thought up BEFORE implementation: signal, expected direction,\n"
        f"      what would falsify it>\n"
        f"    **Carry-forward notes:** none | <implementation-relevant findings\n"
        f"      discovery hit along the way — constraints, legacy quirks, data\n"
        f"      shapes engineering would otherwise re-discover the hard way>\n"
        f"  Seeds written AFTER the build describe what got built; that is why\n"
        f"  they belong here, at the seam, and not in a later review. An explicit\n"
        f"  `none` is a valid answer — silence is not. Add the field(s) and\n"
        f"  re-write; never drop the section to dodge the gate.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
