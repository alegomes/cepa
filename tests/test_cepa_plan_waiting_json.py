#!/usr/bin/env python3
"""`cepa queue waiting --json` returns queues, items, runs and totals as valid
JSON (spec docs/spec/decisoes-de-todas-as-filas.md, CS-5). Read only.

Against the real CLI, in a temporary git repo:

  - CS-5 red test, in the repo of CS-1 (queue `a` with a1 blocked and
    owner_question "Rodo X à mão?", queue `b` with b1 done and human_pending
    "Rotacionar o segredo"): exit 0, stdout parses as JSON as a whole,
    `filas[0].itens[0].id == "a1"`, `total_itens == 2` and the key `runs`
  - the top-level keys are exactly root, filas, total_itens, runs, and the
    second queue is `b` with b1
  - `runs` is a list even when `cepa-run pending` has nothing to say
  - stdout stays parseable when a queue is unreadable: the warning goes to
    stderr, never into the JSON
  - the launcher `cepa queue waiting --json` prints the same JSON

Before CS-1 (commit 42bc4df^) the subcommand did not exist and this test
fails on the exit code.

Run with `python3 tests/test_cepa_plan_waiting_json.py`.
"""
import json
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
CEPA = REPO / "common" / "bin" / "cepa"
FAILURES = []


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def run(repo, *args, launcher=False):
    cmd = ([str(CEPA), "queue"] if launcher
           else [sys.executable, str(CEPA_PLAN)]) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo))


def item(ident, status="pending", **extra):
    it = {"id": ident, "title": f"item {ident}", "why": "porque",
          "status": status, "blocked_by": [], "human_pending": None,
          "evidence": None}
    it.update(extra)
    return it


def write_queue(root, name, items):
    d = root / ".claude" / "queues" / name
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": "single-track", "queue": name,
            "source": "teste", "items": items}
    (d / "queue.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                  encoding="utf-8")


def cs1_repo(tmp):
    """The repo of the CS-1 red test, which CS-5 reuses."""
    root = Path(tmp) / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    write_queue(root, "b", [
        item("b1", status="done", human_pending="Rotacionar o segredo"),
        item("b2", status="done")])
    write_queue(root, "a", [
        item("a1", status="blocked", owner_question="Rodo X à mão?",
             evidence="travou no ambiente"),
        item("a2")])
    return root


def parse(stdout):
    try:
        return json.loads(stdout), None
    except ValueError as e:
        return None, str(e)


def red_test():
    print("CS-5: --json no repo do CS-1")
    with tempfile.TemporaryDirectory() as tmp:
        root = cs1_repo(tmp)
        p = run(root, "waiting", "--json")
        check("sai com 0", p.returncode == 0, p.stdout + p.stderr)
        data, err = parse(p.stdout)
        check("a saída inteira é JSON válido", data is not None, err or "")
        data = data if isinstance(data, dict) else {}
        filas = data.get("filas") or []
        first = (filas[0].get("itens") or [{}])[0] if filas else {}
        check("filas[0].itens[0].id == \"a1\"", first.get("id") == "a1",
              p.stdout)
        check("total_itens == 2", data.get("total_itens") == 2, p.stdout)
        check("tem a chave `runs`", "runs" in data, p.stdout)
        check("`runs` é uma lista, vazia sem run esperando",
              data.get("runs") == [], p.stdout)
        check("as chaves do topo são root, filas, total_itens e runs",
              set(data) == {"root", "filas", "total_itens", "runs"}, p.stdout)
        check("a segunda fila é `b`, com b1",
              len(filas) == 2 and filas[1].get("queue") == "b"
              and [i.get("id") for i in filas[1].get("itens") or []] == ["b1"],
              p.stdout)
        check("a1 traz motivo e pergunta",
              first.get("motivo") == "item travado"
              and first.get("pergunta") == "Rodo X à mão?", p.stdout)
        lp = run(root, "waiting", "--json", launcher=True)
        check("o lançador `cepa queue waiting --json` imprime o mesmo JSON",
              lp.returncode == 0 and parse(lp.stdout)[0] == parse(p.stdout)[0],
              lp.stdout + lp.stderr)


def unreadable_stays_out_of_stdout():
    print("fila ilegível: aviso no stderr, stdout continua JSON")
    with tempfile.TemporaryDirectory() as tmp:
        root = cs1_repo(tmp)
        bad = root / ".claude" / "queues" / "quebrada"
        bad.mkdir(parents=True)
        (bad / "queue.yaml").write_text("items: [: ::\n", encoding="utf-8")
        p = run(root, "waiting", "--json")
        check("sai com 0", p.returncode == 0, p.stdout + p.stderr)
        data, err = parse(p.stdout)
        check("stdout continua JSON válido", isinstance(data, dict), err or "")
        check("o aviso vai para o stderr",
              "aviso: fila quebrada ilegível" in p.stderr
              and "aviso" not in p.stdout, p.stdout + p.stderr)
        check("o total não muda por causa da fila ilegível",
              isinstance(data, dict) and data.get("total_itens") == 2, p.stdout)


if __name__ == "__main__":
    red_test()
    unreadable_stays_out_of_stdout()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\n✓ tudo passou")
