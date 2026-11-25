#!/usr/bin/env python3
"""Tests of CS-1 of docs/spec/resposta-do-decide-vira-trabalho.md: opening an owner
route (`cepa-queue finish --human-pending`, `cepa-queue reword-route`) also declares the
queue item each answer without return creates, or says `nenhum`. The answers without
return are the "sim" of a route on a `done` item and the "não" of any route. Nothing is
written on a refusal.

Run with `python3 tests/test_cepa_plan_route_item_declaration.py`. Subprocess against
the real CLI in temporary git repos.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-queue"
FAILURES = []

ROUTE = "calibrar o limite depende de você"
QUESTION = "Ponho na fila um item para calibrar o limite? Recomendo sim, o limite ficou chutado."
BASE = ["--route-kind", "open-question", "--question", QUESTION,
        "--if-yes", "o limite é calibrado", "--if-no", "o limite fica como está"]


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run(repo, *args):
    env = dict(os.environ)
    for k in ("CLAUDE_WT_CLAIM", "CEPA_UNTIL_RUN", "CLAUDE_SESSION_ID"):
        env.pop(k, None)
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args),
                          capture_output=True, text=True, cwd=str(repo), env=env)


def git(d, *args):
    return subprocess.run(["git", "-C", str(d), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


def make_repo(base, name):
    d = Path(base) / name
    d.mkdir(parents=True)
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    (d / "code.py").write_text("x = 1\n")
    p = d / "itens.json"
    p.write_text(json.dumps([{"id": "A", "title": "item A", "why": "porque A",
                              "status": "pending", "blocked_by": [],
                              "human_pending": None}]), encoding="utf-8")
    r = run(d, "write", "fila", "--items", str(p), "--source", "teste",
            "--when", "2026-11-18", "--repo", ".")
    assert r.returncode == 0, r.stderr
    p.unlink()
    git(d, "add", "-A")
    git(d, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "init")
    return d


def queue_file(d):
    return d / ".claude" / "queues" / "fila" / "queue.yaml"


def item_a(d):
    plan = yaml.safe_load(queue_file(d).read_text())
    return next(i for i in plan["items"] if i["id"] == "A")


def finish(d, status, *extra):
    return run(d, "finish", "fila", "A", "--status", status,
               "--human-pending", ROUTE, "--evidence", "x", "--repo", ".",
               *(["--blocker", "falta calibrar o limite"] if status == "blocked" else []),
               *extra)


def open_route(d, *extra):
    r = finish(d, "pending", *BASE, *extra)
    assert r.returncode == 0, r.stderr
    return r


def reword(d, *extra):
    return run(d, "reword-route", "fila", "A", "--route-kind", "open-question",
               "--question", QUESTION, "--if-yes", "o limite é calibrado",
               "--if-no", "o limite fica como está", "--repo", ".", *extra)


def test_red_test_done_route_without_declaration_is_refused():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r1")
        before = queue_file(d).read_bytes()
        r = finish(d, "done", *BASE)
        check("done sem declaração: sai com 2", r.returncode == 2, f"{r.returncode} {r.stderr}")
        check("nomeia --if-yes-item e --if-no-item",
              "`--if-yes-item`" in r.stderr and "`--if-no-item`" in r.stderr, r.stderr)
        check("explica que `nenhum` vale", "nenhum" in r.stderr, r.stderr)
        check("queue.yaml idêntica byte a byte", queue_file(d).read_bytes() == before)


def test_done_route_with_only_the_no_declaration_is_refused():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r2")
        before = queue_file(d).read_bytes()
        r = finish(d, "done", *BASE, "--if-no-item", "nenhum")
        check("sai com 2", r.returncode == 2, r.stderr)
        check("nomeia só o do sim",
              "`--if-yes-item`" in r.stderr and "`--if-no-item`" not in r.stderr.split(
                  "faltou:")[1].split(".")[0], r.stderr)
        check("nada gravado", queue_file(d).read_bytes() == before)


def test_blocked_and_pending_route_needs_only_the_no_declaration():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r3")
        before = queue_file(d).read_bytes()
        r = finish(d, "blocked", *BASE)
        check("blocked sem declaração: recusa", r.returncode == 2
              and "`--if-no-item`" in r.stderr and "`--if-yes-item`" not in r.stderr,
              r.stderr)
        check("nada gravado", queue_file(d).read_bytes() == before)
        r = finish(d, "blocked", *BASE, "--if-no-item", "nenhum")
        check("blocked só com a do não: aceito", r.returncode == 0, r.stderr)
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r3b")
        r = finish(d, "pending", *BASE, "--if-no-item", "nenhum", "--if-yes-item",
                   "Calibrar o limite")
        check("a do sim é aceita mesmo sem ser exigida", r.returncode == 0, r.stderr)


def test_nenhum_is_accepted_on_done_and_stored():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r4")
        r = finish(d, "done", *BASE, "--if-yes-item", "nenhum", "--if-no-item", "Nenhum")
        check("sai com 0", r.returncode == 0, r.stderr)
        s = item_a(d)["owner_summary"]
        check("guardado como `nenhum`",
              s.get("item_se_sim") == "nenhum" and s.get("item_se_nao") == "nenhum", s)
        check("se_sim e se_nao continuam", s.get("se_sim") == "o limite é calibrado", s)


def test_declaration_is_stored_with_title_and_needs_owner_flag():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r5")
        r = finish(d, "done", *BASE, "--if-yes-item", "Calibrar o limite de lotes",
                   "--if-yes-item-needs-owner", "--if-no-item", "Registrar que o limite ficou")
        check("sai com 0", r.returncode == 0, r.stderr)
        s = item_a(d)["owner_summary"]
        check("sim: título e marca do dono",
              s.get("item_se_sim") == {"titulo": "Calibrar o limite de lotes",
                                       "precisa_do_dono": True}, s)
        check("não: título e marca falsa",
              s.get("item_se_nao") == {"titulo": "Registrar que o limite ficou",
                                       "precisa_do_dono": False}, s)
        r = run(d, "show", "fila", "A", "--json", "--repo", ".")
        check("show --json segue lendo o item", r.returncode == 0, r.stderr)
        r = run(d, "validate", "fila", "--repo", ".")
        check("a fila segue válida", r.returncode == 0, r.stdout + r.stderr)


def test_needs_owner_flag_without_title_or_with_nenhum_is_refused():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r6")
        before = queue_file(d).read_bytes()
        r = finish(d, "pending", *BASE, "--if-no-item-needs-owner")
        check("marca sem título: recusa", r.returncode == 2
              and "--if-no-item-needs-owner" in r.stderr, r.stderr)
        r = finish(d, "pending", *BASE, "--if-no-item", "nenhum", "--if-no-item-needs-owner")
        check("marca com nenhum: recusa", r.returncode == 2, r.stderr)
        check("nada gravado", queue_file(d).read_bytes() == before)


def test_title_with_code_is_refused_by_the_lay_text_rules():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r7")
        before = queue_file(d).read_bytes()
        for bad, why in (("Revisar o commit 3fa9c21", "commit"),
                         ("Ajustar o arquivo limite.py", "arquivo"),
                         ("Ajustar WEGO-123", "card")):
            r = finish(d, "pending", *BASE, "--if-no-item", bad)
            check(f"título com {why}: recusa nomeando a flag",
                  r.returncode == 2 and "--if-no-item" in r.stderr, r.stderr)
        r = finish(d, "pending", *BASE, "--if-no-item", " ".join(["palavra"] * 21))
        check("título longo demais: recusa", r.returncode == 2, r.stderr)
        check("nada gravado", queue_file(d).read_bytes() == before)


def test_reword_route_requires_the_no_declaration():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r8")
        # an OLD route: opened before the kind, the question and the effects existed
        plan = yaml.safe_load(queue_file(d).read_text())
        plan["items"][0]["human_pending"] = ROUTE
        queue_file(d).write_text(yaml.safe_dump(plan, allow_unicode=True), encoding="utf-8")
        before = queue_file(d).read_bytes()
        r = reword(d)
        check("sem a do não: sai com 2", r.returncode == 2
              and "`--if-no-item`" in r.stderr, r.stderr)
        check("a do sim não é cobrada (item aberto)", "`--if-yes-item`" not in r.stderr, r.stderr)
        check("queue.yaml idêntica byte a byte", queue_file(d).read_bytes() == before)
        r = reword(d, "--if-no-item", "Registrar o limite", "--if-no-item-needs-owner")
        check("com a do não: sai com 0", r.returncode == 0, r.stderr)
        s = item_a(d)["owner_summary"]
        check("declaração guardada",
              s.get("item_se_nao") == {"titulo": "Registrar o limite",
                                       "precisa_do_dono": True}, s)
        r = reword(d)
        check("nova chamada sem a flag passa: o item já a tem", r.returncode == 0, r.stderr)
        r = reword(d, "--replace", "--if-no-item", "nenhum")
        check("--replace sobrescreve a declaração",
              r.returncode == 0 and item_a(d)["owner_summary"]["item_se_nao"] == "nenhum",
              r.stderr)
        r = reword(d, "--if-no-item", "Outro título")
        check("sem --replace não sobrescreve",
              r.returncode == 0 and item_a(d)["owner_summary"]["item_se_nao"] == "nenhum",
              r.stderr)


def test_reword_route_title_with_code_is_refused():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r9")
        plan = yaml.safe_load(queue_file(d).read_text())
        plan["items"][0]["human_pending"] = ROUTE
        queue_file(d).write_text(yaml.safe_dump(plan, allow_unicode=True), encoding="utf-8")
        before = queue_file(d).read_bytes()
        r = reword(d, "--if-no-item", "Ver o commit 3fa9c21")
        check("recusa", r.returncode == 2 and "--if-no-item" in r.stderr, r.stderr)
        check("nada gravado", queue_file(d).read_bytes() == before)


def test_reword_route_bad_title_is_refused_even_when_the_item_already_declares():
    # The given title must pass the lay-text rules whether or not a declaration is stored.
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r9b")
        plan = yaml.safe_load(queue_file(d).read_text())
        plan["items"][0]["human_pending"] = ROUTE
        queue_file(d).write_text(yaml.safe_dump(plan, allow_unicode=True), encoding="utf-8")
        r = reword(d, "--if-no-item", "Registrar o limite")
        check("declaração guardada antes", r.returncode == 0, r.stderr)
        before = queue_file(d).read_bytes()
        for bad in ("Ver o commit 3fa9c21", "Editar o arquivo cepa-queue.py"):
            for extra in ((), ("--replace",)):
                r = reword(d, *extra, "--if-no-item", bad)
                check(f"título ruim {bad!r} {extra}: recusa (2)",
                      r.returncode == 2 and "--if-no-item" in r.stderr, r.stderr)
        check("nada gravado", queue_file(d).read_bytes() == before)


def test_finish_without_route_does_not_ask_for_declarations():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r10")
        r = run(d, "finish", "fila", "A", "--status", "pending", "--evidence", "x",
                "--repo", ".")
        check("finish sem --human-pending segue igual", r.returncode == 0, r.stderr)


def test_supervisor_re_finish_keeps_the_declarations():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r11")
        open_route(d, "--if-no-item", "Registrar o limite")
        r = run(d, "finish", "fila", "A", "--status", "pending", "--evidence", "y",
                "--repo", ".", "--supervisor", "--if-no-item", "Registrar o limite")
        check("re-finish com a declaração passa", r.returncode == 0, r.stderr)
        check("declaração segue lá", item_a(d)["owner_summary"]["item_se_nao"]
              == {"titulo": "Registrar o limite", "precisa_do_dono": False})


def main():
    print("cepa-queue: a rota declara o item de cada resposta sem retorno (CS-1)\n")
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
