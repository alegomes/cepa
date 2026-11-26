#!/usr/bin/env python3
"""The /common:worktree-* family calls its argument `<slice>`.

No third-party deps — run with `python3 tests/test_worktree_slice_placeholder.py`.

reforma-de-nomes, CS-10 (docs/spec/reforma-de-nomes-dos-comandos.md, P8):
`worktree-start` and `worktree-merge` already said `<slice>`, while
`worktree-discard` said `<name>` and `worktree-rename` said `<new-name>` /
`<old-name>` for the same thing. The contract:

  - the `argument-hint` of worktree-start, -merge, -discard, -rename and -label
    never cites `<name>`, `<new-name>` or `<old-name>`;
  - start, merge and discard name `<slice>`; rename names `<new-slice>` and
    `<old-slice>`;
  - the body of every `common/commands/worktree-*.md` uses the same words
    (a hint that says `<slice>` over a body that says `<name>` is the drift
    this item removes);
  - the session-start hints (`session-registry.py`, `session-worktrees.py`)
    and the worktree rows of docs/commands.md say `<slice>` too, since they
    are where the owner reads the usage most often.
"""

import re
import sys
from pathlib import Path

# The test only READS session-registry.py and session-worktrees.py, but the
# sweep in test_isolated_telemetry.py asks every test that cites an emitter
# hook to isolate: citing becomes executing in one commit.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _isolated_telemetry import isolate  # noqa: E402
isolate()

REPO = Path(__file__).resolve().parent.parent
CMDS = REPO / "common" / "commands"
FAMILY = ["worktree-start", "worktree-merge", "worktree-discard",
          "worktree-rename", "worktree-label"]
OLD = ["<name>", "<new-name>", "<old-name>"]
REQUIRED = {
    "worktree-start": ["<slice>"],
    "worktree-merge": ["<slice>"],
    "worktree-discard": ["<slice>"],
    "worktree-rename": ["<new-slice>", "<old-slice>"],
}

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"ok   {name}")
    else:
        print(f"FAIL {name}{': ' + detail if detail else ''}")
        FAILURES.append(name)


def hint(path):
    for line in path.read_text().splitlines():
        m = re.match(r"argument-hint:\s*(.*)", line)
        if m:
            return m.group(1)
    return None


def main():
    for cmd in FAMILY:
        path = CMDS / f"{cmd}.md"
        check(f"{cmd}.md exists", path.is_file())
        if not path.is_file():
            continue
        h = hint(path)
        check(f"{cmd} has an argument-hint", h is not None)
        if h is None:
            continue
        for old in OLD:
            check(f"{cmd} argument-hint does not cite {old}", old not in h, h)
        for new in REQUIRED.get(cmd, []):
            check(f"{cmd} argument-hint names {new}", new in h, h)

    for path in sorted(CMDS.glob("worktree-*.md")):
        text = path.read_text()
        for old in OLD:
            hits = [i + 1 for i, l in enumerate(text.splitlines()) if old in l]
            check(f"{path.name} body does not use {old}", not hits,
                  f"lines {hits}")

    # the hint the hooks print at session start, and the commands reference
    hooks = REPO / "common" / "hooks"
    for path in [hooks / "session-registry.py", hooks / "session-worktrees.py"]:
        text = path.read_text()
        for cmd in ["worktree-merge", "worktree-discard"]:
            uses = re.findall(rf"/common:{cmd} (<[^>]+>)", text)
            check(f"{path.name} cites /common:{cmd} with an argument",
                  bool(uses))
            check(f"{path.name} cites /common:{cmd} <slice>",
                  uses and all(u == "<slice>" for u in uses), str(uses))
    rows = [l for l in (REPO / "docs" / "commands.md").read_text().splitlines()
            if l.startswith("| `/common:worktree-")]
    check("docs/commands.md has the worktree rows", len(rows) >= 6, str(len(rows)))
    for row in rows:
        for old in OLD:
            check(f"docs/commands.md row {row.split('|')[1].strip()} "
                  f"does not use {old}", old not in row, row)

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
