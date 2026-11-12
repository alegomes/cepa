#!/usr/bin/env python3
"""Injects the active work mode into the context, every turn.

The mode is declared in `cepa --mode <x>` and recorded in .claude/session-mode.
It is a STATE that lasts the whole session, unlike the routine, which is a task
that ends. Full design: docs/modos-de-trabalho.md.

Why UserPromptSubmit and not SessionStart: the boundary has to be present in the
turn where the deviation appears. Injected only at opening, the mode vanishes
from the useful context precisely in long sessions, which are where leakage
between activities happens.

Lean output on purpose (fits in a few lines): it pays a toll on every turn. It
says the mode, its exit condition and the deviation rule, nothing more.

Along with the mode goes the session's INTENT (`.claude/session-intent`,
written only by `cepa-intent`; design in docs/estrategia-intencao-da-sessao.md),
capped at two lines, in one of three states:

  - no recorded intent (and a session opened by `cepa`, that is, with a mode):
    the session's first three prompts and the request to propose and record.
    The prompts are the intent in the owner's voice before any deviation (path
    C4);
  - intent recorded by ANOTHER session: the date and the question "do I
    continue or open a new one?", instead of displaying it as current
    (decision D1);
  - this session's intent: purpose, step N/M with how many turns the cursor has
    been stalled, and the next step. The age is what gives away the cursor the
    agent forgot to advance (decision D2); the whole plan stays in whereami.

A `cepa-until` run (`CEPA_UNTIL_RUN`) gets no intent at all: there the intent is
the plan.yaml item, and a file inherited from another session would become a
question nobody is there to answer.

The PROJECT altitude comes once per session, on the first turn only (the hook
pays a toll per turn): when `docs/epics/` has an Epic, one `[epic]` line per
Epic with the cycles closed, in progress and without a queue, and the owner's
open questions. It is not written anywhere: `cepa-plan epics --brief` derives it
from the Epic and the queues, so it cannot drift. It needs no mode (the session
that lost the Epic's thread may have had none) and is skipped in a `cepa-until`
run, where the intent is the queue item.

A `[lembretes]` line also comes on the first turn only (and not in a `cepa-until`
run) when `.claude/reminders` in the main clone has owner reminders: it counts
them and gives the oldest date; the list is `/common:whereami`.

On the OPENING turn of a session `cepa` opened with no request (the prompt
starts with `[menu do modo] <mode>`), a `[menu]` block tells the agent how to
show the menu (translated, same order, numbering and commands) and how to treat
the owner's next reply: number or command fires the action, an action with an
argument gets its one-line question first, an action with no command is led in
conversation, free text is a normal request. The actions come from
`cepa-modes --menu <mode> --json`, the only builder of the menu.

Never blocks anything. With no mode and no intent, it is silent.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Exit condition of each mode: what has to be true for it to close.
# Without it the mode is a label, not a boundary. The table lives in `_modes.py`
# (single source, shared with `cepa-modes`); here it is only read.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _modes import EXIT
except Exception:  # noqa: BLE001 — the hook runs every turn; it must never break
    EXIT = {}
try:
    from _modes import read_intent, same_session, other_session_question
except Exception:  # noqa: BLE001
    read_intent = None
try:
    from _modes import read_reminders
except Exception:  # noqa: BLE001
    read_reminders = None
try:
    from _modes import parse_session_mode
except Exception:  # noqa: BLE001
    parse_session_mode = None
# The exit VERDICT of exploration, read from the disk (docs/reviews/): the
# condition alone was a reminder nobody measured, and the agent kept proposing
# one more turn. Only exploration has it; the other modes close by their gates.
try:
    from _modes import exploration_exit_line
except Exception:  # noqa: BLE001
    exploration_exit_line = None

# The mark `cepa-until` exports on each run (same as session-registry).
ENV_WINDOW = "CEPA_UNTIL_RUN"

# How many log prompts enter the empty state, and the cut of each: they are a
# hint of the intent, not a transcript, and they pay a toll every turn.
FIRST_N = 3
PROMPT_CUT = 120
# The same toll applies to the purpose and the step name: the writer does not
# limit their size, and the hook repeats both on every turn.
PURPOSE_CUT = 160
STEP_CUT = 80


def repo_root(cwd):
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd,
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else cwd
    except Exception:  # noqa: BLE001
        return cwd


def read_mode(root):
    """Reads .claude/session-mode. A format shallow enough not to require PyYAML
    (the hook runs every turn; importing yaml here would be a pointless toll)."""
    path = os.path.join(root, ".claude", "session-mode")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception:  # noqa: BLE001
        return None
    if parse_session_mode is None:
        return None
    # new keys (mode, budget, ...) even if the file is from the old `cepa`
    data = parse_session_mode(text)
    return data if data.get("mode") else None


def _iso(stamp):
    """`2026-10-16T21:40:00Z` (or with offset) -> UTC datetime; None if impossible."""
    try:
        d = datetime.fromisoformat(str(stamp).strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def log_prompts(root):
    """`.claude/session-log.md` -> [(UTC datetime, prompt on one line)].

    The format is that of `session-log.py`: `## YYYY-MM-DD` groups the day and
    `### HH:MM:SS UTC` opens each prompt."""
    path = os.path.join(root, ".claude", "session-log.md")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return []
    out, day, when, body = [], None, None, []

    def close():
        t = " ".join(" ".join(body).split())
        if when is not None and t:
            out.append((when, t))

    for line in text.splitlines():
        m = re.match(r"^## (\d{4}-\d{2}-\d{2})\s*$", line)
        if m:
            close()
            day, when, body = m.group(1), None, []
            continue
        m = re.match(r"^### (\d{2}:\d{2}:\d{2}) UTC\s*$", line)
        if m:
            close()
            when, body = _iso(f"{day}T{m.group(1)}Z") if day else None, []
            continue
        # the top `# Session log` falls here before the 1st `###` and is
        # discarded by `close()`; inside a prompt, `# title` is the owner's text
        body.append(line)
    close()
    return out


def session_start(root, session_id):
    """When THIS session began, from the session registry (main clone).

    The prompt log is per worktree and spans sessions; without the start, "the
    first prompts" would be those of a session from weeks ago."""
    if not session_id:
        return None
    try:
        import _wtlib as L
        entry = L.find_entry(L.main_root(root), session_id) or {}
    except Exception:  # noqa: BLE001
        return None
    return _iso(entry.get("started_at", ""))


