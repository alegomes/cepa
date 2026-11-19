#!/usr/bin/env python3
"""cepa-until --auto-land — CS-1 of docs/spec/fim-do-until-sem-espera.md.

A clean run (the clone's branch did not move since the start, the last full build
of the run branch is green, nothing stuck or waiting on the owner) launched with
`--auto-land` does by itself what `cepa-until land --yes` does: merge, full build,
push, return point recorded, and the state ends `aterrissado`.

Every case runs a real `cepa-until` against a fake repo with a fake `claude`.
"""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from datetime import timedelta
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
    `main` stays as it was, and the line names the item (spec CS-2, red test)."""
    body = ("ident = primeiro_pendente()\n"
            "if ident == 'a2':\n"
            "    marca(ident, status='blocked', evidence='falta credencial')\n"
            "    sys.exit(0)\n" + WORKS)
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        remote = with_origin(root)
        binv = fake_claude(root.parent, body)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", VERIFY, "--no-analysis",
                          "--auto-land"])
        out = p.stdout + p.stderr
        start = [e for e in ledger_of(root) if e["evento"] == "run_start"][0]
        st = state(root)
        check("item travado: a run termina esperando-dono",
              st.get("estado") == "esperando-dono", out[-2000:])
        check("...o código do item entregue não está na main do clone",
              "a1" not in git(root, "log", "--format=%s", "HEAD").splitlines())
        pushed = subprocess.run(["git", "--git-dir", str(remote), "log",
                                 "--format=%s", "HEAD"], capture_output=True,
                                text=True).stdout.splitlines()
        check("...nem no origin", "a1" not in pushed, str(pushed))
        check("...e a branch da run continua", git(root, "branch", "--list",
                                                    start["branch"]), out[-800:])
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
        check("...e diz a condição: o último build não está verde",
              "not merged: the last full build of the run branch is not green"
              in out, out[-2000:])


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


def _clean_world(mod, tmp, verdes=(True,), deferred=(), itens=None):
    """`not_clean_reason` over a run that is clean on every condition but the one
    under test: git says fast-forward, the clone is on `main`, every item delivered,
    and the queue holds `deferred`. The ledger's `verify` events are `verdes`."""
    mod.current_branch = lambda repo: "main"
    mod.git = lambda args, cwd, timeout=120: (0, "")
    mod.is_all_run = lambda repo, queue: False
    mod.query_queue = lambda name, repo, max_items=1: (
        {"deferred": list(deferred)}, None)
    ledger = Path(tmp) / "r.jsonl"
    ledger.write_text("".join(json.dumps({"evento": "verify", "verde": v}) + "\n"
                              for v in verdes))
    st = {"estado": "esperando-dono", "verify": "true",
          "acoes": [{"id": "aterrissar", "destino": "main", "sha": "x"}],
          "itens": itens or [{"id": "a1", "desfecho": "entregue",
                              "texto": "ok"}],
          "fica_com_voce": []}
    return mod.not_clean_reason(Path(tmp), "fila", st, ledger)


def test_clean_reference_has_no_reason():
    with tempfile.TemporaryDirectory() as tmp:
        r = _clean_world(_module(), tmp)
        check("referência limpa: nenhum motivo para não fazer o merge", r is None,
              str(r))


def test_red_last_build_alone_is_not_clean():
    """Every item delivered, and the LAST full build went red (an earlier one was
    green): not clean, and the reason is the build."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _clean_world(_module(), tmp, verdes=(True, False))
        check("último build vermelho, tudo entregue: não está limpa",
              r is not None and "not green" in r, str(r))


def test_owner_question_alone_is_not_clean():
    """Every item delivered and the build green, but the queue holds an item
    waiting on the owner: not clean, and the reason names that item."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _clean_world(_module(), tmp, deferred=[
            {"id": "b9", "reason": "human_pending", "detail": "credencial"}])
        check("pergunta pendente com o dono: não está limpa",
              r is not None and "b9" in r and "waiting on you" in r, str(r))


def test_explicit_false_in_the_state_reads_as_no():
    mod = _module()
    check("auto_land false no estado vale não",
          mod.state_auto_land({"auto_land": False}) is False)
    check("auto_land com valor que não é true vale não",
          mod.state_auto_land({"auto_land": "yes"}) is False)


