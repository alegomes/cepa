#!/usr/bin/env python3
"""cepa-until --auto-land — CS-1 of docs/spec/fim-do-until-sem-espera.md.

A clean run (the clone's branch did not move since the start, the last full build
of the run branch is green, nothing stuck or waiting on the owner) launched with
`--auto-land` does by itself what `cepa-until land --yes` does: merge, full build,
push, return point recorded, and the state ends `aterrissado`.

Every case runs a real `cepa-until` against a fake repo with a fake `claude`.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, ledger_of, build_repo, run_until)
from test_cepa_until_run_branch import WORKS, VERIFY, git, plan_of  # noqa: E402
from test_cepa_until_land import state, with_origin  # noqa: E402


def night(root, *extra):
    binv = fake_claude(root.parent, WORKS)
    p, _ = run_until(root, binv, plan_of(root),
                     ["--for", "2h", "--verify", VERIFY, "--no-analysis", *extra])
    start = [e for e in ledger_of(root) if e["evento"] == "run_start"][0]
    return p, start


def test_clean_run_with_auto_land_merges_by_itself():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        remote = with_origin(root)
        before = git(root, "rev-parse", "HEAD")
        p, start = night(root, "--auto-land")
        out = p.stdout + p.stderr
        check("a flag existe (o argparse não sai com 2)", p.returncode != 2, out)
        log = git(root, "log", "--format=%s", "HEAD").splitlines()
        check("o commit do item está na main do clone", "a1" in log, str(log))
        check("...e o ponto de partida da main é ancestral (merge, não reescrita)",
              subprocess.run(["git", "merge-base", "--is-ancestor", before, "HEAD"],
                             cwd=str(root)).returncode == 0)
        pushed = subprocess.run(["git", "--git-dir", str(remote), "log",
                                 "--format=%s", "HEAD"], capture_output=True,
                                text=True).stdout.splitlines()
        check("o push levou o commit do item ao origin", "a1" in pushed,
              str(pushed))
        st = state(root)
        check("o estado termina aterrissado", st.get("estado") == "aterrissado",
              json.dumps(st, ensure_ascii=False)[:600])
        check("...com o ponto de retorno gravado",
              (st.get("aterrissagem") or {}).get("retorno") == before, str(st))
        check("...e auto_land true no estado", st.get("auto_land") is True, str(st))
        check("a branch da run some", not git(root, "branch", "--list",
                                              start["branch"]), out)
        check("o fim não pergunta Land now?", "Land now?" not in out, out)


def test_without_the_flag_nothing_lands_and_state_says_false():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        with_origin(root)
        before = git(root, "rev-parse", "HEAD")
        p, start = night(root)
        st = state(root)
        check("sem a flag a run não faz o merge",
              st.get("estado") == "esperando-dono", str(st))
        check("...o estado grava auto_land false", st.get("auto_land") is False,
              str(st))
        check("...e a branch da run continua", git(root, "branch", "--list",
                                                    start["branch"]))
        # The run records commit lands on main by itself; the item's code does not.
        check("...o código do item não está na main",
              "a1" not in git(root, "log", "--format=%s", "HEAD").splitlines(),
              git(root, "log", "--format=%s", f"{before}..HEAD"))


def test_main_moved_during_the_run_is_not_clean():
    """No fast-forward: the clone's branch moved after the run started. Simulated by
    a fake `claude` that commits on the clone while it works on the item."""
    body = (WORKS + "\nimport subprocess as _sp\n"
            "_r = os.environ['FAKE_CLONE']\n"
            "open(os.path.join(_r, 'andou.txt'), 'w').write('x')\n"
            "_sp.run(['git', 'add', 'andou.txt'], cwd=_r)\n"
            "_sp.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit',"
            " '-qm', 'main andou'], cwd=_r)\n")
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        with_origin(root)
        binv = fake_claude(root.parent, body)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", VERIFY, "--no-analysis",
                          "--auto-land"], extra_env={"FAKE_CLONE": str(root)})
        out = p.stdout + p.stderr
        st = state(root)
        check("main andou: a run não faz o merge",
              st.get("estado") == "esperando-dono", out[-2000:])
        check("...e diz que não houve fast-forward",
              "not merged" in out and "fast-forward" in out, out[-2000:])


def test_stuck_item_is_not_clean():
    """One item delivers green, the other ends `blocked`: the run does not merge,
    `main` stays as it was, and the line names the item."""
    body = ("ident = primeiro_pendente()\n"
            "if ident == 'a2':\n"
            "    marca(ident, status='blocked', evidence='falta credencial')\n"
            "    sys.exit(0)\n" + WORKS)
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        with_origin(root)
        binv = fake_claude(root.parent, body)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", VERIFY, "--no-analysis",
                          "--auto-land"])
        out = p.stdout + p.stderr
        st = state(root)
        check("item travado: a run não faz o merge",
              st.get("estado") == "esperando-dono", out[-2000:])
        check("...o código do item entregue não está na main",
              "a1" not in git(root, "log", "--format=%s", "HEAD").splitlines())
        check("...e a linha nomeia o item travado",
              "not merged: a2 is stuck" in out, out[-2000:])


def test_red_last_build_is_not_clean():
    """The last full build went red (its commits were taken off): not clean."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        with_origin(root)
        binv = fake_claude(root.parent, WORKS)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", VERIFY, "--no-analysis",
                          "--auto-land", "--attempts-per-item", "1"],
                         extra_env={"FAKE_QUEBRA": "a2"})
        out = p.stdout + p.stderr
        st = state(root)
        check("build vermelho por último: a run não faz o merge",
              st.get("estado") != "aterrissado", out[-2000:])
        check("...e diz por quê", "not merged:" in out, out[-2000:])


def _module():
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    from test_cepa_until import CEPA_UNTIL
    loader = SourceFileLoader("cepa_until", str(CEPA_UNTIL))
    mod = module_from_spec(spec_from_loader("cepa_until", loader))
    loader.exec_module(mod)
    return mod


def test_old_state_without_the_field_reads_as_no():
    """Spec, "Estado e migração": a state written before `auto_land` existed reads
    as false, and the automatic merge never starts from it, even if the run is
    otherwise clean."""
    mod = _module()
    check("estado sem o campo vale não", mod.state_auto_land({"estado":
                                                               "esperando-dono"})
          is False)
    check("estado com true vale sim", mod.state_auto_land({"auto_land": True}))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "r.estado.json"
        path.write_text(json.dumps({"estado": "esperando-dono", "acoes": [
            {"id": "aterrissar", "destino": "main", "sha": "x"}]}))
        called = []
        mod.cmd_land = lambda argv: called.append(argv) or 0
        mod.not_clean_reason = lambda *a: None  # clean on every other condition
        r = mod.auto_land(Path(tmp), "fila", "r", path, Path(tmp) / "r.jsonl")
        check("...e o merge automático não começa a partir dele",
              r is None and not called, str(called))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    sys.exit(1 if FAILURES else 0)
