#!/usr/bin/env python3
"""cepa-until — a plugin hook changed on the night branch only takes effect after
landing and reinstalling.

In run 2026-09-28-1146 item 2 fixed `bash-path-lock` and item 1 fixed
`no-background-build`, and the 4 following rounds stayed blocked by the old
versions: hooks run from the plugin installed in the cache (a copy of the clone),
not from the night branch. No round was lost, but nothing in the run said so.

The cases below pin the warning:
  - the item that commits `<plugin>/hooks/...` gets a line on the screen, before the
    next item starts, and a `hook_so_apos_reinstalar` event in the record;
  - the end of the run charges `bin/install.sh` in "Left with you" and in the state;
  - `hooks/` outside a plugin (without `.claude-plugin/plugin.json`) does not warn;
  - a hook that left the branch with the red build is not charged at the end.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, ledger_of, build_repo, run_until)


def with_plugin(root):
    """The test repo becomes a plugin repo: `meuplug/` with plugin.json and a
    hook, and `solto/hooks/` without plugin.json."""
    (root / "meuplug" / ".claude-plugin").mkdir(parents=True)
    (root / "meuplug" / ".claude-plugin" / "plugin.json").write_text("{}")
    (root / "meuplug" / "hooks").mkdir()
    (root / "meuplug" / "hooks" / "trava.py").write_text("v1\n")
    (root / "solto" / "hooks").mkdir(parents=True)
    (root / "solto" / "hooks" / "x.py").write_text("v1\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "plugin"], cwd=root, check=True)
    return root


# The fake `claude` commits the file that FAKE_ARQUIVOS assigns to the item
# (`a1=meuplug/hooks/trava.py;a2=...`), or just `<id>.txt`.
WORKS = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "mapa = dict(p.split('=') for p in "
    "os.environ.get('FAKE_ARQUIVOS', '').split(';') if p)\n"
    "alvo = mapa.get(ident, ident + '.txt')\n"
    "open(alvo, 'a').write(ident + '\\n')\n"
    "if ident in os.environ.get('FAKE_QUEBRA', '').split(','):\n"
    "    open('quebra.txt', 'w').write('x')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', ident], check=True)\n"
    "marca(ident, status='done', evidence='ok')\n")

VERIFY = "test ! -f quebra.txt"


def plan_of(root):
    return root / ".claude" / "programs" / "fila" / "plan.yaml"


def state_of(root):
    d = root / ".claude" / "programs" / "fila" / "until"
    files = sorted(d.glob("*.estado.json"))
    return json.loads(files[-1].read_text()) if files else {}


def warnings(root):
    return [e for e in ledger_of(root)
            if e["evento"] == "hook_so_apos_reinstalar"]


def test_item_that_changes_plugin_hook_is_warned_at_once_and_at_the_end():
    with tempfile.TemporaryDirectory() as tmp:
        root = with_plugin(build_repo(tmp, [item("a1"), item("a2")]))
        binv = fake_claude(tmp, WORKS)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h"],
                    extra_env={"FAKE_ARQUIVOS": "a1=meuplug/hooks/trava.py"})
        ev = warnings(root)
        check("o registro ganha hook_so_apos_reinstalar do a1",
              len(ev) == 1 and ev[0]["id"] == "a1"
              and ev[0]["arquivos"] == ["meuplug/hooks/trava.py"], str(ev))
        out = p.stdout
        i_warning = out.find("a1 changed plugin hook(s) (meuplug/hooks/trava.py)")
        i_a2 = out.find("] a2 — ")
        check("a tela avisa o hook logo depois do a1, antes do a2 começar",
              0 <= i_warning < i_a2, out[-1500:])
        check("...e o aviso diz o que fazer",
              "bin/install.sh" in out[i_warning:i_a2], out[i_warning:i_a2])
        stays = {f["id"]: f["texto"]
                for f in state_of(root).get("fica_com_voce", [])}
        check("o estado do run cobra a reinstalação em fica_com_voce",
              "reinstalar-plugin" in stays
              and "meuplug/hooks/trava.py" in stays["reinstalar-plugin"],
              str(stays))
        check("o resumo do fim traz a reinstalação em Left with you",
              "- reinstalar-plugin:" in out.split("── ended at")[-1], out[-1200:])


def test_hooks_outside_plugin_does_not_warn():
    with tempfile.TemporaryDirectory() as tmp:
        root = with_plugin(build_repo(tmp, [item("a1")]))
        binv = fake_claude(tmp, WORKS)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h"],
                    extra_env={"FAKE_ARQUIVOS": "a1=solto/hooks/x.py"})
        check("pasta hooks/ sem plugin.json não gera aviso",
              not warnings(root) and "mudou hook" not in p.stdout,
              p.stdout[-800:])
        check("...nem cobrança no fim",
              "reinstalar-plugin" not in p.stdout
              and all(f["id"] != "reinstalar-plugin" for f in
                      state_of(root).get("fica_com_voce", [])),
              p.stdout[-800:])


def test_hook_that_left_with_the_red_build_is_not_charged_at_the_end():
    with tempfile.TemporaryDirectory() as tmp:
        root = with_plugin(build_repo(tmp, [item("a1"), item("a2")]))
        binv = fake_claude(tmp, WORKS)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h",
                                                 "--verify", VERIFY],
                    extra_env={"FAKE_ARQUIVOS": "a1=meuplug/hooks/trava.py",
                               "FAKE_QUEBRA": "a1"})
        ev = warnings(root)
        check("o hook do item vermelho não fica na branch, então não avisa",
              not ev, str(ev))
        check("...e o fim não cobra reinstalação",
              "reinstalar-plugin" not in p.stdout, p.stdout[-1200:])


# 1st attempt of a1: commits the hook and leaves `pending` (a commit is progress, the
# supervisor warns about the hook). 2nd: commits `quebra.txt` and closes `done`; the red
# build takes the commits of BOTH attempts to the side branch. After that
# a1 leaves `blocked` so the run can end.
WARNS_AND_EXITS = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "cont = os.environ['FAKE_CHAMADAS'] + '.vez'\n"
    "vez = (int(open(cont).read()) if os.path.exists(cont) else 0) + 1\n"
    "open(cont, 'w').write(str(vez))\n"
    "def commita(alvo):\n"
    "    open(alvo, 'a').write(str(vez) + '\\n')\n"
    "    subprocess.run(['git', 'add', '-A'], check=True)\n"
    "    subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                    'commit', '-qm', f'{ident} {vez}'], check=True)\n"
    "if vez == 1:\n"
    "    commita('meuplug/hooks/trava.py')\n"
    "elif vez == 2:\n"
    "    commita('quebra.txt')\n"
    "    marca(ident, status='done', evidence='ok')\n"
    "else:\n"
    "    marca(ident, status='blocked', evidence='fim do teste')\n")


def test_warned_hook_that_left_later_is_not_charged_at_the_end():
    with tempfile.TemporaryDirectory() as tmp:
        root = with_plugin(build_repo(tmp, [item("a1")]))
        binv = fake_claude(tmp, WARNS_AND_EXITS)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h",
                                                 "--verify", VERIFY])
        check("a 1ª tentativa deixou o hook na branch e a tela avisou",
              len(warnings(root)) == 1, str(warnings(root)))
        check("o build vermelho da 2ª levou o hook para a lateral",
              "vermelho-a1" in p.stdout, p.stdout[-1500:])
        check("o fim recalcula e não cobra o hook que saiu",
              "reinstalar-plugin" not in p.stdout
              and all(f["id"] != "reinstalar-plugin" for f in
                      state_of(root).get("fica_com_voce", [])),
              p.stdout[-1500:])


# Attempts per item, like TRIES of test_cepa_until_run_branch: attempt
# n commits `<id>-t<n>.txt`; FAKE_HOOK1 puts the hook in the 1st attempt,
# FAKE_HOOK2 in the 2nd; FAKE_QUEBRA breaks the build from the 2nd on; FAKE_DUAS
# leaves the 1st `pending` (and FAKE_ADIA throws it to the end of the queue).
TRIES = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "lista = lambda k: os.environ.get(k, '').split(',')\n"
    "cont = os.environ['FAKE_CHAMADAS'] + '.n.' + ident\n"
    "n = int(open(cont).read()) + 1 if os.path.exists(cont) else 1\n"
    "open(cont, 'w').write(str(n))\n"
    "open(f'{ident}-t{n}.txt', 'w').write('x')\n"
    "if ident in lista(f'FAKE_HOOK{n}'):\n"
    "    open('meuplug/hooks/trava.py', 'a').write(f'{ident}-t{n}\\n')\n"
    "if n >= 2 and ident in lista('FAKE_QUEBRA'):\n"
    "    open('quebra.txt', 'w').write('x')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', f'{ident}-t{n}'], check=True)\n"
    "if ident not in lista('FAKE_DUAS') or n >= 2:\n"
    "    marca(ident, status='done', evidence='ok')\n"
    "elif ident in lista('FAKE_ADIA'):\n"
    "    p = carrega()\n"
    "    p['items'].sort(key=lambda it: it['id'] == ident)\n"
    "    grava(p)\n")


def test_hook_of_the_item_that_ends_the_run_inside_the_loop_is_warned():
    """The warning at the top of the loop does not see the item that leaves through a `break` in the body.
    Here a1 changes the hook in the 2nd attempt, the build goes red and the reset
    would erase a2 in the middle: the run stops at `verify-vermelho` with the hook on
    the night branch, and only the warning before `run_end` catches it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = with_plugin(build_repo(tmp, [item("a1"), item("a2")]))
        binv = fake_claude(tmp, TRIES)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_DUAS": "a1", "FAKE_ADIA": "a1",
                               "FAKE_QUEBRA": "a1", "FAKE_HOOK2": "a1"})
        end = [e for e in ledger_of(root) if e["evento"] == "run_end"]
        check("o run para por dentro do laço (verify-vermelho)",
              end and end[0]["motivo"] == "verify-vermelho", str(end))
        ev = warnings(root)
        check("o registro ganha hook_so_apos_reinstalar do a1",
              [e["id"] for e in ev] == ["a1"], str(ev))
        before_the_end = p.stdout.split("── ended at")[0]
        check("a tela avisa antes do resumo do fim",
              "a1 changed plugin hook(s)" in before_the_end, before_the_end[-1200:])


