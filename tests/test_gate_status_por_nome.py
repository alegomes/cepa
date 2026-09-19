#!/usr/bin/env python3
"""Regressão: `twg ... --transition-id "<NOME DO STATUS>"` nos gates de Jira.

A CLI `twg` aceita o NOME do status no lugar do id da transição. O `_jiramut`
só baixava a caixa do nome, então "In Review" chegava aos gates como
`in review`, que não é chave lógica nenhuma. O `acceptance-gate` lia isso como
movimento lateral e LIBERAVA um card de auditoria incompleta rumo a Review
(reproduzido em 2026-09-19). O `merge-truth-gate` tinha o mesmo furo para
qualquer nome de status de fechamento que não fosse literalmente "done"
(ex.: "Concluído").

Contrato:
  - o nome do status vira chave lógica pelo `status_map` do board-flow.yaml
    (nome técnico → chave), ou pela forma normalizada (espaço/hífen → `_`);
  - nome que não resolve para chave conhecida = alvo NÃO resolvido, e o
    acceptance-gate barra por padrão (config ruim nunca abre gate).

Rode com `python3 tests/test_gate_status_por_nome.py`.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ACCEPT = REPO / "common" / "hooks" / "acceptance-gate.py"
MERGE = REPO / "common" / "hooks" / "merge-truth-gate.py"
KEY = "PROJ-1"
FAILURES = []

BOARD_FLOW = """\
defaults:
  project_key: PROJ
  status_map:
    to_do: "A Fazer"
    in_progress: "Em Andamento"
    in_review: "Em Revisão"
    done: "Concluído"
    wont_do: "Descartados"
"""


def check(name, cond, detail=""):
    print(("  ok  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILURES.append(name)


def projeto(board_flow=None):
    d = Path(tempfile.mkdtemp(prefix="gate-nome-"))
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    acc = d / ".claude" / "acceptance"
    acc.mkdir(parents=True)
    (acc / f"{KEY}.yaml").write_text(f"key: {KEY}\nstatus: incomplete\n", encoding="utf-8")
    if board_flow:
        (d / "board-flow.yaml").write_text(board_flow, encoding="utf-8")
    return d


def roda(hook, cwd, nome):
    cmd = f'twg jira workitem transition --id {KEY} --transition-id "{nome}"'
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd)})
    return subprocess.run([sys.executable, str(hook)], input=payload,
                          capture_output=True, text=True).returncode


# ── sem board-flow.yaml: só a forma normalizada resolve ─────────────────────
sem_mapa = projeto()
for nome in ("In Review", "in review", "In-Review", "in_review", "Done", "DONE"):
    check(f"sem mapa, auditoria incompleta, '{nome}' → BARRA",
          roda(ACCEPT, sem_mapa, nome) == 2)
for nome in ("In Progress", "To Do"):
    check(f"sem mapa, '{nome}' (devolução) → PASSA", roda(ACCEPT, sem_mapa, nome) == 0)
check("sem mapa, nome desconhecido 'Homologação' → BARRA (alvo não resolvido)",
      roda(ACCEPT, sem_mapa, "Homologação") == 2)

# ── com status_map em português: o nome técnico resolve pela tabela ─────────
com_mapa = projeto(BOARD_FLOW)
for nome in ("Em Revisão", "em revisão", "Concluído"):
    check(f"com mapa, '{nome}' → BARRA", roda(ACCEPT, com_mapa, nome) == 2)
for nome in ("Em Andamento", "A Fazer", "Descartados"):
    check(f"com mapa, '{nome}' (devolução) → PASSA", roda(ACCEPT, com_mapa, nome) == 0)

# ── merge-truth-gate: fechar por nome técnico conta como fechamento ─────────
# Sem branch de integração o gate não tem o que conferir e sai 0 de qualquer
# jeito; o que se verifica aqui é que o NOME chega resolvido como `done`, pela
# função que os dois gates compartilham.
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _jiramut as J  # noqa: E402

check("resolve 'Concluído' → done pelo status_map",
      J.logical_status("Concluído", com_mapa) == "done")
check("resolve 'In Review' → in_review sem mapa",
      J.logical_status("In Review", sem_mapa) == "in_review")
check("nome desconhecido → None", J.logical_status("Homologação", sem_mapa) is None)
check("None → None", J.logical_status(None, sem_mapa) is None)

print()
if FAILURES:
    print(f"{len(FAILURES)} falha(s)")
    sys.exit(1)
print("tudo verde")
