#!/usr/bin/env python3
"""The 4 path-locked agents say Auto Mode does not apply to them.

No dependencies — run with `python3 tests/test_auto_mode_does_not_cover_path_lock.py`.
Exits non-zero on failure.

## The hole this file locks

Claude Code's Auto Mode / bypass-permissions mode injects into the session the
directive "do the work through Bash: edit with sed, heredocs or short scripts
instead of Edit/Write". The agents domain-dev, api-dev, adapter-dev and
qa-engineer are contained by `path-lock.py` (looks at Edit/Write by glob) and
`bash-path-lock.py` (denies shell writes by default). Following the directive is
getting around the lock: in the drain of 2026-08-20 three agents spent the report
explaining why they disobeyed and a qa-engineer got around the lock with a python
heredoc. The cheap fix (front 1 of the BACKLOG) is the agent's own prompt
saying the preference does not apply to it.

## Perturbation (how to know this test proves something)

Delete the bullet "The Auto Mode preference for Bash does not apply to you" from one
of the four files in `build-hex/agents/`: that file's case turns
red and the script exits with code 1.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FAILURES = []

SENTENCE = "The Auto Mode preference for Bash does not apply to you"
AGENTS = ("domain-dev", "api-dev", "adapter-dev", "qa-engineer")


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(label)
        print(f"FAIL  {label}  {detail}")


def test_locked_agents_say_auto_mode_does_not_count():
    for name in AGENTS:
        rel = f"build-hex/agents/{name}.md"
        txt = (REPO / rel).read_text(encoding="utf-8")
        check(f"{rel} diz que a preferência do Auto Mode por Bash não se aplica",
              SENTENCE in txt)


def main():
    test_locked_agents_say_auto_mode_does_not_count()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s)")
        return 1
    print("tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
