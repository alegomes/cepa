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

It also enforces the debt-with-an-exit rule: declaring "New debt introduced:
<something>" and stopping there is how debt outlives the card that created it
with nobody holding the string. When the declared debt is anything other than
none/unknown, the gate additionally requires a **Revisit trigger** — the
condition that brings the debt back into view ("when the PlugSign contract
adds retries", "next time this endpoint changes"). `Closure condition:` is
accepted as an optional companion. The board is the ledger: debt that
survives the card becomes a Jira card labeled `debt`, not a new file format.

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
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _jiramut as J  # noqa: E402

# Structural markers that can introduce a heading or a labeled field.
# Jira comments are written in WIKI markup (`h3. Label`), not markdown, so a
# markdown-only gate is blind to the format its own callers naturally use:
# before 2026-07-21 a wiki-formatted summary with ZERO fields passed silently,
# and a wiki-formatted summary WITH all four was blocked as if it had none.
# Both directions were wrong; both are covered by tests now.
MARKER = r"(?:\*\*|__|#{1,6}\s*|h[1-6]\.\s*|[-*+]\s+)"

SUMMARY_HEADING_RE = re.compile(
    rf"^{MARKER}?\s*Implementation summary", re.MULTILINE | re.IGNORECASE
)

# Field label → accepted spellings. English is canonical; pt-BR is accepted
# because the harness mandates pt-BR prose. Word order is deliberately loose
# ("dívida nova" vs "nova dívida") — the gate's job is to prove the QUESTION
# was answered, not to police phrasing.
FIELD_LABELS = {
    "New debt introduced": (
        r"New debt introduced",
        r"(?:Nova\s+d[íi]vida|D[íi]vida\s+nova)\s+introduzida",
        r"D[íi]vida\s+introduzida",
    ),
    "Scope captured outside the card": (
        r"Scope captured outside the card",
        r"Escopo capturado fora do card",
    ),
    "Release needed": (
        r"Release needed",
        r"Release\s+necess[áa]ri[ao]",
    ),
    "Human validation route": (
        r"Human validation route",
        r"Rota de valida[çc][ãa]o humana",
    ),
}

# Matched WITH a structural marker — the field is properly labeled.
REQUIRED_FIELDS = {
    label: re.compile(rf"{MARKER}\s*(?:{'|'.join(spellings)})", re.IGNORECASE)
    for label, spellings in FIELD_LABELS.items()
}

# Matched WITHOUT any marker — used only to tell "you never answered this"
# apart from "you answered it in a shape I don't recognize". Reporting the
# second as the first is how a formatting slip gets mistaken for an omission,
# which teaches agents that this gate is formatting noise.
BARE_FIELDS = {
    label: re.compile(rf"(?:{'|'.join(spellings)})", re.IGNORECASE)
    for label, spellings in FIELD_LABELS.items()
}

# ── conditional field: debt declared → revisit trigger required ─────────────
# The debt value, inline (`**New debt introduced:** foo`) or block-style
# (`h3. Nova dívida introduzida` with the value on the next line).
DEBT_SPELLINGS = "|".join(FIELD_LABELS["New debt introduced"])
DEBT_INLINE_RE = re.compile(
    rf"{MARKER}\s*(?:{DEBT_SPELLINGS})\s*:?\s*\**[^\S\n]*(?P<value>\S[^\n]*)",
    re.IGNORECASE,
)
DEBT_BLOCK_RE = re.compile(
    rf"^{MARKER}\s*(?:{DEBT_SPELLINGS})\s*:?\s*\**\s*$\n+(?!{MARKER})(?P<value>\S[^\n]*)",
    re.MULTILINE | re.IGNORECASE,
)

# Values that mean "there is no debt to hold a string on". `unknown` is here
# deliberately: /board-flow:triage routes pre-existing implementations with
# "unknown (assess at proof)", and demanding a revisit trigger for debt nobody
# has assessed yet would only teach agents to invent one.
NO_DEBT_VALUES = (
    r"none", r"no\b", r"n/?a", r"not applicable", r"nothing", r"zero",
    r"nenhum[ao]?", r"n[ãa]o\s+aplic[áa]vel", r"sem\s+d[íi]vida", r"nada",
    r"unknown", r"desconhecid[ao]", r"a\s+avaliar", r"to\s+assess",
)
NO_DEBT_RE = re.compile(rf"^\W*(?:{'|'.join(NO_DEBT_VALUES)})\b", re.IGNORECASE)

REVISIT_LABELS = (
    r"Revisit trigger",
    r"Gatilho de revisita",
    r"Gatilho de revis[ãa]o",
)
REVISIT_RE = re.compile(
    rf"{MARKER}\s*(?:{'|'.join(REVISIT_LABELS)})", re.IGNORECASE
)
REVISIT_BARE_RE = re.compile(rf"(?:{'|'.join(REVISIT_LABELS)})", re.IGNORECASE)


def debt_value(body: str) -> str | None:
    for rx in (DEBT_INLINE_RE, DEBT_BLOCK_RE):
        m = rx.search(body)
        if m:
            return m.group("value").strip()
    return None


def declares_real_debt(body: str) -> bool:
    """True when the summary names debt that outlives the card."""
    value = debt_value(body)
    if value is None:
        return False
    return not NO_DEBT_RE.match(value)


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
    # Reconhecimento por EFEITO, nao por nome de ferramenta (ver _jiramut).
    _mut = J.classify(payload)
    if _mut is None:
        sys.exit(0)
    # A opacidade se checa ANTES de filtrar por tipo: uma mutacao que nao da
    # para ler pode ser justamente a que este gate guarda. Filtrar primeiro
    # deixava `twg api ... -X POST` escapar por nao ser classificavel.
    if _mut["opaque"]:
        J.block(_mut, "summary-nulls-gate")
    if _mut["kind"] != "comment":
        sys.exit(0)

    body = extract_body(_mut["tool_input"])
    if body is None:
        # Can't see the comment body -> can't gate. Never spuriously block.
        sys.exit(0)

    if not SUMMARY_HEADING_RE.search(body):
        # Not an Implementation Summary (triage note, NOT-A-BUG, block reason,
        # proof verdict...) — none of those carry these fields.
        sys.exit(0)

    missing = [label for label, rx in REQUIRED_FIELDS.items() if not rx.search(body)]

    # Conditional field: debt that outlives the card must carry the condition
    # that brings it back. Only checked once the debt field itself is present —
    # otherwise the agent gets two errors for one omission.
    bare_lookup = dict(BARE_FIELDS)
    debt_declared = "New debt introduced" not in missing and declares_real_debt(body)
    if debt_declared and not REVISIT_RE.search(body):
        missing.append("Revisit trigger")
        bare_lookup["Revisit trigger"] = REVISIT_BARE_RE

    if not missing:
        sys.exit(0)

    # Split the diagnosis: absent vs. present-but-unlabeled. Same block either
    # way, but the agent needs to know whether to ANSWER the question or just
    # re-format the answer it already wrote.
    absent = [m for m in missing if not bare_lookup[m].search(body)]
    unlabeled = [m for m in missing if m not in absent]

    missing_lines = "".join(f"\n    - **{m}:**" for m in absent)
    unlabeled_lines = "".join(f"\n    - **{m}:**" for m in unlabeled)

    detail = ""
    if absent:
        detail += (
            f"[summary-nulls-gate] BLOCKED: Implementation Summary is missing "
            f"explicit-null field(s):{missing_lines}\n"
        )
    if unlabeled:
        detail += (
            f"[summary-nulls-gate] BLOCKED: field(s) present but NOT in a recognized "
            f"format:{unlabeled_lines}\n"
            f"  The text is there — the label just isn't marked up. Prefix it with "
            f"`**bold**`, a heading (`###` or `h3.`), or a list bullet. Do NOT re-write "
            f"the answer; only the label's markup is wrong.\n"
        )

    debt_note = ""
    if debt_declared:
        debt_note = (
            f"  You declared debt ({debt_value(body)[:60]!r}) — debt without a\n"
            f"  revisit trigger is debt nobody is holding the string on:\n"
            f"    **Revisit trigger:** <the condition that brings this back into view>\n"
            f"    **Closure condition:** <optional — what would let us drop it>\n"
            f"  If the debt outlives this card, open a Jira card labeled `debt`; the\n"
            f"  board is the ledger. If there is really no debt, say so: `none`.\n"
        )

    print(
        f"{detail}"
        f"{debt_note}"
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
