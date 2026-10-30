#!/usr/bin/env python3
"""The description of the common plugin in the marketplace cites every common command.

No third-party dependency — run with `python3 tests/test_marketplace_common_description.py`.
Exits non-zero if any command is missing.

The pain: the catalog guard (test_commands_catalog.py) covered only
docs/commands.md. The description of common in .claude-plugin/marketplace.json
stayed stuck on the mindset skills while the plugin gained /plan, /spec,
/session, /doctor and two more dozen commands (deviations.md 2026-08-25). Whoever
looked at the marketplace storefront did not see half of what the plugin delivers.

`/<command>` counts with a word boundary: the character after the name cannot
be [A-Za-z0-9_-], so `/plan` does not count through `/plan-x` nor `/worktree-list`
through `/worktree`.

An optional argument points to another marketplace.json (used to show the
test red against the old description).
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARKETPLACE = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / ".claude-plugin" / "marketplace.json"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def commands(repo):
    """Every stem of common/commands/*.md."""
    return [a.stem for a in sorted((repo / "common" / "commands").glob("*.md"))]


def missing(stems, description):
    """The commands that the description does not cite as a whole `/<stem>`."""
    return [
        s for s in stems
        if not re.search(r"(?<![A-Za-z0-9_-])/" + re.escape(s) + r"(?![A-Za-z0-9_-])", description)
    ]


def common_description(file_path):
    for p in json.loads(file_path.read_text())["plugins"]:
        if p["name"] == "common":
            return p["description"]
    return None


def main():
    stems = commands(REPO)
    description = common_description(MARKETPLACE)

    check("a varredura acha comandos", len(stems) > 20, f"achou {len(stems)}")
    check("o marketplace tem a entrada do common", description is not None)
    description = description or ""

    outside = missing(stems, description)
    check("todo comando do common está na descrição", not outside,
          "fora da descrição: " + ", ".join("/" + s for s in outside))

    # The test has to be able to turn red.
    target = "worktree-list"
    without_target = description.replace("/" + target, "")
    check("tirar um comando da descrição faz ele faltar",
          missing([target], without_target) == [target])
    check("prefixo de outro comando não conta",
          missing(["plan"], "cobre /plan-x e /planner") == ["plan"]
          and missing(["worktree-list"], "cobre /worktree e /worktree-listar") == ["worktree-list"])
    check("o comando com pontuação em volta conta",
          missing(["plan"], "(/plan, /spec).") == [])

    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print(f"\ntudo ok ({len(stems)} comandos na descrição)")


if __name__ == "__main__":
    main()