def is_menu_opening(prompt):
    """True for the launcher's opening prompt of the mode menu (CS-3/CS-6): the
    prompt STARTS with `MENU_MARK`. The one rule, shared by `menu_lines`."""
    return str(prompt or "").startswith(MENU_MARK)


def first_prompts(root, session_id, current_prompt):
    """The FIRST prompts of this session, cut. Without a recorded start, falls
    back to today's prompts (UTC). The turn's prompt is included if the log does
    not have it yet: hooks of the same event have no guaranteed order."""
    prompts = log_prompts(root)
    start = session_start(root, session_id)
    if start is not None:
        prompts = [t for q, t in prompts if q >= start]
    else:
        today = datetime.now(timezone.utc).date()
        prompts = [t for q, t in prompts if q.date() == today]
    prompts = [t for t in prompts if not is_menu_opening(t)]
    current = " ".join(str(current_prompt or "").split())
    if is_menu_opening(current_prompt):  # RAW prompt: same rule as menu_lines
        current = ""
    if current and (not prompts or prompts[-1] != current):
        prompts.append(current)
    return [cut(t, PROMPT_CUT) for t in prompts[:FIRST_N]]


def cut(text, n):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def turns_since(root, stamp):
    """Log prompts from `stamp` on: for how many turns the cursor has stalled."""
    since = _iso(stamp)
    if since is None:
        return None
    return sum(1 for q, _ in log_prompts(root) if q >= since)


