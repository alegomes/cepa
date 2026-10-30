#!/usr/bin/env python3
"""Every agent that delegates carries the async delegation section.

No external dependency — run with `python3 tests/test_async_delegation_specs.py`.

## Why it exists

The `Agent` tool of this harness returns `Async agent launched successfully`, not the
result: the subagent runs in the background and the result arrives later, as a notification
that re-invokes whoever delegated. The 10 specs that delegate were silent about this — none
said where the turn ends — and the leads filled the silence by polling the disk for the
worker's file. Measurement of 2026-08-26 over 5 runs: 912 minutes (15 hours) in commands
that did nothing, between 19% and 52% of each run's clock.

The section went into all 10. The hole that remains is the next agent: whoever creates the
11th lead, or a new topology, has no way to know that this section needs to exist — and its
absence fails nothing, it just brings the polling back in silence. It is the pattern this
repo has already catalogued three times (memory `gate-por-nome-de-ferramenta-falha-aberto`):
a fix applied in N copies, copy N+1 is born without it.

This test is the radar. The rule is mechanical and derived from the frontmatter, not from a
fixed list: **if the agent has `Task` in its tools, it delegates; if it delegates, it needs
the section.** A fixed list would age exactly as the 10 specs aged.

## The exception of the unattended run

On 2026-10-19 the section gained the exception for the unattended run (`cepa-until`, `claude -p`): there the
lead is a subagent of the orchestrator, and ending the turn does not wait for the notification, it returns the item
to the orchestrator with the worker still running. Measurement in run `until/2026-10-15-1946`: 10
hand resumptions in 5 of 7 rounds. The fourth mark (`run_in_background: false`) keeps the
exception from getting lost in a copy.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TITLE = "## Delegation is asynchronous"

# What the section has to say, beyond existing. Each mark is one of the three things
# the lead needs to know; a section that lost any of them stopped teaching.
# The specs break lines in the middle of sentences, so each mark tolerates whitespace
# wherever there is a space — match with `\s+` and not with a literal " ".
MARKS = [
    ("o retorno real da chamada", re.compile(r"Async\s+agent\s+launched\s+successfully")),
    ("o que fazer no lugar", re.compile(r"[Ee]nd\s+the\s+turn")),
    ("o antipadrão medido", re.compile(r"until\s+\[\s+-f")),
    ("a exceção do run desatendido", re.compile(r"run_in_background:\s*false")),
]


def delegates(text: str) -> bool:
    """The agent declares `Task` in the `tools:` field of the frontmatter."""
    m = re.search(r"^tools:.*$", text, flags=re.M)
    return bool(m) and re.search(r"\bTask\b", m.group(0)) is not None


def main():
    specs = sorted(REPO.glob("*/agents/*.md"))
    if not specs:
        print(f"FAIL: nenhum */agents/*.md sob {REPO}", file=sys.stderr)
        return 1

    delegators = [p for p in specs if delegates(p.read_text(encoding="utf-8"))]
    if not delegators:
        print("FAIL: nenhum agente com Task encontrado — o detector quebrou, "
              "não o repo", file=sys.stderr)
        return 1

    fails = []
    for p in delegators:
        text = p.read_text(encoding="utf-8")
        rel = p.relative_to(REPO)
        if TITLE not in text:
            fails.append(f"{rel}: delega (tem Task) e NÃO tem a seção "
                          f"'{TITLE}'")
            continue
        for name, mark in MARKS:
            if not mark.search(text):
                fails.append(f"{rel}: tem a seção mas perdeu {name} "
                              f"({mark.pattern})")

    for f in fails:
        print("FAIL:", f, file=sys.stderr)
    if fails:
        print(f"\n{len(fails)} falha(s) em {len(delegators)} agentes que delegam.\n"
              "Todo agente com `Task` precisa da seção — copie de "
              "build-hex/agents/engineering-lead.md.", file=sys.stderr)
        return 1

    print(f"ok — {len(delegators)} agentes que delegam, todos com a seção completa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