def test_warned_hook_that_left_is_not_charged_in_a_run_with_something_to_land():
    """With `actions` empty the end charge already comes out empty, and the case above of a
    hook that left does not tell recomputing from the diff apart from reusing the list of
    warnings. Here a0 stays on the branch (there is something to land) and a1's hook,
    warned in the 1st attempt, leaves with the 2nd attempt's red build."""
    with tempfile.TemporaryDirectory() as tmp:
        root = with_plugin(build_repo(tmp, [item("a0"), item("a1")]))
        binv = fake_claude(tmp, TRIES)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_DUAS": "a1", "FAKE_QUEBRA": "a1",
                               "FAKE_HOOK1": "a1"})
        check("o hook da 1ª tentativa do a1 foi avisado",
              [e["id"] for e in warnings(root)] == ["a1"], str(warnings(root)))
        check("há o que aterrissar (o a0 ficou na branch)",
              "aterrissar" in p.stdout.split("── ended at")[-1], p.stdout[-1200:])
        check("o fim não cobra o hook que saiu",
              "reinstalar-plugin" not in p.stdout
              and all(f["id"] != "reinstalar-plugin" for f in
                      state_of(root).get("fica_com_voce", [])),
              p.stdout[-1500:])


def main():
    print("cepa-until — hook que só vale depois de reinstalar\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