def intent_lines(root, payload, has_mode):
    """The up-to-two intent lines of this turn, or [] (silence)."""
    if read_intent is None:
        return []
    intent = read_intent(root)
    plan = (intent or {}).get("plan")
    if not intent or not intent.get("purpose") or not isinstance(plan, list) or not plan:
        if not has_mode:
            return []
        prompts = first_prompts(root, payload.get("session_id"),
                                payload.get("prompt"))
        listing = " | ".join(f'"{t}"' for t in prompts) or "nenhum ainda"
        return [
            "[intenção] Esta sessão ainda não tem intenção gravada. "
            f"Primeiros prompts: {listing}.",
            "Se este prompt tem conteúdo, proponha em três linhas (propósito, para "
            "quando, plano numerado), grave com `cepa-intent write --purpose "
            '"..." --by-when "..." --plan "passo 1" "passo 2"`, e feche com: a '
            "qualquer momento `/common:whereami` mostra onde estamos. Se o prompt é "
            "trivial ou um comando de abertura, não proponha ainda.",
        ]

    prop = cut(intent["purpose"], PURPOSE_CUT)
    if not same_session(intent.get("session_id"), payload.get("session_id")):
        return other_session_question(intent, prop)

    m = len(plan)
    step = intent.get("step")
    if not isinstance(step, int) or not 1 <= step <= m + 1:
        step = 1
    if step > m:
        stop = cut(intent.get("by_when"), PURPOSE_CUT)
        return [f"[intenção] {prop}. Plano cumprido ({m}/{m})"
                + (f"; ponto de parada: {stop}" if stop else "")
                + ". Próximo: hora de /common:wrap-up."]
    k = turns_since(root, intent.get("step_since"))
    age = f" (há {k} turno{'s' if k != 1 else ''})" if k is not None else ""
    name = cut(plan[step - 1], STEP_CUT)
    nxt = (cut(plan[step], STEP_CUT) if step < m
           else "plano cumprido: hora de /common:wrap-up")
    return [
        f"[intenção] {prop}. Passo {step}/{m}: {name}{age}. Próximo: {nxt}.",
        f"Ao concluir o passo, rode `cepa-intent --step {step + 1}`.",
    ]


def epic_lines(root, payload):
    """The `[epic]` lines (one per Epic) on the session's FIRST turn, or [].

    Fail-silent: any error or non-zero exit from `cepa-plan epics` is silence."""
    try:
        epics = os.path.join(root, "docs", "epics")
        if not os.path.isdir(epics) or not any(
                n.endswith(".md") for n in os.listdir(epics)):
            return []
        if len(first_prompts(root, payload.get("session_id"),
                             payload.get("prompt"))) > 1:
            return []
        plan = Path(__file__).resolve().parent.parent / "bin" / "cepa-plan"
        out = subprocess.run(
            [sys.executable, str(plan), "epics", "--brief", "--repo", root],
            capture_output=True, text=True, timeout=8)
        if out.returncode != 0:
            return []
        return [l for l in out.stdout.splitlines() if l.strip()]
    except Exception:  # noqa: BLE001
        return []


def reminders_lines(root, payload):
    """One `[lembretes]` line on the session's FIRST turn when the owner has
    recorded reminders (`.claude/reminders` in the main clone), or []. The line
    only points: the list, with dates and context, is `/common:whereami`.
    Fail-silent."""
    try:
        if read_reminders is None:
            return []
        import _wtlib as L
        items = read_reminders(L.main_root(root))
        if not items:
            return []
        if len(first_prompts(root, payload.get("session_id"),
                             payload.get("prompt"))) > 1:
            return []
        oldest = min((str(e.get("at") or "") for e in items if e.get("at")),
                     default="data desconhecida")
        return [f"[lembretes] {len(items)} lembrete(s) do dono gravado(s), o mais "
                f"antigo de {oldest}. Ao citar um, diga a data e o contexto e "
                "pergunte se ainda vale; /common:whereami lista todos."]
    except Exception:  # noqa: BLE001
        return []


# The fixed marker `cepa` puts at the start of the opening prompt (CS-3). Only a
# prompt that STARTS with it is the opening turn: the launcher knows for sure no
# request came, so the hook does not have to guess whether a prompt is vague.
MENU_MARK = "[menu do modo]"


