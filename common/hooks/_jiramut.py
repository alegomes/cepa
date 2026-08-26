#!/usr/bin/env python3
"""_jiramut — reconhece mutação de Jira (e de Bitbucket) por EFEITO, não por nome de ferramenta.

## Por que existe

Quatro gates do `common` decidem se uma mudança no Jira pode passar:
`acceptance-gate` (critério de aceite cumprido), `merge-truth-gate` (o código
está mesmo na branch de integração), `summary-nulls-gate` (sumário sem buraco) e
`bounce-reason-gate` (motivo de devolução preenchido).

Os quatro casavam pelo **nome da ferramenta MCP** e liberavam quando o nome não
batia:

    if "transitionJiraIssue" not in tool_name and "jira_transition_issue" not in tool_name:
        sys.exit(0)          # <- exit 0 é LIBERAR

Isso funcionava enquanto o único caminho até o Jira era MCP. Deixou de funcionar
quando a Atlassian lançou a CLI `twg` (2026-08): a chamada chega como
`tool_name == "Bash"`, não casa com nenhum dos dois nomes, e os quatro gates
liberam **em silêncio**. Não é enforcement enfraquecido, é enforcement
desligado — e o `twg` já está instalado e autenticado nesta máquina, com skills
`twg-*` visíveis a qualquer sessão, então a exposição não depende de ninguém
migrar nada.

Este módulo é a resposta: dado o payload do hook, ele diz se a chamada **muta o
Jira**, por qual mecanismo, e devolve os campos já normalizados para os nomes que
os gates sempre usaram — de forma que cada gate continue com sua lógica de
negócio intacta.

## A regra que não pode ser afrouxada

Diante de uma chamada que toca o Jira e que ele **não consegue classificar**,
este módulo devolve `opaque=True` e o gate deve **barrar**. O caso concreto é
`twg api`, a escapatória REST/GraphQL da CLI:

    twg api jira:/rest/api/3/issue -X POST --input payload.json

Isso cria card sem conter `create` na linha de comando, e com `--input` o corpo
sequer aparece na string inspecionada. Qualquer desenho por lista negra de
verbos é furado por essa única linha. Por isso o reconhecimento de leitura aqui
é **lista branca**: o que não está declarado como leitura conhecida é tratado
como mutação, e o que é mutação e não dá para inspecionar é barrado.

Uso, seguindo o padrão dos outros helpers privados desta pasta:

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _jiramut as J

    m = J.classify(payload)
    if m is None:
        sys.exit(0)                      # não é mutação de Jira
    if m["opaque"]:
        J.block(m, "nome-do-gate")       # barra com exit 2 e explicação
    tool_input = m["tool_input"]         # normalizado; use como antes
"""

import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _shellscan as S  # noqa: E402

_split_segments = S._split_segments

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")

# Nomes MCP que os gates sempre conheceram. Mantidos porque o caminho MCP
# continua vivo (rotina cloud `/schedule` não tem shell).
_MCP_TRANSITION = ("transitionJiraIssue", "jira_transition_issue")
_MCP_COMMENT = ("addCommentToJiraIssue", "jira_add_comment")

# Caminhos `twg jira ...` que são comprovadamente leitura. LISTA BRANCA: o que
# não estiver aqui e cair sob `twg jira` é tratado como mutação. Verificado no
# `--help` da CLI 1.2.5.
_TWG_JIRA_READ = frozenset({
    ("workitem", "get"), ("workitem", "bulk-get"), ("workitem", "query"),
    ("workitem", "search"), ("workitem", "similar"), ("workitem", "statuses"),
    ("workitem", "transitions"), ("workitem", "types"), ("workitem", "priorities"),
    ("workitem", "changelog"), ("workitem", "link-types"),
    ("workitem", "project-link-candidates"),
    ("space", "get"), ("space", "query"), ("space", "list"),
    ("space", "issue-types"), ("space", "status"),
    ("board", "get"), ("board", "query"), ("board", "list"),
    ("sprint", "get"), ("sprint", "query"), ("sprint", "list"),
    ("filter", "get"), ("filter", "query"), ("filter", "list"),
    ("field", "get"), ("field", "query"), ("field", "list"),
    ("dashboard", "get"), ("dashboard", "query"), ("dashboard", "list"),
})

# Subcomandos de `comment` que gravam texto no card.
_TWG_COMMENT_WRITE = frozenset({"create", "update"})

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# `twg bitbucket pull-requests ...` que sao comprovadamente leitura. LISTA BRANCA,
# pelo mesmo motivo do Jira. Verificado no --help da CLI 1.2.5.
_TWG_BB_PR_READ = frozenset({
    "get", "query", "list", "activity", "commits", "diff", "diffstat", "patch",
    "for-commit", "merge-status", "effective-default-reviewer",
})

