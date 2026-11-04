#!/usr/bin/env python3
"""PreToolUse hook: blocks a specification that declares itself ready to build
while some success criterion has no surface and no red test.

`/common:spec` runs an interrogation: the agent asks, the owner answers, and the
specification grows. The risk is not the interrogation being short -- it is it
ENDING out of tiredness. The agent decides it is good enough, writes `Status:
ready-to-build` (or the old `pronta-para-construir`), and what comes out is a
plausible specification whose criteria are statements of intent ("the system
must validate the registration") with no observable surface where anyone could
prove it happened. That does not fail in the specification: it fails three
weeks later, in construction, when the criterion is interpreted differently by
someone else.

That is why closing is mechanical, not editorial. `Status: draft` (or the old
`rascunho`) never blocks anything -- the interrogation must be free to write
while it runs. What is gated is exclusively the CLAIM that it is over.

Mechanism:
  - Fires on Write/Edit/MultiEdit; only looks at content with a Status field.
  - On Edit/MultiEdit with `file_path`, it does not judge the fragment
    (`new_string`) alone: it reads the file from disk, applies each
    `old_string` -> `new_string` in order (honoring `replace_all`; without it,
    it requires `old_string` to be unique in the text and replaces that single
    occurrence -- the same as the Edit tool really does) and judges the whole
    RESULTING FILE, Status included. Without that, an Edit that only swaps
    `Status:` fools the gate (it does not see the criteria, which are outside
    the fragment) and an Edit that punches a hole in a criterion or reopens a
    question fools the gate from the other side (the fragment has no Status, so
    nothing fires). If the file does not exist, cannot be read, some
    `old_string` does not match, or matches more than once without
    `replace_all`, it allows (the tool itself will fail on its own). Without
    `file_path`, it keeps the old behavior: it judges only the fragments
    (`new_string`).
  - Status other than "ready-to-build" (or the old `pronta-para-construir`) ->
    allows, without looking at anything else.
  - Declared ready, so it requires, in each `### CS-<n>` block:
      * **Surface:** (or the old Superfície:) with a value from the closed
        vocabulary (the same as the acceptance-completeness skill: http, cli,
        ui, event, domain, application);
      * **Red test:** (or the old Teste vermelho:) with text that is not a
        placeholder.
  - Requires at least one criterion: a ready specification with zero criteria
    is the quietest case of all.
  - Requires that no open question (`- [ ]`) was left over.
  - The format's own template line (enumeration or <placeholder>) passes,
    otherwise the gate would stop editing the document that defines the format.

Epic screen (`/common:epic`, CS-5 of cycle 1 of the spiral Cepa Epic):
  - An Epic closes by script, not by criterion. An Epic is the document in
    `docs/epics/*.md` or the one that opens with `# Epic:`; in it, `Status:
    ready` (or `ready-to-build`; the old `pronta`/`pronta-para-construir` also
    count) is the gated claim, and the screen is a different one:
      * the table under `## Value ladder` (or the old `Escada de valor`) has at
        least one cycle, and the columns "Script", "Effect on screen" and
        "Effect in backend" (or the old Roteiro, Efeito em tela, Efeito em
        backend);
      * each cycle row fills all three, with no placeholder: the script is what
        the owner sees, and screen and backend are where someone observes that
        it happened;
      * `## Invariants` (or the old Invariantes) has at least one list item that
        is not a placeholder;
      * the `## Decided without asking` section (or the old Decidido sem
        perguntar) exists;
      * no open question (`- [ ]`) was left over.
  - Outcome screen (2026-11-02, owner's "1. sim" and "3. sim" on the PRD
    rules review): an Epic that declares the NEW word `ready` (or `closed`)
    must also say who it is for, what stays out and which number shows it
    helped, not only that it works:
      * `## Who it is for` has text that is not a placeholder;
      * `## Out of scope` has at least one list item;
      * `## Outcome metric` fills **Baseline:**, **Target:** and **Source:**.
    The old `pronta` keeps the earlier screen, so an Epic already closed
    before this rule (wego-product `leitura-de-guias-fase-0-kairos.md`) is not
    blocked on its next unrelated edit.
  - `Status: closed` is the claim that the Epic is over: it passes the whole
    `ready` screen plus `## Impact` filling **Measured value:** and
    **Measured on:**. Delivered is not the same as helped; closed requires
    someone to have gone back and measured.
  - A document that is not an Epic keeps the earlier yardstick: `Status:
    pronta` in it is not gated, only `ready-to-build` (or the old
    `pronta-para-construir`).

Exit codes:
  0 -- allowed
  2 -- blocked (stderr reaches the agent, which fixes it on its own)
"""

