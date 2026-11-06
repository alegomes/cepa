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

In the cepa repo itself (`.claude-plugin/marketplace.json` named `cepa` + `bin/install.sh`)
the supervisor reinstalls after the green build of an item that touched `<plugin>/hooks/**`
or `<plugin>/bin/**` (DUR-3); anywhere else it keeps the warning.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
DIGEST = Path(__file__).resolve().parent.parent / "common" / "bin" / "cepa-until-digest"
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
        i_warning = out.find("a1 changed plugin hook(s) or bin (meuplug/hooks/trava.py)")
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
              not warnings(root) and "changed plugin hook" not in p.stdout,
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
              "a1 changed plugin hook(s) or bin" in before_the_end, before_the_end[-1200:])


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


FAKE_INSTALL = """#!/bin/sh
echo "$@" >> "$FAKE_INSTALL_LOG"
case "$1" in
  --clean)
    if [ -n "$FAKE_INSTALL_VAZIO" ]; then
      rm -rf "$CEPA_PLUGIN_CACHE_DIR.prev"
      mv "$CEPA_PLUGIN_CACHE_DIR" "$CEPA_PLUGIN_CACHE_DIR.prev"
      exit 0
    fi
    if [ -n "$FAKE_INSTALL_FALHA" ]; then
      echo "install quebrou" >&2
      [ -n "$FAKE_ROLLBACK_FALHA" ] && mv "$CEPA_PLUGIN_CACHE_DIR" "$CEPA_PLUGIN_CACHE_DIR.prev"
      exit 1
    fi
    rm -rf "$CEPA_PLUGIN_CACHE_DIR.prev"
    [ -d "$CEPA_PLUGIN_CACHE_DIR" ] && mv "$CEPA_PLUGIN_CACHE_DIR" "$CEPA_PLUGIN_CACHE_DIR.prev"
    mkdir -p "$CEPA_PLUGIN_CACHE_DIR/meuplug/1.0.0"
    cp -R meuplug/hooks meuplug/bin "$CEPA_PLUGIN_CACHE_DIR/meuplug/1.0.0/"
    ;;
  --rollback)
    [ -n "$FAKE_ROLLBACK_FALHA" ] && exit 1
    if [ -d "$CEPA_PLUGIN_CACHE_DIR.prev" ]; then
      rm -rf "$CEPA_PLUGIN_CACHE_DIR"
      mv "$CEPA_PLUGIN_CACHE_DIR.prev" "$CEPA_PLUGIN_CACHE_DIR"
    fi
    ;;
esac
exit 0
"""


def with_fake_install(root):
    """A `bin/install.sh` that only touches the cache named by CEPA_PLUGIN_CACHE_DIR."""
    (root / "meuplug" / "bin").mkdir(exist_ok=True)
    (root / "meuplug" / "bin" / "ferramenta").write_text("v1\n")
    (root / "bin").mkdir(exist_ok=True)
    inst = root / "bin" / "install.sh"
    inst.write_text(FAKE_INSTALL)
    inst.chmod(inst.stat().st_mode | stat.S_IXUSR)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "install"], cwd=root, check=True)


def as_cepa(root, cache):
    """The test repo becomes the cepa repo: marketplace.json named `cepa`, a tracked
    `meuplug/bin/ferramenta`, a fake `bin/install.sh`, and a cache pre-seeded with the v1
    hook so `sha_antes` is not None. Returns the env for `run_until`."""
    (root / ".claude-plugin").mkdir(exist_ok=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "cepa", "plugins": []}))
    with_fake_install(root)
    seed = Path(cache) / "meuplug" / "1.0.0" / "hooks"
    seed.mkdir(parents=True)
    (seed / "trava.py").write_text("v1\n")
    (seed.parent / "bin").mkdir()
    (seed.parent / "bin" / "ferramenta").write_text("v1\n")
    return {"CEPA_PLUGIN_CACHE_DIR": str(cache),
            "FAKE_INSTALL_LOG": str(Path(cache).parent / "install.log")}


def install_calls(env):
    f = Path(env["FAKE_INSTALL_LOG"])
    return f.read_text().split("\n")[:-1] if f.exists() else []


def log_text(root):
    logs = sorted((root / ".claude/programs/fila/until").glob("*.log"))
    return logs[-1].read_text(errors="replace") if logs else ""


