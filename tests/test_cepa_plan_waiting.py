#!/usr/bin/env python3
"""`cepa queue waiting` lists, grouped by queue, the items waiting on the owner
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
  - the launcher `cepa queue waiting` reaches the same subcommand

Run with `python3 tests/test_cepa_plan_waiting.py`.
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
        check("o lançador `cepa queue waiting` chega no mesmo subcomando",
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


def output_shape():
    print("cabeçalho, numeração, filas sem nada, --json")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        write_queue(root, "a", [
            "não é um item",
            item("a1"),
            item("a2", status="blocked", human_pending="Rota da a2"),
            item("a3", status="blocked")])
        write_queue(root, "b", [
            item("b1", status="done", human_pending="Rotacionar o segredo")])
        write_queue(root, "vazia", [item("v1"), item("v2", status="done")])
        write_queue(root, "ondas", [
            item("w1", status="blocked", owner_question="Onda?")],
            mode="parallel-waves")
        p = run(root, "waiting")
        out = p.stdout
        check("sai com 0 mesmo com item que não é dicionário",
              p.returncode == 0, p.stderr)
        check("cabeçalho com filas e itens",
              out.splitlines()[0] == "esperam você · 2 filas · 3 itens", out)
        check("linha com posição, id, motivo e pergunta",
              "    3. a2 — item travado: Rota da a2" in out.splitlines(), out)
        check("travado sem pergunta nem motivo diz que não há motivo",
              "    4. a3 — item travado: sem motivo registrado" in out.splitlines(),
              out)
        check("fila sem nada esperando não aparece", "vazia" not in out, out)
        check("plano em ondas não é fila", "ondas" not in out and "w1" not in out,
              out)
        j = run(root, "waiting", "--json")
        check("--json sai com 0", j.returncode == 0, j.stderr)
        try:
            data = json.loads(j.stdout)
        except ValueError:
            data = {}
        filas = data.get("filas") or []
        check("--json traz só as filas com itens, na ordem",
              [f.get("queue") for f in filas] == ["a", "b"], j.stdout)
        check("--json traz o total de itens", data.get("total_itens") == 3,
              j.stdout)
        check("--json traz root e o caminho de cada fila",
              data.get("root") == str(root.resolve())
              and filas and filas[0].get("path", "").endswith(
                  "/.claude/queues/a/queue.yaml"), j.stdout)
        check("--json guarda os acentos como texto",
              "tarefa que sobrou em item concluído" in j.stdout, j.stdout)
        sec = lines_after(out, "fila a") or []
        check("itens na ordem da fila",
              [l.split()[1] for l in sec] == ["a2", "a3"], out)
        check("--json traz id, posição, motivo e pergunta",
              filas and filas[0]["itens"][0] == {
                  "posicao": 3, "id": "a2", "motivo": "item travado",
                  "pergunta": "Rota da a2"}, j.stdout)


def no_queue_and_unreadable():
    print("sem fila nenhuma, fila ilegível")
    with tempfile.TemporaryDirectory() as tmp:
        root = git_repo(tmp)
        p = run(root, "waiting")
        check("sem .claude/queues sai com 2", p.returncode == 2,
              p.stdout + p.stderr)
        check("sem fila diz quem escreve a fila",
              "nenhuma fila em" in p.stderr and "/common:queue" in p.stderr,
              p.stderr)
        only_bad = root / ".claude" / "queues" / "so-quebrada"
        only_bad.mkdir(parents=True)
        (only_bad / "queue.yaml").write_text("items: [: ::\n", encoding="utf-8")
        p = run(root, "waiting")
        check("só filas ilegíveis: avisa e sai com 0, não com 2",
              p.returncode == 0 and "aviso: fila so-quebrada ilegível" in p.stderr
              and "nenhuma fila em" not in p.stderr, p.stdout + p.stderr)
        import shutil
        shutil.rmtree(only_bad)
        write_queue(root, "boa", [item("g1", status="blocked",
                                       owner_question="Destravo g1?")])
        bad = root / ".claude" / "queues" / "quebrada"
        bad.mkdir(parents=True)
        (bad / "queue.yaml").write_text("items: [: ::\n", encoding="utf-8")
        p = run(root, "waiting")
        check("fila ilegível não derruba o comando", p.returncode == 0, p.stderr)
        check("fila ilegível avisada pelo nome no stderr",
              "aviso: fila quebrada ilegível" in p.stderr, p.stderr)
        check("a fila boa continua listada", "g1" in p.stdout, p.stdout)


if __name__ == "__main__":
    red_test()
    reasons_and_fallbacks()
    output_shape()
    no_queue_and_unreadable()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\n✓ tudo passou")
