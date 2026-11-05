#!/usr/bin/env python3
"""`cepa-plan ready` lists the items ready to be built now, across EVERY
single-track queue of the repo (owner, 2026-11-05: "os itens prontos para serem
construídos de todas as filas disponíveis").

`status` answers it for one queue and refuses to pick when there are several;
`ready` is the repo-wide view. "Ready" is the same rule `queue` uses with no
ceiling (build_batch): `pending`, no open human route, no unresolved
dependency, not reserved by a live session.

Against the real CLI, in a temporary git repo with three queues:

  - every queue listed, alphabetical, items in recorded order with position
  - human_pending / blocked / dependency on a pending item are NOT ready
  - a dependency on a ready item IS ready, and the line names it
  - a queue with nothing ready is one line with what holds it
  - a waves plan is not a queue and does not appear
  - a broken queue is warned on stderr BY NAME and skipped, exit stays 0
  - a queue stuck only on a pending dependency says "nada pronto"
  - `adiados` names every deferred item with build_batch's reason
  - --json carries `filas`, `prontos`, `total_prontos`
  - the launcher `cepa plan ready` reaches the same subcommand
  - no queue at all -> exit 2

Run with `python3 tests/test_cepa_plan_ready.py`.
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
FAILURES = []


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


def write_queue(root, name, items, mode="single-track"):
    d = root / ".claude" / "queues" / name
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": mode, "queue": name,
            "source": "teste", "items": items}
    (d / "queue.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                  encoding="utf-8")


def git_repo(tmp):
    root = Path(tmp) / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    return root


def build(tmp):
    root = git_repo(tmp)
    write_queue(root, "beta", [
        item("B-1", status="done"),
        item("B-2", human_pending="valide o login real"),
        item("B-3", status="blocked"),
        item("B-4", blocked_by=["B-3"]),          # waits on a blocked item
        item("B-5"),                              # ready
        item("B-6", blocked_by=["B-5"]),          # ready: B-5 enters first
        item("B-7", blocked_by=["B-1"]),          # ready: B-1 already done
    ])
    write_queue(root, "alpha", [
        item("A-1", status="done"),
        item("A-2", status="dropped"),
    ])
    write_queue(root, "gamma", [
        item("G-1", human_pending="aprove o PR"),
    ])
    write_queue(root, "delta", [
        item("D-1", blocked_by=["D-2"]),          # waits on a pending item below
        item("D-2"),
    ])
    write_queue(root, "waves", [item("W-1")], mode="parallel-waves")
    return root


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp)
        r = run(root, "ready", "--json")
        check("ready --json exit 0", r.returncode == 0, r.stderr)
        data = json.loads(r.stdout)
        names = [q["queue"] for q in data["filas"]]
        check("every single-track queue listed, alphabetical",
              names == ["alpha", "beta", "delta", "gamma"], names)
        check("waves plan is not a queue", "waves" not in names)
        beta = next(q for q in data["filas"] if q["queue"] == "beta")
        ready_ids = [p["id"] for p in beta["prontos"]]
        check("ready = pending without human route, block or pending dep",
              ready_ids == ["B-5", "B-6", "B-7"], ready_ids)
        check("positions are the recorded order",
              [p["posicao"] for p in beta["prontos"]] == [5, 6, 7],
              [p["posicao"] for p in beta["prontos"]])
        check("dependency on a ready item is kept, on a done one dropped",
              [p["blocked_by"] for p in beta["prontos"]] == [[], ["B-5"], []],
              [p["blocked_by"] for p in beta["prontos"]])
        check("pending count of the queue",
              beta["pendentes"] == 5, beta["pendentes"])
        check("items that wait on the owner are named",
              beta["esperam_dono"] == ["B-2", "B-3"], beta["esperam_dono"])
        check("total across queues", data["total_prontos"] == 3,
              data["total_prontos"])
        check("every ready item carries its why",
              all(p["why"] == "porque" for p in beta["prontos"]))

        # The owner asked for "um comando cepa": the launcher is the surface.
        r = subprocess.run(["sh", str(CEPA), "plan", "ready", "--json",
                            "--repo", str(root)],
                           capture_output=True, text=True, cwd=str(root))
        check("cepa plan ready (launcher) exit 0", r.returncode == 0, r.stderr)
        via_launcher = json.loads(r.stdout)
        check("cepa plan ready lists the same queues and total",
              [q["queue"] for q in via_launcher["filas"]] == ["alpha", "beta", "delta", "gamma"]
              and via_launcher["total_prontos"] == 3, r.stdout[:300])

        r = run(root, "ready")
        check("ready (text) exit 0", r.returncode == 0, r.stderr)
        out = r.stdout
        check("text header counts queues and items",
              "4 filas · 3 itens" in out, out.splitlines()[0])
        check("text lists the ready items with position",
              "    5. B-5 — item B-5" in out and "    6. B-6 — item B-6" in out
              and "    7. B-7 — item B-7" in out, out)
        check("text names the dependency that enters first",
              "espera: B-5 (entra antes neste lote)" in out, out)
        check("text does not list what is not ready",
              not any(f"{i} — item" in out for i in ("B-2", "B-3", "B-4", "G-1")),
              out)
        check("closed queue is one line saying so",
              "fila alpha · 0 de 0 pendentes prontos — fila fechada" in out, out)
        check("queue held by the owner names the items and the command",
              "fila gamma · 0 de 1 pendentes prontos — esperam você: G-1 "
              "(cepa until decide gamma)" in out, out)
        check("beta header counts ready over pending",
              "fila beta · 3 de 5 pendentes prontos" in out, out)
        check("queue stuck on a pending dependency says so",
              "fila delta · 0 de 2 pendentes prontos — nada pronto: os abertos "
              "esperam outro item ou estão reservados" in out, out)
        check("text does not list items stuck on a pending dependency",
              "D-1 — item" not in out and "D-2 — item" not in out, out)

        # A broken queue is warned and skipped, the others still show.
        (root / ".claude" / "queues" / "gamma" / "queue.yaml").write_text(
            "items: [\n", encoding="utf-8")
        r = run(root, "ready", "--json")
        check("broken queue: exit 0", r.returncode == 0, r.stderr)
        data = json.loads(r.stdout)
        check("broken queue: skipped, the others listed",
              [q["queue"] for q in data["filas"]] == ["alpha", "beta", "delta"],
              [q["queue"] for q in data["filas"]])
        check("broken queue: warned on stderr, by name",
              "aviso: fila gamma ilegível" in r.stderr, r.stderr)

        # Reserved by a live session: not ready. Orphan reservation: ready.
        beta_file = root / ".claude" / "queues" / "beta" / "queue.yaml"
        plan = yaml.safe_load(beta_file.read_text())
        import socket
        import os
        for it in plan["items"]:
            if it["id"] == "B-5":
                it["status"] = "in_progress"
                it["claimed_by"] = {"session_id": "s", "pid": os.getpid(),
                                    "hostname": socket.gethostname(),
                                    "cwd": str(root),
                                    "started_at": "2026-11-05T10:00:00+00:00"}
        beta_file.write_text(yaml.safe_dump(plan, allow_unicode=True))
        r = run(root, "ready", "--json")
        data = json.loads(r.stdout)
        beta = next(q for q in data["filas"] if q["queue"] == "beta")
        check("reserved by a live session: not ready, and its dependent waits",
              [p["id"] for p in beta["prontos"]] == ["B-7"],
              [p["id"] for p in beta["prontos"]])
        check("adiados names the deferred items with the reason",
              beta["adiados"] == [{"id": "B-2", "reason": "human_pending"},
                                  {"id": "B-3", "reason": "bloqueado-antes"},
                                  {"id": "B-4", "reason": "depende-de-adiado"},
                                  {"id": "B-5", "reason": "reservado"},
                                  {"id": "B-6", "reason": "depende-de-adiado"}],
              beta["adiados"])

    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        r = run(root, "ready")
        check("no queue at all: exit 2 and says who writes one",
              r.returncode == 2 and "/common:queue" in r.stderr, r.stderr)

    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ cepa-plan ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