def load_cepa_until():
    """The real `common/bin/cepa-until` loaded as a module, for the direct checks."""
    from importlib.machinery import SourceFileLoader
    path = Path(__file__).resolve().parent.parent / "common" / "bin" / "cepa-until"
    return SourceFileLoader("cepa_until_mod", str(path)).load_module()


def sha_of_cache(mod, cache):
    old = os.environ.get("CEPA_PLUGIN_CACHE_DIR")
    os.environ["CEPA_PLUGIN_CACHE_DIR"] = str(cache)
    try:
        return mod.installed_hooks_sha()
    finally:
        if old is None:
            del os.environ["CEPA_PLUGIN_CACHE_DIR"]
        else:
            os.environ["CEPA_PLUGIN_CACHE_DIR"] = old


def put(cache, version, rel, text, plugin="meuplug"):
    f = Path(cache) / plugin / version / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)


def of_kind(root, kind):
    return [e for e in ledger_of(root) if e["evento"] == kind]


def cepa_run(tmp, items, files, extra=None, args=("--verify", VERIFY), cepa=True,
             claude=WORKS, window="2h", prepare=None):
    root = with_plugin(build_repo(tmp, items))
    cache = Path(tmp) / "cache"
    env = as_cepa(root, cache) if cepa else {
        "CEPA_PLUGIN_CACHE_DIR": str(cache),
        "FAKE_INSTALL_LOG": str(Path(tmp) / "install.log")}
    if prepare:
        prepare(root)
    if not cepa:
        with_fake_install(root)
        (cache / "meuplug" / "1.0.0" / "hooks").mkdir(parents=True)
        (cache / "meuplug" / "1.0.0" / "hooks" / "trava.py").write_text("v1\n")
    env["FAKE_ARQUIVOS"] = files
    env.update(extra or {})
    binv = fake_claude(tmp, claude)
    p, _ = run_until(root, binv, plan_of(root), ["--for", window, *args],
                     extra_env=env)
    return root, p, env


def test_cepa_repo_reinstalls_after_green_build_of_a_hook():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(tmp, [item("a1"), item("a2")],
                                "a1=meuplug/hooks/trava.py")
        check("o install.sh rodou uma vez, com --clean",
              install_calls(env) == ["--clean"], str(install_calls(env)))
        ev = of_kind(root, "hooks_reinstalados")
        check("um hooks_reinstalados do a1, ok, com sha antes e depois diferentes",
              len(ev) == 1 and ev[0]["id"] == "a1" and ev[0]["ok"] is True
              and ev[0]["sha_antes"] != ev[0]["sha_depois"]
              and len(ev[0]["sha_antes"]) == 12 and len(ev[0]["sha_depois"]) == 12,
              str(ev))
        starts = {e["id"]: e for e in of_kind(root, "item_start")}
        check("item_start do a1 traz o sha de antes e o do a2 o de depois",
              ev and starts["a1"]["hooks_sha"] == ev[0]["sha_antes"]
              and starts["a2"]["hooks_sha"] == ev[0]["sha_depois"], str(starts))
        check("não avisa hook_so_apos_reinstalar", not warnings(root),
              str(warnings(root)))
        stays = {f["id"]: f["texto"]
                 for f in state_of(root).get("fica_com_voce", [])}
        check("o fim diz que já foi instalado e cobra o bin/install.sh da manhã",
              "were already installed" in stays.get("reinstalar-plugin", "")
              and "bin/install.sh" in stays.get("reinstalar-plugin", ""),
              str(stays))
        check("o .log traz o trecho com o rótulo reinstall",
              "· reinstall · sh bin/install.sh --clean" in log_text(root))
        ledger = sorted((root / ".claude/programs/fila/until").glob("*.jsonl"))[-1]
        d = subprocess.run([sys.executable, str(DIGEST), str(ledger)],
                           capture_output=True, text=True)
        check("o digest mostra o sha dos hooks por rodada",
              f"hooks {ev[0]['sha_depois']}" in d.stdout, d.stdout[-1500:])


def test_cepa_repo_reinstalls_when_plugin_bin_changes():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(tmp, [item("a1")], "a1=meuplug/bin/ferramenta")
        ev = of_kind(root, "hooks_reinstalados")
        check("mexer em <plugin>/bin/ também reinstala",
              install_calls(env) == ["--clean"] and len(ev) == 1
              and ev[0]["ok"] is True, str(ev))


