#!/usr/bin/env python3
"""cepa-until-digest — o resumo mecânico de um run do `cepa-until`.

O `.log` de um run real passa de 10 MB. O resumo tem de trazer, de cada
rodada, o relatório final, os agentes chamados, os erros de ferramenta e o
custo, e de cada item tocado o estado ATUAL na fila — e dizer quando o
pareamento registro↔log não fecha, em vez de parear errado calado.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
DIGEST = REPO / "common" / "bin" / "cepa-until-digest"
FAILURES = []


def check(nome, cond, detalhe=""):
    print(("  ok  " if cond else "FAIL  ") + nome + ("" if cond else f"  {detalhe}"))
    if not cond:
        FAILURES.append(nome)


def rodada(texto_final, agentes=(), erro=None, custo=0.5, extra=()):
    linhas = [json.dumps({"type": "system", "subtype": "init"})]
    for a in agentes:
        linhas.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Agent",
             "input": {"subagent_type": a}}]}}))
    if erro:
        linhas.append(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": True, "content": erro}]}}))
    linhas.extend(json.dumps(e) for e in extra)
    linhas.append(json.dumps({"type": "result", "subtype": "success",
                              "result": texto_final, "total_cost_usd": custo,
                              "num_turns": 9}))
    return "\n".join(linhas) + "\n"


def chamada(nome, inp, ident=None, pai=None):
    c = {"type": "tool_use", "name": nome, "input": inp}
    if ident:
        c["id"] = ident
    e = {"type": "assistant", "message": {"content": [c]}}
    if pai:
        e["parent_tool_use_id"] = pai
    return e


def devolvido(ident, texto, pai=None):
    e = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": ident, "content": texto}]}}
    if pai:
        e["parent_tool_use_id"] = pai
    return e


DICA_DO_HOOK = ("[build-hex bash-path-lock] NEGADO. A pista: provar RED "
                "revertendo código: worktree descartável FORA da raiz "
                "(lá o cadeado não tem jurisdição): D=$(mktemp -d)")

# O que o run 2026-09-27-1632 do WEGO deixou no `.log` (WEGO-2329): o
# qa-engineer é neto do orquestrador, então as chamadas dele não aparecem;
# aparece o relatório que o engineering-lead devolve, o RESULT.md que ele
# escreve, e as chamadas de ferramenta dos filhos diretos.
RODADA_COM_DESVIOS = [
    chamada("Agent", {"subagent_type": "build-hex:engineering-lead",
                      "prompt": "build it"}, ident="tu_lead"),
    # filho direto lendo algo: a dica do hook vem em resultado de ferramenta
    chamada("Bash", {"command": "git status"}, pai="tu_lead"),
    devolvido("tu_bash_1", DICA_DO_HOOK, pai="tu_lead"),
    # o próprio engineering-lead abrindo worktree (proibido na noite)
    chamada("Bash", {"command": "git worktree add --detach /tmp/lead-x HEAD"},
            pai="tu_lead"),
    chamada("Write", {"file_path": "/r/docs/tasks/x/RESULT.md",
                      "content": "# RESULT\n- Processo: o qa-engineer criou "
                                 "um worktree descartável (removido) para "
                                 "medir os vermelhos."}, pai="tu_lead"),
    devolvido("tu_lead", "Task fechada. O hook de gate bloqueou o commit por "
              "BUILD FAILURE do bootstrap; o qa-engineer contornou rodando um "
              "build verde de outro módulo antes de commitar."),
    # um worker que RECUSA contornar não é sinal
    chamada("Agent", {"subagent_type": "build-hex:adapter-dev"},
            ident="tu_adapter"),
    devolvido("tu_adapter", "Não posso contornar nem pedir para o hook ser "
              "desativado; parei aqui."),
    # a worktree do proof-reviewer é a permitida
    chamada("Agent", {"subagent_type": "build-hex:proof-reviewer"},
            ident="tu_proof"),
    chamada("Bash", {"command": "cd /r && git worktree add --detach "
                                "/tmp/proof-X HEAD"}, pai="tu_proof"),
    # Agent forkando worktree pelo parâmetro da ferramenta
    chamada("Agent", {"subagent_type": "build-hex:qa-engineer",
                      "isolation": "worktree"}, pai="tu_lead"),
]


def monta_run(tmp, n_rodadas_no_log=2, extra_rodada_1=()):
    fila = Path(tmp) / ".claude" / "programs" / "F"
    until = fila / "until"
    until.mkdir(parents=True)
    (fila / "plan.yaml").write_text(yaml.safe_dump({"items": [
        {"id": "A1", "status": "done", "blocked_by": [],
         "evidence": "commits abc; build verde"},
        {"id": "A2", "status": "blocked", "blocked_by": [],
         "evidence": "depende do A1 que não está na main"}]}), encoding="utf-8")
    ev = [{"evento": "run_start", "fila": "F", "branch": "until/r",
           "base": "deadbeef00", "verify": "./mvnw -B clean verify"},
          {"evento": "item_start", "id": "A1", "title": "um"},
          {"evento": "item_end", "id": "A1", "status": "done", "segundos": 10,
           "exit_code": 0, "commits": 3, "tentativa": 1},
          {"evento": "verify", "id": "A1", "verde": True, "segundos": 5},
          {"evento": "item_start", "id": "A2", "title": "dois"},
          {"evento": "item_end", "id": "A2", "status": "blocked", "segundos": 4,
           "exit_code": 0, "commits": 0, "tentativa": 1},
          {"evento": "run_end", "motivo": "fim-da-fila", "detalhe": "acabou",
           "itens": 2, "entregues": 1, "travados": 1}]
    ledger = until / "r.jsonl"
    ledger.write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    log = ("\n===== t · claude -p /common:drain-plan F --max 1\n"
           + rodada("RELATORIO A1 " + "x" * 50,
                    agentes=["build-hex:engineering-lead",
                             "common:completion-auditor"],
                    erro="Exit code 1 mvn quebrou", custo=1.25,
                    extra=extra_rodada_1)
           + "\n===== t · verify · ./mvnw -B clean verify\n"
           + "\n".join(f"linha {i}" for i in range(40)) + "\nBUILD SUCCESS\n")
    if n_rodadas_no_log >= 2:
        log += ("\n===== t · claude -p /common:drain-plan F --max 1\n"
                + rodada("RELATORIO A2 travou", custo=0.25))
    (until / "r.log").write_text(log)
    return ledger


def roda(ledger, *args):
    return subprocess.run([sys.executable, str(DIGEST), str(ledger), *args],
                          capture_output=True, text=True, timeout=60)


def test_resumo_traz_o_que_cada_rodada_disse_e_fez():
    with tempfile.TemporaryDirectory() as tmp:
        p = roda(monta_run(tmp))
        out = p.stdout
        check("sai 0", p.returncode == 0, p.stderr)
        check("traz o relatório final de cada rodada",
              "RELATORIO A1" in out and "RELATORIO A2 travou" in out)
        check("pareia cada relatório com o item certo",
              out.index("RELATORIO A1") < out.index("### 2. A2"))
        check("conta os agentes por tipo",
              "build-hex:engineering-lead ×1" in out
              and "common:completion-auditor ×1" in out)
        check("traz os erros de ferramenta", "mvn quebrou" in out)
        check("traz a cauda do build do supervisor, não a saída inteira",
              "BUILD SUCCESS" in out and "linha 39" in out
              and "linha 5\n" not in out)
        check("traz o estado atual da fila com a evidence",
              "depende do A1 que não está na main" in out)
        check("soma o custo com a origem da conta",
              "US$ 1.50" in out and "total_cost_usd" in out, out[-300:])
        check("traz os commits de cada item na branch da noite",
              "commits na branch da noite: 3" in out)


def test_relatorio_longo_e_cortado_e_diz_que_cortou():
    with tempfile.TemporaryDirectory() as tmp:
        p = roda(monta_run(tmp), "--result-max", "20")
        check("o corte é declarado", "[… cortado]" in p.stdout)


def test_pareamento_que_nao_fecha_e_avisado():
    with tempfile.TemporaryDirectory() as tmp:
        p = roda(monta_run(tmp, n_rodadas_no_log=1))
        check("avisa quando registro e log discordam",
              "ATENÇÃO: 2 item_start" in p.stdout, p.stdout[:800])


def test_estado_da_fila_vem_do_clone_principal_nao_da_worktree():
    """O registro mora na árvore de onde o `cepa-until` largou. Se ela é uma
    worktree ligada, o plan.yaml dela é uma cópia velha; a fila de verdade é a
    do clone principal (mesma regra do `cepa-plan`). Em 2026-09-26 o resumo
    leu a cópia e mostrou 21 itens `pending` que já estavam fechados."""
    with tempfile.TemporaryDirectory() as tmp:
        principal = Path(tmp) / "principal"
        principal.mkdir()
        g = lambda *a, cwd=principal: subprocess.run(
            ["git", *a], cwd=str(cwd), capture_output=True, text=True, check=True)
        g("init", "-q")
        g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
          "--allow-empty", "-m", "raiz")
        wt = Path(tmp) / "wt"
        g("worktree", "add", "-q", "--detach", str(wt))
        ledger = monta_run(wt)  # cópia velha na worktree: A2 blocked
        fila = principal / ".claude" / "programs" / "F"
        fila.mkdir(parents=True)
        (fila / "plan.yaml").write_text(yaml.safe_dump({"items": [
            {"id": "A1", "status": "done", "blocked_by": [],
             "evidence": "commits abc; build verde"},
            {"id": "A2", "status": "done", "blocked_by": [],
             "evidence": "FECHADO NO CLONE PRINCIPAL"}]}), encoding="utf-8")
        p = roda(ledger)
        check("lê o estado da fila do clone principal",
              "FECHADO NO CLONE PRINCIPAL" in p.stdout, p.stdout[-900:])
        check("não lê a cópia velha da worktree",
              "depende do A1 que não está na main" not in p.stdout)
        check("diz de qual arquivo leu a fila",
              str((fila / "plan.yaml").resolve()) in p.stdout
              or str(fila / "plan.yaml") in p.stdout, p.stdout[-900:])


def test_sinais_de_processo_worktree_e_build_alheio():
    """No run 2026-09-27-1632 do WEGO o qa-engineer abriu worktree descartável
    (2327, 2329) e no 2329 contornou o gate de build vermelho apresentando o
    build verde de outro módulo. Nada disso aparecia no resumo: as chamadas
    dele não estão no `.log` (é neto do orquestrador), só o relatório que o
    engineering-lead devolve e o RESULT.md que ele escreve. O resumo tem de
    mostrar cada sinal, dizer de quem é, e não confundir com a dica que o hook
    imprime nem com um worker que se RECUSA a contornar."""
    with tempfile.TemporaryDirectory() as tmp:
        p = roda(monta_run(tmp, extra_rodada_1=RODADA_COM_DESVIOS))
        out = p.stdout
        check("sai 0", p.returncode == 0, p.stderr)
        r1 = out[out.index("### 1. A1"):out.index("### 2. A2")]
        r2 = out[out.index("### 2. A2"):out.index("## Builds")]
        check("mostra o gate de build contornado, e de quem veio o relato",
              "build verde de outro módulo / gate de build contornado · "
              "quem: build-hex:engineering-lead · onde: relatório devolvido"
              in r1, r1[-1500:])
        check("mostra a worktree descartável relatada no RESULT.md",
              "worktree descartável relatada · quem: build-hex:engineering-lead"
              " · onde: Write em RESULT.md" in r1, r1[-1500:])
        check("mostra a worktree que um filho direto abriu por Bash",
              "worktree aberta (--detach) · quem: build-hex:engineering-lead"
              " · onde: Bash" in r1, r1[-1500:])
        check("mostra o Agent forkado com isolation=worktree",
              "worktree aberta (Agent com isolation=worktree) · quem: "
              "build-hex:engineering-lead" in r1, r1[-1500:])
        check("a worktree do proof-reviewer vem anotada como permitida",
              "quem: build-hex:proof-reviewer (prova por perturbação: "
              "permitida na noite)" in r1, r1[-1500:])
        check("a permitida vem depois das outras",
              r1.index("gate de build contornado")
              < r1.index("permitida na noite"))
        check("a dica do hook em resultado de ferramenta NÃO vira sinal",
              "FORA da raiz" not in r1, r1[-1500:])
        check("worker que se recusa a contornar NÃO vira sinal",
              "adapter-dev" not in r1.split("sinais de processo")[1]
              .split("Relatório final")[0], r1[-1500:])
        check("conta os sinais (5: gate, relato, Bash, isolation, prova)",
              "- sinais de processo: 5:" in r1, r1[-1500:])
        check("rodada sem desvio diz que não há sinal",
              "sinais de processo: nenhum" in r2, r2[:800])


def test_registro_inexistente_sai_2():
    p = roda("/nao/existe.jsonl")
    check("registro inexistente sai 2", p.returncode == 2, p.stderr)


def main():
    print("cepa-until-digest\n")
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"{nome}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
