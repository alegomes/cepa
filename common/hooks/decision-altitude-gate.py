#!/usr/bin/env python3
"""PreToolUse hook: blocks a Decision block whose Altitude field is not one of
the three values of the vocabulary.

The `**Altitude:**` of a `### Decision:` block does not describe the decision;
it says WHO reviews it: `strategic` goes to the owner in `/common:debrief`,
`tactical` stays with the lead, `implementation` only shows up with `--all`. It
is the only mechanism the debrief has to separate what deserves the owner's
attention from what is detail.

What happened on 2026-08-19: four autonomous runs produced 57 well-formatted
decision blocks, and 51 of them carried a free Portuguese word in the altitude
field ("contrato", "schema", "fronteira", "retenção", "semântica"), 35 distinct
values. The agent answered "what subject is this decision about", which is a
different question. With 89% of the blocks outside the vocabulary, the debrief
filter does not filter: the owner would review three decisions, all from the
first card, while the most consequential ones stayed invisible because they were
tagged with a word the filter does not recognize.

None of this shows up as an error. The block looks great, the run ends, the
debrief runs and says "3 strategic decisions". That is why the gate is
mechanical and blocks at write time, while the author is still there to fix it.

Mechanism:
  - Fires on Write/Edit/MultiEdit; only looks at content that has an Altitude
    field.
  - Only looks at an Altitude field INSIDE a `### Decision:` block, from the
    heading to the next heading of equal or higher level. Outside the block,
    `altitude:` is another vocabulary: in the acceptance artifact
    (.claude/acceptance/<KEY>.yaml) it says on which surface the criterion is
    observable (http/cli/ui/event/domain/application), and the gate blocked that
    write on 2026-08-22, forcing the completion-auditor to rename the field by
    force.
  - Accepted value: strategic | tactical | implementation (only these).
  - The template line in the documentation itself ("strategic | tactical |
    implementation", or a <placeholder>) passes; otherwise the gate would
    prevent editing the document that defines the vocabulary.
  - A missing field is NOT blocked: the debrief already treats absence as
    `tactical`, and blocking absence would turn editing a legacy block into a
    wall.

Exit codes:
  0 - allowed
  2 - blocked (stderr reaches the agent, which fixes it on its own)
"""

import json
import re
import sys
from pathlib import Path

GATED_TOOLS = ("Write", "Edit", "MultiEdit")

VOCABULARY = ("strategic", "tactical", "implementation")

MARKER = r"(?:\*\*|__|#{1,6}\s*|h[1-6]\.\s*|[-*+]\s+)"

# Altitude field and the rest of the line. pt-BR is accepted in the label
# because the harness mandates writing prose in pt-BR; the VALUE remains the
# English vocabulary, which is what the debrief matches.
# The colon is MANDATORY: without it the rule matched prose that TALKS about the
# field ("**Altitude field** classifies who reviews...") and blocked editing the
# document that defines the vocabulary. A gate that prevents fixing its own
# definition is how one learns to switch the gate off.
ALTITUDE_RE = re.compile(
    rf"^{MARKER}?\s*(?:Altitude|Altitude do bloco)\s*(?:\*\*|__)?\s*:\s*{MARKER}?\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)


# Markdown heading (`### Decision: ...`) and any heading, to know where the
# block ends. The level is the number of `#`: the block runs to the next heading
# of equal or lower level (`###` closes at `###`, `##` or `#`).
DECISION_RE = re.compile(r"^(#{1,6})\s*Decision\s*:", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s")


def decision_blocks(content: str):
    """The stretches that are decision blocks, one per `### Decision:` heading."""
    lines = content.splitlines()
    blocks, current, level = [], None, 0
    for line in lines:
        m = DECISION_RE.match(line)
        if m:
            if current is not None:
                blocks.append("\n".join(current))
            current, level = [line], len(m.group(1))
            continue
        if current is not None:
            h = HEADING_RE.match(line)
            if h and len(h.group(1)) <= level:
                blocks.append("\n".join(current))
                current = None
                continue
            current.append(line)
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def extract_content(tool_input: dict):
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


def clean(value: str) -> str:
    """Strips markup and edge punctuation, preserving the value's text."""
    v = value.strip()
    v = re.sub(r"^(\*\*|__|`)+|(\*\*|__|`)+$", "", v).strip()
    v = v.strip("*_`").strip()
    return v.rstrip(".;,").strip()


def is_template_line(value: str) -> bool:
    """The line that TEACHES the vocabulary, not a real decision.

    Two forms: the whole enumeration ("strategic | tactical | implementation")
    and the fill-in marker ("<strategic|tactical|implementation>").
    """
    v = clean(value).lower()
    # The fill-in marker may be followed by a comment on the same line
    # ("<strategic|tactical|implementation>   ← escolha uma"), and is still a
    # template line.
    if v.startswith("<"):
        return True
    v = v.strip("<>").strip()
    parts = [p.strip() for p in re.split(r"[|/]", v) if p.strip()]
    return len(parts) > 1 and all(p in VOCABULARY for p in parts)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[decision-altitude-gate] payload ilegível; liberando", file=sys.stderr)
        sys.exit(0)

    if not any(t in payload.get("tool_name", "") for t in GATED_TOOLS):
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    content = extract_content(tool_input)
    if content is None:
        sys.exit(0)          # without seeing the content, nothing is blocked

    targets = decision_blocks(content)
    if not targets:
        # An Edit may carry only the field line, without the heading. In that
        # case the destination file decides: if IT has a decision block, the
        # fragment is treated as part of one; if it does not (the acceptance
        # .yaml, for example), nothing here is a decision block and the gate
        # has no opinion.
        file_path = tool_input.get("file_path")
        if isinstance(file_path, str) and file_path:
            try:
                destination = Path(file_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                destination = ""
            if decision_blocks(destination):
                targets = [content]
    if not targets:
        sys.exit(0)

    outside = []
    for value in ALTITUDE_RE.findall("\n".join(targets)):
        if is_template_line(value):
            continue
        v = clean(value).lower()
        if v not in VOCABULARY:
            outside.append(clean(value))

    if not outside:
        sys.exit(0)

    listing = ", ".join(f'"{v}"' for v in dict.fromkeys(outside))
    print(
        "[decision-altitude-gate] BLOQUEADO: campo Altitude fora do vocabulário: "
        f"{listing}.\n"
        "  Altitude tem exatamente três valores — strategic, tactical, "
        "implementation — e diz QUEM revisa a decisão, não sobre o que ela é:\n"
        "   · strategic     — o dono revisa no debrief (escopo, contrato, "
        "nome público, semântica de spec, adiamento)\n"
        "   · tactical      — o lead revisa (decomposição, costura entre "
        "tarefas, estratégia de merge)\n"
        "   · implementation— fica registrado, o debrief só mostra com --all\n"
        "  O assunto da decisão vai no título (`### Decision: <assunto>`), "
        "nunca aqui.\n"
        "  Na dúvida entre strategic e tactical, use tactical.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
