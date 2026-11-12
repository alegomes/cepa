#!/usr/bin/env python3
"""The table of modes has a single source, and it cannot diverge from `cepa`.

No external dependency — run with `python3 tests/test_modes_single_source.py`.

## Why it exists

The definition of the working modes was in three places: the list of valid
names in `common/bin/cepa` (`MODES=`), the exit conditions in
`common/hooks/session-mode.py`, and the prose in `docs/modos-de-trabalho.md`. Three
copies of the same table is exactly the pattern this repo has already paid dearly for — the
memory `hooks-texto-citado-nao-e-shell` records 7 copies of the same parser with the
fix applied to 5.

The table became `common/hooks/_modes.py`. This test guarantees that it and `cepa`
keep talking about the same modes: a new mode accepted by `--mode` but absent from
the table starts a session whose hook cannot say when it closes, and a mode in the
table that `cepa` refuses is documentation of something nobody can use.

It also checks that each mode has the five fields filled: purpose,
entry, produces, exit and gate. The purpose is what the `cepa` menu help
shows — a mode without it goes back to being chosen by name. A mode without an exit
condition is a label, not a boundary — which is the whole thesis of
`docs/modos-de-trabalho.md`.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "common" / "hooks"))

FIELDS = ("purpose", "entry", "produces", "exit", "gate")


def cepa_modes():
    """The list that `cepa --mode` accepts, read from the shell script."""
    text = (REPO / "common" / "bin" / "cepa").read_text(encoding="utf-8")
    m = re.search(r'^MODES="([^"]+)"', text, flags=re.M)
    if not m:
        return None
    return m.group(1).split()


# --- menus of the modes (CS-10, modos-opinativos) ----------------------
# A menu that cites a command the repo does not ship sends the owner to an
# "unknown command"; a `needs` outside the three closed kinds is a filter
# `cepa-modes --menu` does not know how to evaluate.
WITH_MENU = ("construction", "discovery", "exploration")
NEEDS_KINDS = ("file:", "topology:", "plugin:")
COMMAND_RE = re.compile(r"^/([a-z0-9-]+):([a-z0-9-]+)(?:\s|$)")


def menu_failures(modes, repo=REPO):
    failures = []
    for name, d in modes.items():
        actions = d["actions"]
        if not isinstance(actions, list):
            failures.append(f"`{name}`: `actions` deveria ser lista, é {type(actions).__name__}")
            continue
        # variants share a `label` and the menu shows only the first that
        # passes, so what the owner sees is one line per distinct label
        shown = len({a.get("label") for a in actions})
        if name in WITH_MENU:
            if not 3 <= shown <= 8:
                failures.append(f"`{name}`: menu com {shown} ação(ões) distintas; "
                                f"o combinado é de 3 a 8")
        elif actions:
            failures.append(f"`{name}`: deveria ter menu vazio, tem {len(actions)} ação(ões)")
        for i, a in enumerate(actions, 1):
            where = f"`{name}` ação {i}"
            label = a.get("label")
            if not isinstance(label, str) or not label.strip():
                failures.append(f"{where}: sem frase leiga (`label`)")
            command = a.get("command")
            if command is None:
                if "(no command yet)" not in (label or ""):
                    failures.append(f"{where}: sem comando e a frase não diz "
                                    f"\"(no command yet)\"")
                commands = []
            elif isinstance(command, str):
                commands = [command]
            elif isinstance(command, list) and command:
                commands = command
            else:
                failures.append(f"{where}: `command` deveria ser str, lista de str ou None")
                commands = []
            for c in commands:
                m = COMMAND_RE.match(c) if isinstance(c, str) else None
                if not m:
                    failures.append(f"{where}: comando {c!r} fora do formato /<plugin>:<nome>")
                    continue
                plugin, cmd = m.groups()
                if not (repo / plugin / "commands" / f"{cmd}.md").is_file():
                    failures.append(f"{where}: `/{plugin}:{cmd}` não existe "
                                    f"({plugin}/commands/{cmd}.md ausente)")
            for need in a.get("needs", []) or []:
                if not (isinstance(need, str) and need.startswith(NEEDS_KINDS)
                        and need.split(":", 1)[1].strip()):
                    failures.append(f"{where}: requisito {need!r} fora dos tipos "
                                    f"file:, topology:, plugin:")
    return failures


# --- the doc keeps "mode is not routine" while describing the menu (CS-11) --
# The menu offers the mode's routines; it must not undo the rule that a session
# is one mandatory mode plus at most one routine. The paragraph lives INSIDE the
# section, so a reader who only reads that section learns both things.
DOC = REPO / "docs" / "modos-de-trabalho.md"
RULE = "Uma sessão = um modo obrigatório + no máximo uma rotina"


def doc_section(text, title="## Modo não é Rotina"):
    start = text.find(title)
    if start < 0:
        return None
    end = text.find("\n## ", start + len(title))
    return text[start:] if end < 0 else text[start:end]


def doc_failures(text):
    section = doc_section(text)
    if section is None:
        return ["docs/modos-de-trabalho.md: seção \"Modo não é Rotina\" sumiu"]
    failures = []
    if RULE not in section:
        failures.append(f"docs/modos-de-trabalho.md: a seção \"Modo não é Rotina\" "
                        f"perdeu a frase \"{RULE}\"")
    paragraphs = [p for p in section.split("\n\n")
                  if "`actions`" in p and "cepa-modes --menu" in p]
    if not paragraphs:
        failures.append("docs/modos-de-trabalho.md: a seção \"Modo não é Rotina\" "
                        "não tem parágrafo que cite o campo `actions` e o comando "
                        "`cepa-modes --menu`")
    return failures


# --- `/common:modes --exit` is a declared argument and reaches cepa-modes (CS-12)
# `cepa-modes --exit` exists; the slash command must advertise it in its header
# (`argument-hint:`, what the picker shows) and keep forwarding `$ARGUMENTS`
# verbatim to the script, otherwise `/common:modes --exit` is undiscoverable or
# silently dropped.
COMMAND = REPO / "common" / "commands" / "modes.md"


def command_failures(text):
    failures = []
    header = text.split("\n---", 1)[0] if text.startswith("---") else ""
    hint = next((l for l in header.splitlines() if l.startswith("argument-hint:")), None)
    if hint is None:
        failures.append("common/commands/modes.md: cabeçalho sem linha `argument-hint:`")
    elif "--exit" not in hint:
        failures.append("common/commands/modes.md: `argument-hint:` não declara `--exit` "
                        f"({hint.strip()!r})")
    runs = [l for l in text.splitlines() if "bin/cepa-modes" in l and "python3" in l]
    if not runs:
        failures.append("common/commands/modes.md: nenhum passo roda `cepa-modes`")
    elif not any(l.rstrip().endswith("$ARGUMENTS") for l in runs):
        failures.append("common/commands/modes.md: o passo que roda `cepa-modes` "
                        "não repassa `$ARGUMENTS` como veio")
    return failures


def main():
    try:
        from _modes import MODES, EXIT
    except ImportError as e:
        print(f"FAIL: não consegui importar common/hooks/_modes.py ({e})", file=sys.stderr)
        return 1

    failures = []

    from_cepa = cepa_modes()
    if from_cepa is None:
        failures.append("não achei `MODES=\"...\"` em common/bin/cepa — o detector "
                      "quebrou, não o repo")
    else:
        only_in_cepa = [m for m in from_cepa if m not in MODES]
        only_in_table = [m for m in MODES if m not in from_cepa]
        for m in only_in_cepa:
            failures.append(f"`{m}` é aceito pelo `cepa --mode` e NÃO está em "
                          f"_modes.py — sessão que não sabe quando fecha")
        for m in only_in_table:
            failures.append(f"`{m}` está em _modes.py e o `cepa --mode` RECUSA — "
                          f"documentação de algo inusável")
        if from_cepa == list(MODES) and not failures:
            pass  # the order matches too; not a requirement, but a good sign

    for name, d in MODES.items():
        for field in FIELDS:
            if not (d.get(field) or "").strip():
                failures.append(f"`{name}`: campo `{field}` vazio — modo sem "
                              f"{field} não é fronteira")

    if set(EXIT) != set(MODES):
        failures.append("EXIT e MODES discordam — EXIT é derivado, alguém o "
                      "reescreveu à mão")

    # --- English interface (item `interface-in-english`) ----------------
    new_names = ["exploration", "discovery", "design", "construction",
                   "refactor", "reflection", "documentation"]
    if list(MODES) != new_names:
        failures.append(f"os modos deveriam ser {new_names}, são {list(MODES)}")
    if from_cepa is not None and from_cepa != new_names:
        failures.append(f"`MODES=` do cepa deveria ser {new_names}, é {from_cepa}")
    from _modes import OLD_TO_NEW_MODE, normalize_mode
    for old, new in (("exploracao", "exploration"), ("descoberta", "discovery"),
                        ("design", "design"), ("construcao", "construction"),
                        ("reforma", "refactor"), ("reflexao", "reflection"),
                        ("documentacao", "documentation")):
        if normalize_mode(old) != new or OLD_TO_NEW_MODE.get(old) != new:
            failures.append(f"o nome antigo `{old}` deveria virar `{new}`")
        if normalize_mode(new) != new:
            failures.append(f"o nome novo `{new}` deveria ficar como está")
    # alias: the old script `cepa-modos` prints the same as `cepa-modes`
    bindir = REPO / "common" / "bin"
    for args in (["--json"], ["--purposes", "--no-color"], ["refactor", "--no-color"],
                 ["reforma", "--no-color"], ["--propositos", "--sem-cor"]):
        new = subprocess.run([sys.executable, str(bindir / "cepa-modes"), *args],
                              capture_output=True, text=True, timeout=30)
        old = subprocess.run([sys.executable, str(bindir / "cepa-modos"), *args],
                               capture_output=True, text=True, timeout=30)
        if new.returncode != 0 or not new.stdout.strip():
            failures.append(f"cepa-modes {' '.join(args)} falhou: {new.stderr[:200]}")
        if (new.returncode, new.stdout) != (old.returncode, old.stdout):
            failures.append(f"o atalho cepa-modos {' '.join(args)} não imprime o mesmo que cepa-modes")
    # the shortcut also runs as a direct executable (not only via `python3`)
    direct = subprocess.run([str(bindir / "cepa-modos"), "--purposes", "--no-color"],
                            capture_output=True, text=True, timeout=30)
    if direct.returncode != 0 or "construction" not in direct.stdout:
        failures.append("o atalho cepa-modos não roda como executável direto")

    failures.extend(menu_failures(MODES))
    failures.extend(doc_failures(DOC.read_text(encoding="utf-8")))
    failures.extend(command_failures(COMMAND.read_text(encoding="utf-8")))

    for f in failures:
        print("FAIL:", f, file=sys.stderr)
    if failures:
        print(f"\n{len(failures)} falha(s).", file=sys.stderr)
        return 1

    print(f"ok — {len(MODES)} modos, mesma lista no `cepa` e em _modes.py, "
          f"todos com os {len(FIELDS)} campos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