def menu_lines(root, prompt):
    """The `[menu]` block of the opening turn, or [] on any other turn.

    The actions come from `cepa-modes --menu <mode> --json`, the only builder of
    the menu, so the numbers here are the numbers the owner sees in the prompt.
    Only the opening turn pays this subprocess. Fail-silent."""
    text = str(prompt or "")
    if not is_menu_opening(text):
        return []
    try:
        mode = text[len(MENU_MARK):].split("\n", 1)[0].strip()
        if not mode:
            return []
        modes_bin = Path(__file__).resolve().parent.parent / "bin" / "cepa-modes"
        out = subprocess.run(
            [sys.executable, str(modes_bin), "--menu", mode, "--json", "--no-color"],
            cwd=root, capture_output=True, text=True, timeout=8)
        if out.returncode != 0:
            return []
        actions = json.loads(out.stdout or "[]")
    except Exception:  # noqa: BLE001
        return []
    if not actions:
        return []
    rules = [
        "[menu] Este é o turno de abertura do modo: o prompt traz o menu de ações dele. "
        "Mostre o menu ao dono traduzido para a língua do dono: traduza só as frases e "
        "mantenha a ordem, a numeração e os comandos exatamente como vieram. Não "
        "acrescente, não tire, não reordene ação nenhuma.",
        "Na resposta seguinte do dono: número ou comando do menu dispara a ação.",
    ]
    for a in actions:
        n, cmds, ask = a.get("n"), a.get("commands") or [], a.get("ask")
        if not cmds:
            rules.append(f"Ação {n} está sem comando ainda: se escolhida, conduza-a em "
                         "conversa com o dono.")
            continue
        if len(cmds) > 1:
            first, last = cmds[0], cmds[-1]
            rules.append(
                f"Ação {n} pede argumento: antes de rodar, pergunte em uma linha "
                f'"{ask}" (traduzida). Se a resposta for a chave de um card, rode só '
                f"`{last}` nessa chave; se for uma descrição, rode `{first}` com ela e "
                f"depois `{last}` na chave criada.")
        elif ask:
            rules.append(f"Ação {n} pede argumento: antes de rodar, pergunte em uma linha "
                         f'"{ask}" (traduzida) e rode `{cmds[0]}` com a resposta.')
    rules.append("Resposta em texto livre, que não é número nem comando do menu, é pedido "
                 "normal: atenda como atenderia sem o menu.")
    return [" ".join(rules)]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    try:
        if os.environ.get("CEPA_MODO", "on") == "off":
            sys.exit(0)

        cwd = payload.get("cwd") or os.getcwd()
        root = repo_root(cwd)
        mode = read_mode(root)

        blocks = []
        if mode:
            name = mode["mode"]
            lines = [f"[modo] Esta sessão opera em **{name}**."]
            if mode.get("budget"):
                lines.append(f"Orçamento declarado: {mode['budget']}.")
            if name in EXIT:
                lines.append(f"Fecha quando: {EXIT[name]}.")
            if name == "exploration" and exploration_exit_line is not None:
                lines.append(exploration_exit_line(root))
            lines.append(
                "Ação fora deste modo NÃO vira pergunta e NÃO vira trabalho agora: "
                "registre pelo skill `off-mode-capture` e siga. As capturas entram "
                "no relatório final."
            )
            blocks.append(" ".join(lines))

        if not os.environ.get(ENV_WINDOW):
            try:
                blocks += intent_lines(root, payload, bool(mode))
            except Exception as e:  # noqa: BLE001 — intent never takes the mode down
                print(f"[session-mode] intenção: {e}", file=sys.stderr)

        if not os.environ.get(ENV_WINDOW):
            blocks += menu_lines(root, payload.get("prompt"))
            blocks += epic_lines(root, payload)
            blocks += reminders_lines(root, payload)

        if not blocks:
            sys.exit(0)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(blocks),
        }}))
    except Exception as e:  # noqa: BLE001
        print(f"[session-mode] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
