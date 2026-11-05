#!/usr/bin/env python3
"""Every help path of `cepa` and the `cepa-*` commands follows one layout.

No third-party deps — run with `python3 tests/test_cepa_help_layout.py`.

Before common/hooks/_clihelp.py each command wrote its own help: `cepa plan
help` was an argparse error while `cepa doctor help` worked, some helps had
examples and exit codes and others did not, Portuguese and English aliases
were mixed. This test walks every command and every subcommand it lists and
checks the contract mechanically:

  - `--help`, `-h` and `help` print the same text and exit 0, at every level;
  - `cepa help <x>` is `cepa-<x> --help`;
  - usage says `cepa <x>`, and every help has examples and exit codes;
  - Portuguese aliases do not show up in the help;
  - a usage error is `✗ cepa <x>: ...`, exit 2, pointing to the full help.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin"
CEPA = BIN / "cepa"
ALIASES = {"intencao", "modos"}
# Old Portuguese names that are aliases of an English one. They must keep
# working but never be listed in a help.
HIDDEN = ["responde", "aterrissados", "ordena", "divergencia", "--proposito",
          "--para-quando", "--plano", "--passo", "--motivo", "--max-falhas",
          "--sujo-ok", "--todas", "--arquivo", "--propositos", "--sem-cor",
          "--ciclo", "--quando", "gravar", "mostrar", "continuar", "estado",
          "encerrar", "decidir", "triar", "--alvo", "--origem"]

FAILURES = []
ENV = {k: v for k, v in os.environ.items() if k not in ("CEPA_COR", "NO_COLOR")}
ENV["COLUMNS"] = "100"


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {str(detail)[-400:]}")
        FAILURES.append(name)


def run(*args):
    return subprocess.run([str(a) for a in args], capture_output=True, text=True,
                          timeout=60, env=ENV, cwd=REPO)


def commands():
    return sorted(p.name[len("cepa-"):] for p in BIN.glob("cepa-*")
                  if os.access(p, os.X_OK) and p.name[len("cepa-"):] not in ALIASES)


def subcommands(text):
    """Names listed under `subcommands:` (one per row, first column)."""
    m = re.search(r"^subcommands:\n(.*?)(?:\n\n|\Z)", text, re.S | re.M)
    if not m:
        return []
    names = []
    for line in m.group(1).splitlines():
        mm = re.match(r"^ {2,4}([a-z][\w-]*)(?:\s{2,}|$)", line)
        if mm and not line.startswith(" " * 6):
            names.append(mm.group(1))
    return names


def same_help(label, argv):
    outs = []
    for word in ("--help", "-h", "help"):
        p = run(*(argv + [word]))
        outs.append(p)
    ref = outs[0]
    check(f"{label}: --help exits 0", ref.returncode == 0, ref.stdout + ref.stderr)
    check(f"{label}: -h and help print the same as --help",
          all(o.returncode == 0 and o.stdout == ref.stdout for o in outs[1:]),
          [o.stdout[:200] + o.stderr[:200] for o in outs[1:]])
    return ref.stdout


def layout(label, text, prog):
    check(f"{label}: usage names `{prog}`", text.startswith(f"usage: {prog}"), text[:200])
    check(f"{label}: has examples", "\nexamples:\n" in text, text[-400:])
    check(f"{label}: has exit codes", "\nexit codes:\n" in text, text[-400:])
    shown = [w for w in HIDDEN if re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", text)]
    check(f"{label}: no Portuguese alias listed", not shown, shown)
    check(f"{label}: no argparse default help line",
          "show this help message and exit" not in text, text)


def test_launcher():
    ref = run(CEPA, "help").stdout
    for flag in ("--help", "-h"):
        check(f"cepa {flag} == cepa help", run(CEPA, flag).stdout == ref)
    layout("cepa", ref, "cepa")
    check("cepa: launcher flags section", "\nlauncher flags:\n" in ref, ref)
    listed = subcommands(ref)
    check("cepa: lists every subcommand", listed == commands(), (listed, commands()))
    p = run(CEPA, "help", "nope")
    check("cepa help <unknown>: exit 2", p.returncode == 2 and "is not a subcommand"
          in p.stderr, p.stderr)


def test_every_command():
    for name in commands():
        script = BIN / f"cepa-{name}"
        text = same_help(f"cepa {name}", [script])
        layout(f"cepa {name}", text, f"cepa {name}")
        via = run(CEPA, "help", name).stdout
        check(f"cepa help {name} == cepa-{name} --help", via == text)
        via = run(CEPA, name, "help").stdout
        check(f"cepa {name} help == cepa-{name} --help", via == text)
        bad = run(script, "--no-such-flag-xyz")
        if name == "doctor":
            continue  # parses argv by hand and ignores unknown flags (by design)
        check(f"cepa {name} --no-such-flag-xyz: exit 2, ✗ line, points to help",
              bad.returncode == 2 and bad.stderr.startswith(f"✗ cepa {name}")
              and f"cepa {name} --help" in bad.stderr, bad.stderr)
        for sub in subcommands(text):
            stext = same_help(f"cepa {name} {sub}", [script, sub])
            layout(f"cepa {name} {sub}", stext, f"cepa {name} {sub}")
            check(f"cepa {name} {sub}: has a summary line",
                  len(stext.split("\n\n")) > 1 and stext.split("\n\n")[1].strip() != "",
                  stext[:300])


def test_color_only_on_request():
    plain = run(BIN / "cepa-hotspots", "--help").stdout
    check("piped help has no escape codes", "\033" not in plain)
    env = dict(ENV, CEPA_COR="sempre")
    p = subprocess.run([str(BIN / "cepa-hotspots"), "--help"], capture_output=True,
                       text=True, env=env, cwd=REPO)
    check("CEPA_COR=sempre colors headings", "\033[" in p.stdout and "── " in p.stdout,
          p.stdout[:300])


def main():
    test_launcher()
    test_every_command()
    test_color_only_on_request()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