# Verbos de PR que decidem o destino do codigo. Aprovar e mergear o proprio PR e
# exatamente o que o review-gate existe para impedir.
_TWG_BB_PR_DECIDE = frozenset({
    "approve", "merge", "decline", "request-changes", "remove-request-changes",
})


def classify_bitbucket(command: str):
    """Mutacao de Bitbucket via `twg`. None quando nao ha nenhuma.

    Devolve {"verb", "decides", "reason"} — `decides` marca os verbos que
    determinam se o codigo entra (approve/merge/decline/request-changes), que sao
    os que so o agente do review-gate pode executar.
    """
    if not command or "twg" not in command:
        return None
    for seg in _split_segments(command):
        seg = seg.strip()
        if not seg:
            continue
        try:
            argv = shlex.split(seg)
        except ValueError:
            if re.search(r"(^|/)twg\b", seg) and "bitbucket" in seg:
                return {"verb": "<ilegivel>", "decides": True,
                        "reason": "linha com aspas nao fechadas, impossivel de ler"}
            continue
        while argv and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
            argv.pop(0)
        if not argv or os.path.basename(argv[0]) != "twg":
            continue
        rest = [a for a in argv[1:] if a]
        if not rest or rest[0] not in ("bitbucket", "bb"):
            continue
        words = [a for a in rest[1:] if not a.startswith("-")]
        if len(words) < 2:
            continue
        resource, verb = words[0], words[1]
        if resource in ("pull-requests", "pr"):
            if verb in _TWG_BB_PR_READ:
                return None
            return {"verb": f"{resource} {verb}",
                    "decides": verb in _TWG_BB_PR_DECIDE,
                    "reason": f"`twg bitbucket {resource} {verb}` escreve no pull request"}
        # repo/branch/deployment/pipeline: leitura conhecida passa, resto e escrita
        if verb in ("get", "query", "list", "url", "file", "contributors", "search"):
            return None
        return {"verb": f"{resource} {verb}", "decides": False,
                "reason": f"`twg bitbucket {resource} {verb}` nao esta na lista de leituras conhecidas"}
    return None


def _flag(argv, *names):
    """Valor de `--flag valor` ou `--flag=valor`, o primeiro que aparecer."""
    for i, tok in enumerate(argv):
        for n in names:
            if tok == n and i + 1 < len(argv):
                return argv[i + 1]
            if tok.startswith(n + "="):
                return tok.split("=", 1)[1]
    return None


def _first_key(argv):
    """Primeira chave de card entre os argumentos posicionais (ex.: WEGO-123)."""
    for tok in argv:
        if KEY_RE.match(tok.strip()):
            return tok.strip()
    return None


