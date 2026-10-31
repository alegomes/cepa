#!/usr/bin/env python3
"""Measures the turn's final report against the format of the `plain-report` skill.

Reason (2026-08-03): the user reported having to read the reports more than
once to understand them -- too much internal jargon, inverted order (mechanism
before result) and irrelevant detail. The rule already existed in the global
CLAUDE.md ("2 lay sentences, default recommendation, technical last") and had
only been applied to isolated findings. A clear rule that keeps being violated
needs measurement, not more prose -- same principle as proof-verdict-guard.

Two events, one file:

  Stop              -- reads the assistant's last message in the transcript,
                       measures it and, if there is a deviation, BLOCKS the
                       stop: returns {"decision": "block"} with the deviations,
                       and the turn goes on to rewrite the report in the
                       format. Tightening decided on 2026-08-25: a month of
                       "warn and measure" gave 247 off-format reports out of
                       501 measured (49%) -- the warning was not enough.
                       Anti-loop lock: if the stop ALREADY came from a block by
                       this hook (`stop_hook_active`), it does not block again;
                       it records the pending item and lets it through, so the
                       warning reaches the next turn without trapping the
                       session.
  UserPromptSubmit  -- if there is a deviation pending from last time, injects
                       the warning into the next turn's context and deletes the
                       pending item. That is how the warning reaches the model
                       without blocking the turn.

Scope (owner decision, 2026-08-03): only reports of WORK DONE. To know whether
the reply is a report, the hook checks whether the turn used Edit, Write,
MultiEdit, NotebookEdit or ran `git commit`. If it did not, the hook does not
even open the text: conversation, short questions and design discussion are
left out, because formatting a "yes, it exists" into three blocks would be
worse than the problem.

Exception (CS-5, 2026-10-08): the INTERVIEW turn of `/common:epic`. There the
command orders the accepted answer to be written into the document in the same
turn, so every turn writes, and the hook treated it as a report: in the
`/common:epic` test transcript it ordered the challenge rewritten into the
plain-report format, and the question became a numbered item with "I recommend
yes", which is the menu the interview forbids. The turn is spared when ALL of
its writes were to `docs/epics/<name>.md`, there was no commit, the last
paragraph of the speech has a question and the speech carries no mark of the
report (`**For you:**`, "Technical detail", "Decisions and next steps", or the
old pt-BR labels). The closing report has those marks and ends in a numbered
question, so it is still measured. `/common:spec` is outside the exception: its
turn asks in rounds of up to four, and sparing it is another decision.

Owner task with step by step (2026-10-15). On 2026-10-14 the owner rejected a
report whose `Pra você:` said "close the two human routes ... and the seven
holes of the RIPD" and whose closing list said "Nada pendente.": his task only
existed as a category, and he asked "What, after all, do I have to do? Give me
the step by step." Two new measurements: `pra-voce-sem-lista` (the `Pra você:`
announces something pending and the closing list has no numbered item at all)
and `tarefa-sem-passo` (a "Você ..." item without a command or file, or
without the "Pronto quando" line). The first only checks whether what the top
announces shows up at the end; the second only checks the shape of the item,
not whether the command is right.

Session already closed by wrap-up (2026-10-16, feedback fb-20261016-4). After
`/common:wrap-up` finished with "Safe to `exit`", the agent offered
`/common:metrics` in the closing list, the owner accepted, and the metrics
report ended with a new closed question: the closed session opened a new
front, and the owner got lost in the fork tree. New measurement, category
`pergunta-pos-wrap-up`: if wrap-up was invoked and AFTER that some assistant
text says "Safe to exit", every following report that carries a numbered item
with `?` in the closing list, or a `Pra você:` that announces something, is
blocked. The closed session is read from the TRANSCRIPT, not from a marker
file, on purpose: a marker in the handoff would leak into the next session on
the same branch, and a marker in `.claude/` would depend on the model
remembering to write it. The transcript has the session's scope and is
mechanical. A wrap-up that was invoked and stopped on a lock (a merge
conflict, for example) never said "Safe to exit" and does NOT close the
session: there the report may indeed ask the user to resolve something. The
metrics turn only reads, so the scope rule above (turn that changed something)
would leave the incident unmeasured; that is why, with the session closed, the
hook reads the report even without a change and measures only this category.

Reference code without a legend (2026-10-31, feedback fb-20261031-1). The
owner read a closing list that asked "Mantenho E2 como recomendação de P1, com a
comparação reescrita por PR8?" and said: "EU NÃO SEI! Não sei a que se referem e
tampouco sei onde buscar seus significados." The codes came from two places --
the "Reference Points" instruction that labels findings/decisions/options as
F1/D1/O1, and the lens labels of `/common:advisors` (E2, CR2, PR8) -- and
nothing checked that the report itself said what they meant. New measurement,
category `codigo-sem-legenda`: every code (one to three capitals followed by
one or two digits, outside backticks) must be defined in the SAME message,
either inline on first mention -- `E2 (exportar XML pelo Konsist)` -- or in a
legend line (`| E2 | ... |`, `- **E2**: ...`, `E2: ...`). A code from an earlier
turn is dead on arrival: the report is read on its own. Short allowlist for
names that look like codes and are not (S3, MD5, UTF8, L0..L4 of the glossary,
H1..H6).

Output: always exit 0. The block travels in the stdout JSON, not in the exit
code -- the hook never takes the turn down over its own error.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── format limits (common/skills/plain-report/SKILL.md) ────────────────────
MAX_OPENING_SENTENCES = 3
MAX_WORDS_BEFORE_TECHNICAL = 200
MIN_WORDS_TO_MEASURE = 80   # below this it is not a report, it is a note
MAX_PASSIVES = 3            # density, not a hunt: one passive is normal

# Canonical English labels (interface-in-english, 2026-10-23); the pt-BR labels
# remain accepted during the transition.
TECHNICAL_MARKER = re.compile(
    r"^\s{0,3}#{1,6}\s*(?:technical\s+detail|detalhe\s+t[ée]cnico)", re.I | re.M)
FOR_YOU_MARKER = re.compile(
    r"(^\s{0,3}#{1,6}\s*(?:for\s+you|pra\s+voc[êe])"
    r"|\*\*\s*(?:for\s+you|pra\s+voc[êe])\s*:?\s*\*\*)", re.I | re.M)
# The closing list (user request, 2026-08-03). Accepts "Next steps",
# "Decisions" or both together -- the skill's canonical title is the third.
STEPS_MARKER = re.compile(
    r"^\s{0,3}#{1,6}\s*(decisions(?:\s+and\s+next\s+steps)?|next\s+steps|"
    r"decis(?:ões|oes)(?:\s+e\s+pr[óo]ximos\s+passos)?|"
    r"pr[óo]ximos\s+passos)\s*$", re.I | re.M)
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.M)
LIST_ITEM = re.compile(r"^\s{0,3}([-*+]|\d+[.)])\s+\S", re.M)
# Numbered item: the user answers "1 yes, 2 no, 3 let's talk" without having to
# copy the text back. A loose marker ("- ") gives no number to cite.
NUMBERED_ITEM = re.compile(r"^\s{0,3}\d+[.)]\s+\S", re.M)
RECOMMENDATION = re.compile(r"recomendo\b|i\s+recommend\b", re.I)
# Owner task item: the question starts with "Você ..." (2026-10-15).
YOU_ITEM = re.compile(r"^\s*\d+[.)]\s+\**\s*(?:voc[êe]|you)\b", re.I)
NOTHING_PENDING = re.compile(r"nada\s+pendente|nothing\s+pending", re.I)
DONE_WHEN = re.compile(r"pronto\s+quando|done\s+when", re.I)
# File path: starts with / ~/ ./ ../ ; or has 2+ ASCII segments separated by
# slash ("docs/lgpd"); or is a name with an extension ("ripd.md"). A segment
# with an accent does not count, so "sim/não" does not pass as a path.
PATH_RE = re.compile(
    r"(?:(?:^|[\s(])(?:~|\.{1,2})?/[\w.-]+)"
    r"|(?:(?:^|[\s(])[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)"
    r"|(?:\b[A-Za-z0-9_-]+\.[A-Za-z]\w{0,4}\b)")

# Reference code (2026-10-31): `E2`, `P1`, `CR2`, `PR8`, `F6`. Inside backticks
# it is code, not a label, so the inline-code spans are blanked before the scan.
REF_CODE = re.compile(r"(?<![\w/-])([A-Z]{1,3}\d{1,2})(?![\w/-])")
INLINE_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
# A definition: the code followed by an opening parenthesis on the same line, or
# a legend line -- a table row, a bullet, or a line that starts with the code
# and a colon/dash.
def _definition_patterns(code: str) -> list:
    c = re.escape(code)
    return [re.compile(r"(?<![\w/-])" + c + r"\s*\("),
            re.compile(r"^\s*\|\s*\**" + c + r"\**\s*\|", re.M),
            re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*\**" + c + r"\**\s*[:—–-]\s*\S", re.M)]
# Names that look like codes and are vocabulary, not labels.
MAX_INLINE_CODES = 3   # above this, inline parentheses become noise: legend block
REF_CODE_ALLOW = {"S3", "MD5", "UTF8", "H1", "H2", "H3", "H4", "H5", "H6",
                  "L0", "L1", "L2", "L3", "L4"}

STATE_DIR = Path(os.environ.get("CEPA_REPORT_STYLE_DIR")
                 or (Path.home() / ".claude" / "cepa-report-style"))


def _t_emit(event: str, cwd: str = None, **fields) -> None:
    """Minimal mirror of common/hooks/_telemetry.py (cross-plugin import is
    fragile across versioned cache directories). Strictly fail-silent."""
    try:
        import subprocess
        repo = ""
        try:
            out = subprocess.run(
                ["git", "-C", cwd or os.getcwd(), "rev-parse",
                 "--path-format=absolute", "--git-common-dir"],
                capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                common = out.stdout.strip()
                repo = Path(common).parent.name if common.endswith("/.git") else Path(common).name
        except Exception:
            pass
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "event": event, "repo": repo}
        entry.update(fields)
        tdir = Path(os.environ.get("CEPA_TELEMETRY_DIR") or (Path.home() / ".claude" / "cepa-telemetry"))
        tdir.mkdir(parents=True, exist_ok=True)
        with open(tdir / f"events-{entry['ts'][:7]}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


# ── glossary ───────────────────────────────────────────────────────────────
def _glossary_section(title: str) -> list:
    """The bold terms of a section of common/glossario.md."""
    for base in (Path(__file__).resolve().parent.parent,          # common/
                 Path(__file__).resolve().parent.parent.parent):  # repo/common
        f = base / "glossario.md"
        if f.is_file():
            break
    else:
        return []
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    m = re.search(r"^##\s*" + re.escape(title) + r"\s*$(.*?)(?=^##\s|\Z)",
                  text, re.S | re.M | re.I)
    if not m:
        return []
    terms = []
    for line in m.group(1).splitlines():
        m2 = re.match(r"^\s*-\s*\*\*(.+?)\*\*", line)
        if not m2:
            continue
        # "portão", "falha aberto / falha fechado", "é medido / são medidas" (several terms per line)
        for term in m2.group(1).split("/"):
            term = term.strip().lower()
            if len(term) >= 4:
                terms.append(term)
    return terms


def load_jargon() -> list:
    """Internal project terms -- flagged only in the OPENING.

    The 'Aceitos sem tradução' section is left out on purpose: it is the
    vocabulary already current between the user and the harness, and flagging
    it would generate noise that would make the meter get ignored. In the
    technical detail these terms are allowed: there they are dense and useful.
    """
    return _glossary_section("Traduzir sempre")


def load_abstractions() -> list:
    """Invented categories that take the place of the fact -- flagged in the
    WHOLE text, including the technical detail.

    Reason (2026-08-03): the first version of this hook treated the technical
    block as a free zone, and it was exactly there that the user found "virou
    um sinal mecânico", "nunca são medidas" and "chega por um caminho
    indireto" -- none of them is project jargon, all are abstractions invented
    on the spot. The technical block has freedom of LENGTH, not of clarity.
    """
    return _glossary_section("Abstrações a evitar")


def load_hygiene() -> list:
    """Phrases that only matter when they fail -- flagged in the opening and in
    `Pra você:`, never in the technical detail.

    Reason (2026-08-03): the user read a whole report inside the format and
    still asked "so what?". Four lines of it said the tree was clean, that no
    worktree was left and that memory was updated -- none of them changes
    anything for the reader. In the technical detail such a sentence is cheap;
    in the 200 words at the top it takes the place of the consequence.
    """
    return _glossary_section("Higiene (não relatar)")


# Passive voice and nominalization hide who does what: "são medidas" does not
# say who measures or how. Deliberate regex over "to be" + participle.
PASSIVE = re.compile(
    r"\b(é|são|foi|foram|será|serão|era|eram|seja|sejam|sendo|ser)\s+"
    r"(\w{3,}(?:ad|id)[oa]s?)\b", re.I)


# ── reading the transcript ───────────────────────────────────────────────────
def read_rows(transcript_path: str) -> list:
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            return [json.loads(l) for l in fh if l.strip()]
    except Exception:
        return []


def _is_user_prompt(row) -> bool:
    """A real user turn -- not a tool_result disguised as user."""
    if row.get("type") != "user" or row.get("isSidechain"):
        return False
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in content)
    return False


def turn_changed_something(rows) -> bool:
    """Was there a write, edit or commit since the user's last prompt?

    If so, the final answer counts as a report of work done. It also looks at
    what the subagent did: subagent work is work done.
    """
    start = 0
    for i in range(len(rows) - 1, -1, -1):
        if _is_user_prompt(rows[i]):
            start = i
            break
    for row in rows[start:]:
        if row.get("type") != "assistant":
            continue
        for block in (row.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                return True
            if name == "Bash":
                cmd = str((block.get("input") or {}).get("command", ""))
                if re.search(r"\bgit\s+(commit|merge|push)\b", cmd):
                    return True
    return False


SAFE_TO_EXIT = re.compile(r"safe\s+to\s+`?exit`?", re.I)
WRAP_UP_INVOKED = re.compile(
    r"<command-name>\s*/?(?:common:)?wrap-up\s*</command-name>", re.I)


def _user_text(row) -> str:
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def session_closed(rows) -> bool:
    """Was `/common:wrap-up` invoked and AFTER that said "Safe to exit"?

    Only the main conversation counts (never `isSidechain`). Invocation: the
    user line with `<command-name>/common:wrap-up</command-name>` (that is how
    a slash command lands in the transcript) or starting with
    `/common:wrap-up` or `/wrap-up`; or a `tool_use` of `Skill` whose
    `input.skill` ends in `wrap-up`. "Safe to exit" counts on the same line as
    the invocation or in any later assistant text, including the last report.
    Only assistant text counts: the command body, injected as a user line,
    also quotes the phrase."""
    invoked = False
    for row in rows:
        if row.get("isSidechain"):
            continue
        kind = row.get("type")
        if kind == "user":
            text = _user_text(row)
            if WRAP_UP_INVOKED.search(text) or re.match(
                    r"\s*/(?:common:)?wrap-up\b", text):
                invoked = True
        elif kind == "assistant":
            for block in (row.get("message") or {}).get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and block.get("name") == "Skill":
                    skill = str((block.get("input") or {}).get("skill", ""))
                    if skill.endswith("wrap-up"):
                        invoked = True
                elif (block.get("type") == "text" and invoked
                      and SAFE_TO_EXIT.search(block.get("text", ""))):
                    return True
    return False


INTERVIEW_DOC = re.compile(r"(^|/)docs/epics/[^/]+\.md$")


def interview_turn(rows, speech: str) -> bool:
    """Did the turn only write the interview document and end by asking?

    "Ends by asking" means the last paragraph has a `?`, not the last
    character: the proposal that accompanies the question sometimes comes
    after it ("...? My proposal: X. Correct me."), and that was the turn
    blocked in the transcript."""
    if (FOR_YOU_MARKER.search(speech) or TECHNICAL_MARKER.search(speech)
            or STEPS_MARKER.search(speech)):
        return False
    paragraphs = [p for p in re.split(r"\n\s*\n", speech) if p.strip()]
    if not paragraphs or "?" not in paragraphs[-1]:
        return False
    start = 0
    for i in range(len(rows) - 1, -1, -1):
        if _is_user_prompt(rows[i]):
            start = i
            break
    wrote = False
    for row in rows[start:]:
        if row.get("type") != "assistant" or row.get("isSidechain"):
            continue
        for block in (row.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            tool_input = block.get("input") or {}
            if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                target = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
                if not INTERVIEW_DOC.search(target.replace("\\", "/")):
                    return False
                wrote = True
            elif name == "Bash" and re.search(
                    r"\bgit\s+(commit|merge|push)\b",
                    str(tool_input.get("command", ""))):
                return False
    return wrote


def last_report(rows) -> str:
    """The assistant's last text in the main conversation (never sidechain:
    a subagent's reply is not the report the user reads)."""
    for row in reversed(rows):
        if row.get("type") != "assistant" or row.get("isSidechain"):
            continue
        content = (row.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        texts = [b.get("text", "") for b in content
                  if isinstance(b, dict) and b.get("type") == "text"]
        joined = "\n".join(t for t in texts if t.strip())
        if joined.strip():
            return joined
    return ""


# ── measurement ─────────────────────────────────────────────────────────────────
def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def sentences(text: str) -> list:
    """Deliberately crude split: it only needs to tell 3 from 8. Abbreviations
    and numbers with a dot count extra, so the limit is generous."""
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [p for p in parts if p.strip()]


def first_paragraph(text: str) -> str:
    """The opening: everything up to the first blank line, heading or list."""
    lines = []
    for line in text.strip().splitlines():
        if not line.strip():
            break
        if re.match(r"^\s{0,3}(#{1,6}\s|[-*+]\s|\d+\.\s|\||>)", line):
            break
        lines.append(line)
    return " ".join(lines).strip()


def list_items(tail: str) -> list:
    """The items of the final section, one per number. Continuation lines
    (indented or loose) belong to the open item -- the recommendation is almost
    always on the second line."""
    items, current, fenced = [], None, False
    for line in tail.splitlines():
        if current is not None and line.strip().startswith("```"):
            fenced = not fenced
        if NUMBERED_ITEM.match(line) and not fenced:
            if current is not None:
                items.append(current)
            current = line
        elif current is not None:
            if line.strip():
                current += " " + line.strip()
            elif not fenced:
                items.append(current)
                current = None
    if current is not None:
        items.append(current)
    return items


def measure_items(tail: str) -> list:
    """Each item of the closing list is a closed question with a recommendation.

    Reason (2026-08-03, the user's second correction on the same day): the
    first version of the list named the subject and handed the decision back --
    *"which is actually the decision I have to make? I need to interpret the
    text, open the card, understand the whole context, to be able to write a
    next instruction"*. He wants to answer "1 yes, 2 no, 3 let's talk".
    """
    if NOTHING_PENDING.search(tail):
        return []
    if not LIST_ITEM.search(tail):
        return []          # the missing items already became a deviation in the caller

    deviations = []
    items = list_items(tail)
    if not items:
        return [("passos-nao-numerados",
                 "a lista do fim não é numerada — numere para o usuário poder "
                 "responder \"1 sim, 2 não\" sem citar o texto de volta")]

    no_question = [i for i in items if "?" not in i]
    if no_question:
        deviations.append(("item-sem-pergunta",
                        f"{len(no_question)} de {len(items)} itens não fazem uma "
                        f"pergunta fechada (ex.: {no_question[0][:70].strip()}…) — "
                        f"o usuário precisa poder responder sim ou não sem "
                        f"interpretar o assunto"))

    no_reco = [i for i in items if not RECOMMENDATION.search(i)]
    if no_reco:
        deviations.append(("item-sem-recomendacao",
                        f"{len(no_reco)} de {len(items)} itens não trazem "
                        f"\"I recommend yes/no\" — decisão crua sem recomendação "
                        f"devolve o trabalho para o usuário"))

    tasks = [i for i in items if YOU_ITEM.match(i)]
    no_command = [i for i in tasks if "`" not in i and not PATH_RE.search(
        re.sub(r"^\s*\d+[.)]\s+", "", i))]
    no_done = [i for i in tasks if not DONE_WHEN.search(i)]
    if no_command or no_done:
        bad = [i for i in tasks if i in no_command or i in no_done]
        missing = []
        if no_command:
            missing.append("comando ou arquivo")
        if no_done:
            missing.append("a linha 'Done when:'")
        deviations.append(("tarefa-sem-passo",
                        f"{len(bad)} de {len(tasks)} itens de tarefa sua "
                        f"(\"Você ...\") não trazem o passo a passo — falta "
                        f"{' e '.join(missing)} (ex.: {bad[0][:70].strip()}…); "
                        f"sem isso o item diz a categoria, não o passo"))
    return deviations


def for_you_text(report: str) -> str:
    """From the `Pra você:` marker to the end of the paragraph."""
    m = FOR_YOU_MARKER.search(report)
    if not m:
        return ""
    rest = report[m.end():]
    return re.split(r"\n\s*\n", rest, maxsplit=1)[0].strip()


def for_you_announces(text: str) -> bool:
    """Does the `Pra você:` say something is waiting for the user?"""
    cleaned = re.sub(r"^[\W_]+", "", text)
    if not cleaned:
        return False
    return not cleaned.lower().startswith(("nada", "nothing"))


def post_wrap_up_deviation(report: str):
    """The session is already closed: does the report open a new front?

    Returns (category, message) or None. New front = numbered item with `?` in
    the closing list, or a `Pra você:` that announces something."""
    steps_match = STEPS_MARKER.search(report)
    cuts = [x.start() for x in (TECHNICAL_MARKER.search(report), steps_match) if x]
    head = report[:min(cuts)] if cuts else report
    question = bool(steps_match) and any(
        "?" in i for i in list_items(report[steps_match.end():]))
    if not (question or for_you_announces(for_you_text(head))):
        return None
    return ("pergunta-pos-wrap-up",
            "a sessão já foi encerrada pelo wrap-up (\"Safe to exit\"): o "
            "relatório não abre frente nova: nenhuma pergunta fechada na "
            "lista do fim, e `For you:` diz \"nothing\"; o que sobrou você "
            "registra (seção no BACKLOG.md, item de fila ou `cepa-feedback "
            "add`) e a lista diz \"Nothing pending. Próxima sessão começa por "
            "<o Próximo do handoff>.\"")


def codes_without_legend(report: str) -> list:
    """Reference codes used in the report and defined nowhere in it."""
    text = INLINE_CODE.sub(" ", report)
    found = []
    for m in REF_CODE.finditer(text):
        code = m.group(1)
        if code in REF_CODE_ALLOW or code in found:
            continue
        if not any(p.search(text) for p in _definition_patterns(code)):
            found.append(code)
    return found


LEGEND_LINE = re.compile(
    r"^\s*(?:\|\s*\**[A-Z]{1,3}\d{1,2}\**\s*\||(?:[-*+]|\d+[.)])?\s*\**[A-Z]{1,3}\d{1,2}\**\s*[:—–-]\s)",
    re.M)


def distinct_codes(report: str) -> list:
    text = INLINE_CODE.sub(" ", report)
    seen = []
    for m in REF_CODE.finditer(text):
        c = m.group(1)
        if c not in REF_CODE_ALLOW and c not in seen:
            seen.append(c)
    return seen


def decision_list(report: str) -> bool:
    """A numbered list with a recommendation: the shape of the closing list,
    even when the turn wrote nothing (the batch of questions of 2026-10-31)."""
    return bool(NUMBERED_ITEM.search(report) and RECOMMENDATION.search(report))


def code_deviations(report: str) -> list:
    """The two code measurements, applied to any decision list."""
    out = []
    codes = codes_without_legend(report)
    if codes:
        shown = ", ".join(codes[:5])
        rest = f" (+{len(codes) - 5})" if len(codes) > 5 else ""
        out.append(("codigo-sem-legenda",
                    f"código de referência sem legenda nesta mensagem: "
                    f"{shown}{rest} — o leitor não sabe a que se refere nem "
                    f"onde buscar; defina na primeira menção, "
                    f"`E2 (o que E2 é)`, ou numa linha de legenda "
                    f"(`- **E2**: ...`), e código de turno anterior se "
                    f"redefine aqui"))
    total = distinct_codes(report)
    if len(total) > MAX_INLINE_CODES and not LEGEND_LINE.search(
            INLINE_CODE.sub(" ", report)):
        out.append(("legenda-inline",
                    f"{len(total)} códigos distintos ({', '.join(total[:6])}"
                    f"{'...' if len(total) > 6 else ''}) definidos só entre "
                    f"parênteses dentro das frases — acima de "
                    f"{MAX_INLINE_CODES} a lista fica ilegível; ponha um bloco "
                    f"`Legenda:` com uma linha `- **E2**: ...` por código "
                    f"antes da lista final e deixe as perguntas limpas"))
    return out


def measure(report: str, jargon: list, abstractions: list = (),
          hygiene: list = (), closed: bool = False) -> list:
    """Returns the deviations as (category, message). Category is a stable label
    for telemetry; message is what the model reads. Empty list = report inside
    the format."""
    deviations = []

    # The top goes up to the first of the two headings -- without the technical
    # detail, the closing list must not fall inside the 200-word ceiling.
    cuts = [x.start() for x in (TECHNICAL_MARKER.search(report),
                                  STEPS_MARKER.search(report)) if x]
    head = report[:min(cuts)] if cuts else report

    opening = first_paragraph(report)
    if not opening:
        deviations.append(("sem-abertura",
                        "não abre com um parágrafo de resultado — a primeira "
                        "coisa é cabeçalho, lista ou tabela"))
    else:
        n = len(sentences(opening))
        if n > MAX_OPENING_SENTENCES:
            deviations.append(("abertura-longa",
                            f"abertura com {n} frases (máximo {MAX_OPENING_SENTENCES})"))
        found = sorted({t for t in jargon if t in opening.lower()})
        if found:
            deviations.append(("jargao",
                            "jargão na abertura: " + ", ".join(found) +
                            " — traduza ou mova para o detalhe técnico"))

    if not FOR_YOU_MARKER.search(head):
        deviations.append(("sem-pra-voce",
                        "falta a linha `**For you:**` — mesmo que seja "
                        "\"nothing to decide\""))

    # The closing list: it exists, is the last section, and carries real items.
    steps_match = STEPS_MARKER.search(report)
    if not steps_match:
        deviations.append(("sem-proximos-passos",
                        "falta a seção final `### Decisions and next steps` — "
                        "uma linha por ação (Decidir / Você faz / Eu faço), ou "
                        "\"Nothing pending.\" quando não há nenhuma"))
    else:
        tail = report[steps_match.end():]
        if HEADING.search(tail):
            deviations.append(("passos-nao-sao-o-fim",
                            "`### Decisions and next steps` não é a última seção — "
                            "nada vem depois dela"))
        if not LIST_ITEM.search(tail) and not NOTHING_PENDING.search(tail):
            deviations.append(("passos-em-prosa",
                            "a seção final não tem itens de lista — cada ação em "
                            "uma linha começando por verbo, não em prosa"))
        deviations += measure_items(tail)
        top = for_you_text(head)
        if (for_you_announces(top) and not NUMBERED_ITEM.search(tail)
                and not closed):
            deviations.append(("pra-voce-sem-lista",
                            f"`For you:` diz que algo espera pelo usuário "
                            f"({top[:60].strip()}), e a lista do fim não tem "
                            f"item numerado nenhum — cada tarefa dele é um item "
                            f"numerado com Onde, Comando (ou arquivo) e Done "
                            f"when; só quando o For you diz \"nothing\" a lista "
                            f"pode dizer \"Nothing pending.\""))

    if closed:
        d = post_wrap_up_deviation(report)
        if d:
            deviations.append(d)

    words = count_words(head)
    if words > MAX_WORDS_BEFORE_TECHNICAL:
        deviations.append(("acima-do-teto",
                        f"{words} palavras antes do detalhe técnico "
                        f"(teto {MAX_WORDS_BEFORE_TECHNICAL}) — o resto desce "
                        f"para `### Technical detail`"))

    # Hygiene: only at the top (opening + `Pra você:`). In the technical detail
    # "commit 8827471" is cheap, useful information; up here it pushes out the
    # sentence that says what changed for the reader.
    hits = sorted({h for h in hygiene if h in head.lower()})
    if hits:
        shown = ", ".join(f"\"{v}\"" for v in hits[:3])
        deviations.append(("higiene",
                        f"higiene relatada como resultado: {shown} — só interessa "
                        f"quando falha ou quando exige algo do usuário; no topo, "
                        f"escreva no lugar o que mudou para ele"))

    # These two apply to the WHOLE text. The technical block has freedom of
    # length, not of clarity -- it was in there that the user found the three
    # obscure sentences that motivated this version.
    lowered = report.lower()
    vague = sorted({a for a in abstractions if a in lowered})
    if vague:
        shown = ", ".join(f"\"{v}\"" for v in vague[:4])
        rest = f" (+{len(vague) - 4})" if len(vague) > 4 else ""
        deviations.append(("abstracao",
                        f"abstração no lugar do fato: {shown}{rest} — nomeie a "
                        f"coisa, não a categoria da coisa (ver a seção "
                        f"\"Abstrações a evitar\" do glossário)"))

    deviations += code_deviations(report)

    passives = PASSIVE.findall(report)
    if len(passives) > MAX_PASSIVES:
        examples = ", ".join(f"\"{a} {b}\"" for a, b in passives[:3])
        deviations.append(("passiva",
                        f"{len(passives)} construções passivas ({examples}...) — "
                        f"escondem quem faz o quê; diga quem age"))

    return deviations


# ── pending item between turns ──────────────────────────────────────────────────
def pending_path(session_id: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "sem-sessao")
    return STATE_DIR / f"{slug}.json"


def on_stop(payload):
    """Returns the block reason, or None to let the stop proceed."""
    rows = read_rows(payload.get("transcript_path", ""))
    if not rows:
        return None
    changed = turn_changed_something(rows)
    closed = session_closed(rows)
    # Scope: report of work done. Narrow exception: session closed by wrap-up,
    # where even the turn that only reads (metrics) is measured, but only by
    # the `pergunta-pos-wrap-up` category.
    report = last_report(rows)
    # Third scope (2026-10-31): a decision list that the turn only WROTE --
    # no edit, no commit -- still carries codes the owner has to answer by
    # number. The batch of eight questions with `PR8`, `E1`, `E3` undefined
    # went out through this door. Only the code measurements apply here.
    listed = decision_list(report)
    if not changed and not closed and not listed:
        return None

    if count_words(report) < MIN_WORDS_TO_MEASURE:
        return None
    if interview_turn(rows, report):
        return None

    if changed:
        deviations = measure(report, load_jargon(), load_abstractions(),
                        load_hygiene(), closed=closed)
    elif closed:
        d = post_wrap_up_deviation(report)
        deviations = [d] if d else []
    else:
        deviations = code_deviations(report)
    cwd = payload.get("cwd") or os.getcwd()

    # Anti-loop lock: this stop is already the consequence of a block by this hook.
    # Blocking again would trap the session in an endless rewrite-block pair.
    repeat = bool(payload.get("stop_hook_active"))
    will_block = bool(deviations) and not repeat

    _t_emit("report_style", cwd=cwd,
            palavras=count_words(report),
            desvios=len(deviations),
            tipos=[cat for cat, _ in deviations],
            bloqueou=will_block,
            reincidente=repeat,
            pos_wrap_up=closed)

    p = pending_path(payload.get("session_id", ""))
    if not deviations:
        p.unlink(missing_ok=True)
        return None

    if will_block:
        # The report is rewritten NOW, in the same turn: no pending item for the
        # next turn, otherwise the user gets the warning for an already fixed text.
        p.unlink(missing_ok=True)
        return block_reason([m for _, m in deviations], closed,
                            codes_only=not changed and not closed)

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"desvios": [m for _, m in deviations],
                                "encerrada": closed},
                               ensure_ascii=False),
                     encoding="utf-8")
    except Exception:
        pass
    return None