import json
import re
import sys
from pathlib import Path

GATED_TOOLS = ("Write", "Edit", "MultiEdit")

SURFACES = ("http", "cli", "ui", "event", "domain", "application")

# English names (2026-10-23, item interface-in-english) and the old ones: the
# gate accepts both; the messages tell the agent to write the new ones.
READY = "ready-to-build"
READY_OLD = "pronta-para-construir"
SPEC_READY = (READY, READY_OLD)

MARKER = r"(?:\*\*|__|#{1,6}\s*|h[1-6]\.\s*|[-*+]\s+)"

STATUS_RE = re.compile(
    rf"^{MARKER}?\s*Status\s*(?:\*\*|__)?\s*:\s*{MARKER}?\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)

# Criterion heading: "### CS-1: text". The id is what shows up in the block
# message, so the agent knows WHICH criterion to fix.
CS_RE = re.compile(r"^#{2,6}\s*(CS-[0-9A-Za-z]+)\s*:?\s*(.*)$", re.MULTILINE)

FIELD_RE = {
    "superficie": re.compile(
        rf"^{MARKER}?\s*(?:Superf[íi]cie|Surface)\s*(?:\*\*|__)?\s*:\s*{MARKER}?\s*(.+)$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "teste": re.compile(
        rf"^{MARKER}?\s*(?:Teste vermelho|Red test)\s*(?:\*\*|__)?\s*:\s*{MARKER}?\s*(.+)$",
        re.MULTILINE | re.IGNORECASE,
    ),
}

# Open question in markdown checklist format.
OPEN_RE = re.compile(r"^\s*[-*+]\s*\[\s\]\s*(.+)$", re.MULTILINE)

# Epic: the status it claims when closing. `pronta-para-construir` also counts,
# otherwise an Epic that uses the specification's word would escape its screen.
EPIC_READY = ("ready", "pronta", READY, READY_OLD, "closed")

# Words that also get the outcome screen (who, out of scope, metric). The old
# `pronta` does not: see the docstring.
EPIC_OUTCOME = ("ready", "closed")
EPIC_CLOSED = "closed"

EPIC_TITLE_RE = re.compile(r"^#\s+Epic\s*:", re.MULTILINE | re.IGNORECASE)
EPIC_PATH_RE = re.compile(r"(^|/)docs/epics/[^/]+\.md$")

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

# Ladder columns the screen requires, found by the table header.
EPIC_COLUMNS = (
    (("script", "roteiro"), "Script",
     "o que o dono vê funcionando no fim do ciclo"),
    (("effect on screen", "efeito em tela"), "Effect on screen",
     "onde, na tela, alguém vê que aconteceu"),
    (("effect in backend", "efeito em backend"), "Effect in backend",
     "o registro, endpoint ou evento que prova que aconteceu de verdade"),
)

ITEM_RE = re.compile(r"^\s*[-*+]\s+(?!\[[ xX]\])(.+)$", re.MULTILINE)


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


def apply_edit(text: str, edit: dict):
    """Apply an `old_string` -> `new_string` over `text`, as the Edit tool
    really would. Returns None if `old_string` does not match, or if it matches
    more than once without `replace_all` -- the real tool requires
    `old_string` to be unique in that case and fails on its own; the caller
    here decides to allow."""
    old = edit.get("old_string")
    new = edit.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str) or old == "":
        return None
    if old not in text:
        return None
    if edit.get("replace_all"):
        return text.replace(old, new)
    if text.count(old) > 1:
        return None
    return text.replace(old, new, 1)