def test_cepa_repo_red_build_does_not_reinstall():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(tmp, [item("a1"), item("a2")],
                                "a1=meuplug/hooks/trava.py",
                                extra={"FAKE_QUEBRA": "a1"})
        check("build vermelho: install.sh não roda e não há hooks_reinstalados",
              not install_calls(env) and not of_kind(root, "hooks_reinstalados"),
              str(install_calls(env)))


def test_cepa_repo_without_verify_only_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(tmp, [item("a1")], "a1=meuplug/hooks/trava.py",
                                args=())
        check("sem --verify: install.sh não roda e o aviso antigo dispara",
              not install_calls(env) and len(warnings(root)) == 1
              and not of_kind(root, "hooks_reinstalados"), str(warnings(root)))


def test_repo_that_is_not_cepa_warns_and_changes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(tmp, [item("a1")], "a1=meuplug/hooks/trava.py",
                                cepa=False)
        check("repo não é o cepa: install.sh não roda, nada é reinstalado",
              not install_calls(env) and not of_kind(root, "hooks_reinstalados"),
              str(install_calls(env)))
        check("...avisa hook_so_apos_reinstalar", len(warnings(root)) == 1,
              str(warnings(root)))
        stays = {f["id"]: f["texto"]
                 for f in state_of(root).get("fica_com_voce", [])}
        check("...e o fim cobra com o texto de sempre",
              "no round of this run" in stays.get("reinstalar-plugin", ""),
              str(stays))


def test_failed_install_is_rolled_back_and_the_night_goes_on():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(tmp, [item("a1"), item("a2")],
                                "a1=meuplug/hooks/trava.py",
                                extra={"FAKE_INSTALL_FALHA": "1"})
        ev = of_kind(root, "hooks_reinstalados")
        check("hooks_reinstalados com ok falso",
              len(ev) == 1 and ev[0]["ok"] is False, str(ev))
        check("install.sh rodou --clean e depois --rollback",
              install_calls(env) == ["--clean", "--rollback"],
              str(install_calls(env)))
        check("o .log traz o trecho com o rótulo rollback",
              "· rollback · sh bin/install.sh --rollback" in log_text(root))
        undone = of_kind(root, "reinstalacao_desfeita")
        check("reinstalacao_desfeita ok: o cache voltou ao sha de antes",
              len(undone) == 1 and undone[0]["ok"] is True
              and undone[0]["sha"] == ev[0]["sha_antes"], str(undone))
        check("o a2 ainda rodou",
              any(e["id"] == "a2" for e in of_kind(root, "item_start")))
        stays = [f["id"] for f in state_of(root).get("fica_com_voce", [])]
        check("fica_com_voce traz reinstalacao-falhou", "reinstalacao-falhou" in stays,
              str(stays))
        end = of_kind(root, "run_end")
        check("o run não termina por reinstalacao-falhou",
              end and end[0]["motivo"] != "reinstalacao-falhou", str(end))


def test_rollback_that_fails_ends_the_run_with_reinstalacao_falhou():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(tmp, [item("a1"), item("a2")],
                                "a1=meuplug/hooks/trava.py",
                                extra={"FAKE_INSTALL_FALHA": "1",
                                       "FAKE_ROLLBACK_FALHA": "1"})
        undone = of_kind(root, "reinstalacao_desfeita")
        check("reinstalacao_desfeita com ok falso",
              len(undone) == 1 and undone[0]["ok"] is False, str(undone))
        check("o desfecho do a1 diz que o rollback não devolveu o cache",
              "the hook reinstall failed and the rollback did not restore the cache"
              in p.stdout, p.stdout[-1500:])
        end = of_kind(root, "run_end")
        check("o run termina por reinstalacao-falhou",
              end and end[0]["motivo"] == "reinstalacao-falhou", str(end))
        st = state_of(root)
        check("o a1 segue como entregue",
              any(i["id"] == "a1" and i["desfecho"] == "entregue"
                  for i in st.get("itens", [])), str(st.get("itens")))
        check("o a2 não rodou",
              [e["id"] for e in of_kind(root, "item_start")] == ["a1"])
        check("fica_com_voce traz reinstalacao-falhou",
              "reinstalacao-falhou" in
              [f["id"] for f in st.get("fica_com_voce", [])])