def test_unfinished_outcomes_are_named_in_english():
    """Each outcome that is not a delivery names the condition in English, never the
    id stored in the state; an outcome this version does not know still refuses."""
    expected = {
        "volta-vermelha": "a2 went back to the queue after a red build",
        "sem-rede": "a2 was cut by a network drop",
        "limite-de-uso": "a2 stopped on the usage limit",
        "em-andamento": "a2 was still running",
    }
    for kind, phrase in expected.items():
        with tempfile.TemporaryDirectory() as tmp:
            r = _clean_world(_module(), tmp, itens=[
                {"id": "a1", "desfecho": "entregue", "texto": "ok"},
                {"id": "a2", "desfecho": kind, "texto": "x"}])
            check(f"desfecho {kind}: o motivo é a frase em inglês", r == phrase,
                  str(r))
            check(f"...e o id {kind} não aparece na tela", kind not in (r or ""),
                  str(r))
    with tempfile.TemporaryDirectory() as tmp:
        r = _clean_world(_module(), tmp, itens=[
            {"id": "a2", "desfecho": "inventado-depois", "texto": "x"}])
        check("desfecho desconhecido ainda recusa o merge, nomeando o item",
              r is not None and "a2" in r, str(r))
        check("...sem imprimir o id cru do desfecho",
              "inventado-depois" not in (r or ""), str(r))


def _ledger_with_build(tmp, seconds):
    ledger = Path(tmp) / "r.jsonl"
    ledger.write_text(
        json.dumps({"evento": "verify", "verde": True, "segundos": 5}) + "\n"
        + json.dumps({"evento": "verify", "verde": True, "segundos": seconds})
        + "\n")
    return ledger


def test_window_shorter_than_the_last_build_refuses():
    mod = _module()
    with tempfile.TemporaryDirectory() as tmp:
        r = mod.window_reason(timedelta(minutes=4),
                              _ledger_with_build(tmp, 15 * 60))
        check("janela de 4min e build de 15min: recusa nomeando as duas durações",
              r == "the window ends in 4min and the last full build took 15min",
              str(r))
        # The slack is for an item already running, so it never counts here.
        called = []
        mod.cmd_land = lambda argv: called.append(argv) or 0
        mod.not_clean_reason = lambda *a: None
        path = Path(tmp) / "r.estado.json"
        path.write_text(json.dumps({"auto_land": True, "estado":
                                    "esperando-dono", "acoes": [
            {"id": "aterrissar", "destino": "main", "sha": "x"}]}))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = mod.auto_land(Path(tmp), "fila", "r", path,
                                _ledger_with_build(tmp, 15 * 60),
                                left=timedelta(minutes=4))
        check("auto_land: o merge não começa", ret is None and not called,
              str(called))
        check("...e a linha not merged diz a janela",
              "not merged: the window ends in 4min and the last full build "
              "took 15min" in buf.getvalue(), buf.getvalue())


def test_expired_window_refuses():
    """A window already at zero, or past the deadline (a run that ended on it),
    is shorter than any build and must refuse without starting the merge."""
    mod = _module()
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _ledger_with_build(tmp, 15 * 60)
        for label, left in (("zerada", timedelta(0)),
                            ("negativa (run terminou no prazo)",
                             timedelta(minutes=-3))):
            r = mod.window_reason(left, ledger)
            check(f"janela {label}: window_reason recusa", r is not None, str(r))
            called = []
            mod.cmd_land = lambda argv, called=called: called.append(argv) or 0
            mod.not_clean_reason = lambda *a: None
            path = Path(tmp) / "r.estado.json"
            path.write_text(json.dumps({"auto_land": True, "estado":
                                        "esperando-dono", "acoes": [
                {"id": "aterrissar", "destino": "main", "sha": "x"}]}))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ret = mod.auto_land(Path(tmp), "fila", "r", path, ledger,
                                    left=left)
            check(f"janela {label}: auto_land não chama cmd_land",
                  ret is None and not called, str(called))
            check(f"janela {label}: a linha not merged é impressa",
                  "not merged:" in buf.getvalue(), buf.getvalue())


def test_window_that_fits_the_last_build_has_no_reason():
    mod = _module()
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _ledger_with_build(tmp, 15 * 60)
        check("janela de 20min e build de 15min: nenhum motivo",
              mod.window_reason(timedelta(minutes=20), ledger) is None)
        check("janela exatamente igual ao build: cabe",
              mod.window_reason(timedelta(minutes=15), ledger) is None)
        check("sem build no ledger a janela não recusa (o outro motivo já cobre)",
              mod.window_reason(timedelta(minutes=1),
                                Path(tmp) / "nao-existe.jsonl") is None)
        called = []
        mod.cmd_land = lambda argv: called.append(argv) or 0
        mod.not_clean_reason = lambda *a: None
        path = Path(tmp) / "r.estado.json"
        path.write_text(json.dumps({"auto_land": True, "estado":
                                    "esperando-dono", "acoes": [
            {"id": "aterrissar", "destino": "main", "sha": "x"}]}))
        with contextlib.redirect_stdout(io.StringIO()):
            mod.auto_land(Path(tmp), "fila", "r", path, ledger,
                          left=timedelta(minutes=20))
        check("auto_land com a janela folgada: o merge começa", len(called) == 1,
              str(called))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    sys.exit(1 if FAILURES else 0)
