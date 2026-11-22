#!/usr/bin/env python3
"""`cepa plan waiting` lists, grouped by queue, the items waiting on the owner
across every single-track queue (spec docs/spec/decisoes-de-todas-as-filas.md,
CS-1). Read only.

An item waits on the owner when it is `blocked` ("item travado"), carries an
open `human_pending` while not closed ("tarefa só sua"), or is `done` with a
`human_pending` left ("tarefa que sobrou em item concluído") — the three
reasons cepa-until already uses for the owner, translated. Each line: id,
reason, the question cut to one line.

Against the real CLI, in a temporary git repo:

  - CS-1 red test: queue `a` (a1 blocked, owner_question "Rodo X à mão?")
    before queue `b` (b1 done, human_pending "Rotacionar o segredo"), exit 0
  - an open route on a pending item is "tarefa só sua"; blocked wins over
    an open route on the same item (same precedence as build_batch)
  - the question falls back to human_pending, then to the blocked reason
  - pending/in_progress/done items with no route are not listed
  - a long question is cut to one line
  - the launcher `cepa plan waiting` reaches the same subcommand

Run with `python3 tests/test_cepa_plan_waiting.py`.
"""
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


def run(repo, *args, launcher=False):
    cmd = ([str(CEPA), "plan"] if launcher
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


def git_repo(tmp):
    root = Path(tmp) / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    return root


def lines_after(out, header):
    """The lines of the section opened by `header`, up to the next blank line."""
    lines = out.splitlines()
    for i, l in enumerate(lines):
        if l.strip() == header:
            body = []
            for x in lines[i + 1:]:
                if not x.strip():
                    break
                body.append(x)
            return body
    return None


def red_test():
    print("CS-1: a1 travado em `a`, b1 com tarefa sobrando em `b`")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "b", [
            item("b1", status="done", human_pending="Rotacionar o segredo"),
            item("b2", status="done")])
        write_queue(root, "a", [
            item("a1", status="blocked", owner_question="Rodo X à mão?",
                 evidence="travou no ambiente"),
            item("a2")])
        p = run(root, "waiting")
        check("sai com 0", p.returncode == 0, p.stderr)
        out = p.stdout
        ia, ib = out.find("fila a"), out.find("fila b")
        check("seção a antes de b", 0 <= ia < ib, out)
        sec_a = lines_after(out, "fila a") or []
        sec_b = lines_after(out, "fila b") or []
        check("a1 com motivo e pergunta",
              any("a1" in l and "item travado" in l and "Rodo X à mão?" in l
                  for l in sec_a), out)
        check("b1 com motivo e pergunta",
              any("b1" in l and "tarefa que sobrou em item concluído" in l
                  and "Rotacionar o segredo" in l for l in sec_b), out)
        check("a2 pendente sem rota não aparece", "a2" not in out, out)
        check("b2 concluído sem rota não aparece", "b2" not in out, out)
        lp = run(root, "waiting", launcher=True)
        check("o lançador `cepa plan waiting` chega no mesmo subcomando",
              lp.returncode == 0 and lp.stdout == out, lp.stderr)


def reasons_and_fallbacks():
    print("motivos e de onde vem a pergunta")
    long_q = "Rotaciono " + "o segredo antigo de produção " * 20 + "agora?"
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "c", [
            item("c1", human_pending="Validar o login real"),
            item("c2", status="blocked", human_pending="Rota aberta",
                 owner_question="Destravo c2?"),
            item("c3", status="blocked",
                 owner_summary={"impede": "falta a credencial do portal"}),
            item("c4", status="in_progress", human_pending="Aprovar o PR",
                 owner_question=long_q),
            item("c5", status="dropped", human_pending="Esquecida"),
        ])
        p = run(root, "waiting")
        out = p.stdout
        check("sai com 0", p.returncode == 0, p.stderr)
        sec = lines_after(out, "fila c") or []
        check("rota aberta em pendente é tarefa só sua, com a rota",
              any("c1" in l and "tarefa só sua" in l and "Validar o login real" in l
                  for l in sec), out)
        check("travado ganha de rota aberta, pergunta do agente",
              any("c2" in l and "item travado" in l and "Destravo c2?" in l
                  for l in sec), out)
        check("travado sem pergunta usa o motivo do travamento",
              any("c3" in l and "falta a credencial do portal" in l for l in sec),
              out)
        c4 = [l for l in sec if "c4" in l]
        check("pergunta longa cortada numa linha",
              len(c4) == 1 and len(c4[0]) < 200 and "…" in c4[0], out)
        check("descartado não aparece", "c5" not in out, out)


if __name__ == "__main__":
    red_test()
    reasons_and_fallbacks()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\n✓ tudo passou")
