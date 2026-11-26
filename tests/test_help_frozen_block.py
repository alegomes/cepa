#!/usr/bin/env python3
"""What is frozen shows up in a "frozen" block at the end of the help.

No third-party deps — run with `python3 tests/test_help_frozen_block.py`.

reforma-de-nomes, CS-9 (docs/spec/reforma-de-nomes-dos-comandos.md, P7): the
Maestro has been frozen since 2026-10-08, and `cepa dor` and `cepa hotspots`
only serve its wave plans. Before this, `cepa help` listed `dor` and `hotspots`
in alphabetical order among the current subcommands, and docs/commands.md and
docs/cepa-cli.md mixed the three in with everything else. The contract:

  - `cepa help` (and its no-python3 fallback) lists `dor` and `hotspots` after
    a `frozen:` line and after every other subcommand;
  - docs/commands.md and docs/cepa-cli.md end in a `## Frozen` section that
    holds `/maestro:*`, `cepa dor` and `cepa hotspots`, and neither appears in
    a table row or reference heading before that section.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin"
CEPA = BIN / "cepa"
FROZEN = ["dor", "hotspots"]
SHIMS = {"plan", "until", "until-digest"}
MAESTRO = ["/maestro:program-plan", "/maestro:run", "/maestro:resume"]

FAILURES = []
ENV = {k: v for k, v in os.environ.items() if k not in ("CEPA_COLOR", "NO_COLOR")}
ENV["COLUMNS"] = "100"


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {str(detail)[-600:]}")
        FAILURES.append(name)


def current():
    return sorted(p.name[len("cepa-"):] for p in BIN.glob("cepa-*")
                  if os.access(p, os.X_OK)
                  and p.name[len("cepa-"):] not in SHIMS | set(FROZEN))


def block(text):
    """The lines of the `subcommands:` block, up to the first blank line."""
    m = re.search(r"^subcommands:\n(.*?)(?:\n\n|\Z)", text, re.S | re.M)
    return m.group(1).splitlines() if m else []


def check_help(label, text):
    lines = block(text)
    names = [m.group(1) for m in (re.match(r"^  ([a-z][\w-]*)\s{2,}\S", l) for l in lines) if m]
    marks = [i for i, l in enumerate(lines) if l.strip() == "frozen:"]
    check(f"{label}: one `frozen:` line in the subcommands block", len(marks) == 1, lines)
    if len(marks) != 1:
        return
    before = [m.group(1) for m in (re.match(r"^  ([a-z][\w-]*)\s{2,}\S", l)
                                   for l in lines[:marks[0]]) if m]
    after = [m.group(1) for m in (re.match(r"^  ([a-z][\w-]*)\s{2,}\S", l)
                                  for l in lines[marks[0] + 1:]) if m]
    check(f"{label}: dor and hotspots come after the `frozen:` line",
          after == FROZEN, after)
    check(f"{label}: every other subcommand comes before it, in order",
          before == current(), (before, current()))
    check(f"{label}: the frozen ones are the last rows of the block",
          names[-len(FROZEN):] == FROZEN, names)


def test_cepa_help():
    p = subprocess.run([str(CEPA), "help"], capture_output=True, text=True,
                       timeout=60, env=ENV, cwd=REPO)
    check("cepa help: exit 0", p.returncode == 0, p.stderr)
    check_help("cepa help", p.stdout)


def test_fallback_help():
    """Without common/hooks/_clihelp.py next to it, the launcher prints its
    plain-text help; it follows the same rule."""
    with tempfile.TemporaryDirectory() as tmp:
        bindir = Path(tmp) / "bin"
        bindir.mkdir()
        shutil.copy2(CEPA, bindir / "cepa")
        for script in BIN.glob("cepa-*"):
            (bindir / script.name).symlink_to(script)
        p = subprocess.run([str(bindir / "cepa"), "help"], capture_output=True,
                           text=True, timeout=60, env=ENV, cwd=tmp)
    check("cepa help (no _clihelp): exit 0", p.returncode == 0, p.stderr)
    check("cepa help (no _clihelp): it is the fallback text",
          "runs common/bin/cepa-<subcommand>" in p.stdout, p.stdout[:300])
    check_help("cepa help (no _clihelp)", p.stdout)


def sections(text):
    """`## ` sections of a markdown file, outside code blocks: [(title, body)]."""
    visible = re.sub(r"^(```|~~~).*?^\1[^\n]*$", "", text, flags=re.S | re.M)
    parts = re.split(r"^## (.+)$", visible, flags=re.M)
    return list(zip(parts[1::2], parts[2::2])), parts[0]


def check_doc(name, needles, ref_headings=()):
    text = (REPO / "docs" / name).read_text()
    secs, head = sections(text)
    check(f"{name}: the last `## ` section is `Frozen`",
          bool(secs) and secs[-1][0].strip() == "Frozen", [t for t, _ in secs][-3:])
    if not secs or secs[-1][0].strip() != "Frozen":
        return
    frozen = secs[-1][1]
    rest = head + "".join(f"## {t}\n{b}" for t, b in secs[:-1])
    for needle in needles:
        # A row where some cell STARTS with the command; a passing mention in the
        # middle of another command's description does not list it.
        row = re.compile(r"^\|(?:[^|\n]*\|)*?\s*`" + re.escape(needle) + r"[ `]", re.M)
        check(f"{name}: `{needle}` has a table row in Frozen", row.search(frozen),
              frozen[:400])
        check(f"{name}: `{needle}` has no table row before Frozen",
              not row.search(rest), [l for l in rest.splitlines() if row.match(l)])
    for h in ref_headings:
        mark = f"### `{h}`"
        check(f"{name}: `{mark}` lives in Frozen", mark in frozen)
        check(f"{name}: `{mark}` is not before Frozen", mark not in rest)


def test_docs():
    check_doc("commands.md", MAESTRO + ["cepa dor", "cepa hotspots"])
    check_doc("cepa-cli.md", ["/maestro:program-plan", "cepa dor", "cepa hotspots"],
              ref_headings=["cepa-dor", "cepa-hotspots"])
    cli = (REPO / "docs" / "cepa-cli.md").read_text()
    frozen = cli[cli.rfind("\n## Frozen"):] if "\n## Frozen" in cli else ""
    for cmd in MAESTRO:
        check(f"cepa-cli.md: Frozen names `{cmd}`", f"`{cmd}`" in frozen)


if __name__ == "__main__":
    test_cepa_help()
    test_fallback_help()
    test_docs()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        sys.exit(1)
    print("\nall ok")
