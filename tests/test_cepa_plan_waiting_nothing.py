#!/usr/bin/env python3
"""`cepa plan waiting` with nothing waiting says so in one line and exits 0;
with no queue at all it exits 2 (spec docs/spec/decisoes-de-todas-as-filas.md,
CS-4). Read only.

"Nothing waiting" means: no item line in any queue, no route already answered
"não" being counted, no run waiting, and nothing hidden from the list (an
unreadable queue or a failed `cepa until pending`). When something is hidden,
the command cannot claim there is nothing, so it keeps the counter header.

Against the real CLI, in a temporary git repo:

  - CS-4 red test: one queue with only `done` items without a route and no
    run pending → stdout is exactly "nada espera você", exit 0
  - no `.claude/queues/` → exit 2 (and no "nada espera você")
  - the launcher `cepa plan waiting` reaches the same subcommand
  - a route answered "não" is still counted: not "nada espera você"
  - an unreadable queue, or a failed `cepa until pending`, keeps the header
  - --json keeps its shape (empty `filas`, `total_itens` 0, `runs` [])

Run with `python3 tests/test_cepa_plan_waiting_nothing.py`.
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
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
CEPA = REPO / "common" / "bin" / "cepa"
NOTHING = "nada espera você"
FAILURES = []


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def run(repo, *args, launcher=False, plan=CEPA_PLAN):
    cmd = ([str(CEPA), "plan"] if launcher
           else [sys.executable, str(plan)]) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo))


def item(ident, status="done", **extra):
    it = {"id": ident, "title": f"item {ident}", "why": "porque",
          "status": status, "blocked_by": [], "human_pending": None,
          "evidence": "feito"}
    it.update(extra)
    return it


def write_queue(root, name, items):
    d = root / ".claude" / "queues" / name
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": "single-track", "queue": name,
            "source": "teste", "items": items}
    (d / "queue.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                  encoding="utf-8")


def git_repo(tmp):
    root = Path(tmp) / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    return root


def red_test():
    print("CS-4: fila só de itens `done` sem rota, nenhum run pendente")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "p", [item("p1"), item("p2"), item("p3")])
        p = run(root, "waiting")
        check("sai com 0", p.returncode == 0, p.stderr)
        check("imprime só \"nada espera você\", numa linha",
              p.stdout == NOTHING + "\n", repr(p.stdout))
        check("sem aviso no stderr", p.stderr == "", p.stderr)
        lp = run(root, "waiting", launcher=True)
        check("o lançador `cepa plan waiting` diz o mesmo",
              lp.returncode == 0 and lp.stdout == NOTHING + "\n",
              lp.stdout + lp.stderr)
        j = run(root, "waiting", "--json")
        try:
            data = json.loads(j.stdout)
        except ValueError:
            data = None
        check("--json continua JSON, com filas vazias, 0 itens e runs vazio",
              j.returncode == 0 and isinstance(data, dict)
              and data.get("filas") == [] and data.get("total_itens") == 0
              and data.get("runs") == [] and NOTHING not in j.stdout,
              j.stdout)

    print("CS-4: sem nenhuma fila")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        p = run(root, "waiting")
        check("sem .claude/queues sai com 2", p.returncode == 2,
              p.stdout + p.stderr)
        check("e não diz \"nada espera você\"",
              NOTHING not in p.stdout + p.stderr, p.stdout + p.stderr)
        (root / ".claude" / "queues").mkdir(parents=True)
        p = run(root, "waiting")
        check(".claude/queues vazio também sai com 2", p.returncode == 2,
              p.stdout + p.stderr)


def not_nothing():
    print("quando há algo, ou algo escondido, não diz \"nada espera você\"")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "p", [item("p1", status="blocked",
                                     owner_question="Destravo p1?")])
        p = run(root, "waiting")
        check("com item esperando, mantém o cabeçalho",
              p.returncode == 0 and NOTHING not in p.stdout
              and p.stdout.startswith("esperam você · 1 filas · 1 itens"),
              p.stdout)

    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "p", [item(
            "p1", status="blocked", owner_question="Destravo p1?",
            evidence="Resposta do dono em 2026-11-18: não: deixa\n\ntravou")])
        p = run(root, "waiting")
        check("só rota respondida \"não\": é contada, não \"nada\"",
              p.returncode == 0 and NOTHING not in p.stdout
              and "que você já respondeu \"não\"" in p.stdout, p.stdout)

    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "p", [item("p1")])
        bad = root / ".claude" / "queues" / "quebrada"
        bad.mkdir(parents=True)
        (bad / "queue.yaml").write_text("items: [: ::\n", encoding="utf-8")
        p = run(root, "waiting")
        check("fila ilegível: não afirma \"nada\", mantém o cabeçalho e avisa",
              p.returncode == 0 and NOTHING not in p.stdout
              and p.stdout.startswith("esperam você · 0 filas · 0 itens")
              and "aviso: fila quebrada ilegível" in p.stderr,
              p.stdout + p.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "p", [item("p1")])
        plugin = Path(tmp) / "plugin"
        (plugin / "bin").mkdir(parents=True)
        for d in ("hooks", "_vendor"):
            (plugin / d).symlink_to(REPO / "common" / d)
        (plugin / "bin" / "cepa-plan").write_text(CEPA_PLAN.read_text())
        (plugin / "bin" / "cepa-until").write_text(
            "import sys\nsys.stderr.write('boom')\nsys.exit(1)\n")
        p = run(root, "waiting", plan=plugin / "bin" / "cepa-plan")
        check("`cepa until pending` falhou: não afirma \"nada\" e avisa",
              p.returncode == 0 and NOTHING not in p.stdout
              and p.stdout.startswith("esperam você · 0 filas · 0 itens")
              and "aviso: runs fora da lista" in p.stderr,
              p.stdout + p.stderr)


if __name__ == "__main__":
    red_test()
    not_nothing()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\n✓ tudo passou")
