#!/usr/bin/env python3
"""A card read that the session already had does not go back into the specs.

Measured on 2026-09-13 in 30 days of transcripts: 924 card rereads, of
which 277 fetched from Jira something the session already had in hand. Each call to the
atlassian-expert costs a median of ~47 thousand tokens. Three origins were cut:

  - the agent read the status before transitioning or commenting (156 rereads),
    although the list of transitions and the read-back already bring the current state;
  - `/board-flow:prove` (inside prove-drain) and `/board-flow:fix` (coming from
    execute) fetched again the card the previous step had just read;
  - `/board-flow:capture` delegated a second existence check after the
    read-back the agent is already obliged to do.

What must NOT go out together: the read-back after each write and the reservation
read (claim), which need Jira up to date.

Run: python3 tests/test_jira_reread.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BF = REPO / "board-flow"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def read_file(rel):
    return (BF / rel).read_text(encoding="utf-8")


def main():
    agent = read_file("agents/atlassian-expert.md")
    check("agente não lê o card só para olhar antes de escrever",
          "No read just to look before a write" in agent)
    check("agente mantém o read-back depois de cada escrita",
          "Verify every write with a read-back" in agent)
    check("a regra antiga de ler antes de agir saiu",
          "Read, then act" not in agent)

    drain = read_file("commands/prove-drain.md")
    check("claim do prove-drain lê também o que a prova precisa",
          "full text of the latest Implementation Summary" in drain)
    check("prove-drain entrega o conteúdo à prova sem buscar de novo",
          "skip\n     prove's step 1 fetch" in drain or "skip prove's step 1 fetch" in drain)

    prove = read_file("commands/prove.md")
    check("prove reaproveita o card lido pelo claim do prove-drain",
          "Already have the card?" in prove and "prove-drain" in prove)

    fix = read_file("commands/fix.md")
    check("fix reaproveita o card lido pelo execute",
          "Already have the card?" in fix and "/board-flow:execute" in fix)
    execute = read_file("commands/execute.md")
    check("execute entrega o card ao fix",
          "Hand `fix` the card content" in execute and "re-fetches" not in execute)

    capture = read_file("commands/capture.md")
    check("capture não delega segunda checagem de existência",
          "Confirm Jira issue" not in capture)
    check("capture ainda exige o read-back do agente",
          "Apply your read-back verification rule" in capture)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