CLOSED_FORMAT = (
    "abertura de até 3 frases sem jargão → **For you:** nothing → "
    "### Technical detail → ### Decisions and next steps contendo só "
    "\"Nothing pending. Próxima sessão começa por <o Próximo do handoff>.\", "
    "sem item numerado e sem pergunta. O que sobrou vai para registro "
    "(BACKLOG.md, item de fila ou `cepa-feedback add`) e o relatório diz onde.")


def block_reason(deviations, closed: bool = False,
                 codes_only: bool = False) -> str:
    if codes_only:
        return ("Sua lista de decisões usa código de referência que o leitor "
                "não consegue resolver:\n" +
                "".join(f"  - {d}\n" for d in deviations) +
                "Reenvie a MESMA lista com um bloco `Legenda:` antes dela, uma "
                "linha `- **CÓDIGO**: o que é` por código, e as perguntas sem "
                "parênteses de definição. Não mude o resto, não peça desculpa "
                "e não explique a reescrita.")
    if closed:
        ending = ("Reescreva o relatório inteiro nesta ordem, antes de encerrar o "
               "turno: " + CLOSED_FORMAT + " ")
    else:
        ending = ("Reescreva o relatório inteiro nesta ordem, antes de encerrar o "
               "turno: abertura de até 3 frases sem jargão → **For you:** → "
               "### Technical detail → ### Decisions and next steps (lista "
               "numerada, uma pergunta fechada por item, cada uma com "
               "\"I recommend yes/no\" e o porquê em uma linha; tarefa sua com "
               "Onde, Comando (ou arquivo) e Done when; \"Nothing pending.\" "
               "só se o For you disser nothing). ")
    return ("Seu relatório final saiu do formato `plain-report`:\n" +
            "".join(f"  - {d}\n" for d in deviations) + ending +
            "Não peça desculpa e não explique a reescrita \u2014 entregue o "
            "relatório corrigido e nada mais.")