def _classify_twg(argv):
    """argv já tokenizado, argv[0] é o `twg`. Devolve dict ou None."""
    rest = [a for a in argv[1:] if a]
    if not rest:
        return None

    head = rest[0]

    # ---- escapatória REST/GraphQL: o furo que derruba qualquer lista negra ----
    if head == "api":
        method = (_flag(rest, "-X", "--method") or "GET").upper()
        target = rest[1] if len(rest) > 1 else ""
        touches_jira = "jira" in target.lower() or "graphql" in target.lower()
        if method in _WRITE_METHODS and touches_jira:
            return {
                "kind": "mutation",
                "mechanism": "twg",
                "tool_input": {},
                "opaque": True,
                "reason": (
                    f"`twg api` com -X {method} em {target or '<endpoint>'} muta o Jira por "
                    "REST cru. O gate não consegue ler qual card nem qual conteúdo — "
                    "ainda mais com --input, onde o corpo está num arquivo e não na linha."
                ),
                "target_status": None,
            }
        return None  # GET, ou endpoint que não é Jira

    if head != "jira":
        return None  # bitbucket, confluence, goals... não são deste gate

    path = tuple(a for a in rest[1:3] if not a.startswith("-"))
    if len(path) < 2:
        return None
    if path in _TWG_JIRA_READ:
        return None

    resource, verb = path

    # ---- transição ----
    if (resource, verb) == ("workitem", "transition"):
        tid = _flag(rest, "--transition-id", "--transitionId")
        if tid is None:
            # Sem --transition-id o comando é descoberta read-only: lista as
            # transições disponíveis. Verificado no `--help` e em execução real.
            return None
        key = _flag(rest, "--id", "--issue-id", "--key") or _first_key(rest)
        ti = {}
        if key:
            ti["issueIdOrKey"] = key
        target_status = None
        if tid.isdigit():
            ti["transition_id"] = tid
        else:
            # A CLI aceita o NOME do status no lugar do id. Nesse caso não há o
            # que procurar no transition_ids do board-flow.yaml — o alvo já veio.
            target_status = tid.strip().lower()
        comment = _flag(rest, "--transition-comment")
        if comment:
            ti["commentBody"] = comment
        return {
            "kind": "transition",
            "mechanism": "twg",
            "tool_input": ti,
            "opaque": not key,
            "reason": "não foi possível achar a chave do card na linha de comando",
            "target_status": target_status,
        }

    # ---- comentário ----
    if resource == "comment" or (resource == "workitem" and verb == "comment"):
        sub = None
        for tok in rest[2:]:
            if not tok.startswith("-"):
                if tok == "comment":
                    continue
                sub = tok
                break
        if sub is not None and sub not in _TWG_COMMENT_WRITE:
            return None  # query/delete: delete não carrega corpo para auditar
        key = _flag(rest, "--issue-id", "--id", "--key") or _first_key(rest)
        body = _flag(rest, "--body")
        ti = {}
        if key:
            ti["issueIdOrKey"] = key
        if body is not None:
            ti["commentBody"] = body
        opaque = body is None
        return {
            "kind": "comment",
            "mechanism": "twg",
            "tool_input": ti,
            "opaque": opaque,
            "reason": (
                "o corpo do comentário não está na linha de comando (provavelmente "
                "veio de arquivo ou stdin), então o gate não tem o que auditar"
            ),
            "target_status": None,
        }

    # ---- qualquer outra coisa sob `twg jira` ----
    # Lista branca: create, update, delete, archive, clone, bulk-transition,
    # create-bulk, link, worklog, watcher... e o que a CLI ganhar amanhã.
    return {
        "kind": "mutation",
        "mechanism": "twg",
        "tool_input": {},
        "opaque": True,
        "reason": (
            f"`twg jira {resource} {verb}` não está na lista de leituras conhecidas, "
            "então é tratado como escrita que o gate não sabe auditar"
        ),
        "target_status": None,
    }


def _scan_bash(command: str):
    """Varre a linha de comando inteira. Devolve a primeira mutação achada."""
    if not command or "twg" not in command:
        return None
    for seg in _split_segments(command):
        seg = seg.strip()
        if not seg:
            continue
        try:
            argv = shlex.split(seg)
        except ValueError:
            # Aspas não fechadas. Se o segmento menciona twg, não dá para ler —
            # e não ler é justamente quando se barra.
            if re.search(r"(^|/)twg\b", seg):
                return {
                    "kind": "mutation", "mechanism": "twg", "tool_input": {},
                    "opaque": True,
                    "reason": "linha de comando com aspas não fechadas, impossível de ler",
                    "target_status": None,
                }
            continue
        if not argv:
            continue
        # pula env vars à frente do comando: FOO=1 twg ...
        while argv and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
            argv.pop(0)
        if not argv:
            continue
        if os.path.basename(argv[0]) != "twg":
            continue
        hit = _classify_twg(argv)
        if hit:
            return hit
    return None


def classify(payload: dict):
    """None quando a chamada não muta o Jira; senão o dict descrito no topo."""
    tool_name = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input") or {}

    if any(n in tool_name for n in _MCP_TRANSITION):
        return {"kind": "transition", "mechanism": "mcp", "tool_input": tool_input,
                "opaque": False, "reason": "", "target_status": None}
    if any(n in tool_name for n in _MCP_COMMENT):
        return {"kind": "comment", "mechanism": "mcp", "tool_input": tool_input,
                "opaque": False, "reason": "", "target_status": None}

    if tool_name == "Bash":
        return _scan_bash(tool_input.get("command", "") or "")

    return None


def block(m: dict, gate: str):
    """Barra uma mutação que o gate não consegue auditar. Não retorna."""
    print(
        f"[{gate}] BLOCKED: mutação de Jira que este gate não consegue auditar.\n"
        f"  Motivo: {m['reason']}\n"
        f"  Este gate existe para conferir uma condição ANTES de o card mudar de estado.\n"
        f"  Uma chamada que ele não consegue ler não é uma chamada segura — é uma\n"
        f"  chamada invisível, e liberar por não enxergar é como o enforcement morre\n"
        f"  calado. Faça a mudança por um caminho auditável:\n"
        f"    - `twg jira workitem transition --id <KEY> --transition-id <ID>`\n"
        f"    - `twg jira workitem comment create --issue-id <KEY> --body '<texto>'`\n"
        f"    - ou a ferramenta MCP equivalente.\n"
        f"  Se o caminho opaco for mesmo necessário, quem libera é uma pessoa, não o agente.",
        file=sys.stderr,
    )
    sys.exit(2)
