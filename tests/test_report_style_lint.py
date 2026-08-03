#!/usr/bin/env python3
"""Testes do medidor de formato de relatório (common/hooks/report-style-lint.py).

O defeito que ele mede (relatado pelo usuário em 03/08/2026): relatórios que
exigem duas leituras — jargão interno na abertura, mecanismo antes do resultado,
sem um ponto onde dá pra parar de ler.

Garantias:
  - turno que ALTEROU algo + relatório fora do formato -> desvio registrado, e o
    aviso aparece no UserPromptSubmit seguinte;
  - relatório dentro do formato -> nenhum aviso;
  - turno de CONVERSA (nada alterado) -> nunca medido, por pior que seja;
  - relatório curto -> nunca medido (é recado, não relatório);
  - jargão no bloco de detalhe técnico -> permitido; na abertura -> sinalizado;
  - higiene ("árvore limpa", "memória atualizada") no topo -> sinalizada; a
    mesma frase no detalhe técnico -> permitida;
  - a lista final `### Decisões e próximos passos` é obrigatória, é a última
    seção, tem itens de lista (ou "Nada pendente.") e fica fora do teto de 200
    palavras;
  - resposta de subagente (sidechain) nunca é confundida com o relatório;
  - o hook NUNCA bloqueia: exit 0 em todos os casos.
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

# A lista do fim, obrigatória desde 03/08/2026. Como todo relatório de
# trabalho feito precisa dela, ela entra em todos os fixtures; os testes que
# medem OUTRA coisa não devem falhar por falta dela.
PASSOS = ("\n\n### Decisões e próximos passos\n"
          "- **Você faz —** rodar `bin/install.sh`; sem isso a mudança não vale.\n")


BOM = ("O verificador de provas aceitava qualquer palavra fora de uma lista de "
       "proibidas, então um erro de digitação virava aprovação. Agora ele só "
       "aceita as palavras previstas para cada checagem, e recusa o resto.\n\n"
       "**Pra você:** nada pra decidir agora; precisa reinstalar pra valer.\n\n"
       "### Detalhe técnico\n"
       "O portão passou a comparar contra um enum fechado por nível; o dublê "
       "segue barrado e cada perturbação foi ao vermelho sozinha. " * 6
       + PASSOS)

RUIM = ("O portão agora falha fechado. Cada status é conferido contra o enum "
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


def turno(relatorio, alterou=True, sidechain_extra=None):
    """Um turno completo: prompt do usuário, trabalho, relatório final."""
    rows = [msg("user", [{"type": "text", "text": "faça a coisa"}], mtype="user")]
    if alterou:
        rows.append(msg("assistant", [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "x.py"}}]))
    rows.append(msg("assistant", [{"type": "text", "text": relatorio}]))
    if sidechain_extra:
        # DEPOIS do relatório de propósito: é assim que cai no transcript um
        # subagente em background, que termina depois da resposta principal.
        # Sidechain antes do relatório não prova nada — a ordem já resolveria.
        rows.append(msg("assistant", [{"type": "text", "text": sidechain_extra}],
                        sidechain=True))
    return transcript(*rows)


def run(evento, transcript_path="", session="s1"):
    payload = json.dumps({"hook_event_name": evento, "session_id": session,
                          "transcript_path": transcript_path, "cwd": str(TMP)})
    env = dict(os.environ, CEPA_REPORT_STYLE_DIR=str(STATE),
               CEPA_TELEMETRY_DIR=str(TELEM))
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True, env=env)


def ciclo(relatorio, **kw):
    """Stop (mede) seguido de UserPromptSubmit (avisa). Devolve o aviso."""
    r1 = run("Stop", turno(relatorio, **kw))
    check(f"Stop nunca bloqueia (rc=0) — {relatorio[:24]!r}", r1.returncode == 0,
          f"rc={r1.returncode} {r1.stderr[:200]}")
    r2 = run("UserPromptSubmit")
    check("UserPromptSubmit nunca bloqueia (rc=0)", r2.returncode == 0,
          f"rc={r2.returncode}")
    return r2.stdout


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# ── o caso que motivou tudo ────────────────────────────────────────────────
aviso = ciclo(RUIM)
check("relatório com jargão na abertura → avisa", "report-style" in aviso,
      repr(aviso[:200]))
check("…e nomeia os termos que precisam de tradução",
      "portão" in aviso and "falha fechado" in aviso, repr(aviso[:400]))
check("…e cobra a linha Pra você", "Pra você" in aviso, repr(aviso[:400]))

# ── o mesmo conteúdo, dentro do formato ────────────────────────────────────
aviso = ciclo(BOM)
check("relatório no formato → nenhum aviso", aviso.strip() == "", repr(aviso[:300]))

# ── jargão é permitido no bloco técnico ────────────────────────────────────
check("jargão no detalhe técnico não é sinalizado",
      "portão" in BOM and "dublê" in BOM)

# ── conversa nunca é medida ────────────────────────────────────────────────
aviso = ciclo(RUIM, alterou=False)
check("turno sem alteração → não mede, mesmo com relatório ruim",
      aviso.strip() == "", repr(aviso[:300]))

# ── recado curto nunca é medido ────────────────────────────────────────────
aviso = ciclo("O portão agora falha fechado e o dublê segue barrado.")
check("relatório curto → não mede", aviso.strip() == "", repr(aviso[:300]))

# ── abertura longa demais ──────────────────────────────────────────────────
aviso = ciclo("Primeira frase de resultado. Segunda frase. Terceira frase. "
              "Quarta frase que já passou do limite. Quinta.\n\n"
              "**Pra você:** nada.\n\n### Detalhe técnico\n" + "x " * 90)
check("abertura com 5 frases → avisa", "frases" in aviso, repr(aviso[:300]))

# ── falta o Pra você ───────────────────────────────────────────────────────
aviso = ciclo("Resultado dito de forma clara e sem termo interno nenhum, "
              "em uma frase só.\n\n### Detalhe técnico\n" + "x " * 90)
check("sem a linha Pra você → avisa", "Pra você" in aviso, repr(aviso[:300]))

# ── teto de palavras antes do técnico ──────────────────────────────────────
aviso = ciclo("Resultado em uma frase clara.\n\n**Pra você:** nada.\n\n" +
              "palavra " * 210 + "\n\n### Detalhe técnico\nx")
check("mais de 200 palavras antes do detalhe técnico → avisa",
      "palavras antes do detalhe" in aviso, repr(aviso[:300]))

# ── abstração no lugar do fato (vale no texto INTEIRO) ─────────────────────
# O bloco técnico era zona franca na v1, e foi exatamente lá que o usuário
# achou as três frases obscuras em 03/08/2026.
aviso = ciclo("Resultado dito de forma clara em uma frase.\n\n"
              "**Pra você:** nada.\n\n"
              "### Detalhe técnico\n"
              "O escopo virou um sinal mecânico e o aviso chega por um "
              "caminho indireto. " + "detalhe " * 70)
check("abstração DENTRO do detalhe técnico → avisa", "abstração" in aviso,
      repr(aviso[:300]))
check("…e cita as expressões encontradas",
      "sinal mecânico" in aviso and "caminho indireto" in aviso, repr(aviso[:400]))

aviso = ciclo("Resultado dito de forma clara em uma frase.\n\n"
              "**Pra você:** nada.\n\n### Detalhe técnico\n" + "detalhe " * 90
              + PASSOS)
check("detalhe técnico sem abstração → nenhum aviso", aviso.strip() == "",
      repr(aviso[:300]))

# ── higiene relatada como resultado ────────────────────────────────────────
# 03/08/2026: relatório dentro do formato, e o usuário mesmo assim perguntou
# "so what?" — quatro linhas dele diziam que a árvore ficou limpa, que nenhum
# worktree sobrou e que a memória foi atualizada.
aviso = ciclo("Os três cards que estavam presos passaram e foram para Done. "
              "A árvore de trabalho ficou limpa e nenhum worktree sobrou.\n\n"
              "**Pra você:** nada pra decidir. Memória atualizada.\n\n"
              "### Detalhe técnico\n" + "detalhe " * 90 + PASSOS)
check("higiene na abertura → avisa", "higiene" in aviso, repr(aviso[:300]))
check("…e cita as frases encontradas",
      "árvore de trabalho limpa" in aviso or "nenhum worktree" in aviso,
      repr(aviso[:400]))

aviso = ciclo("Os três cards que estavam presos passaram, agora com prova "
              "refeita do zero.\n\n**Pra você:** nada pra decidir.\n\n"
              "### Detalhe técnico\n"
              "Commit feito; a árvore de trabalho ficou limpa e nenhum "
              "worktree sobrou. " + "detalhe " * 80 + PASSOS)
check("mesma higiene DENTRO do detalhe técnico → não avisa",
      aviso.strip() == "", repr(aviso[:300]))

# ── voz passiva: densidade, não caça ───────────────────────────────────────
aviso = ciclo("Resultado dito de forma clara em uma frase.\n\n"
              "**Pra você:** nada.\n\n### Detalhe técnico\n"
              "O arquivo foi criado, o teste foi rodado, a regra é aplicada "
              "e a saída é verificada pelo hook. " + "detalhe " * 70)
check("quatro passivas → avisa", "passivas" in aviso, repr(aviso[:300]))

aviso = ciclo("Resultado dito de forma clara em uma frase.\n\n"
              "**Pra você:** nada.\n\n### Detalhe técnico\n"
              "O arquivo foi criado pelo hook. " + "detalhe " * 80 + PASSOS)
check("uma passiva só → não avisa (é português normal)", aviso.strip() == "",
      repr(aviso[:300]))

# ── a lista do fim ─────────────────────────────────────────────────────────
# Pedido do usuário em 03/08/2026: "ao final de cada report, uma lista objetiva
# de decisões a serem tomadas ou próximos passos a serem seguidos".
CORPO = ("Resultado dito de forma clara em uma frase.\n\n"
         "**Pra você:** um passo manual — lista no fim.\n\n"
         "### Detalhe técnico\n" + "detalhe " * 90)

aviso = ciclo(CORPO)
check("sem a seção final → avisa", "Decisões e próximos passos" in aviso,
      repr(aviso[:300]))

aviso = ciclo(CORPO + PASSOS +
              "\n### Uma observação final\nnão devia existir aqui.\n")
check("seção final que não é a última → avisa",
      "não é a última seção" in aviso, repr(aviso[:400]))

aviso = ciclo(CORPO + "\n\n### Decisões e próximos passos\n"
              "Precisa reinstalar e depois decidir se aperta.\n")
check("lista do fim escrita em prosa → avisa",
      "itens de lista" in aviso, repr(aviso[:400]))

aviso = ciclo(CORPO + "\n\n### Próximos passos\nNada pendente.\n")
check("\"Nada pendente.\" satisfaz a lista", aviso.strip() == "",
      repr(aviso[:300]))

# O teto de 200 palavras vale até o detalhe técnico; a lista do fim não entra
# nele nem quando o relatório não tem bloco técnico nenhum.
aviso = ciclo("Resultado em uma frase clara.\n\n**Pra você:** um passo.\n\n"
              "### Decisões e próximos passos\n"
              + "- **Você faz —** rodar o install.\n" * 40)
check("lista longa sem bloco técnico → não estoura o teto",
      "palavras antes do detalhe" not in aviso, repr(aviso[:300]))

# ── resposta de subagente não é o relatório ────────────────────────────────
aviso = ciclo(BOM, sidechain_extra=RUIM)
check("texto de subagente (sidechain) é ignorado", aviso.strip() == "",
      repr(aviso[:300]))

# ── a pendência é consumida uma única vez ──────────────────────────────────
run("Stop", turno(RUIM))
primeiro = run("UserPromptSubmit").stdout
segundo = run("UserPromptSubmit").stdout
check("aviso é entregue uma vez só", primeiro.strip() != "" and segundo.strip() == "",
      repr(segundo[:200]))

# ── telemetria ─────────────────────────────────────────────────────────────
eventos = []
for f in TELEM.glob("events-*.jsonl"):
    eventos += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
check("cada medição vira evento de telemetria",
      any(e.get("event") == "report_style" for e in eventos), str(eventos[:2]))
check("…com relatório bom registrando zero desvios",
      any(e.get("event") == "report_style" and e.get("desvios") == 0 for e in eventos))

# ── entrada corrompida não derruba o turno ─────────────────────────────────
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