def result_after_edits(tool_name: str, tool_input: dict):
    """For Edit/MultiEdit with `file_path`: reads the file from disk and applies
    each edit in order, returning the whole resulting content. Returns None
    when it cannot be computed safely (no `file_path`, unreadable file,
    unexpected format, or some `old_string` that does not match) -- in those
    cases the caller allows, because the real tool will fail on its own."""
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return None

    if tool_name == "MultiEdit":
        edits = tool_input.get("edits")
    else:
        edits = [tool_input]
    if not isinstance(edits, list) or not edits:
        return None

    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    for edit in edits:
        if not isinstance(edit, dict):
            return None
        text = apply_edit(text, edit)
        if text is None:
            return None
    return text


def clean(value: str) -> str:
    v = value.strip()
    v = re.sub(r"^(\*\*|__|`)+|(\*\*|__|`)+$", "", v).strip()
    v = v.strip("*_`").strip()
    return v.rstrip(".;,").strip()


def is_template_line(value: str) -> bool:
    """The line that TEACHES the format, not a real criterion."""
    v = clean(value).lower()
    if v.startswith("<"):
        return True
    v = v.strip("<>").strip()
    parts = [p.strip() for p in re.split(r"[|/]", v) if p.strip()]
    return len(parts) > 1 and all(p in SURFACES for p in parts)


def is_empty(value: str) -> bool:
    """Text that takes up the line without saying anything."""
    v = clean(value).lower()
    if not v or v.startswith("<"):
        return True
    return v in ("", "-", "n/a", "na", "tbd", "todo", "a definir", "?", "...")


def criterion_blocks(content: str):
    """Slice the document into (id, body) by `### CS-<n>` heading."""
    marks = list(CS_RE.finditer(content))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(content)
        yield m.group(1), content[m.end():end]


def is_epic(content: str, file_path) -> bool:
    if isinstance(file_path, str) and EPIC_PATH_RE.search(
            file_path.replace("\\", "/")):
        return True
    return EPIC_TITLE_RE.search(content) is not None


def sections(content: str):
    """{lowercase ## section title: body up to the next ##}."""
    marks = list(SECTION_RE.finditer(content))
    out = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(content)
        out.setdefault(m.group(1).strip().lower(), content[m.end():end])
    return out


def section(content: str, prefix: str):
    """The body of the first `## <prefix>...` section, or None if it does not
    exist. `prefix` may be a tuple: the new name and the old one both count."""
    if isinstance(prefix, str):
        prefix = (prefix,)
    for title, body in sections(content).items():
        if title.startswith(tuple(prefix)):
            return body
    return None


