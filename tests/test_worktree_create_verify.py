#!/usr/bin/env python3
"""Contract test: /maestro:run checks IN GIT that the slice's worktree exists.

The loss this guards, measured in a real execution (WEGO-paralelo program,
wave 2, repo wego-acesso-backend, 2026-08-24, herdr 0.7.3): in 4 of 5 calls
`herdr worktree create --json` returned a COMPLETE success JSON — with
`path`, `branch`, `workspace_id` and `"is_prunable": false` — and git did not
register any worktree; the directories did not exist either. `herdr worktree list`
kept showing the ghosts, because herdr keeps its own registry. Without checking
`git worktree list` by hand, the following steps (seed of .env, maestro-fork-settings,
herdr agent start) would run against nonexistent paths and the whole wave would be
born dead — failing in a way that looks like a problem of the daughters, not of the fork.

The trigger is in herdr, out of our reach. What is ours: not accepting an external
tool's word about an effect that git checks in one command —
the same pattern as the `MAESTRO-EXIT` marker, which synchronizes by FILE and not
by pane.

Since the contract lives in command prose (the model is the one who executes), the guard has
to be mechanical, in the mold of tests/test_plan_anchor_root.py: prose saying
"trust the --json" is exactly what erodes in silence.

Run: python3 tests/test_worktree_create_verify.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUN = REPO / "maestro" / "commands" / "run.md"
RESUME = REPO / "maestro" / "commands" / "resume.md"

FAILURES = []


def check(label, cond, extra=""):
    if cond:
        print(f"✓ {label}")
    else:
        print(f"✗ {label}" + (f" — {extra}" if extra else ""))
        FAILURES.append(label)


def flat(txt):
    """Text with collapsed whitespace: the checks match a PHRASE, not a line
    break — otherwise an innocent re-wrap goes red and teaches loosening the
    guard, which is how a mechanical guard becomes decoration.
    """
    return " ".join(txt.split())


def step_6a(txt):
    """The snippet of step 6a — from 'a. **Worktree herdr**' to item 'b.'."""
    start = txt.find("a. **Worktree herdr**")
    if start == -1:
        return ""
    end_marker = txt.find("\n   b. ", start)
    return txt[start:end_marker if end_marker != -1 else len(txt)]


def main():
    run = RUN.read_text(encoding="utf-8")
    block = step_6a(run)
    check("run.md ainda tem o passo 6a (fork da worktree da slice)", bool(block),
          "o passo mudou de forma — reancore este teste antes de seguir")
    fb = flat(block)

    check("6a: chama o `herdr worktree create`",
          "herdr worktree create" in fb)
    check("6a: confere o resultado com `git worktree list`",
          "git worktree list" in fb,
          "sem esta conferência o fork confia no exit code do herdr")
    check("6a: confere no CLONE PRINCIPAL, não na árvore corrente",
          "git -C <main-root> worktree list" in fb)
    check("6a: diz explicitamente que o JSON de sucesso não basta",
          "the success `--json` is not enough" in fb,
          "a prosa tem de nomear o motivo, senão alguém 'simplifica' de volta")
    check("6a: registra a evidência que originou a checagem",
          "2026-08-24" in fb and "is_prunable" in fb)
    check("6a: manda tentar de novo UMA vez",
          "try **once** more" in fb)
    check("6a: marca a slice como FAIL com detalhe nomeado quando persiste",
          "set-slice" in fb and "fail" in fb and "--detail" in fb)
    check("6a: proíbe forkar as demais slices em silêncio",
          "do **not** fork silently" in fb)

    # resume.md today does NOT create a worktree (it only reconciles and resumes the event loop).
    # If one day it starts creating, the same check must come along — this is the
    # guard that keeps the rule from being born in only one of the two commands.
    res = flat(RESUME.read_text(encoding="utf-8"))
    if "herdr worktree create" in res:
        check("resume.md: se cria worktree, confere por `git worktree list`",
              "git worktree list" in res,
              "resume passou a forkar sem herdar a conferência do run.md")
    else:
        print("✓ resume.md não cria worktree (nada a conferir lá)")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
