#!/usr/bin/env python3
"""The header of `cepa-queue ready` says how many items wait on the owner
(fb-20261120-5).

The header counts only what an agent can build alone now. With one `pending`
item behind an open `human_pending` route and one `blocked` item it said
"0 itens", and the owner read "nothing pending". Now the header adds
`· esperam você: 1 pendente e 1 bloqueado` when any item waits on him.

Against the real CLI, in a temporary git repo:

  - one queue: the exact first line, singular forms
  - two queues: counts summed, plural forms
  - only pending-with-route, only blocked: no "e 0 ..."
  - nothing waiting: header exactly as before, no suffix
  - blocked + human_pending counts once (bloqueado); done with a leftover
    route, dropped, and a pending held only by a dependency count in neither
  - --json: top-level `total_esperam_dono`, per-queue `esperam_dono_pendentes`
    and `esperam_dono_bloqueados`; `esperam_dono` id list unchanged

Run with `python3 tests/test_cepa_plan_ready_header_waiting.py`.
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
FAILURES = []
SEP = " · "


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def run(repo, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args),
                          capture_output=True, text=True, cwd=str(repo))


def item(ident, status="pending", human_pending=None, blocked_by=()):
    return {"id": ident, "title": f"item {ident}", "why": "porque",
            "status": status, "blocked_by": list(blocked_by),
            "human_pending": human_pending, "evidence": None}


def write_queue(root, name, items):
    d = root / ".claude" / "queues" / name
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": "single-track", "queue": name,
            "source": "teste", "items": items}
    (d / "queue.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                  encoding="utf-8")


def repo_with(tmp, queues):
    root = Path(tmp) / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    for name, items in queues.items():
        write_queue(root, name, items)
    return root


def first_line(root):
    r = run(root, "ready")
    return r.stdout.splitlines()[0] if r.stdout else "", r


def main():
    # 1. one pending-with-route + one blocked, nothing ready.
    with tempfile.TemporaryDirectory() as tmp:
        root = repo_with(tmp, {"q": [
            item("Q-1", human_pending="valide o login"),
            item("Q-2", status="blocked"),
        ]})
        line, r = first_line(root)
        check("1 pendente e 1 bloqueado: exact header",
              line == "prontos para construir · 1 filas · 0 itens · "
                      "esperam você: 1 pendente e 1 bloqueado", line)
        check("exit 0", r.returncode == 0, r.stderr)

    # 2. two queues, summed, plural.
    with tempfile.TemporaryDirectory() as tmp:
        root = repo_with(tmp, {
            "a": [item("A-1", human_pending="x"), item("A-2", human_pending="y"),
                  item("A-3", status="blocked")],
            # `b` waits too, with different counts: a max() over the queues,
            # or the two counts swapped, cannot give 3 and 4.
            "b": [item("B-0", human_pending="z"),
                  item("B-1", status="blocked"),
                  item("B-2", status="blocked"),
                  item("B-3", status="blocked")],
        })
        line, _ = first_line(root)
        check("two queues summed, plural forms",
              line == "prontos para construir · 2 filas · 0 itens · "
                      "esperam você: 3 pendentes e 4 bloqueados", line)

    # 3. only one kind.
    with tempfile.TemporaryDirectory() as tmp:
        root = repo_with(tmp, {"q": [item("Q-1", human_pending="x")]})
        line, _ = first_line(root)
        check("only pending-with-route: no 'e 0 bloqueados'",
              line == "prontos para construir · 1 filas · 0 itens · "
                      "esperam você: 1 pendente", line)
    with tempfile.TemporaryDirectory() as tmp:
        root = repo_with(tmp, {"q": [item("Q-1", status="blocked"),
                                     item("Q-2", status="blocked")]})
        line, _ = first_line(root)
        check("only blocked: no '0 pendentes e'",
              line == "prontos para construir · 1 filas · 0 itens · "
                      "esperam você: 2 bloqueados", line)

    # 4. nothing waiting: header unchanged.
    with tempfile.TemporaryDirectory() as tmp:
        root = repo_with(tmp, {"q": [item("Q-1"), item("Q-2")]})
        line, _ = first_line(root)
        check("only ready items: no suffix",
              line == "prontos para construir · 1 filas · 2 itens", line)
    with tempfile.TemporaryDirectory() as tmp:
        root = repo_with(tmp, {"q": [item("Q-1", status="done")]})
        line, _ = first_line(root)
        check("only done items: no suffix",
              line == "prontos para construir · 1 filas · 0 itens", line)

    # 5. counted once / not counted.
    with tempfile.TemporaryDirectory() as tmp:
        root = repo_with(tmp, {"q": [
            item("Q-2", status="done", human_pending="resto"),
            item("Q-3", status="dropped"),
            item("Q-5"),
            item("Q-4", blocked_by=["Q-5"]),
            item("Q-1", status="blocked", human_pending="x"),
        ]})
        line, _ = first_line(root)
        check("blocked+route once; done/dropped/dependency-held not counted",
              line == "prontos para construir · 1 filas · 2 itens · "
                      "esperam você: 1 bloqueado", line)

    # 6. --json.
    with tempfile.TemporaryDirectory() as tmp:
        root = repo_with(tmp, {
            # 2 and 1, not 1 and 1: swapped counts must show.
            "a": [item("A-1", human_pending="x"),
                  item("A-3", human_pending="y"),
                  item("A-2", status="blocked")],
            "b": [item("B-1")],
        })
        r = run(root, "ready", "--json")
        data = json.loads(r.stdout)
        check("json: total_esperam_dono",
              data.get("total_esperam_dono") == {"pendentes": 2, "bloqueados": 1},
              data.get("total_esperam_dono"))
        check("json: total_prontos unchanged", data["total_prontos"] == 1,
              data["total_prontos"])
        qa = next(q for q in data["filas"] if q["queue"] == "a")
        qb = next(q for q in data["filas"] if q["queue"] == "b")
        check("json: per-queue counts",
              qa.get("esperam_dono_pendentes") == 2
              and qa.get("esperam_dono_bloqueados") == 1
              and qb.get("esperam_dono_pendentes") == 0
              and qb.get("esperam_dono_bloqueados") == 0, (qa, qb))
        check("json: esperam_dono id list unchanged",
              qa["esperam_dono"] == ["A-1", "A-3", "A-2"], qa["esperam_dono"])
    with tempfile.TemporaryDirectory() as tmp:
        root = repo_with(tmp, {"q": [item("Q-1")]})
        data = json.loads(run(root, "ready", "--json").stdout)
        check("json: total_esperam_dono present with zeros",
              data.get("total_esperam_dono") == {"pendentes": 0, "bloqueados": 0},
              data.get("total_esperam_dono"))

    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ cepa-queue ready header: esperam você")
    return 0


if __name__ == "__main__":
    sys.exit(main())
