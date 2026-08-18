#!/usr/bin/env python3
"""Contract tests for "camada 0": the execution plan lives at the MAIN clone.

The loss it guards against, verified on disk 2026-08-18 (wego-acesso-backend):
a triage ran inside the session worktree `todo_18080945`, wrote its plan to that
worktree's `.claude/programs/WEGO/plan.yaml`, and the worktree was removed. In a
repo whose `.gitignore` covers `.claude/` wholesale the file is invisible to
git, so nothing on the removal path even saw it — only the rescue net
(`_wtlib.rescue_artifacts`, "camada 1") carried a copy out. The next session,
running in ANOTHER worktree, then read its own empty `.claude/` and reported the
plan dead.

Camada 0 removes the need for the net: one plan, at the main clone, resolved via
`git rev-parse --git-common-dir` on read AND on write. These are prompt
contracts, so the guard has to be mechanical — prose saying "the command should
use the main root" is exactly what erodes silently.

Run with `python3 tests/test_plan_anchor_root.py`.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "docs" / "execution-plan.md"
NEXT = REPO / "common" / "commands" / "next.md"

# Every command prose that resolves a plan path, and the token each one uses for
# the main clone (English plugins vs the pt-BR maestro).
COMMANDS = {
    REPO / "common" / "commands" / "next.md": "<main-root>",
    REPO / "board-flow" / "commands" / "triage.md": "<main-root>",
    REPO / "board-flow" / "commands" / "fix.md": "<main-root>",
    REPO / "board-flow" / "commands" / "prove.md": "<main-root>",
    REPO / "board-flow" / "commands" / "execute.md": "<main-root>",
    REPO / "maestro" / "commands" / "run.md": "<raiz-principal>",
    REPO / "maestro" / "commands" / "program-plan.md": "<raiz-principal>",
    REPO / "maestro" / "commands" / "resume.md": "<raiz-principal>",
}

FAILURES = []


def check(label, cond, extra=""):
    if cond:
        print(f"✓ {label}")
    else:
        print(f"✗ {label}" + (f" — {extra}" if extra else ""))
        FAILURES.append(label)


def read(p):
    return p.read_text(encoding="utf-8")


def flat(txt):
    """Whitespace-collapsed text. Prose checks match phrases, not line breaks —
    otherwise a harmless re-wrap turns the guard red and teaches people to
    loosen it, which is how a mechanical guard becomes decorative."""
    return " ".join(txt.split())


def body(p):
    """The file without its YAML frontmatter — the `description:` one-liner is
    user-facing copy in the plugin manifest, not a path the model resolves."""
    txt = read(p)
    if txt.startswith("---"):
        end = txt.find("\n---", 3)
        if end != -1:
            return txt[end + 4:]
    return txt


def main():
    # ── the canonical statement lives in the doc, once ──────────────────────
    doc = flat(read(DOC))
    check("docs/execution-plan.md tem a seção 'Where the file lives'",
          "### Where the file lives" in doc)
    check("a seção nomeia o comando que resolve a raiz principal",
          "git rev-parse --git-common-dir" in doc)
    check("a seção nomeia os DOIS jeitos de perder o plano",
          "Writing it under the current worktree" in doc
          and "Copying a plan per worktree" in doc,
          "sem os dois, o leitor conserta um e reintroduz o outro")
    check("a seção liga o conserto ao item do BACKLOG",
          "camada 0" in doc)

    # ── cada comando ancora, e nenhum deixa caminho relativo ao cwd ─────────
    for path, token in COMMANDS.items():
        name = path.name
        txt = body(path)
        ftxt = flat(txt)
        check(f"{name}: resolve a raiz pelo --git-common-dir",
              "git rev-parse --git-common-dir" in ftxt)
        check(f"{name}: usa o token da raiz principal ({token})",
              token in ftxt)
        # o guard que importa: nenhuma menção a .claude/programs SEM prefixo de
        # raiz. É o que a perturbação quebra primeiro se alguém "simplificar".
        bare = re.findall(r"(?<!main-root>/)(?<!raiz-principal>/)\.claude/programs",
                          ftxt)
        check(f"{name}: nenhum caminho de plano relativo ao diretório corrente",
              not bare,
              f"{len(bare)} ocorrência(s) de .claude/programs sem raiz")

    # ── /common:next procura antes de declarar ausência ─────────────────────
    nxt = flat(body(NEXT))
    check("next procura no clone principal e no resgate antes de dizer 'não há plano'",
          "Before declaring absence" in nxt)
    check("next conhece o diretório onde o resgate deposita",
          ".claude/rescued/*/programs/*/plan.yaml" in nxt)
    check("next não sobrescreve o plano vivo com o resgatado",
          "never copy it over the live one" in nxt,
          "restaurar às cegas troca 47 itens por 14 — a perda vira o conserto")
    check("next manda mostrar as duas contagens de itens ao dono",
          "put both counts in front of the user" in nxt)
    check("next ainda se recusa a inventar ordem quando não há plano mesmo",
          "Don't manufacture an order" in nxt)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