def on_prompt(payload) -> None:
    p = pending_path(payload.get("session_id", ""))
    if not p.is_file():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        deviations = data.get("desvios") or []
        closed = bool(data.get("encerrada"))
    except Exception:
        deviations, closed = [], False
    p.unlink(missing_ok=True)
    if not deviations:
        return
    print("[cepa report-style] Seu relatório anterior saiu do formato "
          "`plain-report`:\n" +
          "".join(f"  - {d}\n" for d in deviations) +
          "  Formato: " + (CLOSED_FORMAT + " " if closed else
          "abertura de até 3 frases sem jargão → **For you:** → "
          "### Technical detail → ### Decisions and next steps (numerada, uma "
          "pergunta fechada por item, cada uma com \"I recommend yes/no\"; tarefa "
          "sua com Onde, Comando e Done when). ") +
          "Este é o caminho de aviso — o relatório anterior já tinha sido "
          "bloqueado uma vez e a reescrita ainda desviou. Aplique no próximo "
          "relatório em vez de reescrever o anterior.")


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    event = payload.get("hook_event_name") or ""
    try:
        if event == "Stop":
            reason = on_stop(payload)
            if reason:
                print(json.dumps({"decision": "block", "reason": reason},
                                 ensure_ascii=False))
        elif event == "UserPromptSubmit":
            on_prompt(payload)
    except Exception:
        pass  # the meter never takes the turn down over its own error
    sys.exit(0)


if __name__ == "__main__":
    main()
