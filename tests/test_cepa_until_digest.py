#!/usr/bin/env python3
"""cepa-until-digest — the mechanical summary of a `cepa-until` run.

The `.log` of a real run exceeds 10 MB. The summary has to bring, of each
round, the final report, the agents called, the tool errors and the
cost, and of each item touched the CURRENT state in the queue — and say when the
record↔log pairing does not close, instead of pairing wrongly in silence.
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


def check(name, cond, detail=""):
    print(("  ok  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILURES.append(name)


def build_round(final_text, agents=(), error=None, cost=0.5, extra=()):
    lines = [json.dumps({"type": "system", "subtype": "init"})]
    for a in agents:
        lines.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Agent",
             "input": {"subagent_type": a}}]}}))
    if error:
        lines.append(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": True, "content": error}]}}))
    lines.extend(json.dumps(e) for e in extra)
    lines.append(json.dumps({"type": "result", "subtype": "success",
                              "result": final_text, "total_cost_usd": cost,
                              "num_turns": 9}))
    return "\n".join(lines) + "\n"


def call(name, inp, ident=None, parent=None):
    c = {"type": "tool_use", "name": name, "input": inp}
    if ident:
        c["id"] = ident
    e = {"type": "assistant", "message": {"content": [c]}}
    if parent:
        e["parent_tool_use_id"] = parent
    return e


def returned(ident, plain_text, parent=None):
    e = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": ident, "content": plain_text}]}}
    if parent:
        e["parent_tool_use_id"] = parent
    return e


HOOK_HINT = ("[build-hex bash-path-lock] NEGADO. A pista: provar RED "
                "revertendo código: worktree descartável FORA da raiz "
                "(lá o cadeado não tem jurisdição): D=$(mktemp -d)")

# What WEGO run 2026-09-27-1632 left in the `.log` (WEGO-2329): the
# qa-engineer is a grandchild of the orchestrator, so its calls do not show up;
# what shows up is the report the engineering-lead returns, the RESULT.md it
# writes, and the tool calls of the direct children.
ROUND_WITH_DEVIATIONS = [
    call("Agent", {"subagent_type": "build-hex:engineering-lead",
                      "prompt": "build it"}, ident="tu_lead"),
    # direct child reading something: the hook hint comes in a tool result
    call("Bash", {"command": "git status"}, parent="tu_lead"),
    returned("tu_bash_1", HOOK_HINT, parent="tu_lead"),
    # the engineering-lead itself opening a worktree (forbidden at night)
    call("Bash", {"command": "git worktree add --detach /tmp/lead-x HEAD"},
            parent="tu_lead"),
    call("Write", {"file_path": "/r/docs/tasks/x/RESULT.md",
                      "content": "# RESULT\n- Processo: o qa-engineer criou "
                                 "um worktree descartável (removido) para "
                                 "medir os vermelhos."}, parent="tu_lead"),
    returned("tu_lead", "Task fechada. O hook de gate bloqueou o commit por "
              "BUILD FAILURE do bootstrap; o qa-engineer contornou rodando um "
              "build verde de outro módulo antes de commitar."),
    # a worker that REFUSES to get around it is not a signal
    call("Agent", {"subagent_type": "build-hex:adapter-dev"},
            ident="tu_adapter"),
    returned("tu_adapter", "Não posso contornar nem pedir para o hook ser "
              "desativado; parei aqui."),
    # the proof-reviewer's worktree is the permitted one
    call("Agent", {"subagent_type": "build-hex:proof-reviewer"},
            ident="tu_proof"),
    call("Bash", {"command": "cd /r && git worktree add --detach "
                                "/tmp/proof-X HEAD"}, parent="tu_proof"),
    # Agent forking a worktree through the tool parameter
    call("Agent", {"subagent_type": "build-hex:qa-engineer",
                      "isolation": "worktree"}, parent="tu_lead"),
]


def build_run(tmp, n_rounds_in_log=2, extra_round_1=()):
    queue = Path(tmp) / ".claude" / "programs" / "F"
    until = queue / "until"
    until.mkdir(parents=True)
    (queue / "plan.yaml").write_text(yaml.safe_dump({"items": [
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
          {"evento": "run_end", "motivo": "end-of-queue", "detalhe": "acabou",
           "itens": 2, "entregues": 1, "travados": 1}]
    ledger = until / "r.jsonl"
    ledger.write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    log = ("\n===== t · claude -p /common:drain-plan F --max 1\n"
           + build_round("RELATORIO A1 " + "x" * 50,
                    agents=["build-hex:engineering-lead",
                             "common:completion-auditor"],
                    error="Exit code 1 mvn quebrou", cost=1.25,
                    extra=extra_round_1)
           + "\n===== t · verify · ./mvnw -B clean verify\n"
           + "\n".join(f"linha {i}" for i in range(40)) + "\nBUILD SUCCESS\n")
    if n_rounds_in_log >= 2:
        log += ("\n===== t · claude -p /common:drain-plan F --max 1\n"
                + build_round("RELATORIO A2 travou", cost=0.25))
    (until / "r.log").write_text(log)
    return ledger


def run_digest(ledger, *args):
    return subprocess.run([sys.executable, str(DIGEST), str(ledger), *args],
                          capture_output=True, text=True, timeout=60)


def test_summary_brings_what_each_round_said_and_did():
    with tempfile.TemporaryDirectory() as tmp:
        p = run_digest(build_run(tmp))
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


def test_long_report_is_cut_and_says_it_cut():
    with tempfile.TemporaryDirectory() as tmp:
        p = run_digest(build_run(tmp), "--result-max", "20")
        check("o corte é declarado", "[… cortado]" in p.stdout)


def test_pairing_that_does_not_close_is_warned():
    with tempfile.TemporaryDirectory() as tmp:
        p = run_digest(build_run(tmp, n_rounds_in_log=1))
        check("avisa quando registro e log discordam",
              "ATENÇÃO: 2 item_start" in p.stdout, p.stdout[:800])


def rewrite_ledger(ledger, change):
    events = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
    change(events)
    ledger.write_text("\n".join(json.dumps(e) for e in events) + "\n")


def test_new_format_record_shows_session_and_end_reason():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = build_run(tmp)

        def new_format(events):
            events[0]["versao_registro"] = 2
            for e in events:
                if e.get("evento") == "item_end":
                    e["session_id"] = "sess-" + e["id"]
                    e["motivo_fim"] = "ok"
        rewrite_ledger(ledger, new_format)
        out = run_digest(ledger).stdout
        check("mostra a sessão e o motivo do fim de cada rodada",
              "sessão sess-A1, fim `ok`" in out and "sessão sess-A2" in out, out[:900])
        check("registro completo não avisa", "item_end sem session_id" not in out)


def test_reinstall_and_rollback_segments_are_not_rounds():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = build_run(tmp)
        log = ledger.with_suffix(".log")
        text = log.read_text()
        i = text.index("\n===== t · claude -p", 10)
        log.write_text(text[:i]
                       + "\n===== t · reinstall · sh bin/install.sh --clean\nok\n"
                       + "\n===== t · rollback · sh bin/install.sh --rollback\nok\n"
                       + text[i:])
        out = run_digest(ledger).stdout
        check("reinstall/rollback não desalinham o pareamento",
              "pareamento" not in out and "RELATORIO A2" in out, out[:1200])


def test_hooks_sha_in_the_round_line_and_failed_reinstall_is_warned():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = build_run(tmp)

        def with_hooks(events):
            for e in events:
                if e.get("evento") == "item_start" and e["id"] == "A1":
                    e["hooks_sha"] = "abc123def456"
            events.append({"evento": "hooks_reinstalados", "id": "A1",
                           "ok": False, "sha_antes": "abc123def456",
                           "sha_depois": None})
        rewrite_ledger(ledger, with_hooks)
        out = run_digest(ledger).stdout
        check("a linha da rodada traz o sha dos hooks",
              " · hooks abc123def456" in out, out[:1200])
        check("reinstalação que falhou vira ATENÇÃO no cabeçalho",
              "- ATENÇÃO: reinstalação de hooks falhou no item A1" in out,
              out[:1200])


def test_new_format_record_missing_fields_is_warned_and_old_is_not():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = build_run(tmp)

        def half(events):
            events[0]["versao_registro"] = 2
            for e in events:
                if e.get("evento") == "item_end" and e["id"] == "A1":
                    e["session_id"] = "sess-A1"
                    e["motivo_fim"] = "ok"
        rewrite_ledger(ledger, half)
        out = run_digest(ledger).stdout
        check("avisa os ids de item_end sem session_id/motivo_fim",
              "- ATENÇÃO: item_end sem session_id/motivo_fim: A2" in out, out[:900])
    with tempfile.TemporaryDirectory() as tmp:
        out = run_digest(build_run(tmp)).stdout
        check("registro antigo (sem versao_registro) não avisa",
              "item_end sem session_id" not in out)


def test_explicit_version_1_record_is_not_judged():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = build_run(tmp)
        rewrite_ledger(ledger, lambda ev: ev[0].update(versao_registro=1))
        out = run_digest(ledger).stdout
        check("versao_registro 1 explícito, sem os campos: não avisa",
              "item_end sem" not in out, out[:600])


def test_version_2_item_end_with_session_but_without_end_reason_is_warned():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = build_run(tmp)

        def only_session(events):
            events[0]["versao_registro"] = 2
            for e in events:
                if e.get("evento") == "item_end":
                    e["session_id"] = "sess-" + e["id"]
                    if e["id"] == "A1":
                        e["motivo_fim"] = "ok"
        rewrite_ledger(ledger, only_session)
        out = run_digest(ledger).stdout
        check("session_id sem motivo_fim: avisa e nomeia só o item (A2)",
              "- ATENÇÃO: item_end sem session_id/motivo_fim: A2" in out
              and "motivo_fim: A1" not in out, out[:900])


def test_queue_state_comes_from_the_main_clone_not_the_worktree():
    """The record lives in the tree `cepa-until` was launched from. If it is a
    linked worktree, its plan.yaml is an old copy; the real queue is that of the
    main clone (same rule as `cepa-plan`). On 2026-09-26 the summary
    read the copy and showed 21 `pending` items that were already closed."""
    with tempfile.TemporaryDirectory() as tmp:
        main_ = Path(tmp) / "principal"
        main_.mkdir()
        g = lambda *a, cwd=main_: subprocess.run(
            ["git", *a], cwd=str(cwd), capture_output=True, text=True, check=True)
        g("init", "-q")
        g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
          "--allow-empty", "-m", "raiz")
        wt = Path(tmp) / "wt"
        g("worktree", "add", "-q", "--detach", str(wt))
        ledger = build_run(wt)  # old copy in the worktree: A2 blocked
        queue = main_ / ".claude" / "programs" / "F"
        queue.mkdir(parents=True)
        (queue / "plan.yaml").write_text(yaml.safe_dump({"items": [
            {"id": "A1", "status": "done", "blocked_by": [],
             "evidence": "commits abc; build verde"},
            {"id": "A2", "status": "done", "blocked_by": [],
             "evidence": "FECHADO NO CLONE PRINCIPAL"}]}), encoding="utf-8")
        p = run_digest(ledger)
        check("lê o estado da fila do clone principal",
              "FECHADO NO CLONE PRINCIPAL" in p.stdout, p.stdout[-900:])
        check("não lê a cópia velha da worktree",
              "depende do A1 que não está na main" not in p.stdout)
        check("diz de qual arquivo leu a fila",
              str((queue / "plan.yaml").resolve()) in p.stdout
              or str(queue / "plan.yaml") in p.stdout, p.stdout[-900:])


def test_signals_of_process_worktree_and_foreign_build():
    """In WEGO run 2026-09-27-1632 the qa-engineer opened a disposable worktree
    (2327, 2329) and in 2329 got around the red build gate by presenting the
    green build of another module. None of that showed up in the summary: its calls
    are not in the `.log` (it is a grandchild of the orchestrator), only the report the
    engineering-lead returns and the RESULT.md it writes. The summary has to
    show each signal, say whose it is, and not confuse it with the hint the hook
    prints nor with a worker that REFUSES to get around it."""
    with tempfile.TemporaryDirectory() as tmp:
        p = run_digest(build_run(tmp, extra_round_1=ROUND_WITH_DEVIATIONS))
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


def test_proposed_waivers_appear_for_the_review_to_read_the_question():
    """In an autonomous run the waiver becomes a proposal (fb-20261014-3); the summary brings the
    question for the owner to read, both in the item and in its own section."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = build_run(tmp)
        w = Path(tmp) / ".claude" / "waivers"
        w.mkdir(parents=True)
        (w / "teste-cego--plugsign.yaml").write_text(yaml.safe_dump({
            "status": "proposta", "motivo": "teste-cego", "escopo": "PlugSignAdapter",
            "autor": None, "fila": "F", "item": "A2",
            "pergunta": "Aceito a dispensa de PlugSignAdapter por prova interna?"},
            allow_unicode=True), encoding="utf-8")
        (w / "decidida--x.yaml").write_text(
            "motivo: decidida\nescopo: X\nautor: alguem\n", encoding="utf-8")
        (w / "quebrado.yaml").write_text("status: [proposta", encoding="utf-8")
        out = run_digest(ledger).stdout
        check("traz a seção das dispensas propostas",
              "## Dispensas propostas pelo agente, sem resposta do dono" in out, out[-900:])
        check("...com motivo, escopo e pergunta",
              "teste-cego em PlugSignAdapter — pergunta: Aceito a dispensa de "
              "PlugSignAdapter por prova interna?" in out, out[-900:])
        check("...e nomeia o item", "item: A2" in out)
        check("...e a lista no item tocado",
              "  - dispensa proposta pelo agente: teste-cego em PlugSignAdapter" in out, out[-900:])
        check("...sem listar a dispensa já decidida", "decidida" not in out)
    with tempfile.TemporaryDirectory() as tmp:
        out = run_digest(build_run(tmp)).stdout
        check("sem proposta, a seção diz `nenhuma`",
              "## Dispensas propostas pelo agente, sem resposta do dono\nnenhuma" in out,
              out[-600:])