def cells(line: str):
    """The cells of a table row. `\\|` is an escaped pipe inside the cell, not
    a divider: splitting on it would shift the following columns."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


# Ladder cell that takes up space without saying anything, beyond what
# `is_empty` already catches. It stays only in the Epic screen so as not to
# touch the specification's yardstick.
EPIC_EMPTY = ("—", "–", "nenhum", "nenhuma", "n/d", "nd", "-/-")


def epic_problems(content: str):
    problems = []

    ladder = section(content, ("value ladder", "escada de valor"))
    if ladder is None:
        problems.append(
            "falta a seção `## Value ladder` — um Epic pronto sem ciclo "
            "não tem o que demonstrar"
        )
    else:
        lines = [l for l in ladder.splitlines() if l.strip().startswith("|")]
        header = [c.lower() for c in cells(lines[0])] if lines else []
        idx = {}
        for key, name, _ in EPIC_COLUMNS:
            pos = [i for i, c in enumerate(header) if c.startswith(key)]
            if pos:
                idx[key] = pos[0]
            else:
                problems.append(
                    f'Value ladder: falta a coluna "{name}"'
                )
        cycles = [l for l in lines[1:]
                  if not re.fullmatch(r"[\s|:\-]*", l)]
        if not cycles:
            problems.append(
                "Value ladder: nenhum ciclo — a tabela precisa de pelo menos "
                "uma linha"
            )
        if len(idx) == len(EPIC_COLUMNS):
            for l in cycles:
                row_cells = cells(l)
                cycle_name = clean(row_cells[0]) if row_cells and row_cells[0] else "(sem nome)"
                for key, name, _ in EPIC_COLUMNS:
                    i = idx[key]
                    value = row_cells[i] if i < len(row_cells) else ""
                    if is_empty(value) or clean(value).lower() in EPIC_EMPTY:
                        problems.append(
                            f'ciclo "{cycle_name}": falta "{name}"'
                        )

    invariants = section(content, ("invariants", "invariantes"))
    if invariants is None:
        problems.append("falta a seção `## Invariants`")
    else:
        items = [v for v in ITEM_RE.findall(invariants) if not is_empty(v)]
        if not items:
            problems.append(
                "Invariants: a lista está vazia — diga o que nunca pode "
                "regredir enquanto os ciclos andam"
            )

    if section(content, ("decided without asking", "decidido sem perguntar")) is None:
        problems.append(
            "falta a seção `## Decided without asking` — é onde o dono veta o "
            "que você decidiu sozinho"
        )

    open_questions = [clean(q) for q in OPEN_RE.findall(content) if not is_empty(q)]
    for q in open_questions[:5]:
        problems.append(f'pergunta em aberto sem resposta: "{q}"')
    if len(open_questions) > 5:
        problems.append(f"... e mais {len(open_questions) - 5} pergunta(s) em aberto")

    return problems


def field_value(body: str, names):
    """The value of `**<name>:** value` inside a section body, or None. The
    fields may share a line, separated by `·` (the format puts Baseline, Target
    and Source on one line), so each value runs up to the next `·` or the end
    of the line."""
    for name in names:
        pat = (rf"(?:^|[·•])[ \t]*{MARKER}?[ \t]*{re.escape(name)}[ \t]*"
               rf"(?:\*\*|__)?[ \t]*:[ \t]*(?:\*\*|__)?[ \t]*([^·•\n]*)")
        for m in re.finditer(pat, body, re.MULTILINE | re.IGNORECASE):
            if not is_empty(m.group(1)):
                return m.group(1)
    return None


def has_text(body: str) -> bool:
    for line in body.splitlines():
        v = line.strip()
        if not v or v.startswith("|") or v.startswith("#"):
            continue
        v = re.sub(r"^[-*+]\s+", "", v)
        if not is_empty(v):
            return True
    return False


# (accepted field names, label for the message) per required field.
OUTCOME_FIELDS = (("Baseline",), "Baseline"), (("Target",), "Target"), \
    (("Source",), "Source")
IMPACT_FIELDS = (("Measured value",), "Measured value"), \
    (("Measured on",), "Measured on")


def outcome_problems(content: str, closed: bool):
    problems = []
    who = section(content, ("who it is for",))
    if who is None:
        problems.append("falta a seção `## Who it is for` — diga quem tem o "
                        "problema, um papel concreto e não \"usuários\"")
    elif not has_text(who):
        problems.append("Who it is for: a seção está vazia")

    out = section(content, ("out of scope",))
    if out is None:
        problems.append("falta a seção `## Out of scope` — o que este Epic "
                        "explicitamente não entrega")
    elif not [v for v in ITEM_RE.findall(out) if not is_empty(v)]:
        problems.append("Out of scope: a lista está vazia")

    metric = section(content, ("outcome metric",))
    if metric is None:
        problems.append("falta a seção `## Outcome metric` — o número que "
                        "diz que o Epic ajudou, não só que funciona")
    else:
        for names, label in OUTCOME_FIELDS:
            if field_value(metric, names) is None:
                problems.append(f"Outcome metric: falta **{label}:**")

    if closed:
        impact = section(content, ("impact",))
        if impact is None:
            problems.append("falta a seção `## Impact` — `closed` exige que "
                            "alguém tenha voltado e medido a métrica")
        else:
            for names, label in IMPACT_FIELDS:
                if field_value(impact, names) is None:
                    problems.append(f"Impact: falta **{label}:**")
    return problems


def block_epic(problems, status="ready"):
    lines = "\n".join(f"   · {p}" for p in problems)
    columns = "\n".join(f'   · "{name}": {what}' for _, name, what in EPIC_COLUMNS)
    print(
        f"[spec-readiness-gate] BLOQUEADO: o Epic se declara `Status: {status}` "
        "mas ainda não passa no crivo.\n"
        f"{lines}\n"
        "  O que o crivo exige de CADA ciclo da escada:\n"
        f"{columns}\n"
        "  E do documento: pelo menos um invariante, a seção \"Decided without "
        "asking\" e nenhuma pergunta em aberto. Em `ready` e `closed`, também "
        "\"Who it is for\", \"Out of scope\" e \"Outcome metric\" (Baseline, "
        "Target, Source); em `closed`, \"Impact\" (Measured value, Measured on).\n"
        "  Enquanto faltar qualquer um, o Status correto é `draft` — e a "
        "resposta certa é voltar a perguntar ao dono, não relaxar o campo.",
        file=sys.stderr,
    )
    sys.exit(2)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[spec-readiness-gate] payload ilegível; liberando", file=sys.stderr)
        sys.exit(0)

    if not any(t in payload.get("tool_name", "") for t in GATED_TOOLS):
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")

    if tool_name in ("Edit", "MultiEdit") and isinstance(file_path, str) and file_path:
        # With file_path, the fragment (new_string) is not enough -- it needs the
        # WHOLE FILE after the edit, Status included (see docstring).
        content = result_after_edits(tool_name, tool_input)
        if content is None:
            sys.exit(0)      # unreadable file or old_string does not match: allow
    else:
        content = extract_content(tool_input)
        if content is None:
            sys.exit(0)          # without seeing the content, nothing is blocked

    status = [clean(v).lower() for v in STATUS_RE.findall(content)]
    status = [s for s in status if not s.startswith("<")]
    # The template line "draft | ready-to-build" teaches the format.
    status = [s for s in status if "|" not in s]

    if is_epic(content, file_path):
        # The Epic Status often shares the line with other fields
        # (`**Status:** pronta · **Opened on:** ...`): the first word counts.
        first_words = [re.split(r"\s*[·•]\s*|\s+\*\*|\s+__", s)[0].strip()
                     for s in status]
        if not any(s in EPIC_READY for s in first_words):
            sys.exit(0)      # a draft runs free
        claimed = next(s for s in first_words if s in EPIC_READY)
        problems = epic_problems(content)
        if claimed in EPIC_OUTCOME:
            problems += outcome_problems(content, claimed == EPIC_CLOSED)
        if problems:
            block_epic(problems, claimed)
        sys.exit(0)

    if not any(s in SPEC_READY for s in status):
        sys.exit(0)          # a draft runs free; only the claim is gated

    problems = []

    criteria = list(criterion_blocks(content))
    if not criteria:
        problems.append(
            "nenhum critério de sucesso (`### CS-1: ...`) — uma especificação "
            "pronta sem critério é a que mais engana"
        )

    for cid, body in criteria:
        surfaces = [v for v in FIELD_RE["superficie"].findall(body)
               if not is_template_line(v)]
        if not surfaces:
            problems.append(f"{cid}: falta **Surface:**")
        else:
            for v in surfaces:
                if clean(v).lower() not in SURFACES:
                    problems.append(
                        f'{cid}: Surface "{clean(v)}" fora do vocabulário'
                    )

        test = [v for v in FIELD_RE["teste"].findall(body) if not is_empty(v)]
        if not test:
            problems.append(
                f"{cid}: falta **Red test:** — a frase do teste que hoje "
                "falharia"
            )

    open_questions = [clean(q) for q in OPEN_RE.findall(content) if not is_empty(q)]
    for q in open_questions[:5]:
        problems.append(f'pergunta em aberto sem resposta: "{q}"')
    if len(open_questions) > 5:
        problems.append(f"... e mais {len(open_questions) - 5} pergunta(s) em aberto")

    if not problems:
        sys.exit(0)

    lines = "\n".join(f"   · {p}" for p in problems)
    print(
        "[spec-readiness-gate] BLOQUEADO: a especificação se declara "
        f"`Status: {READY}` mas ainda não passa no crivo.\n"
        f"{lines}\n"
        "  O que o crivo exige de CADA critério de sucesso:\n"
        "   · **Surface:** a camada mais externa que o critério nomeia — "
        f"{', '.join(SURFACES)}. Não é o assunto do critério, é onde ele é "
        "observável.\n"
        "   · **Red test:** a frase do teste que HOJE falharia naquela "
        "superfície e passará quando a coisa existir.\n"
        "  Enquanto faltar qualquer um, o Status correto é `draft` — e a "
        "resposta certa é continuar o interrogatório, não relaxar o campo.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
