#!/usr/bin/env python3
"""Tests of the report-format meter (common/hooks/report-style-lint.py).

The defect it measures (reported by the user on 2026-08-03): reports that
require two readings — internal jargon in the opening, mechanism before the result,
no point where it is possible to stop reading.

Guarantees:
  - a turn that CHANGED something + a report outside the format -> deviation recorded, and the
    warning shows up in the next UserPromptSubmit;
  - a report inside the format -> no warning;
  - a CONVERSATION turn (nothing changed) -> never measured, however bad it is;
  - a short report -> never measured (it is a note, not a report);
  - jargon in the technical detail block -> allowed; in the opening -> flagged;
  - hygiene ("clean tree", "updated memory") at the top -> flagged; the
    same sentence in the technical detail -> allowed;
  - the final list `### Decisões e próximos passos` is mandatory, is the last
    section, has list items (or "Nada pendente.") and stays outside the 200-word
    ceiling;
  - each item of the final list is numbered, asks a closed question and carries
    "Recomendo sim/não" -> an item that only names the subject is flagged;
  - everything the `Pra você:` announces appears as a numbered item at the end ("Nada
    pendente." only holds when the top says "nothing"), and every owner-task item
    ("Você ...") carries a command or file and "Pronto quando" — the report of
    2026-10-14 ("close the two human routes ... Nada pendente.") is blocked;
  - a reference code (E2, P1, CR2, PR8) used without a definition in the same
    message is flagged; defined inline on first mention, in a legend line, or
    inside backticks -> allowed (2026-10-31, fb-20261031-1);
  - a subagent's answer (sidechain) is never mistaken for the report;
  - the hook NEVER blocks: exit 0 in all cases.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "report-style-lint.py"

FAILURES = []
TMP = Path(tempfile.mkdtemp(prefix="report-style-"))
STATE = TMP / "state"
TELEM = TMP / "telemetry"

# The list at the end, mandatory since 2026-08-03. Since every completed-work
# report needs it, it enters all the fixtures; tests that measure ANOTHER
# thing must not fail for lack of it.
STEPS = ("\n\n### Decisões e próximos passos\n"
          "*Responda por número: sim, não, ou \"vamos falar\".*\n"
          "1. **Você roda `bin/install.sh --clean` agora?**\n"
          "   Onde: raiz do clone do cepa.\n"
          "   Comando:\n"
          "   ```\n"
          "   bin/install.sh --clean\n"
          "   ```\n"
          "   Pronto quando: o terminal imprime `instalado` e eu recebo o aviso "
          "de volta.\n"
          "   Recomendo **sim** — sem isso a mudança não vale.\n")


GOOD = ("O verificador de provas aceitava qualquer palavra fora de uma lista de "
       "proibidas, então um erro de digitação virava aprovação. Agora ele só "
       "aceita as palavras previstas para cada checagem, e recusa o resto.\n\n"
       "**Pra você:** nada pra decidir agora; precisa reinstalar pra valer.\n\n"
       "### Detalhe técnico\n"
       "O portão passou a comparar contra um enum fechado por nível; o dublê "
       "segue barrado e cada perturbação foi ao vermelho sozinha. " * 6
       + STEPS)

BAD = ("O portão agora falha fechado. Cada status é conferido contra o enum "
        "fechado do seu nível, não contra uma lista de proibidos. O coletor "
        "virou consciente do caminho para isso ser possível, e o dublê segue "
        "barrado como antes. A perturbação de cada garantia foi ao vermelho "
        "sozinha, o que mantém tudo load-bearing.\n\n"
        "Fiz também a parte do glossário e mexi na altitude do relato, "
        "porque o fio condutor pedia. " * 4)


def msg(role, content, sidechain=False, mtype="assistant"):
    return {"type": mtype, "isSidechain": sidechain,
            "message": {"role": role, "content": content}}


def transcript(*rows) -> str:
    p = TMP / f"t{len(list(TMP.glob('t*.jsonl')))}.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                 encoding="utf-8")
    return str(p)


def turn(report, changed=True, sidechain_extra=None):
    """A complete turn: user prompt, work, final report."""
    rows = [msg("user", [{"type": "text", "text": "faça a coisa"}], mtype="user")]
    if changed:
        rows.append(msg("assistant", [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "x.py"}}]))
    rows.append(msg("assistant", [{"type": "text", "text": report}]))
    if sidechain_extra:
        # AFTER the report on purpose: that is how a background subagent, which
        # finishes after the main answer, lands in the transcript.
        # A sidechain before the report proves nothing — the order would already solve it.
        rows.append(msg("assistant", [{"type": "text", "text": sidechain_extra}],
                        sidechain=True))
    return transcript(*rows)


def run(event, transcript_path="", session="s1", stop_hook_active=False):
    payload = json.dumps({"hook_event_name": event, "session_id": session,
                          "transcript_path": transcript_path, "cwd": str(TMP),
                          "stop_hook_active": stop_hook_active})
    env = dict(os.environ, CEPA_REPORT_STYLE_DIR=str(STATE),
               CEPA_TELEMETRY_DIR=str(TELEM))
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True, env=env)


def block_reason(output: str) -> str:
    """The deviation text when the Stop blocks; empty string when it does not."""
    if not output.strip():
        return ""
    try:
        datum = json.loads(output)
    except json.JSONDecodeError:
        return ""
    return datum.get("reason", "") if datum.get("decision") == "block" else ""


def cycle(report, **kw):
    """Stop (measures and, if there is a deviation, blocks) followed by UserPromptSubmit.

    Returns the deviation text whichever path it comes by — block at the
    Stop (the normal since 2026-08-25) or warning on the next turn (recurrence).
    The cases below check WHAT the hook says, not through which door it says it.
    """
    r1 = run("Stop", turn(report, **kw))
    check(f"Stop sai com rc=0 mesmo bloqueando — {report[:24]!r}",
          r1.returncode == 0, f"rc={r1.returncode} {r1.stderr[:200]}")
    block = block_reason(r1.stdout)
    r2 = run("UserPromptSubmit")
    check("UserPromptSubmit nunca bloqueia (rc=0)", r2.returncode == 0,
          f"rc={r2.returncode}")
    return block or r2.stdout


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# ── the case that motivated everything ─────────────────────────────────────
warning = cycle(BAD)
check("relatório com jargão na abertura → cobra o formato",
      "plain-report" in warning, repr(warning[:200]))
check("…e nomeia os termos que precisam de tradução",
      "portão" in warning and "falha fechado" in warning, repr(warning[:400]))
check("…e cobra a linha For you", "For you" in warning, repr(warning[:400]))

# ── the same content, inside the format ────────────────────────────────────
warning = cycle(GOOD)
check("relatório no formato → nenhum aviso", warning.strip() == "", repr(warning[:300]))

# ── jargon is allowed in the technical block ───────────────────────────────
check("jargão no detalhe técnico não é sinalizado",
      "portão" in GOOD and "dublê" in GOOD)

# ── conversation is never measured ─────────────────────────────────────────
warning = cycle(BAD, changed=False)
check("turno sem alteração → não mede, mesmo com relatório ruim",
      warning.strip() == "", repr(warning[:300]))

# ── a short note is never measured ─────────────────────────────────────────
warning = cycle("O portão agora falha fechado e o dublê segue barrado.")
check("relatório curto → não mede", warning.strip() == "", repr(warning[:300]))

# ── opening too long ───────────────────────────────────────────────────────
warning = cycle("Primeira frase de resultado. Segunda frase. Terceira frase. "
              "Quarta frase que já passou do limite. Quinta.\n\n"
              "**Pra você:** nada.\n\n### Detalhe técnico\n" + "x " * 90)
check("abertura com 5 frases → avisa", "frases" in warning, repr(warning[:300]))

# ── the Pra você is missing ────────────────────────────────────────────────
warning = cycle("Resultado dito de forma clara e sem termo interno nenhum, "
              "em uma frase só.\n\n### Detalhe técnico\n" + "x " * 90)
check("sem a linha For you → avisa", "For you" in warning, repr(warning[:300]))

# ── word ceiling before the technical part ─────────────────────────────────
warning = cycle("Resultado em uma frase clara.\n\n**Pra você:** nada.\n\n" +
              "palavra " * 210 + "\n\n### Detalhe técnico\nx")
check("mais de 200 palavras antes do detalhe técnico → avisa",
      "palavras antes do detalhe" in warning, repr(warning[:300]))

# ── abstraction in place of the fact (applies to the WHOLE text) ───────────
# The technical block was a free zone in v1, and that is exactly where the user
# found the three obscure sentences on 2026-08-03.
warning = cycle("Resultado dito de forma clara em uma frase.\n\n"
              "**Pra você:** nada.\n\n"
              "### Detalhe técnico\n"
              "O escopo virou um sinal mecânico e o aviso chega por um "
              "caminho indireto. " + "detalhe " * 70)
check("abstração DENTRO do detalhe técnico → avisa", "abstração" in warning,
      repr(warning[:300]))
check("…e cita as expressões encontradas",
      "sinal mecânico" in warning and "caminho indireto" in warning, repr(warning[:400]))

warning = cycle("Resultado dito de forma clara em uma frase.\n\n"
              "**Pra você:** nada.\n\n### Detalhe técnico\n" + "detalhe " * 90
              + STEPS)
check("detalhe técnico sem abstração → nenhum aviso", warning.strip() == "",
      repr(warning[:300]))

# ── hygiene reported as a result ───────────────────────────────────────────
# 2026-08-03: a report inside the format, and the user still asked
# "so what?" — four lines of it said the tree was left clean, that no
# worktree was left over and that the memory was updated.
warning = cycle("Os três cards que estavam presos passaram e foram para Done. "
              "A árvore de trabalho ficou limpa e nenhum worktree sobrou.\n\n"
              "**Pra você:** nada pra decidir. Memória atualizada.\n\n"
              "### Detalhe técnico\n" + "detalhe " * 90 + STEPS)
check("higiene na abertura → avisa", "higiene" in warning, repr(warning[:300]))
check("…e cita as frases encontradas",
      "árvore de trabalho limpa" in warning or "nenhum worktree" in warning,
      repr(warning[:400]))

warning = cycle("Os três cards que estavam presos passaram, agora com prova "
              "refeita do zero.\n\n**Pra você:** nada pra decidir.\n\n"
              "### Detalhe técnico\n"
              "Commit feito; a árvore de trabalho ficou limpa e nenhum "
              "worktree sobrou. " + "detalhe " * 80 + STEPS)
check("mesma higiene DENTRO do detalhe técnico → não avisa",
      warning.strip() == "", repr(warning[:300]))

# ── passive voice: density, not hunting ────────────────────────────────────
warning = cycle("Resultado dito de forma clara em uma frase.\n\n"
              "**Pra você:** nada.\n\n### Detalhe técnico\n"
              "O arquivo foi criado, o teste foi rodado, a regra é aplicada "
              "e a saída é verificada pelo hook. " + "detalhe " * 70)
check("quatro passivas → avisa", "passivas" in warning, repr(warning[:300]))

warning = cycle("Resultado dito de forma clara em uma frase.\n\n"
              "**Pra você:** nada.\n\n### Detalhe técnico\n"
              "O arquivo foi criado pelo hook. " + "detalhe " * 80 + STEPS)
check("uma passiva só → não avisa (é português normal)", warning.strip() == "",
      repr(warning[:300]))

# ── the list at the end ────────────────────────────────────────────────────
# User request on 2026-08-03: "at the end of each report, an objective list
# of decisions to be made or next steps to be followed".
BODY = ("Resultado dito de forma clara em uma frase.\n\n"
         "**Pra você:** um passo manual — lista no fim.\n\n"
         "### Detalhe técnico\n" + "detalhe " * 90)

warning = cycle(BODY)
check("sem a seção final → avisa", "Decisions and next steps" in warning,
      repr(warning[:300]))

warning = cycle(BODY + STEPS +
              "\n### Uma observação final\nnão devia existir aqui.\n")
check("seção final que não é a última → avisa",
      "não é a última seção" in warning, repr(warning[:400]))

warning = cycle(BODY + "\n\n### Decisões e próximos passos\n"
              "Precisa reinstalar e depois decidir se aperta.\n")
check("lista do fim escrita em prosa → avisa",
      "itens de lista" in warning, repr(warning[:400]))

warning = cycle(BODY.replace("um passo manual — lista no fim.",
                            "nada pra decidir.")
              + "\n\n### Próximos passos\nNada pendente.\n")
check("\"Nada pendente.\" satisfaz a lista", warning.strip() == "",
      repr(warning[:300]))

# The 200-word ceiling applies up to the technical detail; the list at the end does not enter
# it, not even when the report has no technical block at all.
warning = cycle("Resultado em uma frase clara.\n\n**Pra você:** um passo.\n\n"
              "### Decisões e próximos passos\n"
              + "- **Você faz —** rodar o install.\n" * 40)
check("lista longa sem bloco técnico → não estoura o teto",
      "palavras antes do detalhe" not in warning, repr(warning[:300]))

# ── each item is a closed question with a recommendation ───────────────────
# Second correction from the user on the same day: "what actually is the decision I have
# to make? The way it is, I need to interpret the text, access the card,
# understand the whole context". The real item he rejected is in the first case.
warning = cycle(BODY + "\n\n### Decisões e próximos passos\n"
              "1. **Decidir —** WEGO-1631, critério 6 (recusar pedido de "
              "documento com tipo nulo). Se não tiver opinião, mantenha e "
              "confira o volume em produção antes de implementar.\n")
check("item que nomeia o assunto sem perguntar → avisa",
      "pergunta fechada" in warning, repr(warning[:400]))

warning = cycle(BODY + "\n\n### Decisões e próximos passos\n"
              "1. **Mantenho no WEGO-1631 o critério que recusa pedido sem "
              "tipo de documento?** Ele passa a barrar os pedidos legados.\n")
check("pergunta sem recomendação → avisa", "I recommend" in warning,
      repr(warning[:400]))

warning = cycle(BODY + "\n\n### Decisões e próximos passos\n"
              "- **Você roda o install agora?** Recomendo **sim**.\n")
check("lista com marcador em vez de número → avisa",
      "numerada" in warning, repr(warning[:400]))

warning = cycle(BODY + "\n\n### Decisões e próximos passos\n"
              "*Responda por número: sim, não, ou \"vamos falar\".*\n"
              "1. **Mantenho no WEGO-1631 o critério que recusa pedido sem "
              "tipo de documento?**\n"
              "   Recomendo **sim** — é a sua regra \"sem tipo, não emite\".\n"
              "   Se **não**: tiro o critério 6 do card.\n\n"
              "2. **Rodo o prove-drain nos dois cards de In Review?** "
              "Recomendo **não** — a triagem roteou por evidência.\n")
check("item mastigado, com a recomendação na linha seguinte → nenhum aviso",
      warning.strip() == "", repr(warning[:400]))

# ── the owner's task comes with the step by step (2026-10-15) ──────────────
# 2026-10-14: the Pra você said "close the two human routes ... and the seven
# holes of the RIPD" and the end said "Nada pendente." The owner: "What, after all, do
# I have to do? Give me the step by step."
TOP_14_10 = ("Resultado dito de forma clara em uma frase.\n\n"
              "**Pra você:** fechar as duas rotas humanas no `wego-digitacao-backend` "
              "(o comando do S3-port e a conferência dos 50 documentos) e os sete "
              "buracos do RIPD. Nada mais pendente comigo nesta sessão.\n\n"
              "### Detalhe técnico\n" + "detalhe " * 90)
warning = cycle(TOP_14_10 + "\n\n### Decisões e próximos passos\n\nNada pendente.\n")
check("14/10: Pra você com categorias + \"Nada pendente.\" → avisa",
      "For you" in warning and "item numerado" in warning, repr(warning[:400]))

warning = cycle(BODY.replace("um passo manual — lista no fim.", "nada pra decidir.")
              + "\n\n### Decisões e próximos passos\nNada pendente.\n")
check("Pra você \"nada\" + \"Nada pendente.\" → nenhum aviso",
      warning.strip() == "", repr(warning[:300]))

warning = cycle(BODY.replace("um passo manual — lista no fim.",
                            "nada pra decidir; um commit ficou na branch.")
              + "\n\n### Decisões e próximos passos\nNada pendente.\n")
check("Pra você \"nada ...; um commit\" + \"Nada pendente.\" → nenhum aviso",
      warning.strip() == "", repr(warning[:300]))

HEAD_T = ("Resultado dito de forma clara em uma frase.\n\n"
            "**Pra você:** uma tarefa sua — lista no fim.\n\n"
            "### Detalhe técnico\n" + "detalhe " * 90
            + "\n\n### Decisões e próximos passos\n")

warning = cycle(HEAD_T + "1. **Você confere os 50 documentos?** Recomendo **sim** — "
              "sem ela o S5 (a etapa de medir o acerto) não fecha.\n")
check("tarefa \"Você ...\" sem comando, arquivo nem Pronto quando → avisa",
      "passo a passo" in warning, repr(warning[:400]))

warning = cycle(HEAD_T + "1. **Você roda o comando do S3-port?**\n"
              "   Onde: raiz do clone.\n"
              "   Comando:\n"
              "   ```\n"
              "   bin/ler-lote.sh --porta s3 inob/282243\n"
              "   ```\n"
              "   Pronto quando: o terminal imprime 20 lotes lidos.\n"
              "   Recomendo **sim** — destrava o S5 (a etapa de medir o acerto).\n")
check("tarefa com comando em bloco cercado + Pronto quando → nenhum aviso",
      warning.strip() == "", repr(warning[:400]))

warning = cycle(HEAD_T + "1. **Você roda o script com linha em branco?**\n"
              "   Comando:\n"
              "   ```\n"
              "   bin/a.sh\n"
              "\n"
              "   bin/b.sh\n"
              "   ```\n"
              "   Pronto quando: o terminal imprime ok.\n"
              "   Recomendo **sim** — destrava o S5 (a etapa de medir o acerto).\n")
check("linha em branco dentro de bloco cercado não fecha o item → nenhum aviso",
      warning.strip() == "", repr(warning[:400]))

warning = cycle(HEAD_T + "1. **Você preenche os sete campos do RIPD?**\n"
              "   Onde: docs/lgpd/ripd.md, seção 9.\n"
              "   Pronto quando: não sobra campo vazio; me diga \"RIPD pronto\".\n"
              "   Recomendo **sim** — dois campos só você sabe.\n")
check("tarefa com caminho de arquivo sem crase + Pronto quando → nenhum aviso",
      warning.strip() == "", repr(warning[:400]))

warning = cycle(HEAD_T + "1. **Você confere os 50 documentos da amostra?**\n"
              "   Pronto quando: as 50 linhas têm a classe real preenchida.\n"
              "   Recomendo **sim** — sem ela o S5 (a etapa de medir o acerto) não fecha.\n")
check("tarefa sem comando nem arquivo, com Pronto quando → avisa \"comando ou arquivo\"",
      "comando ou arquivo" in warning, repr(warning[:400]))

warning = cycle(HEAD_T + "1. **Você roda `bin/x.sh`?** Recomendo **sim** — destrava.\n")
check("tarefa com comando mas sem Pronto quando → avisa",
      "Done when" in warning, repr(warning[:400]))

warning = cycle(HEAD_T + "1. **Mantenho o critério X?** Recomendo **sim** — "
              "é a sua regra de entrada.\n")
check("pergunta de mérito sem comando → nenhum aviso (regra só vale p/ \"Você\")",
      warning.strip() == "", repr(warning[:400]))

warning = cycle(HEAD_T + "1. **Rodo o prove-drain nos dois cards?** Recomendo "
              "**não** — a triagem roteou por evidência.\n")
check("trabalho meu esperando o vai, sem comando → nenhum aviso",
      warning.strip() == "", repr(warning[:400]))

# ── a subagent's answer is not the report ──────────────────────────────────
warning = cycle(GOOD, sidechain_extra=BAD)
check("texto de subagente (sidechain) é ignorado", warning.strip() == "",
      repr(warning[:300]))

# ── the pending item is consumed only once ─────────────────────────────────
# A pending item only exists on the warning path (recurrence); the block fixes
# the text in the turn itself and leaves no note for the next turn.
run("Stop", turn(BAD), session="s-uma-vez", stop_hook_active=True)
first = run("UserPromptSubmit", session="s-uma-vez").stdout
second = run("UserPromptSubmit", session="s-uma-vez").stdout
check("aviso é entregue uma vez só", first.strip() != "" and second.strip() == "",
      repr(second[:200]))

# ── the tightening of 2026-08-25: the Stop blocks ──────────────────────────
r = run("Stop", turn(BAD), session="s-bloqueio")
check("relatório fora do formato → Stop devolve decision=block",
      block_reason(r.stdout) != "", repr(r.stdout[:200]))
check("…e o motivo manda reescrever agora, não no próximo turno",
      "Reescreva o relatório inteiro" in block_reason(r.stdout),
      repr(r.stdout[:400]))
check("…e não deixa pendência para o turno seguinte (o texto já foi corrigido)",
      run("UserPromptSubmit", session="s-bloqueio").stdout.strip() == "")

r = run("Stop", turn(GOOD), session="s-bloqueio-bom")
check("relatório no formato → Stop não bloqueia",
      block_reason(r.stdout) == "", repr(r.stdout[:200]))

# ── anti-loop lock: a rewrite that still deviates does not block again ─────
r = run("Stop", turn(BAD), session="s-loop", stop_hook_active=True)
check("parada já vinda de bloqueio → não bloqueia de novo",
      block_reason(r.stdout) == "", repr(r.stdout[:200]))
warning = run("UserPromptSubmit", session="s-loop").stdout
check("…e cai no caminho de aviso, no turno seguinte",
      "plain-report" in warning, repr(warning[:200]))

# ── session ended by the wrap-up (2026-10-16, fb-20261016-4) ───────────────
CMD_WRAP = ("<command-message>wrap-up</command-message>\n"
            "<command-name>/common:wrap-up</command-name>")
END_WRAP = ("Tudo integrado e enviado; o handoff está escrito.\n\n"
            "Safe to `exit`.")
NO_QUESTION = GOOD.replace(STEPS, "\n\n### Decisões e próximos passos\n"
                           "Nada pendente. Próxima sessão começa por X.\n")
assert NO_QUESTION != GOOD


def text(t, sidechain=False):
    return msg("assistant", [{"type": "text", "text": t}], sidechain=sidechain)


def multi_turn(opening, end_wrap, report, changed_final=False,
                sidechain_wrap=False):
    """wrap-up -> closing report -> "sim" -> final-turn report."""
    rows = [msg("user", [{"type": "text", "text": "wrap up"}], mtype="user")]
    if opening == "comando":
        rows[0] = msg("user", CMD_WRAP, mtype="user")
    elif opening == "skill":
        rows.append(msg("assistant", [{"type": "tool_use", "name": "Skill",
                                       "input": {"skill": "common:wrap-up"}}]))
    rows.append(msg("assistant", [{"type": "tool_use", "name": "Bash",
                                   "input": {"command": "git commit -m x"}}]))
    if end_wrap:
        rows.append(text(end_wrap, sidechain=sidechain_wrap))
    rows.append(msg("user", [{"type": "text", "text": "sim"}], mtype="user"))
    if changed_final:
        rows.append(msg("assistant", [{"type": "tool_use", "name": "Bash",
                                       "input": {"command": "git commit -m y"}}]))
    rows.append(text(report))
    return transcript(*rows)


r = run("Stop", multi_turn("comando", END_WRAP, GOOD), session="s-wrap-a")
check("(a) wrap-up + Safe to exit + metrics sem Edit com pergunta → bloqueia "
      "citando o wrap-up", "wrap-up" in block_reason(r.stdout),
      repr(r.stdout[:300]))
reason_a = block_reason(r.stdout)
check("(a) o bloqueio pós-wrap-up manda \"Nada pendente\", sem pedir pergunta",
      "Nothing pending" in reason_a
      and "uma pergunta fechada por item" not in reason_a, repr(reason_a[-300:]))

r = run("Stop", multi_turn("comando", END_WRAP, GOOD), session="s-wrap-aw",
        stop_hook_active=True)
check("(a2) Stop com stop_hook_active em sessão encerrada → não bloqueia",
      block_reason(r.stdout) == "", repr(r.stdout[:300]))
r2 = run("UserPromptSubmit", session="s-wrap-aw")
check("(a2) aviso do turno seguinte usa o formato de sessão encerrada",
      "Nothing pending" in r2.stdout
      and "uma pergunta fechada por item" not in r2.stdout, repr(r2.stdout[:400]))

r = run("Stop", multi_turn("comando", END_WRAP, NO_QUESTION), session="s-wrap-b")
check("(b) mesma sequência com \"Nada pendente.\" e Pra você nada → não bloqueia",
      block_reason(r.stdout) == "", repr(r.stdout[:300]))

r = run("Stop", multi_turn("comando", "Parei: conflito de merge em x.py.", GOOD),
        session="s-wrap-c")
check("(c) wrap-up sem Safe to exit (travou) → pergunta NÃO é barrada como pós-wrap-up",
      "wrap-up" not in block_reason(r.stdout), repr(r.stdout[:300]))

end_with_question = END_WRAP + "\n\n" + GOOD
r = run("Stop", multi_turn("comando", None, end_with_question, changed_final=True),
        session="s-wrap-d")
check("(d) o relatório do próprio wrap-up (Safe to exit + pergunta, com commit) → bloqueia",
      "wrap-up" in block_reason(r.stdout), repr(r.stdout[:300]))

rows_e = [msg("user", [{"type": "text", "text": "faça"}], mtype="user"),
          msg("user", CMD_WRAP, mtype="user", sidechain=True),
          text(END_WRAP, sidechain=True),
          msg("assistant", [{"type": "tool_use", "name": "Edit",
                             "input": {"file_path": "x.py"}}]),
          text(GOOD)]
r = run("Stop", transcript(*rows_e), session="s-wrap-e")
check("(e) wrap-up e Safe to exit só em sidechain → não encerra",
      "wrap-up" not in block_reason(r.stdout), repr(r.stdout[:300]))

r = run("Stop", multi_turn("skill", END_WRAP, GOOD), session="s-wrap-f")
check("(f) invocação por tool_use Skill common:wrap-up → encerrada, bloqueia",
      "wrap-up" in block_reason(r.stdout), repr(r.stdout[:300]))

# ── telemetry ──────────────────────────────────────────────────────────────
events = []
for f in TELEM.glob("events-*.jsonl"):
    events += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
check("cada medição vira evento de telemetria",
      any(e.get("event") == "report_style" for e in events), str(events[:2]))
check("…com relatório bom registrando zero desvios",
      any(e.get("event") == "report_style" and e.get("desvios") == 0 for e in events))
check("…e o evento diz se aquela medição bloqueou",
      any(e.get("event") == "report_style" and e.get("bloqueou") is True
          for e in events) and
      any(e.get("event") == "report_style" and e.get("bloqueou") is False
          for e in events), str([e.get("bloqueou") for e in events][:6]))

check("(g) telemetria carrega pos_wrap_up=true no caso (a)",
      any(e.get("event") == "report_style" and e.get("pos_wrap_up") is True
          and e.get("tipos") == ["pergunta-pos-wrap-up"] for e in events),
      str([(e.get("pos_wrap_up"), e.get("tipos")) for e in events][-6:]))
check("…e false nas medições comuns",
      any(e.get("event") == "report_style" and e.get("pos_wrap_up") is False
          for e in events))

# (h) Pra você announces something and the list says "Nada pendente." (no question)
ANNOUNCES = GOOD.replace("nada pra decidir agora; precisa reinstalar pra valer.",
                      "uma decisão sua, lista no fim.").replace(
    STEPS, "\n\n### Decisões e próximos passos\nNada pendente.\n")
assert ANNOUNCES != GOOD and "uma decisão sua" in ANNOUNCES
r = run("Stop", multi_turn("comando", END_WRAP, ANNOUNCES), session="s-wrap-h")
check("(h) pós-wrap-up com Pra você anunciando algo e \"Nada pendente.\" → bloqueia",
      "wrap-up" in block_reason(r.stdout), repr(r.stdout[:300]))

CLOSED = GOOD.replace(STEPS, "\n\n### Decisões e próximos passos\n"
                      "Nada pendente. Próxima sessão começa por X.\n")
r = run("Stop", multi_turn("comando", END_WRAP, CLOSED), session="s-wrap-h2")
check("(h2) pós-wrap-up com Pra você nada e \"Próxima sessão começa por X.\" → não bloqueia",
      block_reason(r.stdout) == "", repr(r.stdout[:300]))

# (h3) final turn CHANGED something (Edit): the pra-voce-sem-lista rule is
# suppressed after the wrap-up; only the closed-session message appears.
rows_h3 = [msg("user", CMD_WRAP, mtype="user"),
           msg("assistant", [{"type": "tool_use", "name": "Bash",
                              "input": {"command": "git commit -m x"}}]),
           text(END_WRAP),
           msg("user", [{"type": "text", "text": "sim"}], mtype="user"),
           msg("assistant", [{"type": "tool_use", "name": "Edit",
                              "input": {"file_path": "x.py"}}]),
           text(ANNOUNCES)]
r = run("Stop", transcript(*rows_h3), session="s-wrap-h3")
reason_h3 = block_reason(r.stdout)
check("(h3) pós-wrap-up com Edit, Pra você anunciando e \"Nada pendente.\" → "
      "bloqueia citando wrap-up, sem pra-voce-sem-lista",
      "wrap-up" in reason_h3 and "item numerado nenhum" not in reason_h3
      and "pra-voce-sem-lista" not in reason_h3, repr(r.stdout[:400]))

# ── the prose that sustains the rule says what the hook charges ────────────
def read_rel(rel):
    return (REPO / rel).read_text(encoding="utf-8")

pr = read_rel("common/skills/plain-report/SKILL.md")
check("spec: plain-report tem o título \"Depois do wrap-up\"",
      any(l.startswith("#") and "Depois do wrap-up" in l for l in pr.splitlines()))
check("spec: plain-report manda \"Nothing pending. Próxima sessão começa por\"",
      "Nothing pending. Próxima sessão começa por" in pr)

mt = read_rel("common/commands/metrics.md")
check("spec: metrics.md trata \"sessão já encerrada\" e cita pergunta-pos-wrap-up",
      "session already closed" in mt and "Safe to exit" in mt
      and "pergunta-pos-wrap-up" in mt)

wu = read_rel("common/commands/wrap-up.md")
check("spec: wrap-up.md cita pergunta-pos-wrap-up e \"Próxima sessão começa por\"",
      "pergunta-pos-wrap-up" in wu and "Próxima sessão começa por" in wu)

dy = read_rel("common/skills/default-yes/SKILL.md")
sec = dy.split("## Keep the thread of the session", 1)[-1].split("\n## ", 1)[0]
check("spec: default-yes, seção \"Keep the thread of the session\" tem \"After the wrap-up\"",
      "## Keep the thread of the session" in dy and "After the wrap-up" in sec)

# ── English labels (interface-in-english, 2026-10-23) ──────────────────────
# The lint accepts the new labels and the old ones; the message orders writing the new ones.
STEPS_EN = ("\n\n### Decisions and next steps\n"
             "*Answer by number: yes, no, or \"let's talk\".*\n"
             "1. **Do you run `bin/install.sh --clean` now?**\n"
             "   Where: root of the cepa clone.\n"
             "   Command:\n"
             "   ```\n"
             "   bin/install.sh --clean\n"
             "   ```\n"
             "   Done when: the terminal prints `installed`.\n"
             "   I recommend **yes** — without it the change does not apply.\n")
GOOD_EN = GOOD.replace(STEPS, STEPS_EN).replace(
    "**Pra você:**", "**For you:**").replace("### Detalhe técnico", "### Technical detail")
check("EN: relatório com For you / Technical detail / Decisions and next steps / "
      "I recommend yes → nenhum aviso", cycle(GOOD_EN).strip() == "", cycle(GOOD_EN)[:300])
check("EN: BOM_EN não tem nenhum rótulo pt-BR (o teste prova a leitura em inglês)",
      not any(x in GOOD_EN for x in ("Pra você", "Detalhe técnico", "Decisões", "Recomendo")))
# mixed (old label at the top, new at the end) also passes
MIXED = GOOD.replace(STEPS, STEPS_EN)
check("EN+pt-BR misto → nenhum aviso", cycle(MIXED).strip() == "", cycle(MIXED)[:300])
check("pt-BR antigo continua passando → nenhum aviso", cycle(GOOD).strip() == "",
      cycle(GOOD)[:300])

warning = cycle(GOOD_EN.replace("**For you:**", "Resumo:"))
check("EN: sem a linha For you → avisa citando o rótulo novo",
      "`**For you:**`" in warning, repr(warning[:300]))
warning = cycle(GOOD_EN.replace(STEPS_EN, ""))
check("EN: sem a seção final → avisa citando Decisions and next steps",
      "### Decisions and next steps" in warning, repr(warning[:300]))
warning = cycle(GOOD_EN.replace("   I recommend **yes** — without it the change does not apply.\n", ""))
check("EN: item sem I recommend → avisa (RECOMENDACAO lê o inglês)",
      "I recommend yes/no" in warning and "item-sem-recomendacao" not in warning
      and "não trazem" in warning, repr(warning[:300]))
warning = cycle(GOOD_EN.replace("Do you run", "You run").replace(
    "   Done when: the terminal prints `installed`.\n", ""))
check("EN: tarefa \"You ...\" sem Done when → avisa (ITEM_VOCE lê o inglês)",
      "Done when" in warning, repr(warning[:300]))
warning = cycle(GOOD_EN.replace("Do you run", "Run").replace(
    "   Done when: the terminal prints `installed`.\n", ""))
check("EN: item que não é \"You ...\" não exige Done when", "Done when" not in warning,
      repr(warning[:300]))
check("EN: For you \"nothing\" + \"Nothing pending.\" → nenhum aviso",
      cycle(GOOD_EN.replace("nada pra decidir agora; precisa reinstalar pra valer.",
                           "nothing to decide.")
            .replace(STEPS_EN, "\n\n### Decisions and next steps\nNothing pending.\n")
            ).strip() == "")
warning = cycle(GOOD_EN.replace("nada pra decidir agora; precisa reinstalar pra valer.",
                             "one manual step.").replace(
    STEPS_EN, "\n\n### Decisions and next steps\nNothing pending.\n"))
check("EN: For you anunciando + Nothing pending. → pra-voce-sem-lista",
      "item numerado" in warning and "For you" in warning, repr(warning[:400]))

# ── reference code without a legend (2026-10-31, fb-20261031-1) ───────────
CODED = GOOD.replace(
    "nada pra decidir agora; precisa reinstalar pra valer.",
    "uma decisão — lista no fim.").replace(
    STEPS,
    "\n\n### Decisões e próximos passos\n"
    "1. **Mantenho E2 como recomendação de P1, com a comparação reescrita "
    "por PR8?**\n   Recomendo **sim** — nenhuma lente derrubou E2.\n")
warning = cycle(CODED)
check("código sem legenda na lista final → codigo-sem-legenda",
      "sem legenda" in warning and "E2" in warning and "PR8" in warning,
      repr(warning[:400]))
LEGEND = ("\n\nLegenda:\n- **E2**: exportar o XML pelo Konsist\n"
          "- **P1**: a proposta de construir a camada 1 primeiro\n"
          "| PR8 | a comparação entre os dois caminhos reescrita pela lente de produto |\n")
warning = cycle(CODED.replace("\n\n### Decisões", LEGEND + "\n\n### Decisões"))
check("mesmos códigos com legenda na mensagem → nenhum aviso sobre código",
      "sem legenda" not in warning, repr(warning[:400]))
warning = cycle(CODED.replace("Mantenho E2 como", "Mantenho E2 (exportar o XML "
                              "pelo Konsist) como")
                .replace("por PR8?", "por PR8 (a lente de produto)?")
                .replace("de P1,", "de P1 (construir a camada 1 primeiro),"))
check("definição inline na primeira menção basta",
      "sem legenda" not in warning, repr(warning[:400]))
warning = cycle(CODED.replace("E2", "`E2`").replace("P1", "`P1`")
                .replace("PR8", "`PR8`"))
check("código entre crases é código, não rótulo → não cobra",
      "sem legenda" not in warning, repr(warning[:400]))
warning = cycle(GOOD.replace("por nível;", "por nível (S3, MD5, L4, UTF8);"))
check("S3, MD5, L4, UTF8 não são códigos de referência",
      "sem legenda" not in warning, repr(warning[:400]))

# ── corrupted entry does not take down the turn ────────────────────────────
r = run("Stop", str(TMP / "nao-existe.jsonl"))
check("transcript ausente → rc=0", r.returncode == 0, f"rc={r.returncode}")
r = subprocess.run([sys.executable, str(HOOK)], input="{lixo",
                   capture_output=True, text=True)
check("payload ilegível → rc=0", r.returncode == 0, f"rc={r.returncode}")

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all report-style tests passed")
