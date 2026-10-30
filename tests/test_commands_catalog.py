#!/usr/bin/env python3
"""Every command that exists is in docs/commands.md.

No third-party dependency — run with `python3 tests/test_commands_catalog.py`.
Exits non-zero on the first sweep with a failure.

The pain: eight commands (spec, session, doctor, metrics, advisors, consolidate,
prove-ui, decide) vanished from the catalog without any test flickering, because nothing
related the `*/commands/*.md` files to the doc's tables. Fixing the
list by hand fixes today's symptom; this test prevents tomorrow's. In the
check of 2026-09-25 three others were already out (the two build-solo
flows and /common:until-review) — the symptom comes back on its own.

The published name comes from the `name` in `.claude-plugin/plugin.json`, not from the
folder name: the `docs-topology/` folder publishes `/docs:*`.

A command that is internal on purpose goes into INTERNAL with the reason written — the exception
stays in the test, never as a silent omission in the doc.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "docs" / "commands.md"

# "/plugin:command" → why it is not in the catalog. Empty today.
INTERNAL = {}

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def commands(repo):
    """Every `/plugin:command` the repo publishes."""
    findings = []
    for file in sorted(repo.glob("*/commands/*.md")):
        manifest = file.parent.parent / ".claude-plugin" / "plugin.json"
        if not manifest.exists():
            continue
        plugin = json.loads(manifest.read_text())["name"]
        findings.append(f"/{plugin}:{file.stem}")
    return findings


def lacking(cmds, text):
    """The commands without their own line in a catalog table.

    Only the line `| `/plugin:command` | argument | what it does |` counts. A loose
    mention in prose ("see also /x:y") does not document the command: the
    proof gate showed that, counting any citation, deleting the table
    line and leaving the mention passed green — and that is how /common:spec
    was left with only the Part 1 line.
    """
    # An HTML comment disappears on rendering, and a code block becomes raw text:
    # a table line inside either is not a catalog line.
    visible = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    visible = re.sub(r"^(```|~~~).*?^\1[^\n]*$", "", visible, flags=re.S | re.M)
    return [
        c for c in cmds
        if c not in INTERNAL
        and not re.search(r"^\|\s*`" + re.escape(c) + r"`\s*\|", visible, re.M)
    ]


def main():
    cmds = commands(REPO)
    text = CATALOG.read_text()

    check("a varredura acha comandos", len(cmds) > 20, f"achou {len(cmds)}")
    check("a pasta docs-topology publica /docs:*",
          any(c.startswith("/docs:") for c in cmds),
          "nome do plugin não veio do plugin.json")

    outside = lacking(cmds, text)
    check("todo comando está em docs/commands.md", not outside,
          "fora do catálogo: " + ", ".join(outside))

    ghosts = [c for c in INTERNAL if c not in cmds]
    check("toda exceção em INTERNOS ainda existe", not ghosts,
          "exceção para comando que sumiu: " + ", ".join(ghosts))

    # The test has to be able to go red: removing a line accuses it,
    # a prefix is not worth the whole command (/common:plan does not cover
    # /common:plan-x) and a mention outside a table is not worth the line.
    target = "/common:until-review"
    without_line = "\n".join(l for l in text.splitlines() if target not in l)
    check("tirar a linha de um comando faz ele faltar",
          lacking([target], without_line) == [target])
    check("prefixo de outro comando não conta como linha",
          lacking(["/common:plan-x"], "| `/common:plan-xyz` | a | b |") == ["/common:plan-x"]
          and lacking(["/common:plan"], "| `/common:plan-x` | a | b |") == ["/common:plan"])
    check("menção solta em prosa não conta como linha do catálogo",
          lacking([target], f"veja também `{target}` para isso.\n- `{target}`. faz algo")
          == [target])
    check("linha dentro de comentário HTML não conta",
          lacking([target], f"<!--\n| `{target}` | `[x]` | faz algo |\n-->") == [target])
    check("linha dentro de bloco de código não conta",
          lacking([target], f"```\n| `{target}` | `[x]` | faz algo |\n```") == [target]
          and lacking([target], f"~~~md\n| `{target}` | `[x]` | faz algo |\n~~~") == [target])
    check("bloco de código antes não engole a tabela depois dele",
          lacking([target], f"```\nx\n```\n| `{target}` | `[x]` | faz algo |") == [])
    check("a linha da tabela conta",
          lacking([target], f"| `{target}` | `[x]` | faz algo |") == [])

    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print(f"\ntudo ok ({len(cmds)} comandos no catálogo)")


if __name__ == "__main__":
    main()
