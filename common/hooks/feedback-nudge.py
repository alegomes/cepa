#!/usr/bin/env python3
"""UserPromptSubmit: when you complain about the harness, reminds you there is
somewhere to record it.

Annoyance with Cepa ALWAYS shows up in the middle of something else: the gate
blocked what it should not have, the command asked again, the report came out
unreadable. At that moment the text of the complaint exists (you just wrote
it), and it gets lost: the agent answers the turn's request and the complaint
becomes conversation history, which dies with the session.

What this hook does is a single line: on seeing a prompt shaped like a
complaint AND with a harness target in it, it injects the instruction to record
it through the `feedback-capture` skill before going on with the turn's work. It
does not block, does not answer, does not decide whether the complaint is valid.

Why a hook and not just the skill: the same lesson the repo has already
catalogued three times: a control that depends on the agent remembering on its
own is not a control. The skill declares HOW to record; the hook guarantees the
moment to record is noticed.

Once per session. Repeating the same line every turn is how one teaches it to be
ignored, and after the first record the mechanism is already in the context.

Fails OPEN on everything: no state, no payload, nothing; it exits silently.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import _wtlib as L
except Exception:  # noqa: BLE001
    L = None

# Target: the complaint has to be ABOUT the harness. Without this, "que porcaria
# de API" (a complaint about the client's code) would become Cepa feedback.
TARGET = re.compile(
    r"\b(cepa|harness|hook|hooks|gate|porteiro|comando|skill|agente|subagente|"
    r"worktree|plugin|prompt|relat[óo]rio|sess[ãa]o|/[a-z-]+:[a-z-]+)\b",
    re.IGNORECASE,
)

# Complaint shape. Deliberately narrow: a false positive here costs a line of
# noise on every normal work turn, and noise is what turns a gate into
# scenery.
COMPLAINT = re.compile(
    r"(n[ãa]o (gost|curt|quero|deveria|devia|era pra|faz sentido)|"
    r"me (irrit|incomod|atrapalh|cansa)|"
    r"irritante|chato|chata|incômod|incomod|atrapalh|"
    r"p[ée]ssim|horr[íi]vel|ruim demais|que saco|de novo\?|"
    r"pare de|para de|parou de|"
    r"por que (voc[êe]|ele|isso) (fez|fica|insiste)|"
    r"est[áa] errado|t[áa] errado|n[ãa]o funciona|"
    r"perd(i|e) tempo|perda de tempo|"
    r"feedback)",
    re.IGNORECASE,
)

# Harness notice that arrives through the same channel as the prompt: the end of
# a subagent or of a background command enters UserPromptSubmit as
# `<task-notification>...</task-notification>`, with the AGENT's text inside (a
# verdict saying "não funciona", a summary that cites the gate). It is not the
# owner speaking, and ordering the complaint recorded "with the owner's text
# verbatim" there would be asking to invent one (deviations.md, 2026-08-30).
# Only what remains outside those blocks counts as prompt.
NOTICE = re.compile(r"<task-notification>.*?(?:</task-notification>|\Z)", re.S)


def owner_speech(prompt):
    """The prompt without the harness notices: what the owner actually wrote."""
    return NOTICE.sub("", prompt).strip()


LINE = (
    "[feedback] Este turno tem forma de queixa sobre o harness. Antes de seguir "
    "com o trabalho pedido, registre-a pelo skill `feedback-capture` "
    "(`cepa-feedback add`), com o texto do dono verbatim e o alvo (comando, hook "
    "ou agente). Registre e siga — não pergunte se deve registrar, e não "
    "interrompa a tarefa do turno para discutir a queixa."
)


def already_warned(root, session):
    """Per-session marker. Anchored at the worktree root (not at the raw cwd,
    which a previous Bash `cd` shifts; see _wtlib.session_root)."""
    if not session:
        return None, False
    marker = Path(root) / ".claude" / "feedback-nudge"
    try:
        return marker, marker.read_text(encoding="utf-8").strip() == str(session)
    except OSError:
        return marker, False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    try:
        if os.environ.get("CEPA_FEEDBACK_NUDGE", "on") == "off":
            sys.exit(0)

        prompt = owner_speech(payload.get("prompt") or "")
        if not prompt or len(prompt) > 4000:
            sys.exit(0)
        if not (COMPLAINT.search(prompt) and TARGET.search(prompt)):
            sys.exit(0)

        cwd = payload.get("cwd") or os.getcwd()
        root = L.session_root(cwd) if L else cwd
        marker, warned = already_warned(root, payload.get("session_id"))
        if warned:
            sys.exit(0)
        if marker:
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(str(payload.get("session_id")), encoding="utf-8")
            except OSError:
                pass  # without the marker the warning repeats; it never fails to warn

        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": LINE,
        }}))
    except Exception as e:  # noqa: BLE001
        print(f"[feedback-nudge] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
