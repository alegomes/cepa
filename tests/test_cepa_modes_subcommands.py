#!/usr/bin/env python3
"""`cepa modes` says the action by subcommand (CS-7 of reforma-de-nomes).

No external dependency: run with `python3 tests/test_cepa_modes_subcommands.py`.
Exits with code != 0 if anything fails.

`exit [MODE]`, `menu MODE` and `purposes` must print exactly what `--exit`,
`--menu MODE` and `--purposes` print (same stdout, same stderr, same exit
code); the flags keep working; with no subcommand the table is still printed;
no mode is named like a subcommand (it would be shadowed).
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _isolated_telemetry import isolate
isolate()

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin" / "cepa-modes"
LAUNCHER = REPO / "common" / "bin" / "cepa"
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _modes as M  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


TMP = Path(tempfile.mkdtemp(prefix="cepa-modes-sub-test-"))
subprocess.run(["git", "init", "-q", "-b", "main", str(TMP)], check=True)
ENV = {**os.environ, "NO_COLOR": "1", "HOME": str(TMP / "home")}


def modes(*args, bin_=None):
    cmd = [str(LAUNCHER), "modes"] if bin_ == "launcher" else [sys.executable, str(BIN)]
    p = subprocess.run([*cmd, *args], cwd=TMP, env=ENV, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


check("nenhum modo tem nome de subcomando",
      not set(M.MODES) & {"exit", "menu", "purposes"}, list(M.MODES))

PAIRS = [
    (["exit", "exploration"], ["--exit", "exploration"]),
    (["exit", "design"], ["--exit", "design"]),       # no mechanical verdict: rc 2
    (["exit"], ["--exit"]),                           # no declared mode: rc 2
    (["menu", "discovery"], ["--menu", "discovery"]),
    (["menu", "discovery", "--json"], ["--menu", "discovery", "--json"]),
    (["--json", "menu", "discovery"], ["--json", "--menu", "discovery"]),
    (["menu", "nope"], ["--menu", "nope"]),           # unknown mode: rc 2
    (["purposes"], ["--purposes"]),
    (["purposes", "--json"], ["--purposes", "--json"]),
    (["--no-color", "purposes"], ["--no-color", "--purposes"]),
]
for new, old in PAIRS:
    rn, rold = modes(*new), modes(*old)
    check(f"`cepa modes {' '.join(new)}` == `{' '.join(old)}` (stdout, stderr, rc)",
          rn == rold, f"{rn} != {rold}")

rc, out, _ = modes("menu", "discovery")
check("`menu discovery` imprime um menu numerado", rc == 0 and out.startswith("1) "), out)
rc, out, _ = modes("purposes")
check("`purposes` imprime uma linha por modo", rc == 0 and all(m in out for m in M.MODES), out)
rc, out, _ = modes("exit", "exploration")
check("`exit exploration` imprime o veredito (aberto = 1)",
      rc == 1 and "Saída da exploração" in out, f"{rc} {out}")
rc, out, err = modes("exit", "design")
check("`exit design` sai 2 (sem veredito mecânico)", rc == 2, f"{rc} {out} {err}")

# the flags and the table keep working
rc, out, _ = modes()
check("`cepa modes` sem subcomando imprime a tabela", rc == 0 and "Modos de trabalho" in out)
rc, out, _ = modes("exploration")
check("`cepa modes exploration` imprime só um modo",
      rc == 0 and "exploration" in out and "discovery" not in out, out)
check("`--saida`/`--propositos` (nomes antigos) seguem aceitos",
      modes("--propositos")[0] == 0 and modes("--saida", "design")[0] == 2)
rc, out, _ = modes("--json")
check("`--json` segue imprimindo a tabela em JSON", rc == 0 and out.lstrip().startswith("{"))

# help of each subcommand, and of the whole command
for sub in ("exit", "menu", "purposes"):
    outs = [modes(sub, w) for w in ("--help", "-h", "help")]
    rc, out, _ = outs[0]
    check(f"`{sub} --help` sai 0 e abre com `usage: cepa modes {sub}`",
          rc == 0 and out.startswith(f"usage: cepa modes {sub}"), out)
    check(f"`{sub} --help`, `-h` e `help` imprimem o mesmo",
          outs[0] == outs[1] == outs[2])
    check(f"`{sub} --help` não traz o menu de subcomandos do comando todo",
          "SUBCOMMAND is one of" not in out)
rc, out, _ = modes("--help")
check("`cepa modes --help` mostra as formas com subcomando como principais",
      rc == 0 and "cepa modes exit" in out and "cepa modes menu discovery" in out
      and "cepa modes purposes" in out and "still accepted" in out, out)

rc, out, _ = modes("menu", "discovery", bin_="launcher")
check("`cepa modes menu discovery` pelo lançador", rc == 0 and out.startswith("1) "), out)

# --- proof survivors: --sem-cor before the subcommand, and the pinned help ---
for new, old in ((["--sem-cor", "purposes"], ["--purposes", "--no-color"]),
                 (["--sem-cor", "exit", "exploration"], ["--exit", "exploration"]),
                 (["--sem-cor", "menu", "discovery"], ["--menu", "discovery"])):
    rn, ro = modes(*new), modes(*old)
    check(f"`cepa modes {' '.join(new)}` == `{' '.join(old)}` (stdout, stderr, rc)",
          rn == ro and rn[0] in (0, 1), f"{rn} != {ro}")


def section(text, title):
    lines = text.splitlines()
    if f"{title}:" not in lines:
        return None
    out = []
    for l in lines[lines.index(f"{title}:") + 1:]:
        if not l.strip():
            break
        out.append(l.strip())
    return out


MODE_HELP = {  # subcommand: (usage line, summary, positional help or None, --json?, exits)
    "exit": ("usage: cepa modes exit [MODE]",
             "The exit verdict of this session's mode (or of MODE), read from disk.",
             "the work mode (default: the mode of this session)", False,
             {"0": "the mode is closed", "1": "the mode is still open",
              "2": "no mode declared in this tree, unknown mode, or no mechanical verdict here"}),
    "menu": ("usage: cepa modes menu MODE [--json]",
             "The numbered menu of common actions of MODE, filtered by this repo.",
             "the work mode", True, {"0": "ok", "2": "unknown mode"}),
    "purposes": ("usage: cepa modes purposes",
                 "One line per mode: what it is for.", None, False, {"0": "ok"}),
}
for sub, (usage, summary, pos, has_json, exits) in MODE_HELP.items():
    out = modes(sub, "--help")[1]
    lines = out.splitlines()
    check(f"ajuda de `{sub}`: usage", lines[0] == usage, lines[:1])
    check(f"ajuda de `{sub}`: resumo", summary in lines, out)
    args = section(out, "arguments")
    if pos:
        check(f"ajuda de `{sub}`: posicional MODE",
              args is not None and len(args) == 1 and args[0].split()[0] == "MODE"
              and pos in " ".join(args[0].split()), args)
    else:
        check(f"ajuda de `{sub}`: sem posicional", args is None, args)
    opts = " ".join(section(out, "options") or [])
    check(f"ajuda de `{sub}`: --json {'aparece' if has_json else 'não aparece'}",
          ("--json" in opts) == has_json, opts)
    if has_json:
        check(f"ajuda de `{sub}`: frase do --json",
              any(l.startswith("--json") and l.endswith("the list as JSON, for code")
                  for l in section(out, "options") or []), out)
    got = {}
    for l in section(out, "exit codes") or []:
        code, _, meaning = l.partition("  ")
        got[code] = meaning.strip()
    check(f"ajuda de `{sub}`: códigos de saída", got == exits, f"{got} vs {exits}")
    check(f"ajuda de `{sub}`: exemplos com `cepa modes {sub}`",
          any(l.startswith(f"cepa modes {sub}") for l in section(out, "examples") or []), out)

main_help = modes("--help")[1]
for frag in ("  menu MODE  the mode's menu of common actions",
             "  exit [MODE]  the exit verdict of this session's mode (or of MODE)",
             "  purposes   one line per mode: what it is for",
             "The flag forms --menu MODE, --exit and --purposes are still accepted.",
             "  cepa modes purposes", "  cepa modes exit", "  cepa modes menu discovery"):
    check(f"`cepa modes --help` traz: {frag.strip()[:34]}", frag in main_help, main_help)

if FAILURES:
    print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
    sys.exit(1)
print("\ntudo ok")
