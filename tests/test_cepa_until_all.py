#!/usr/bin/env python3
"""`cepa until --all` (spec `until-todas-as-filas`).

CS-1: `cepa until --all --for 8h --dry-run` lists the ready items of every
queue, grouped by queue and in the order of `cepa plan ready`, and exits 0
without executing anything. Before the flag existed the call exited 2: the
queue name was a required positional.

Against the real CLI (`cepa until`, through the launcher), in a temporary git
repo with two queues, `a` and `b`, one ready item each, and a fake `claude`
that records any call (none may happen).

Run with `python3 tests/test_cepa_until_all.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until as base  # noqa: E402

import yaml  # noqa: E402

check = base.check
FAILURES = base.FAILURES
REPO = Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"


def _queue(root, name, items):
    d = root / ".claude" / "queues" / name
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": "single-track", "queue": name,
            "source": "teste", "items": items}
    (d / "queue.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                  encoding="utf-8")
    return d / "queue.yaml"


def _repo(tmp, queues):
    root = Path(tmp) / "repo"
    root.mkdir()
    paths = {n: _queue(root, n, its) for n, its in queues.items()}
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)
    return root, paths


def _run(tmp, root, args, via_launcher=True):
    binv = base.fake_claude(tmp, "pass")
    env = dict(os.environ)
    env["PATH"] = f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(Path(tmp) / "nenhum.yaml")
    calls = Path(tmp) / "chamadas.jsonl"
    env["FAKE_CHAMADAS"] = str(calls)
    env["CEPA_UNTIL_LEITOR"] = "off"
    env["CEPA_WORKTREE_HOME"] = str(Path(tmp) / "worktrees")
    cmd = ([str(CEPA), "until"] if via_launcher
           else [sys.executable, str(CEPA_UNTIL)])
    p = subprocess.run(cmd + list(args) + ["--repo", str(root)],
                       capture_output=True, text=True, env=env, timeout=120,
                       stdin=subprocess.DEVNULL)
    return p, (calls.read_text().splitlines() if calls.exists() else [])


def _branches(root):
    return subprocess.run(["git", "branch", "--list", "until/*"], cwd=root,
                          capture_output=True, text=True).stdout.split()


def test_dry_run_lists_every_queue_in_ready_order():
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"b": [base.item("b1")],
                                  "a": [base.item("a1")]})
        before = {n: p.read_text() for n, p in paths.items()}
        p, calls = _run(tmp, root, ["--all", "--for", "8h", "--dry-run"])
        out = p.stdout
        check("--all --dry-run sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-400:]}")
        check("...traz os dois ids", "a1" in out and "b1" in out, out[-800:])
        check("...a fila a antes da b (ordem do `cepa plan ready`)",
              "a1" in out and "b1" in out and out.index("a1") < out.index("b1"),
              out[-800:])
        check("...agrupa por fila: o nome de cada fila precede o seu item",
              "a" in out and out.rfind(" a ", 0, out.index("a1")) >= 0
              and out.rfind(" b ", 0, out.index("b1")) > out.index("a1"),
              out[-800:])
        check("...não chama o claude", not calls, str(calls))
        check("...não toca nenhuma fila",
              all(paths[n].read_text() == before[n] for n in paths))
        check("...não cria branch until/*", not _branches(root),
              str(_branches(root)))


def test_dry_run_order_is_the_order_of_plan_ready():
    """The same order `cepa plan ready --json` gives, item order inside a
    queue included, and a queue with nothing ready does not list an item."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {
            "zeta": [base.item("z1"), base.item("z2")],
            "alfa": [base.item("x1", status="done"), base.item("x2")],
            "meio": [base.item("m1", human_pending="validar à mão")],
        })
        ready = json.loads(subprocess.run(
            [sys.executable, str(REPO / "common" / "bin" / "cepa-plan"),
             "ready", "--repo", str(root), "--json"],
            capture_output=True, text=True, check=True).stdout)
        expected = [l["id"] for q in ready["filas"] for l in q["prontos"]]
        p, _ = _run(tmp, root, ["--all", "--for", "8h", "--dry-run"])
        out = p.stdout
        pos = [out.find(i) for i in expected]
        check("a ordem da saída é a do `cepa plan ready`",
              p.returncode == 0 and all(x >= 0 for x in pos) and pos == sorted(pos),
              f"esperado {expected}, posições {pos}\n{out[-800:]}")
        check("...item feito e item à espera do dono não aparecem como prontos",
              "x1 " not in out and "m1 —" not in out, out[-800:])


def test_all_and_queue_name_together_are_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {"a": [base.item("a1")]})
        p, calls = _run(tmp, root, ["a", "--all", "--for", "8h", "--dry-run"])
        check("nome da fila + --all é recusado com 2", p.returncode == 2,
              f"rc={p.returncode}")
        check("...e a recusa nomeia o --all", "--all" in p.stderr, p.stderr[-400:])
        check("...sem chamar o claude", not calls)


def test_neither_queue_nor_all_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {"a": [base.item("a1")]})
        p, _ = _run(tmp, root, ["--for", "8h", "--dry-run"])
        check("sem fila e sem --all é recusado com 2", p.returncode == 2,
              f"rc={p.returncode}")
        check("...e a recusa sugere o --all", "--all" in p.stderr, p.stderr[-400:])


def test_all_without_dry_run_is_refused_until_cs2():
    """CS-1 ships only the plan of the run. Until CS-2 executes it, a real
    `--all` must refuse instead of running ONE queue or nothing silently."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1")]})
        before = paths["a"].read_text()
        p, calls = _run(tmp, root, ["--all", "--for", "1h", "--no-verify"])
        check("--all sem --dry-run é recusado com 2", p.returncode == 2,
              f"rc={p.returncode} out={p.stdout[-300:]}")
        check("...sem chamar o claude nem tocar a fila",
              not calls and paths["a"].read_text() == before)
        check("...e sem criar branch", not _branches(root))


def test_single_queue_dry_run_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {"a": [base.item("a1")]})
        p, calls = _run(tmp, root, ["a", "--for", "2h", "--dry-run",
                                    "--no-verify"])
        check("`cepa until a --dry-run` segue saindo com 0", p.returncode == 0,
              p.stderr[-400:])
        check("...e nomeia o item", "a1" in p.stdout)


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        print(t.__name__)
        t()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        return 1
    print(f"\n✓ {len(tests)} testes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
