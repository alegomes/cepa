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

Never blocks anything. With no mode and no intent, it is silent.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

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
    from _modes import parse_session_mode
except Exception:  # noqa: BLE001
    parse_session_mode = None

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
    current = " ".join(str(current_prompt or "").split())
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
