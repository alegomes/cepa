#!/usr/bin/env python3
"""Mede o relatório final do turno contra o formato da skill `plain-report`.

Motivo (03/08/2026): o usuário relatou que precisa ler os relatórios mais de
uma vez para entender — jargão interno demais, ordem invertida (mecanismo antes
do resultado) e detalhe irrelevante. A regra já existia no CLAUDE.md global
("2 frases leigas, recomendação default, técnico por último") e vinha sendo
aplicada só a findings isolados. Regra clara que segue violada precisa de
medição, não de mais prosa — mesmo princípio do proof-verdict-guard.

Dois eventos, um arquivo:

  Stop              — lê a última mensagem do assistente no transcript, mede e,
                      havendo desvio, BLOQUEIA a parada: devolve
                      {"decision": "block"} com os desvios, e o turno continua
                      para reescrever o relatório no formato. Aperto decidido em
                      25/08/2026: um mês de "avisa e mede" deu 247 relatórios
                      fora do padrão em 501 medidos (49%) — o aviso não bastou.
                      Trava anti-loop: se a parada JÁ veio de um bloqueio deste
                      hook (`stop_hook_active`), ele não bloqueia de novo; grava
                      a pendência e deixa passar, para o aviso chegar no turno
                      seguinte sem prender a sessão.
  UserPromptSubmit  — se houver desvio pendente da vez anterior, injeta o aviso
                      no contexto do próximo turno e apaga a pendência. É assim
                      que o aviso chega ao modelo sem travar o turno.

Escopo (decisão do usuário, 03/08/2026): só relatório de TRABALHO FEITO. Para
saber se a resposta é um relatório, o hook olha se o turno usou Edit, Write,
MultiEdit, NotebookEdit ou rodou `git commit`. Se não usou, ele nem abre o
texto: conversa, pergunta curta e discussão de design ficam de fora, porque
formatar um "sim, existe" em três blocos seria pior que o problema.

Exceção (CS-5, 2026-10-08): o turno de ENTREVISTA do `/common:epic`. Ali o
comando manda gravar a resposta aceita no documento no mesmo turno, então todo turno escreve, e o hook o tratava como relatório: na
transcrição de teste do `/common:epic` ele mandou reescrever o desafio no
formato plain-report, e a pergunta virou item numerado com "Recomendo sim",
que é o menu que a entrevista proíbe. O turno é poupado quando TODA escrita
dele foi em `docs/epics/<nome>.md`, não houve commit, o último parágrafo da
fala tem uma pergunta e a fala não traz nenhuma marca do relatório
(`**Pra você:**`, "Detalhe técnico", "Decisões e próximos passos"). O
relatório de fechamento tem essas marcas e termina em pergunta numerada, então
continua medido. O `/common:spec` fica fora da exceção: o turno dele pergunta
em rodadas de até quatro, e poupá-lo é outra decisão.

Tarefa do dono com passo a passo (2026-10-15). Em 14/10/2026 o dono reprovou um
relatório cujo `Pra você:` dizia "fechar as duas rotas humanas ... e os sete
buracos do RIPD" e cuja lista do fim dizia "Nada pendente.": a tarefa dele só
existia como categoria, e ele perguntou "O que, afinal, que eu tenho que fazer?
Dê-me o passo a passo." Duas medições novas: `pra-voce-sem-lista` (o `Pra
você:` anuncia algo pendente e a lista do fim não tem item numerado nenhum) e
`tarefa-sem-passo` (item "Você ..." sem comando ou arquivo, ou sem a linha
"Pronto quando"). A primeira só olha se o que o topo anuncia aparece no fim; a
segunda só olha a forma do item, não se o comando está certo.

Sessão já encerrada pelo wrap-up (2026-10-16, feedback fb-20261016-4). Depois
de `/common:wrap-up` terminar com "Safe to `exit`", o agente ofereceu
`/common:metrics` na lista do fim, o dono aceitou, e o relatório do metrics
terminou com uma pergunta fechada nova: a sessão fechada abriu uma frente
nova, e o dono se perdeu na árvore de forks. Medição nova, categoria
`pergunta-pos-wrap-up`: se o wrap-up foi invocado e DEPOIS algum texto do
assistente diz "Safe to exit", todo relatório seguinte que traga item numerado
com `?` na lista do fim, ou um `Pra você:` que anuncia algo, é barrado. A
sessão encerrada é lida do TRANSCRIPT, não de um arquivo-marcador, de
propósito: um marcador no handoff vazaria para a próxima sessão na mesma
branch, e um marcador em `.claude/` dependeria de o modelo lembrar de
escrevê-lo. O transcript tem o escopo da sessão e é mecânico. Um wrap-up
invocado que parou numa trava (conflito de merge, por exemplo) nunca disse
"Safe to exit" e NÃO encerra a sessão: ali o relatório pode mesmo pedir que o
usuário resolva algo. O turno do metrics só lê, então a regra de escopo acima
(turno que alterou algo) deixaria o incidente sem medição; por isso, com a
sessão encerrada, o hook lê o relatório mesmo sem alteração e mede só esta
categoria.

Saída: exit 0 sempre. O bloqueio viaja no JSON de stdout, não no código de
saída — o hook nunca derruba o turno por erro próprio.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── limites do formato (common/skills/plain-report/SKILL.md) ────────────────
MAX_FRASES_ABERTURA = 3
MAX_PALAVRAS_ANTES_DO_TECNICO = 200
MIN_PALAVRAS_PARA_MEDIR = 80   # abaixo disso não é relatório, é recado
MAX_PASSIVAS = 3               # densidade, não caça: uma passiva é normal

MARCADOR_TECNICO = re.compile(r"^\s{0,3}#{1,6}\s*detalhe\s+t[ée]cnico", re.I | re.M)
MARCADOR_PRA_VOCE = re.compile(r"(^\s{0,3}#{1,6}\s*pra\s+voc[êe]|\*\*\s*pra\s+voc[êe]\s*:?\s*\*\*)",
                               re.I | re.M)
# A lista do fim (pedido do usuário, 03/08/2026). Aceita "Próximos passos",
# "Decisões" ou as duas juntas — o título canônico da skill é o terceiro.
MARCADOR_PASSOS = re.compile(
    r"^\s{0,3}#{1,6}\s*(decis(?:ões|oes)(?:\s+e\s+pr[óo]ximos\s+passos)?|"
    r"pr[óo]ximos\s+passos)\s*$", re.I | re.M)
CABECALHO = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.M)
ITEM_DE_LISTA = re.compile(r"^\s{0,3}([-*+]|\d+[.)])\s+\S", re.M)
# Item numerado: o usuário responde "1 sim, 2 não, 3 vamos falar" sem ter de
# copiar o texto de volta. Marcador solto ("- ") não dá número para citar.
ITEM_NUMERADO = re.compile(r"^\s{0,3}\d+[.)]\s+\S", re.M)
RECOMENDACAO = re.compile(r"recomendo\b", re.I)
# Item de tarefa do dono: a pergunta começa por "Você ..." (2026-10-15).
ITEM_VOCE = re.compile(r"^\s*\d+[.)]\s+\**\s*voc[êe]\b", re.I)
PRONTO_QUANDO = re.compile(r"pronto\s+quando", re.I)
# Caminho de arquivo: começa por / ~/ ./ ../ ; ou tem 2+ trechos ASCII
# separados por barra ("docs/lgpd"); ou é nome com extensão ("ripd.md").
# Trecho com acento não conta, para "sim/não" não passar por caminho.
CAMINHO = re.compile(
    r"(?:(?:^|[\s(])(?:~|\.{1,2})?/[\w.-]+)"
    r"|(?:(?:^|[\s(])[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)"
    r"|(?:\b[A-Za-z0-9_-]+\.[A-Za-z]\w{0,4}\b)")

STATE_DIR = Path(os.environ.get("CEPA_REPORT_STYLE_DIR")
                 or (Path.home() / ".claude" / "cepa-report-style"))


def _t_emit(event: str, cwd: str = None, **fields) -> None:
    """Espelho mínimo de common/hooks/_telemetry.py (import cross-plugin é
    frágil entre diretórios de cache versionados). Estritamente fail-silent."""
    try:
        import subprocess
        repo = ""
        try:
            out = subprocess.run(
                ["git", "-C", cwd or os.getcwd(), "rev-parse",
                 "--path-format=absolute", "--git-common-dir"],
                capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                common = out.stdout.strip()
                repo = Path(common).parent.name if common.endswith("/.git") else Path(common).name
        except Exception:
            pass
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "event": event, "repo": repo}
        entry.update(fields)
        tdir = Path(os.environ.get("CEPA_TELEMETRY_DIR") or (Path.home() / ".claude" / "cepa-telemetry"))
        tdir.mkdir(parents=True, exist_ok=True)
        with open(tdir / f"events-{entry['ts'][:7]}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


# ── glossário ───────────────────────────────────────────────────────────────
def _secao(titulo: str) -> list:
    """Os termos em negrito de uma seção do common/glossario.md."""
    for base in (Path(__file__).resolve().parent.parent,          # common/
                 Path(__file__).resolve().parent.parent.parent):  # repo/common
        f = base / "glossario.md"
        if f.is_file():
            break
    else:
        return []
    try:
        texto = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    m = re.search(r"^##\s*" + re.escape(titulo) + r"\s*$(.*?)(?=^##\s|\Z)",
                  texto, re.S | re.M | re.I)
    if not m:
        return []
    termos = []
    for linha in m.group(1).splitlines():
        m2 = re.match(r"^\s*-\s*\*\*(.+?)\*\*", linha)
        if not m2:
            continue
        # "portão", "falha aberto / falha fechado", "é medido / são medidas"
        for termo in m2.group(1).split("/"):
            termo = termo.strip().lower()
            if len(termo) >= 4:
                termos.append(termo)
    return termos


def load_jargao() -> list:
    """Termos internos do projeto — sinalizados só na ABERTURA.

    A seção 'Aceitos sem tradução' fica de fora de propósito: é o vocabulário
    já corrente entre o usuário e o harness, e sinalizá-lo geraria ruído que
    faria o medidor ser ignorado. No detalhe técnico esses termos são
    permitidos: lá eles são densos e úteis.
    """
    return _secao("Traduzir sempre")


def load_abstracoes() -> list:
    """Categorias inventadas que ocupam o lugar do fato — sinalizadas no texto
    INTEIRO, inclusive no detalhe técnico.

    Motivo (03/08/2026): a primeira versão deste hook tratava o bloco técnico
    como zona franca, e foi exatamente lá que o usuário achou "virou um sinal
    mecânico", "nunca são medidas" e "chega por um caminho indireto" — nenhuma
    delas é jargão do projeto, todas são abstração inventada na hora. Bloco
    técnico tem liberdade de TAMANHO, não de clareza.
    """
    return _secao("Abstrações a evitar")


def load_higiene() -> list:
    """Frases que só interessam quando falham — sinalizadas na abertura e no
    `Pra você:`, nunca no detalhe técnico.

    Motivo (03/08/2026): o usuário leu um relatório inteiro dentro do formato e
    ainda assim perguntou "so what?". Quatro linhas dele diziam que a árvore
    ficou limpa, que nenhum worktree sobrou e que a memória foi atualizada —
    nenhuma delas muda alguma coisa para quem lê. No detalhe técnico uma oração
    dessas é barata; nas 200 palavras do topo ela toma o lugar da consequência.
    """
    return _secao("Higiene (não relatar)")


# Voz passiva e nominalização escondem quem faz o quê: "são medidas" não diz
# quem mede nem como. Regex proposital sobre ser + particípio.
PASSIVA = re.compile(
    r"\b(é|são|foi|foram|será|serão|era|eram|seja|sejam|sendo|ser)\s+"
    r"(\w{3,}(?:ad|id)[oa]s?)\b", re.I)


# ── leitura do transcript ───────────────────────────────────────────────────
def read_rows(transcript_path: str) -> list:
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            return [json.loads(l) for l in fh if l.strip()]
    except Exception:
        return []


def _is_user_prompt(row) -> bool:
    """Turno do usuário de verdade — não um tool_result travestido de user."""
    if row.get("type") != "user" or row.get("isSidechain"):
        return False
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in content)
    return False


def turno_alterou_algo(rows) -> bool:
    """Houve escrita, edição ou commit desde o último prompt do usuário?

    Se sim, a resposta final conta como relatório de trabalho feito. Olha
    também o que subagente fez: trabalho de subagente é trabalho feito.
    """
    inicio = 0
    for i in range(len(rows) - 1, -1, -1):
        if _is_user_prompt(rows[i]):
            inicio = i
            break
    for row in rows[inicio:]:
        if row.get("type") != "assistant":
            continue
        for bloco in (row.get("message") or {}).get("content") or []:
            if not isinstance(bloco, dict) or bloco.get("type") != "tool_use":
                continue
            nome = bloco.get("name", "")
            if nome in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                return True
            if nome == "Bash":
                cmd = str((bloco.get("input") or {}).get("command", ""))
                if re.search(r"\bgit\s+(commit|merge|push)\b", cmd):
                    return True
    return False


SAFE_TO_EXIT = re.compile(r"safe\s+to\s+`?exit`?", re.I)
INVOCA_WRAP_UP = re.compile(
    r"<command-name>\s*/?(?:common:)?wrap-up\s*</command-name>", re.I)


def _texto_do_usuario(row) -> str:
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def sessao_encerrada(rows) -> bool:
    """O `/common:wrap-up` foi invocado e DEPOIS disse "Safe to exit"?

    Só a conversa principal conta (nunca `isSidechain`). Invocação: a linha do
    usuário com `<command-name>/common:wrap-up</command-name>` (é assim que um
    slash command cai no transcript) ou começando por `/common:wrap-up` ou
    `/wrap-up`; ou um `tool_use` de `Skill` cujo `input.skill` termina em
    `wrap-up`. "Safe to exit" vale na mesma linha da invocação ou em qualquer
    texto de assistente posterior, inclusive o último relatório. Só texto de
    assistente conta: o corpo do comando, injetado como linha de usuário,
    também cita a frase."""
    invocado = False
    for row in rows:
        if row.get("isSidechain"):
            continue
        tipo = row.get("type")
        if tipo == "user":
            texto = _texto_do_usuario(row)
            if INVOCA_WRAP_UP.search(texto) or re.match(
                    r"\s*/(?:common:)?wrap-up\b", texto):
                invocado = True
        elif tipo == "assistant":
            for bloco in (row.get("message") or {}).get("content") or []:
                if not isinstance(bloco, dict):
                    continue
                if bloco.get("type") == "tool_use" and bloco.get("name") == "Skill":
                    skill = str((bloco.get("input") or {}).get("skill", ""))
                    if skill.endswith("wrap-up"):
                        invocado = True
                elif (bloco.get("type") == "text" and invocado
                      and SAFE_TO_EXIT.search(bloco.get("text", ""))):
                    return True
    return False


DOC_DE_ENTREVISTA = re.compile(r"(^|/)docs/epics/[^/]+\.md$")


def turno_de_entrevista(rows, fala: str) -> bool:
    """O turno só gravou o documento da entrevista e termina perguntando?

    "Termina perguntando" é o último parágrafo ter `?`, não o último
    caractere: a proposta que acompanha a pergunta às vezes vem depois dela
    ("...? Minha proposta: X. Corrija."), e foi esse o turno barrado na
    transcrição."""
    if (MARCADOR_PRA_VOCE.search(fala) or MARCADOR_TECNICO.search(fala)
            or MARCADOR_PASSOS.search(fala)):
        return False
    paragrafos = [p for p in re.split(r"\n\s*\n", fala) if p.strip()]
    if not paragrafos or "?" not in paragrafos[-1]:
        return False
    inicio = 0
    for i in range(len(rows) - 1, -1, -1):
        if _is_user_prompt(rows[i]):
            inicio = i
            break
    escreveu = False
    for row in rows[inicio:]:
        if row.get("type") != "assistant" or row.get("isSidechain"):
            continue
        for bloco in (row.get("message") or {}).get("content") or []:
            if not isinstance(bloco, dict) or bloco.get("type") != "tool_use":
                continue
            nome = bloco.get("name", "")
            entrada = bloco.get("input") or {}
            if nome in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                alvo = str(entrada.get("file_path") or entrada.get("notebook_path") or "")
                if not DOC_DE_ENTREVISTA.search(alvo.replace("\\", "/")):
                    return False
                escreveu = True
            elif nome == "Bash" and re.search(
                    r"\bgit\s+(commit|merge|push)\b",
                    str(entrada.get("command", ""))):
                return False
    return escreveu


def ultimo_relatorio(rows) -> str:
    """O último texto do assistente na conversa principal (nunca sidechain:
    a resposta de um subagente não é o relatório que o usuário lê)."""
    for row in reversed(rows):
        if row.get("type") != "assistant" or row.get("isSidechain"):
            continue
        content = (row.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        textos = [b.get("text", "") for b in content
                  if isinstance(b, dict) and b.get("type") == "text"]
        junto = "\n".join(t for t in textos if t.strip())
        if junto.strip():
            return junto
    return ""


# ── medição ─────────────────────────────────────────────────────────────────
def conta_palavras(texto: str) -> int:
    return len(re.findall(r"\S+", texto))


def frases(texto: str) -> list:
    """Divisão pobre de propósito: só precisa distinguir 3 de 8. Abreviações
    e números com ponto contam a mais, então o limite é generoso."""
    partes = re.split(r"(?<=[.!?…])\s+", texto.strip())
    return [p for p in partes if p.strip()]


def primeiro_paragrafo(texto: str) -> str:
    """A abertura: tudo até a primeira linha em branco, cabeçalho ou lista."""
    linhas = []
    for linha in texto.strip().splitlines():
        if not linha.strip():
            break
        if re.match(r"^\s{0,3}(#{1,6}\s|[-*+]\s|\d+\.\s|\||>)", linha):
            break
        linhas.append(linha)
    return " ".join(linhas).strip()


def itens_da_lista(cauda: str) -> list:
    """Os itens da seção final, um por número. Linhas de continuação (indentadas
    ou soltas) pertencem ao item aberto — a recomendação quase sempre está na
    segunda linha."""
    itens, atual, cercado = [], None, False
    for linha in cauda.splitlines():
        if atual is not None and linha.strip().startswith("```"):
            cercado = not cercado
        if ITEM_NUMERADO.match(linha) and not cercado:
            if atual is not None:
                itens.append(atual)
            atual = linha
        elif atual is not None:
            if linha.strip():
                atual += " " + linha.strip()
            elif not cercado:
                itens.append(atual)
                atual = None
    if atual is not None:
        itens.append(atual)
    return itens


def medir_itens(cauda: str) -> list:
    """Cada item da lista do fim é uma pergunta fechada com recomendação.

    Motivo (03/08/2026, segunda correção do usuário no mesmo dia): a primeira
    versão da lista nomeava o assunto e devolvia a decisão — *"qual de fato é a
    decisão que tenho que tomar? preciso interpretar o texto, acessar o card,
    entender todo o contexto, para poder elaborar uma próxima instrução"*. Ele
    quer responder "1 sim, 2 não, 3 vamos falar".
    """
    if "nada pendente" in cauda.lower():
        return []
    if not ITEM_DE_LISTA.search(cauda):
        return []          # a falta de itens já virou desvio em quem chamou

    desvios = []
    itens = itens_da_lista(cauda)
    if not itens:
        return [("passos-nao-numerados",
                 "a lista do fim não é numerada — numere para o usuário poder "
                 "responder \"1 sim, 2 não\" sem citar o texto de volta")]

    sem_pergunta = [i for i in itens if "?" not in i]
    if sem_pergunta:
        desvios.append(("item-sem-pergunta",
                        f"{len(sem_pergunta)} de {len(itens)} itens não fazem uma "
                        f"pergunta fechada (ex.: {sem_pergunta[0][:70].strip()}…) — "
                        f"o usuário precisa poder responder sim ou não sem "
                        f"interpretar o assunto"))

    sem_reco = [i for i in itens if not RECOMENDACAO.search(i)]
    if sem_reco:
        desvios.append(("item-sem-recomendacao",
                        f"{len(sem_reco)} de {len(itens)} itens não trazem "
                        f"\"Recomendo sim/não\" — decisão crua sem recomendação "
                        f"devolve o trabalho para o usuário"))

    tarefas = [i for i in itens if ITEM_VOCE.match(i)]
    sem_comando = [i for i in tarefas if "`" not in i and not CAMINHO.search(
        re.sub(r"^\s*\d+[.)]\s+", "", i))]
    sem_pronto = [i for i in tarefas if not PRONTO_QUANDO.search(i)]
    if sem_comando or sem_pronto:
        ruins = [i for i in tarefas if i in sem_comando or i in sem_pronto]
        falta = []
        if sem_comando:
            falta.append("comando ou arquivo")
        if sem_pronto:
            falta.append("a linha 'Pronto quando:'")
        desvios.append(("tarefa-sem-passo",
                        f"{len(ruins)} de {len(tarefas)} itens de tarefa sua "
                        f"(\"Você ...\") não trazem o passo a passo — falta "
                        f"{' e '.join(falta)} (ex.: {ruins[0][:70].strip()}…); "
                        f"sem isso o item diz a categoria, não o passo"))
    return desvios


def texto_do_pra_voce(relatorio: str) -> str:
    """Do marcador `Pra você:` até o fim do parágrafo."""
    m = MARCADOR_PRA_VOCE.search(relatorio)
    if not m:
        return ""
    resto = relatorio[m.end():]
    return re.split(r"\n\s*\n", resto, maxsplit=1)[0].strip()


def pra_voce_anuncia(texto: str) -> bool:
    """O `Pra você:` diz que algo espera pelo usuário?"""
    limpo = re.sub(r"^[\W_]+", "", texto)
    if not limpo:
        return False
    return not limpo.lower().startswith("nada")


def desvio_pos_wrap_up(relatorio: str):
    """A sessão já foi encerrada: o relatório abre frente nova?

    Devolve (categoria, mensagem) ou None. Frente nova = item numerado com `?`
    na lista do fim, ou `Pra você:` que anuncia algo."""
    mp = MARCADOR_PASSOS.search(relatorio)
    cortes = [x.start() for x in (MARCADOR_TECNICO.search(relatorio), mp) if x]
    cabeca = relatorio[:min(cortes)] if cortes else relatorio
    pergunta = bool(mp) and any(
        "?" in i for i in itens_da_lista(relatorio[mp.end():]))
    if not (pergunta or pra_voce_anuncia(texto_do_pra_voce(cabeca))):
        return None
    return ("pergunta-pos-wrap-up",
            "a sessão já foi encerrada pelo wrap-up (\"Safe to exit\"): o "
            "relatório não abre frente nova: nenhuma pergunta fechada na "
            "lista do fim, e `Pra você:` diz \"nada\"; o que sobrou você "
            "registra (seção no BACKLOG.md, item de fila ou `cepa-feedback "
            "add`) e a lista diz \"Nada pendente. Próxima sessão começa por "
            "<o Próximo do handoff>.\"")


def medir(relatorio: str, jargao: list, abstracoes: list = (),
          higiene: list = (), encerrada: bool = False) -> list:
    """Devolve os desvios como (categoria, mensagem). Categoria é rótulo
    estável para a telemetria; mensagem é o que o modelo lê. Lista vazia =
    relatório dentro do formato."""
    desvios = []

    # O topo vai até o primeiro dos dois cabeçalhos — sem o detalhe técnico, a
    # lista do fim não pode cair dentro do teto de 200 palavras.
    cortes = [x.start() for x in (MARCADOR_TECNICO.search(relatorio),
                                  MARCADOR_PASSOS.search(relatorio)) if x]
    cabeca = relatorio[:min(cortes)] if cortes else relatorio

    abertura = primeiro_paragrafo(relatorio)
    if not abertura:
        desvios.append(("sem-abertura",
                        "não abre com um parágrafo de resultado — a primeira "
                        "coisa é cabeçalho, lista ou tabela"))
    else:
        n = len(frases(abertura))
        if n > MAX_FRASES_ABERTURA:
            desvios.append(("abertura-longa",
                            f"abertura com {n} frases (máximo {MAX_FRASES_ABERTURA})"))
        achados = sorted({t for t in jargao if t in abertura.lower()})
        if achados:
            desvios.append(("jargao",
                            "jargão na abertura: " + ", ".join(achados) +
                            " — traduza ou mova para o detalhe técnico"))

    if not MARCADOR_PRA_VOCE.search(cabeca):
        desvios.append(("sem-pra-voce",
                        "falta a linha `**Pra você:**` — mesmo que seja "
                        "\"nada pra decidir\""))

    # A lista do fim: existe, é a última seção, e traz itens de verdade.
    mp = MARCADOR_PASSOS.search(relatorio)
    if not mp:
        desvios.append(("sem-proximos-passos",
                        "falta a seção final `### Decisões e próximos passos` — "
                        "uma linha por ação (Decidir / Você faz / Eu faço), ou "
                        "\"Nada pendente.\" quando não há nenhuma"))
    else:
        cauda = relatorio[mp.end():]
        if CABECALHO.search(cauda):
            desvios.append(("passos-nao-sao-o-fim",
                            "`### Decisões e próximos passos` não é a última seção — "
                            "nada vem depois dela"))
        if not ITEM_DE_LISTA.search(cauda) and "nada pendente" not in cauda.lower():
            desvios.append(("passos-em-prosa",
                            "a seção final não tem itens de lista — cada ação em "
                            "uma linha começando por verbo, não em prosa"))
        desvios += medir_itens(cauda)
        topo = texto_do_pra_voce(cabeca)
        if (pra_voce_anuncia(topo) and not ITEM_NUMERADO.search(cauda)
                and not encerrada):
            desvios.append(("pra-voce-sem-lista",
                            f"`Pra você:` diz que algo espera pelo usuário "
                            f"({topo[:60].strip()}), e a lista do fim não tem "
                            f"item numerado nenhum — cada tarefa dele é um item "
                            f"numerado com Onde, Comando (ou arquivo) e Pronto "
                            f"quando; só quando o Pra você diz \"nada\" a lista "
                            f"pode dizer \"Nada pendente.\""))

    if encerrada:
        d = desvio_pos_wrap_up(relatorio)
        if d:
            desvios.append(d)

    palavras = conta_palavras(cabeca)
    if palavras > MAX_PALAVRAS_ANTES_DO_TECNICO:
        desvios.append(("acima-do-teto",
                        f"{palavras} palavras antes do detalhe técnico "
                        f"(teto {MAX_PALAVRAS_ANTES_DO_TECNICO}) — o resto desce "
                        f"para `### Detalhe técnico`"))

    # Higiene: só no topo (abertura + `Pra você:`). No detalhe técnico "commit
    # 8827471" é informação barata e útil; aqui em cima ela empurra para fora a
    # frase que diz o que mudou para o leitor.
    limpas = sorted({h for h in higiene if h in cabeca.lower()})
    if limpas:
        mostra = ", ".join(f"\"{v}\"" for v in limpas[:3])
        desvios.append(("higiene",
                        f"higiene relatada como resultado: {mostra} — só interessa "
                        f"quando falha ou quando exige algo do usuário; no topo, "
                        f"escreva no lugar o que mudou para ele"))

    # Estas duas valem no texto INTEIRO. O bloco técnico tem liberdade de
    # tamanho, não de clareza — foi lá dentro que o usuário achou as três
    # frases obscuras que motivaram esta versão.
    baixo = relatorio.lower()
    vagas = sorted({a for a in abstracoes if a in baixo})
    if vagas:
        mostra = ", ".join(f"\"{v}\"" for v in vagas[:4])
        resto = f" (+{len(vagas) - 4})" if len(vagas) > 4 else ""
        desvios.append(("abstracao",
                        f"abstração no lugar do fato: {mostra}{resto} — nomeie a "
                        f"coisa, não a categoria da coisa (ver a seção "
                        f"\"Abstrações a evitar\" do glossário)"))

    passivas = PASSIVA.findall(relatorio)
    if len(passivas) > MAX_PASSIVAS:
        exemplos = ", ".join(f"\"{a} {b}\"" for a, b in passivas[:3])
        desvios.append(("passiva",
                        f"{len(passivas)} construções passivas ({exemplos}...) — "
                        f"escondem quem faz o quê; diga quem age"))

    return desvios


# ── pendência entre turnos ──────────────────────────────────────────────────
def pendencia_path(session_id: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "sem-sessao")
    return STATE_DIR / f"{slug}.json"


def on_stop(payload):
    """Devolve o motivo do bloqueio, ou None para deixar a parada seguir."""
    rows = read_rows(payload.get("transcript_path", ""))
    if not rows:
        return None
    alterou = turno_alterou_algo(rows)
    encerrada = sessao_encerrada(rows)
    # Escopo: relatório de trabalho feito. Exceção estreita: sessão encerrada
    # pelo wrap-up, onde mesmo o turno que só lê (metrics) é medido, mas só
    # pela categoria `pergunta-pos-wrap-up`.
    if not alterou and not encerrada:
        return None

    relatorio = ultimo_relatorio(rows)
    if conta_palavras(relatorio) < MIN_PALAVRAS_PARA_MEDIR:
        return None
    if turno_de_entrevista(rows, relatorio):
        return None

    if alterou:
        desvios = medir(relatorio, load_jargao(), load_abstracoes(),
                        load_higiene(), encerrada=encerrada)
    else:
        d = desvio_pos_wrap_up(relatorio)
        desvios = [d] if d else []
    cwd = payload.get("cwd") or os.getcwd()

    # Trava anti-loop: esta parada já é consequência de um bloqueio deste hook.
    # Bloquear de novo prenderia a sessão num par reescreve-bloqueia sem fim.
    reincidente = bool(payload.get("stop_hook_active"))
    vai_bloquear = bool(desvios) and not reincidente

    _t_emit("report_style", cwd=cwd,
            palavras=conta_palavras(relatorio),
            desvios=len(desvios),
            tipos=[cat for cat, _ in desvios],
            bloqueou=vai_bloquear,
            reincidente=reincidente,
            pos_wrap_up=encerrada)

    p = pendencia_path(payload.get("session_id", ""))
    if not desvios:
        p.unlink(missing_ok=True)
        return None

    if vai_bloquear:
        # O relatório é reescrito AGORA, no mesmo turno: nada de pendência para
        # o turno seguinte, senão o usuário leva o aviso de um texto já corrigido.
        p.unlink(missing_ok=True)
        return motivo_bloqueio([m for _, m in desvios], encerrada)

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"desvios": [m for _, m in desvios],
                                "encerrada": encerrada},
                               ensure_ascii=False),
                     encoding="utf-8")
    except Exception:
        pass
    return None


FORMATO_ENCERRADA = (
    "abertura de até 3 frases sem jargão → **Pra você:** nada → "
    "### Detalhe técnico → ### Decisões e próximos passos contendo só "
    "\"Nada pendente. Próxima sessão começa por <o Próximo do handoff>.\", "
    "sem item numerado e sem pergunta. O que sobrou vai para registro "
    "(BACKLOG.md, item de fila ou `cepa-feedback add`) e o relatório diz onde.")


def motivo_bloqueio(desvios, encerrada: bool = False) -> str:
    if encerrada:
        fim = ("Reescreva o relatório inteiro nesta ordem, antes de encerrar o "
               "turno: " + FORMATO_ENCERRADA + " ")
    else:
        fim = ("Reescreva o relatório inteiro nesta ordem, antes de encerrar o "
               "turno: abertura de até 3 frases sem jargão → **Pra você:** → "
               "### Detalhe técnico → ### Decisões e próximos passos (lista "
               "numerada, uma pergunta fechada por item, cada uma com "
               "\"Recomendo sim/não\" e o porquê em uma linha; tarefa sua com "
               "Onde, Comando (ou arquivo) e Pronto quando; \"Nada pendente.\" "
               "só se o Pra você disser nada). ")
    return ("Seu relatório final saiu do formato `plain-report`:\n" +
            "".join(f"  - {d}\n" for d in desvios) + fim +
            "Não peça desculpa e não explique a reescrita \u2014 entregue o "
            "relatório corrigido e nada mais.")


def on_prompt(payload) -> None:
    p = pendencia_path(payload.get("session_id", ""))
    if not p.is_file():
        return
    try:
        dado = json.loads(p.read_text(encoding="utf-8"))
        desvios = dado.get("desvios") or []
        encerrada = bool(dado.get("encerrada"))
    except Exception:
        desvios, encerrada = [], False
    p.unlink(missing_ok=True)
    if not desvios:
        return
    print("[cepa report-style] Seu relatório anterior saiu do formato "
          "`plain-report`:\n" +
          "".join(f"  - {d}\n" for d in desvios) +
          "  Formato: " + (FORMATO_ENCERRADA + " " if encerrada else
          "abertura de até 3 frases sem jargão → **Pra você:** → "
          "### Detalhe técnico → ### Decisões e próximos passos (numerada, uma "
          "pergunta fechada por item, cada uma com \"Recomendo sim/não\"; tarefa "
          "sua com Onde, Comando e Pronto quando). ") +
          "Este é o caminho de aviso — o relatório anterior já tinha sido "
          "bloqueado uma vez e a reescrita ainda desviou. Aplique no próximo "
          "relatório em vez de reescrever o anterior.")


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    evento = payload.get("hook_event_name") or ""
    try:
        if evento == "Stop":
            motivo = on_stop(payload)
            if motivo:
                print(json.dumps({"decision": "block", "reason": motivo},
                                 ensure_ascii=False))
        elif evento == "UserPromptSubmit":
            on_prompt(payload)
    except Exception:
        pass  # o medidor nunca derruba o turno por erro próprio
    sys.exit(0)


if __name__ == "__main__":
    main()