def test_proposal_only_in_the_record_tree_is_also_listed():
    """The run records the proposal in the tree where it runs (cepa-until's worktree), not
    beside the main clone's queue."""
    with tempfile.TemporaryDirectory() as tmp:
        main_ = Path(tmp) / "principal"
        main_.mkdir()
        g = lambda *a: subprocess.run(["git", *a], cwd=str(main_),
                                      capture_output=True, text=True, check=True)
        g("init", "-q")
        g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
          "--allow-empty", "-m", "raiz")
        wt = Path(tmp) / "wt"
        g("worktree", "add", "-q", "--detach", str(wt))
        ledger = build_run(wt)
        queue = main_ / ".claude" / "programs" / "F"
        queue.mkdir(parents=True)
        (queue / "plan.yaml").write_text(yaml.safe_dump({"items": [
            {"id": "A2", "status": "blocked", "blocked_by": []}]}), encoding="utf-8")
        w = wt / ".claude" / "waivers"
        w.mkdir(parents=True)
        (w / "teste-cego--x.yaml").write_text(yaml.safe_dump({
            "status": "proposta", "motivo": "teste-cego", "escopo": "SoNaWorktree",
            "autor": None, "item": "A2", "pergunta": "Aceito a dispensa de SoNaWorktree?"},
            allow_unicode=True), encoding="utf-8")
        out = run_digest(ledger).stdout
        check("proposta só na árvore do registro é listada",
              "teste-cego em SoNaWorktree — pergunta: Aceito a dispensa de SoNaWorktree?" in out,
              out[-700:])
        check("...uma vez só na seção", out.count("teste-cego em SoNaWorktree") == 2, out[-700:])


