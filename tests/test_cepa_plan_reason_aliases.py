#!/usr/bin/env python3
"""The six stop/deferral reasons of `cepa-plan queue --json`, in English.

Same alias method as f26a765/84fde4d: the NEW name is what gets emitted
(`end-of-queue`, `cap`, `blocked`, `reserved`, `depends-on-deferred`,
`blocked-before`); the old Portuguese spelling stays available in `reason_pt`
and readers accept both. What these cases prove:

  1. `cepa-plan queue --json` emits each new value, and `reason_pt` carries the
     old one, for all 6 situations;
  2. `cepa-until` (the `decide` path, which consults OWNER_REASON and
     NO_OWNER_REASON) behaves the same for the old and the new spelling of each
     deferral reason, and normalizes the stop reason of the run_end.

Run with `python3 tests/test_cepa_plan_reason_aliases.py`.
"""

import importlib.machinery
import importlib.util
import os
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _isolated_telemetry import isolate  # noqa: E402
import test_common_drain_plan as T  # noqa: E402

isolate()

REPO = Path(__file__).resolve().parent.parent
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"

PAIRS = {
    "end-of-queue": "fim-da-fila",
    "cap": "teto",
    "blocked": "bloqueado",
    "reserved": "reservado",
    "depends-on-deferred": "depende-de-adiado",
    "blocked-before": "bloqueado-antes",
}
check = T.check


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_cepa_plan_emits_english_and_keeps_the_old_in_reason_pt(base):
    seen = {}

    d = T.git_repo(base, "cap")
    T.write_queue(d, [T.item("A"), T.item("B")])
    seen["cap"] = T.queue(d, "fila", "--max", "1")[1]["stop"]

    d = T.git_repo(base, "fim")
    T.write_queue(d, [T.item("A")])
    seen["end-of-queue"] = T.queue(d)[1]["stop"]

    d = T.git_repo(base, "bloq")
    T.write_queue(d, [T.item("A", blocked_by=["Z"]), T.item("Z")])
    seen["blocked"] = T.queue(d)[1]["stop"]

    d = T.git_repo(base, "res")
    owner = {"session_id": "viva", "pid": os.getpid(),
             "hostname": socket.gethostname(), "cwd": str(d),
             "started_at": T.now_iso()}
    T.write_queue(d, [T.item("A", status="in_progress", claimed_by=owner),
                      T.item("B", blocked_by=["A"]), T.item("C")])
    out = T.queue(d)[1]
    deferred = {a["id"]: a for a in out["deferred"]}
    seen["reserved"] = deferred["A"]
    seen["depends-on-deferred"] = deferred["B"]

    d = T.git_repo(base, "antes")
    T.write_queue(d, [T.item("A", status="blocked", evidence="x"), T.item("B")])
    seen["blocked-before"] = T.queue(d)[1]["deferred"][0]

    for new, old in PAIRS.items():
        got = seen.get(new)
        check(f"emite `{new}`", bool(got) and got["reason"] == new, got)
        check(f"...e `reason_pt` carrega `{old}`",
              bool(got) and got.get("reason_pt") == old, got)


def test_cepa_plan_alias_helpers():
    plan = load(CEPA_PLAN, "cepa_plan_alias")
    for new, old in PAIRS.items():
        check(f"cepa-plan: reason_alias({old!r}) == reason_alias({new!r})",
              plan.reason_alias(old) == plan.reason_alias(new) == new)
        check(f"cepa-plan: reason_pt({new!r}) == {old!r}",
              plan.reason_pt(new) == old == plan.reason_pt(old))
    check("cepa-plan: valor desconhecido passa como está",
          plan.reason_alias("human_pending") == "human_pending")
    check("cepa-plan e cepa-until têm o mesmo mapa",
          plan.REASON_ALIASES == load(CEPA_UNTIL, "cepa_until_alias").REASON_ALIASES)


def run_decide(m, reason):
    deferred = [{"id": "W-1", "title": "t", "reason": reason,
                 "question": "Mantenho?", "human_pending": None,
                 "evidence": "e"}]
    screen, questions = [], []
    applied, after = m.decide(
        Path("/nao/existe"), "fila", "run1", {}, deferred, {},
        question=lambda p: questions.append(p) or "",
        output=screen.append,
        answer=lambda i, t, keep=False: (0, f"{i} ok"))
    return questions, screen, applied, after


def test_cepa_until_reader_treats_old_and_new_the_same():
    m = load(CEPA_UNTIL, "cepa_until_reader")
    for new, old in PAIRS.items():
        check(f"cepa-until: alias({old!r}) == alias({new!r}) == {new!r}",
              m.reason_alias(old) == m.reason_alias(new) == new)
    for new in ("blocked-before", "reserved", "depends-on-deferred"):
        old = PAIRS[new]
        r_new, r_old = run_decide(m, new), run_decide(m, old)
        check(f"decide: `{old}` == `{new}` (perguntas, tela, respostas)",
              r_new == r_old, (r_old, r_new))
    q_owner = run_decide(m, "blocked-before")[0]
    q_none = run_decide(m, "reserved")[0]
    check("sanidade: blocked-before pergunta, reserved não",
          len(q_owner) > 0 and q_none == [], (q_owner, q_none))
    check("run_end: o motivo antigo da fila vira o novo",
          m.reason_alias("fim-da-fila") == "end-of-queue")


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (test_cepa_plan_emits_english_and_keeps_the_old_in_reason_pt,):
            print(f"\n{fn.__name__}")
            fn(base)
    for fn in (test_cepa_plan_alias_helpers,
               test_cepa_until_reader_treats_old_and_new_the_same):
        print(f"\n{fn.__name__}")
        fn()
    print()
    if T.FAILURES:
        print(f"{len(T.FAILURES)} failure(s): {T.FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