# a1 commits the hook and closes `done` (green build, reinstall); a2 commits
# `meuplug/bin/ferramenta` and stays `pending` (no build, so no reinstall); its 2nd attempt
# does nothing, and with `--max-failures 1` the breaker ends the run with a2's commit
# still on the night branch.
LATE = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "cont = os.environ['FAKE_CHAMADAS'] + '.n.' + ident\n"
    "n = int(open(cont).read()) + 1 if os.path.exists(cont) else 1\n"
    "open(cont, 'w').write(str(n))\n"
    "alvo = 'meuplug/hooks/trava.py' if ident == 'a1' else 'meuplug/bin/ferramenta'\n"
    "if ident == 'a1' or n == 1:\n"
    "    open(alvo, 'a').write(ident + '\\n')\n"
    "    subprocess.run(['git', 'add', '-A'], check=True)\n"
    "    subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                    'commit', '-qm', ident], check=True)\n"
    "if ident == 'a1':\n"
    "    marca(ident, status='done', evidence='ok')\n"
    )


def test_hook_committed_after_the_last_reinstall_is_not_charged_as_installed():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(tmp, [item("a1"), item("a2")], "", claude=LATE,
                                args=("--verify", VERIFY, "--attempts-per-item", "3",
                                      "--max-failures", "1"))
        check("o a1 reinstalou",
              [e["id"] for e in of_kind(root, "hooks_reinstalados")] == ["a1"])
        check("o aviso de hook_so_apos_reinstalar dispara só para o arquivo do a2",
              [(e["id"], e["arquivos"]) for e in warnings(root)]
              == [("a2", ["meuplug/bin/ferramenta"])], str(warnings(root)))
        stays = {f["id"]: f["texto"]
                 for f in state_of(root).get("fica_com_voce", [])}
        t = stays.get("reinstalar-plugin", "")
        check("o fim lista o arquivo do a2 como ainda não instalado",
              "NOT yet installed" in t
              and "meuplug/bin/ferramenta; those only take effect" in t
              and "Already installed during the run: meuplug/hooks/trava.py" in t, t)


def test_no_time_left_postpones_the_reinstall():
    """Real short window, production floor (120 s): `--for 1.5m --slack 0.01m` leaves
    ~90 s after the build."""
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(
            tmp, [item("a1")], "a1=meuplug/hooks/trava.py", window="1.5m",
            args=("--verify", VERIFY, "--min-reserve", "0.01m",
                  "--slack", "0.01m"))
        ev = of_kind(root, "reinstalacao_adiada")
        check("reinstalacao_adiada no registro e install.sh não roda",
              len(ev) == 1 and ev[0]["id"] == "a1" and not install_calls(env)
              and not of_kind(root, "hooks_reinstalados"), p.stdout[-800:])
        check("...com o piso de 120s no motivo", ev and "120s" in ev[0]["motivo"],
              str(ev))
        check("cai no aviso de sempre", len(warnings(root)) == 1)


def test_not_cepa_marketplace_with_other_name_warns_and_changes_nothing():
    def prep(root):
        (root / ".claude-plugin").mkdir(exist_ok=True)
        (root / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"name": "outro", "plugins": []}))
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(tmp, [item("a1")], "a1=meuplug/hooks/trava.py",
                                cepa=False, prepare=prep)
        check("marketplace `outro`: install.sh não roda, nada reinstalado",
              not install_calls(env) and not of_kind(root, "hooks_reinstalados"),
              str(install_calls(env)))
        check("...e avisa hook_so_apos_reinstalar", len(warnings(root)) == 1)


def test_cepa_marketplace_without_install_script_warns_and_changes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = with_plugin(build_repo(tmp, [item("a1")]))
        (root / ".claude-plugin").mkdir(exist_ok=True)
        (root / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"name": "cepa", "plugins": []}))
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "mkt"], cwd=root, check=True)
        env = {"CEPA_PLUGIN_CACHE_DIR": str(Path(tmp) / "cache"),
               "FAKE_INSTALL_LOG": str(Path(tmp) / "install.log"),
               "FAKE_ARQUIVOS": "a1=meuplug/hooks/trava.py"}
        put(Path(tmp) / "cache", "1.0.0", "hooks/trava.py", "v1\n")
        p, _ = run_until(root, fake_claude(tmp, WORKS), plan_of(root),
                         ["--for", "2h", "--verify", VERIFY], extra_env=env)
        check("sem bin/install.sh: nada reinstalado", not of_kind(
            root, "hooks_reinstalados") and not install_calls(env))
        check("...e avisa hook_so_apos_reinstalar", len(warnings(root)) == 1,
              p.stdout[-600:])