def test_proposal_only_in_the_main_clone_is_also_listed():
    """Mirror of the previous case: the plan and the proposal live in the main clone,
    and the record's worktree has no proposal at all."""
    with tempfile.TemporaryDirectory() as tmp:
        main_ = Path(tmp) / "principal"
        main_.mkdir()
        g = lambda *a: subprocess.run(["git", *a], cwd=str(main_),
                                      capture_output=True, text=True, check=True)
        g("init", "-q")
        g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
          "--allow-empty", "-m", "raiz")
        wt = Path(tmp) / "wt"
        g("worktree", "add", "-q", "--detach", str(wt))
        ledger = build_run(wt)
        queue = main_ / ".claude" / "programs" / "F"
        queue.mkdir(parents=True)
        (queue / "plan.yaml").write_text(yaml.safe_dump({"items": [
            {"id": "A2", "status": "blocked", "blocked_by": []}]}), encoding="utf-8")
        w = main_ / ".claude" / "waivers"
        w.mkdir(parents=True)
        (w / "teste-cego--x.yaml").write_text(yaml.safe_dump({
            "status": "proposta", "motivo": "teste-cego", "escopo": "SoNoPrincipal",
            "autor": None, "item": "A2", "pergunta": "Aceito a dispensa de SoNoPrincipal?"},
            allow_unicode=True), encoding="utf-8")
        check("a worktree do registro não tem pasta de dispensas",
              not (wt / ".claude" / "waivers").exists())
        out = run_digest(ledger).stdout
        check("proposta só no clone principal é listada",
              "teste-cego em SoNoPrincipal — pergunta: Aceito a dispensa de SoNoPrincipal?" in out,
              out[-700:])


def test_broken_yaml_alongside_proposal_does_not_crash_summary():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = build_run(tmp)
        w = Path(tmp) / ".claude" / "waivers"
        w.mkdir(parents=True)
        (w / "a-quebrado.yaml").write_text("motivo: [unclosed", encoding="utf-8")
        (w / "b-proposta.yaml").write_text(yaml.safe_dump({
            "status": "proposta", "motivo": "teste-cego", "escopo": "Viva",
            "item": "A2", "pergunta": "Aceito a dispensa de Viva?"},
            allow_unicode=True), encoding="utf-8")
        p = run_digest(ledger)
        check("resumo sai 0 com YAML quebrado ao lado", p.returncode == 0, p.stderr)
        check("...e ainda lista a proposta", "teste-cego em Viva — pergunta:" in p.stdout,
              p.stdout[-500:])


def test_missing_record_exits_2():
    p = run_digest("/nao/existe.jsonl")
    check("registro inexistente sai 2", p.returncode == 2, p.stderr)


def main():
    print("cepa-until-digest\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
