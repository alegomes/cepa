#!/usr/bin/env python3
"""CS-6 of decisoes-de-todas-as-filas: `cepa plan ready` no longer calls a queue
"tudo concluído ou descartado" when a `done` item still left a task for the
owner (an open `human_pending`). Owner, 2026-11-20 (fb-20261120-1): the pyyaml
queue showed as closed with two questions hidden in CS-4 and CS-6.

Against the real CLI, in a temporary git repo:

  - queue `p`: every item `done`, two with an open route -> "fila fechada, 2
    tarefas esperam você (cepa until decide p)", and NOT "tudo concluído ou
    descartado" on p's line
  - queue `s`: one leftover task -> singular "1 tarefa espera você"
  - queue `q`: done/dropped with no route -> still "tudo concluído ou descartado"
  - queue `r`: the only leftover route was answered "não" by the owner -> not
    counted as waiting (decide does not ask it again), the line says so
  - a route on a `dropped` item is not a leftover task, nor one on an
    open (`pending`/`blocked`) item
  - --json carries `tarefas_sobrando` per queue
  - the launcher `cepa plan ready` prints the same line

Run with `python3 tests/test_cepa_plan_ready_closed_leftover.py`.
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


def item(ident, status="done", human_pending=None, evidence=None):
    return {"id": ident, "title": f"item {ident}", "why": "porque",
            "status": status, "blocked_by": [],
            "human_pending": human_pending, "evidence": evidence}


def write_queue(root, name, items):
    d = root / ".claude" / "queues" / name
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": "single-track", "queue": name,
            "source": "teste", "items": items}
    (d / "queue.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                  encoding="utf-8")


def line_of(out, queue):
    return next((l for l in out.splitlines()
                 if l.startswith(f"fila {queue} ")), "")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
        write_queue(root, "p", [
            item("p1", human_pending="Rotacionar o segredo"),
            item("p2"),
            item("p3", human_pending="Validar a tela à mão"),
        ])
        write_queue(root, "q", [item("q1"), item("q2", status="dropped")])
        write_queue(root, "r", [
            item("r1", human_pending="Medir depois",
                 evidence="Resposta do dono em 2026-11-18: não: depois.\n\nfeito"),
        ])
        write_queue(root, "s", [
            item("s1", human_pending="Aprovar o PR"),
            item("s2", status="dropped", human_pending="rota de item descartado"),
        ])
        # An OPEN item with a route is "esperam você", not a leftover task of
        # a done item: tarefas_sobrando counts only `done` (proof survivor M2).
        write_queue(root, "t", [
            item("t1", status="pending", human_pending="Rodar à mão"),
            item("t2", status="blocked", human_pending="Pedir a credencial"),
            item("t3", human_pending="Aprovar o PR"),
        ])

        r = subprocess.run([sys.executable, str(CEPA_PLAN), "ready",
                            "--repo", str(root)],
                           capture_output=True, text=True, cwd=str(root))
        check("ready exit 0", r.returncode == 0, r.stderr)
        out = r.stdout
        p = line_of(out, "p")
        check("p: closed queue names the 2 leftover tasks and the command",
              p == "fila p · 0 de 0 pendentes prontos — fila fechada, 2 tarefas "
                   "esperam você (cepa until decide p)", repr(p))
        check("p: does not say 'tudo concluído ou descartado'",
              "tudo concluído ou descartado" not in p, repr(p))
        s = line_of(out, "s")
        check("s: one leftover task is singular, dropped route not counted",
              s == "fila s · 0 de 0 pendentes prontos — fila fechada, 1 tarefa "
                   "espera você (cepa until decide s)", repr(s))
        q = line_of(out, "q")
        check("q: closed with no route still says tudo concluído ou descartado",
              q == "fila q · 0 de 0 pendentes prontos — fila fechada: tudo "
                   "concluído ou descartado", repr(q))
        rr = line_of(out, "r")
        check("r: a route answered 'não' is not a task waiting on the owner",
              "esperam você" not in rr and "espera você" not in rr, repr(rr))
        check("r: nor is the queue 'tudo concluído', the route is still open",
              rr == "fila r · 0 de 0 pendentes prontos — fila fechada: 1 tarefa "
                    "que você respondeu não (cepa until decide r)", repr(rr))

        r = subprocess.run([sys.executable, str(CEPA_PLAN), "ready", "--json",
                            "--repo", str(root)],
                           capture_output=True, text=True, cwd=str(root))
        data = {q["queue"]: q for q in json.loads(r.stdout)["filas"]}
        check("--json carries tarefas_sobrando per queue",
              {k: v.get("tarefas_sobrando") for k, v in data.items()}
              == {"p": 2, "q": 0, "r": 0, "s": 1, "t": 1},
              {k: v.get("tarefas_sobrando") for k, v in data.items()})
        check("--json carries tarefas_respondidas_nao per queue",
              {k: v.get("tarefas_respondidas_nao") for k, v in data.items()}
              == {"p": 0, "q": 0, "r": 1, "s": 0, "t": 0},
              {k: v.get("tarefas_respondidas_nao") for k, v in data.items()})

        r = subprocess.run(["sh", str(CEPA), "plan", "ready",
                            "--repo", str(root)],
                           capture_output=True, text=True, cwd=str(root))
        check("launcher `cepa plan ready` prints the same p line",
              line_of(r.stdout, "p") == p and r.returncode == 0,
              repr(line_of(r.stdout, "p")) + r.stderr)

    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        return 1
    print("\n✓ todos os checks passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