def test_reinstall_changes_sha_when_only_the_content_changes():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(tmp, [item("a1")], "a1=meuplug/hooks/trava.py")
        ev = of_kind(root, "hooks_reinstalados")
        seed_names = sorted(
            f.relative_to(Path(tmp) / "cache.prev").as_posix()
            for f in (Path(tmp) / "cache.prev").rglob("*") if f.is_file())
        after_names = sorted(
            f.relative_to(Path(tmp) / "cache").as_posix()
            for f in (Path(tmp) / "cache").rglob("*") if f.is_file())
        check("antes e depois têm os mesmos nomes de arquivo",
              seed_names == after_names, f"{seed_names} {after_names}")
        check("só o conteúdo mudou e o sha mudou",
              ev and ev[0]["sha_antes"] and ev[0]["sha_antes"] != ev[0]["sha_depois"],
              str(ev))


def test_hooks_sha_ignores_pycache_takes_newest_version_and_none_when_empty():
    mod = load_cepa_until()
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        put(t / "a", "1.0.0", "hooks/x.py", "v1\n")
        put(t / "b", "1.0.0", "hooks/x.py", "v1\n")
        put(t / "b", "1.0.0", "hooks/__pycache__/x.pyc", "lixo")
        sa, sb = sha_of_cache(mod, t / "a"), sha_of_cache(mod, t / "b")
        check("__pycache__ não entra no sha", sa is not None and sa == sb,
              f"{sa} {sb}")
        check("o sha tem 12 hex", sa and len(sa) == 12)
        # newest version: 1.2.0 wins over 1.0.0 and over 1.10 vs 1.9 ordering
        put(t / "c", "1.0.0", "hooks/x.py", "velho\n")
        put(t / "c", "1.2.0", "hooks/x.py", "novo\n")
        put(t / "d", "1.2.0", "hooks/x.py", "novo\n")
        check("só a versão mais nova conta",
              sha_of_cache(mod, t / "c") == sha_of_cache(mod, t / "d"))
        put(t / "e", "1.9.0", "hooks/x.py", "nove\n")
        put(t / "e", "1.10.0", "hooks/x.py", "dez\n")
        put(t / "f", "1.10.0", "hooks/x.py", "dez\n")
        check("a ordem das versões é numérica (1.10 > 1.9)",
              sha_of_cache(mod, t / "e") == sha_of_cache(mod, t / "f"))
        (t / "vazio").mkdir()
        check("cache vazio dá None", sha_of_cache(mod, t / "vazio") is None)
        check("cache que não existe dá None",
              sha_of_cache(mod, t / "nao-existe") is None)
        put(t / "g", "1.0.0", "outra/coisa.txt", "x")
        check("sem hooks/ nem bin/ dá None", sha_of_cache(mod, t / "g") is None)
        put(t / "h", "1.0.0", "bin/ferramenta", "x")
        check("bin/ também entra no sha", sha_of_cache(mod, t / "h") is not None)


def test_item_start_hooks_sha_is_none_without_cache():
    with tempfile.TemporaryDirectory() as tmp:
        root = with_plugin(build_repo(tmp, [item("a1")]))
        env = {"CEPA_PLUGIN_CACHE_DIR": str(Path(tmp) / "nao-existe"),
               "FAKE_ARQUIVOS": ""}
        run_until(root, fake_claude(tmp, WORKS), plan_of(root),
                  ["--for", "2h"], extra_env=env)
        st = of_kind(root, "item_start")
        check("hooks_sha é None quando o cache não existe",
              st and all("hooks_sha" in e and e["hooks_sha"] is None for e in st),
              str(st))


def test_install_that_exits_zero_with_empty_cache_counts_as_failure():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, env = cepa_run(tmp, [item("a1"), item("a2")],
                                "a1=meuplug/hooks/trava.py",
                                extra={"FAKE_INSTALL_VAZIO": "1"})
        ev = of_kind(root, "hooks_reinstalados")
        check("hooks_reinstalados ok falso (cache sem hooks/bin)",
              len(ev) == 1 and ev[0]["ok"] is False and ev[0]["sha_depois"] is None,
              str(ev))
        check("o rollback rodou e restaurou",
              install_calls(env) == ["--clean", "--rollback"],
              str(install_calls(env)))
        undone = of_kind(root, "reinstalacao_desfeita")
        check("reinstalacao_desfeita ok com o sha de antes",
              len(undone) == 1 and undone[0]["ok"] is True
              and undone[0]["sha"] == ev[0]["sha_antes"], str(undone))


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
