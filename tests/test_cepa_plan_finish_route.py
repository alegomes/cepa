#!/usr/bin/env python3
"""Tests of CS-1 of docs/spec/perguntas-da-largada-legiveis.md: `cepa-queue finish
--human-pending` refuses to open a route that has no kind, no closed question, or
does not say what yes and no do to the work. Nothing is written on a refusal.

Run with `python3 tests/test_cepa_plan_finish_route.py`. Subprocess against the
real CLI in temporary git repos.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until_decide import on_tty  # noqa: E402

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-queue"
FAILURES = []

ROUTE = "falta o acesso"
QUESTION = "O acesso ao servidor já existe? Recomendo sim, o chamado foi atendido."


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run(repo, *args):
    env = dict(os.environ)
    for k in ("CEPA_WT_CLAIM", "CLAUDE_WT_CLAIM", "CEPA_RUN", "CEPA_UNTIL_RUN", "CLAUDE_SESSION_ID"):
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
            "--when", "2026-11-13", "--repo", ".")
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


def finish(d, *extra):
    return run(d, "finish", "fila", "A", "--status", "pending",
               "--human-pending", ROUTE, "--evidence", "x", "--repo", ".", *extra)


FULL = ["--route-kind", "external-block", "--question", QUESTION,
        "--if-yes", "o item volta para a fila", "--if-no", "o item continua parado",
        "--if-no-item", "nenhum"]


def test_red_test_without_question_is_refused_and_writes_nothing():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r1")
        before = queue_file(d).read_bytes()
        r = run(d, "finish", "fila", "A", "--status", "pending",
                "--human-pending", ROUTE, "--evidence", "x")
        check("sai com 2", r.returncode == 2, f"{r.returncode} {r.stderr}")
        for flag in ("--route-kind", "--question", "--if-yes", "--if-no"):
            check(f"nomeia {flag}", flag in r.stderr, r.stderr)
        check("queue.yaml idêntica byte a byte", queue_file(d).read_bytes() == before)


def test_each_missing_piece_is_named_alone():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r2")
        before = queue_file(d).read_bytes()
        pieces = {"--route-kind": ["--route-kind", "external-block"],
                  "--question": ["--question", QUESTION],
                  "--if-yes": ["--if-yes", "volta para a fila"],
                  "--if-no": ["--if-no", "continua parado"],
                  "--if-no-item": ["--if-no-item", "nenhum"]}
        for missing in pieces:
            args = [a for flag, part in pieces.items() if flag != missing
                    for a in part]
            r = finish(d, *args)
            check(f"sem {missing}: recusa", r.returncode == 2, r.stderr)
            others = [f for f in pieces if f != missing]
            check(f"sem {missing}: nomeia só ele",
                  f"`{missing}`" in r.stderr
                  and not any(f"`{o}`" in r.stderr for o in others), r.stderr)
        r = finish(d, "--route-kind", "external-block", "--question",
                   "O acesso já existe, certo", "--if-yes", "a", "--if-no", "b",
                   "--if-no-item", "nenhum")
        check("pergunta sem `?` recusada", r.returncode == 2
              and "`--question`" in r.stderr, r.stderr)
        check("nada gravado", queue_file(d).read_bytes() == before)


def test_empty_human_pending_keeps_its_own_refusal():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r3")
        r = run(d, "finish", "fila", "A", "--status", "pending",
                "--human-pending", "", "--evidence", "x", "--repo", ".")
        check("vazio recusa dizendo que só o humano fecha",
              r.returncode == 2 and "só o humano" in r.stderr, r.stderr)


def test_full_call_opens_the_route():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r4")
        r = finish(d, *FULL)
        check("sai com 0", r.returncode == 0, r.stderr)
        it = item_a(d)
        check("human_pending gravado", it["human_pending"] == ROUTE, it)
        check("route_kind gravado", it.get("route_kind") == "external-block", it)
        check("owner_question gravada", it.get("owner_question") == QUESTION, it)
        summary = it.get("owner_summary") or {}
        check("se_sim e se_nao gravados",
              summary.get("se_sim") == "o item volta para a fila"
              and summary.get("se_nao") == "o item continua parado", summary)
        r = run(d, "finish", "fila", "A", "--status", "pending", "--evidence", "y",
                "--repo", ".")
        check("finish sem --human-pending mantém a rota e o tipo",
              r.returncode == 0 and item_a(d).get("route_kind") == "external-block"
              and item_a(d)["human_pending"] == ROUTE, r.stderr)


def test_invalid_route_kind_is_rejected_by_argparse():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r5")
        before = queue_file(d).read_bytes()
        r = finish(d, "--route-kind", "whatever", "--question", QUESTION,
                   "--if-yes", "a", "--if-no", "b", "--if-no-item", "nenhum")
        check("valor fora dos três recusado", r.returncode == 2
              and "route-kind" in r.stderr, r.stderr)
        check("nada gravado", queue_file(d).read_bytes() == before)


def test_validator_rejects_route_kind_outside_the_three():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r7")
        plan = yaml.safe_load(queue_file(d).read_text())
        plan["items"][0]["route_kind"] = "whatever"
        queue_file(d).write_text(yaml.safe_dump(plan, allow_unicode=True),
                                 encoding="utf-8")
        r = run(d, "validate", "fila", "--repo", ".")
        check("route_kind inválido: recusa", r.returncode == 2, r.stdout + r.stderr)
        check("a recusa nomeia route_kind", "route_kind" in r.stdout + r.stderr,
              r.stdout + r.stderr)
        del plan["items"][0]["route_kind"]
        queue_file(d).write_text(yaml.safe_dump(plan, allow_unicode=True),
                                 encoding="utf-8")
        r = run(d, "validate", "fila", "--repo", ".")
        check("fila sem a chave segue válida", r.returncode == 0, r.stdout + r.stderr)
        plan["items"][0]["route_kind"] = "open-question"
        queue_file(d).write_text(yaml.safe_dump(plan, allow_unicode=True),
                                 encoding="utf-8")
        r = run(d, "validate", "fila", "--repo", ".")
        check("valor válido passa", r.returncode == 0, r.stdout + r.stderr)


def answer_on_tty(d, *extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CEPA_RUN", "CEPA_UNTIL_RUN", "CEPA_AUTONOMOUS_RUN_ID", "CLAUDE_AUTONOMOUS_RUN_ID",
                        "CLAUDE_SESSION_ID", "CEPA_WT_CLAIM")}
    return on_tty([sys.executable, str(CEPA_PLAN), "answer", "fila", "A",
                   "--answer", "sim: o acesso já existe", "--no-commit",
                   "--repo", str(d), *extra], str(d), env=env)


def test_answer_closes_the_route_and_removes_route_kind_but_keep_does_not():
    with tempfile.TemporaryDirectory() as base:
        d = make_repo(base, "r6")
        check("rota aberta", finish(d, *FULL).returncode == 0)
        rc, out = answer_on_tty(d, "--keep")
        it = item_a(d)
        check("--keep: sai 0", rc == 0, out)
        check("--keep: route_kind e rota continuam",
              it.get("route_kind") == "external-block"
              and it["human_pending"] == ROUTE, it)
        rc, out = answer_on_tty(d)
        it = item_a(d)
        check("answer: sai 0", rc == 0, out)
        check("answer: human_pending nulo com a chave presente",
              "human_pending" in it and it["human_pending"] is None, it)
        check("answer: route_kind removido", "route_kind" not in it, it)


def main():
    print("cepa-queue finish --human-pending exige rota legível (CS-1)\n")
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
