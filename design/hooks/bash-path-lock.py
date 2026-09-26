#!/usr/bin/env python3
"""PreToolUse hook for the design topology — the BASH half of the path-lock.

WHY THIS EXISTS
---------------
`path-lock.py` gates Edit / Write / MultiEdit / NotebookEdit. It does NOT see
Bash. An agent whose Write is blocked can reach for the shell — `sed -i`,
`cat > file`, `tee`, a heredoc — and land the exact write the path-lock was
meant to stop. That is not a hypothetical: a lead once edited source via Bash
because Write was locked and Bash wasn't. The artifact happened to be correct,
so nothing in the pipeline flagged it. A control enforced on one tool but not
its equivalent is not a control.

This hook is the SECOND lock. It reuses path-lock.py's per-agent allowlist
(single source of truth — never re-declare globs here) and applies it to
shell-level writes.

QUATRO BALDES — deny-by-default (Camada 1, desde 2026-09-25)
-------------------------------------------------------------
Até aqui o hook perguntava "este comando parece uma escrita conhecida?" e
liberava o resto. O resto incluía `python3 -c "open('src/main/...','w')"`: foi
exatamente o que um qa-engineer usou no WEGO-1936 depois de ter o `cp` barrado.
Agora a pergunta é "este comando é comprovadamente inofensivo?". Todo segmento
de comando de um agente trancado cai em exatamente um balde:

1. ESCRITOR ANALISÁVEL — o alvo está na linha (redirect, tee, cp, mv, sed -i,
   mkdir, rm, ln, sort -o, git mv/checkout --/restore...). Alvo dentro da raiz e
   fora dos globs do agente → NEGA.
2. VERBO INOCENTE — lista auditada (_SIMPLE, _HANDLERS), cada verbo com as
   flags que o tornam escritor/executor negadas (sed -i/w/e, find -exec/-delete,
   git reset --hard/stash/apply, npm exec, npx -c, mvn exec:...).
3. FORA DA JURISDIÇÃO — o segmento roda num diretório fora da raiz (o worktree
   descartável de perturbação: `cd "$D/red" && ...`, `git -C /tmp/x ...`) e nada
   na linha cita a raiz → tudo permitido. É o mesmo carve-out out-of-root do
   path-lock.py, que a perturbação do proof-reviewer precisa.
4. TODO O RESTO → NEGA. Interpretador inline, shell aninhado, heredoc/pipe para
   interpretador, script fora do projeto ou dentro da própria pista, xargs com
   escritor, verbo que ninguém listou. Um vetor novo cai aqui por construção.

Substituição de comando (`$(...)`, crase, `<(...)`) é outro comando e é
classificada com as mesmas regras antes do segmento que a contém. Um `cd` só
tira da raiz os segmentos ligados por `&&` a ele (com `;` ou `||` o cd pode ter
falhado; em `|` e subshell ele não vale fora).

Main session / built-in agents (no plugin-prefixed agent_type) are NOT gated —
same fail-open contract as path-lock.py.

Modo sombra: CEPA_BASHLOCK_ENFORCE=0 libera o balde 4 e grava
`bash_pathlock_would_deny` no ledger de telemetria (o balde 1 nunca afrouxa).
Toda negação grava `bash_pathlock_deny`; `git worktree add` fora da raiz grava
`perturb_worktree_created`. O log órfão em /tmp que ninguém lia morreu.

LIMITES HONESTOS (guardrail, não sandbox)
-----------------------------------------
- PREVINE: escrita shell com alvo visível fora da pista, e execução de código
  não sancionado no momento do Bash (o vetor nem roda).
- NÃO VÊ: o que um verbo inocente escreve por SUBPROCESSO (`./mvnw test` rodando
  um teste que grava em src/main; `npm test` rodando script do package.json;
  `git merge` do lead). Isso é trabalho da Camada 2 (write-fence por diff), ainda
  não construída.
- NÃO VÊ: caminho da raiz montado em tempo de execução a partir de um diretório
  fora dela (balde 3 é checagem de string). Ofuscar depois de um deny é dolo.
- Script do projeto que o agente NÃO pode escrever (fora da pista dele) é
  tratado como `npm test`: inocente. Script em /tmp ou na própria pista, não.

Exit codes:
  0 — permitido (ou fora de escopo)
  2 — negado: balde 1 (escrita fora da pista) ou balde 4 (fora da lista)
"""

import importlib.util
import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

PLUGIN_NAME = "design"

# ─── reuse path-lock.py as the single source of truth for allowlists ──────────

def _load_pathlock_module():
    """Import the sibling path-lock.py (hyphen in the filename → importlib)."""
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "design_path_lock", str(here / "path-lock.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Redirection: `>` or `>>`, NOT preceded by a digit or `&` (excludes `2>`,
# `&>`, `1>&2`), and the target must not start with `&` (excludes `>&1`) or `=`
# (excludes the `>=` comparison operator — `>` immediately followed by `=` is
# never a redirect; without this, `sed -i 's/>=/>/'`, `grep '>='`, and
# `[[ $a >= $b ]]` capture junk targets and get falsely blocked).
_REDIR_RE = re.compile(r"""(?<![0-9&])>>?\s*(?![&=])("[^"]+"|'[^']+'|[^\s;&|<>()]+)""")

# Constructs we cannot statically analyze — fail open but log.
_UNCOVERED_RE = re.compile(
    r"""(?:
        \bpython3?\s+-c\b | \bperl\s+-[eE]\b | \bruby\s+-e\b | \bnode\s+-e\b |
        \bawk\b[^|;&]*\b-i\b | \b-i\s+inplace\b | \bgawk\b[^|;&]*\binplace\b |
        \bed\b | \bpatch\b | <<-?\s*['"]?\w+   # heredoc
    )""",
    re.VERBOSE,
)

# Targets that are never real files.
_PSEUDO = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty")

# Separadores de comando, aplicados só FORA de aspas (ver _quoted_mask).
_SEP_PAIRS = ("||", "&&")
_SEP_CHARS = ";|&\n"


def _quoted_mask(s: str) -> list:
    """Um booleano por caractere: True onde ele está entre aspas ou escapado.

    Existe porque o hook lia texto citado como se fosse shell. O caso real
    (22/08/2026, WEGO-2087): `git commit -m "titulo\n\ncorpo com A -> B"`. O
    `\n` do corpo era tratado como separador de comando, cada linha da mensagem
    virava um "segmento", e o `->` de uma frase casava com _REDIR_RE — o hook
    acusava escrita fantasma em `B` e barrava o commit. O dev só conseguiu
    commitar depois de encurtar a mensagem para uma linha.

    Aspas não fechadas mascaram o resto da string: é fail-open, coerente com o
    contrato do hook, e um comando com aspas não fechadas não roda no shell.

    O corpo de um heredoc (`<<EOF`, `<<-EOF`, `<<'EOF'`) também é dado, não
    shell, e também é mascarado. Mesmo defeito das aspas, um degrau adiante e
    medido em 04/09/2026: uma mensagem de commit passada por
    `git commit -F - <<'MSG'` que CITAVA `while true` fez o `no-busy-wait`
    barrar o commit como se fosse espera ativa. A citação estava dentro do
    corpo, não numa linha de comando. Um here-string (`<<<`) não abre corpo e
    fica de fora.
    """
    mask = [False] * len(s)
    quote = None
    pendentes = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if quote is None:
            # O corpo de um heredoc anunciado nesta linha começa depois da
            # quebra de linha e vai até a linha do delimitador. Nada dele é
            # shell — é dado.
            if c == "\n" and pendentes:
                j = i + 1
                for delim, apara in pendentes:
                    while j < n:
                        fim_linha = s.find("\n", j)
                        if fim_linha == -1:
                            fim_linha = n
                        linha = s[j:fim_linha]
                        j = fim_linha + 1 if fim_linha < n else n
                        if (linha.lstrip("\t") if apara else linha).strip() == delim:
                            break
                # A quebra de linha que ABRE o corpo entra na máscara junto:
                # ela ainda é separador de comando para `_split_segments`, e sem
                # ela o corpo inteiro virava um "segundo comando" — que foi
                # exatamente como a prosa do corpo voltou a ser lida como shell.
                for p in range(i, min(j, n)):
                    mask[p] = True
                pendentes = []
                i = min(j, n)
                continue
            if s[i:i + 2] == "<<" and s[i:i + 3] != "<<<":
                k = i + 2
                apara = k < n and s[k] == "-"
                if apara:
                    k += 1
                while k < n and s[k] in " \t":
                    k += 1
                citado = s[k] if k < n and s[k] in "\"'" else None
                if citado:
                    k += 1
                inicio = k
                while k < n and (s[k].isalnum() or s[k] in "_-."):
                    k += 1
                delim = s[inicio:k]
                if citado and k < n and s[k] == citado:
                    k += 1
                if delim:
                    # O operador e o delimitador ficam VISÍVEIS de propósito:
                    # `cat <<EOF > out.txt` escreve, e é o `<<` na visão sem
                    # aspas que sustenta o sinal "não sei analisar isto"
                    # (_UNCOVERED_RE). Só o CORPO é dado. Mascarar o operador
                    # junto apagaria o sinal e o heredoc passaria a escrever
                    # calado.
                    pendentes.append((delim, apara))
                    i = k
                    continue
            if c == "\\":
                mask[i] = True
                if i + 1 < n:
                    mask[i + 1] = True
                i += 2
                continue
            if c in "\"'":
                quote = c
                mask[i] = True
            i += 1
            continue
        mask[i] = True
        if quote == '"' and c == "\\":
            if i + 1 < n:
                mask[i + 1] = True
            i += 2
            continue
        if c == quote:
            quote = None
        i += 1
    return mask


def _split_segments(command: str) -> list:
    """Quebra em segmentos de comando ignorando separadores dentro de aspas."""
    mask = _quoted_mask(command)
    segments = []
    start = i = 0
    n = len(command)
    while i < n:
        if mask[i]:
            i += 1
            continue
        if command[i:i + 2] in _SEP_PAIRS:
            segments.append(command[start:i])
            i += 2
            start = i
            continue
        if command[i] in _SEP_CHARS:
            segments.append(command[start:i])
            i += 1
            start = i
            continue
        i += 1
    segments.append(command[start:])
    return segments


# Um redirecionamento inteiro — descritor opcional (`2>`), operador, `&`
# opcional (`>&2`) e o operando. Serve só para APAGAR o redirecionamento antes
# de tokenizar o comando: `tee saida.txt < entrada.txt` tokenizava como
# `["tee", "saida.txt", "<", "entrada.txt"]`, e a regra do `tee` — todo
# argumento que não é flag é escrito — registrava `<` e `entrada.txt` como
# alvos de escrita. `entrada.txt` está sendo LIDO. Mesma família do falso
# positivo do commit multilinha: um pedaço da linha lido como o que não é.
_REDIR_STRIP_RE = re.compile(
    r"""[0-9]?(?:>>?|<<?)&?\s*(?:"[^"]*"|'[^']*'|[^\s;&|<>()]+)?"""
)


def _strip_redirections(segment: str, mask: list) -> str:
    """Remove os redirecionamentos FORA de aspas, preservando o resto intacto."""
    cortes = [
        (m.start(), m.end())
        for m in _REDIR_STRIP_RE.finditer(segment)
        if m.group() and not mask[m.start()]
    ]
    if not cortes:
        return segment
    out, pos = [], 0
    for ini, fim in cortes:
        out.append(segment[pos:ini])
        pos = fim
    out.append(segment[pos:])
    return " ".join(p for p in out if p)


def _unquoted_view(command: str) -> str:
    """A linha de comando com o conteúdo citado trocado por espaço.

    O detector de construção indecidível (_UNCOVERED_RE) varria a linha inteira,
    aspas incluídas: uma mensagem de commit com a palavra `ed`, ou com um `<<`
    no meio da prosa, gerava uma entrada falsa no log de cobertura. O log só
    existe para dizer o que o hook NÃO conseguiu analisar — enchê-lo de prosa
    ensina a ignorá-lo.
    """
    mask = _quoted_mask(command)
    return "".join(" " if m else c for c, m in zip(command, mask))


def _unquote(tok: str) -> str:
    if len(tok) >= 2 and tok[0] in "\"'" and tok[-1] == tok[0]:
        return tok[1:-1]
    return tok


def _is_flag(tok: str) -> bool:
    return tok.startswith("-") and tok != "-"


def _segment_targets(segment: str) -> list:
    """Best-effort extraction of shell-write targets from one command segment."""
    targets = []

    # 1. Redirections (covers `cat > f`, `echo .. >> f`, `cmd > f`, heredoc-to-file).
    #    O `>` precisa estar fora de aspas: um `->` no meio de uma mensagem de
    #    commit é prosa, não redirecionamento.
    redir_mask = _quoted_mask(segment)
    for m in _REDIR_RE.finditer(segment):
        if not redir_mask[m.start()]:
            targets.append(_unquote(m.group(1)))

    # 2. argv-shaped writers — tokenize; fall back silently if shlex chokes.
    #    Sem os redirecionamentos: eles já viraram alvo no passo 1, e deixá-los
    #    aqui faz o `tee` contar o operando de entrada como escrita.
    sem_redir = _strip_redirections(segment, redir_mask)
    try:
        argv = shlex.split(sem_redir, posix=True)
    except ValueError:
        argv = sem_redir.split()
    if not argv:
        return targets

    cmd = os.path.basename(argv[0])
    rest = argv[1:]
    nonflags = [t for t in rest if t and not _is_flag(t)]

    if cmd == "tee":
        # every non-flag arg is written (flags: -a/--append/-i…)
        targets.extend(nonflags)
    elif cmd == "sed":
        if any(t == "-i" or t.startswith("-i") or t == "--in-place"
               or t.startswith("--in-place") for t in rest):
            # in-place edits its file operands — everything after the script.
            # Heuristic: all non-flag args except the first (the sed program).
            if len(nonflags) >= 2:
                targets.extend(nonflags[1:])
            elif nonflags:
                targets.extend(nonflags)  # `sed -i'' file` form with no separate prog
    elif cmd in ("cp", "mv", "install"):
        if len(nonflags) >= 2:
            targets.append(nonflags[-1])  # destination is the last operand
            if cmd == "mv":
                # `mv` DELETES its source(s) — that is a write on the origin
                # path too, not just the destination (P4, CS-5: renaming
                # counts as a write on both paths). `cp`/`install` only READ
                # their source, so they stay destination-only.
                targets.extend(nonflags[:-1])
    elif cmd == "dd":
        for t in rest:
            if t.startswith("of="):
                targets.append(t[3:])
    elif cmd == "git":
        # `git mv <src> <dst>` — move real de arquivo, que o path-lock precisa
        # governar como qualquer outra escrita. Estava só na cópia do docs
        # (structure-surgeon usa git mv para preservar histórico); as outras
        # quatro deixavam passar. Encontrado pelo detector de divergência.
        #
        # Origem E destino contam como escrita (P4, CS-5): `git mv` apaga o
        # caminho de origem tanto quanto cria o de destino — um slice travado
        # para escrever em domain/** que renomeia infrastructure/Foo.java para
        # domain/Foo.java "escreveu" fora da própria pista (removeu um arquivo
        # de infrastructure/), mesmo o destino sendo permitido. Checar só o
        # destino, como antes, deixava esse sentido passar batido.
        if len(nonflags) >= 3 and nonflags[0] == "mv":
            targets.extend(nonflags[1:])
        elif nonflags and nonflags[0] in ("checkout", "restore"):
            # `git checkout <ref> -- arquivo` e `git restore arquivo`
            # SOBRESCREVEM o arquivo no disco com a versão de outro lugar —
            # mesmo efeito do `git mv` acima, na mesma ferramenta já vigiada,
            # e era a forma mais fácil de reverter em silêncio um arquivo fora
            # da pista (achado do proof-reviewer, 26/08/2026).
            #
            # Sem `--`, o `checkout` é troca de branch: escreve muita coisa,
            # mas não é escrita dirigida a um caminho, e tratá-lo como alvo
            # transformaria todo `git checkout main` num bloqueio.
            if "--" in rest:
                targets.extend(t for t in rest[rest.index("--") + 1:]
                               if not _is_flag(t))
            elif nonflags[0] == "restore":
                targets.extend(nonflags[1:])
    elif cmd == "truncate":
        targets.extend(nonflags[1:] if nonflags else [])
    elif cmd in ("curl", "wget"):
        # Baixar para um arquivo é escrever nele. Achado do proof-reviewer em
        # 26/08/2026: `curl -o` e `wget -O` são estaticamente decidíveis — o
        # destino está explícito no argv — e mesmo assim passavam calados, nem
        # bloqueados nem registrados. A forma sem destino explícito (`curl -O`,
        # `wget <url>`, que gravam com o nome remoto no diretório corrente)
        # continua fora: ali o nome não está na linha de comando.
        destino = ("-o", "--output") if cmd == "curl" else ("-O", "--output-document")
        prefixos = tuple(f"{d}=" for d in destino if d.startswith("--"))
        for i, t in enumerate(rest):
            if t in destino and i + 1 < len(rest):
                targets.append(rest[i + 1])
            elif t.startswith(prefixos):
                targets.append(t.split("=", 1)[1])
    elif cmd == "touch":
        # Cria o arquivo se ele não existe: é escrita, mesmo com conteúdo vazio.
        targets.extend(nonflags)
    elif cmd == "rsync":
        # Como `cp`: lê a origem, escreve no último operando.
        if len(nonflags) >= 2:
            targets.append(nonflags[-1])

    return targets


def extract_write_targets(command: str) -> tuple:
    """Return (targets, has_uncovered_construct)."""
    targets = []
    for seg in _split_segments(command):
        seg = seg.strip()
        if seg:
            targets.extend(_segment_targets(seg))
    # de-dup, drop pseudo-devices and fd dups
    clean = []
    seen = set()
    for t in targets:
        t = _unquote(t).strip()
        if not t or t in _PSEUDO or t.startswith("&") or t in seen:
            continue
        seen.add(t)
        clean.append(t)
    return clean, bool(_UNCOVERED_RE.search(_unquoted_view(command)))


# ─────────────────────────────────────────────────────────────────────────────
# CAMADA 1 — deny-by-default em quatro baldes
#
# Desenho: docs/internals/gauntlet-pilot-bash-path-lock.md ("Camada 1"),
# aprovado em 2026-08-15. Motivo: WEGO-1936 — um qa-engineer barrado no `cp`
# reescreveu `src/main` com `python3 -c "open(...,'w')"`, e o hook antigo
# deixava interpretador inline passar ("não sei analisar → libera + log em
# /tmp"). O log ninguém lia.
#
# A pergunta do hook foi invertida. Antes: "isto parece uma escrita conhecida?"
# — cada vetor novo era um falso-negativo invisível. Agora: "isto é
# comprovadamente inofensivo?". Cada segmento de comando de um agente trancado
# cai em exatamente um balde:
#
#   1. ESCRITOR ANALISÁVEL — o alvo está na linha de comando (redirect, tee,
#      cp, sed -i, mkdir, rm...). Alvo dentro da raiz e fora da pista → nega.
#   2. VERBO INOCENTE — lista auditada abaixo (_SIMPLE e _HANDLERS), cada verbo
#      com as flags que o transformam em escritor/executor negadas.
#   3. FORA DA JURISDIÇÃO — todos os diretórios em que o segmento pode rodar
#      estão fora da raiz, e nada na linha cita a raiz: é o worktree descartável
#      de perturbação. Tudo permitido.
#   4. TODO O RESTO → NEGADO. Interpretador inline, shell aninhado, script que o
#      próprio agente poderia ter escrito, verbo que ninguém listou. Um vetor
#      novo cai aqui POR CONSTRUÇÃO: ele não precisa constar em lista nenhuma,
#      basta não constar na de inocentes.
#
# Manutenção vira acrescentar verbo inocente (falso-positivo: barulhento,
# visível, barato) em vez de caçar bypass (falso-negativo: invisível).
# ─────────────────────────────────────────────────────────────────────────────

# Modo sombra (rollout): CEPA_BASHLOCK_ENFORCE=0 libera o balde 4 e registra
# `bash_pathlock_would_deny` no ledger. O balde 1 (escrita fora da pista) nunca
# é afrouxado — ele já bloqueava antes desta camada existir.
_ENFORCE_ENV = "CEPA_BASHLOCK_ENFORCE"

_MAX_DEPTH = 6

# Marcas que a leitura da linha insere no lugar do que não é argv.
_SUB_MARK = "__CEPASUB{}__"
_SUB_MARK_RE = re.compile(r"__CEPASUB(\d+)__")
_HEREDOC_MARK = "<__CEPAHEREDOC__"
_UNKNOWN = "\x00"

_VAR_RE = re.compile(
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*)|(\{[^}]*\}|[0-9@*#?$!-]))"
)
_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\+?=)(.*)$", re.S)

# Redirecionamentos de stdout que o _REDIR_RE compartilhado não vê porque
# começam com dígito ou `&`: `1> f`, `&> f`, `>| f`, `3> f`. `2>` (stderr) segue
# fora de escopo, como sempre foi (`./mvnw test 2> err.log`).
_EXTRA_REDIR_RE = re.compile(
    r"""(?<![0-9&>])(?:[013-9]>>?|&>>?|>>?\|)\s*(?!&)("[^"]+"|'[^']+'|[^\s;&|<>()]+)"""
)

_SYSTEM_BIN_DIRS = {"/bin", "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin",
                    "/usr/sbin", "/sbin"}

# Variáveis que fazem um verbo inocente executar código escolhido por quem as
# define (pager, editor, diff externo, pré-carga de biblioteca, PATH).
_DANGEROUS_ENV = {
    "PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "BASH_ENV", "ENV",
    "PROMPT_COMMAND", "PYTHONSTARTUP", "PERL5OPT", "RUBYOPT", "NODE_OPTIONS",
    "GIT_EXTERNAL_DIFF", "GIT_PAGER", "PAGER", "GIT_EDITOR", "EDITOR", "VISUAL",
    "GIT_SEQUENCE_EDITOR", "GIT_SSH", "GIT_SSH_COMMAND", "GIT_ASKPASS",
    "SSH_ASKPASS", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_CONFIG",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_DIR", "GIT_WORK_TREE",
    "GIT_EXEC_PATH", "GIT_TEMPLATE_DIR", "MANPAGER", "LESSOPEN", "BROWSER",
}
_DANGEROUS_ENV_PREFIX = ("DYLD_", "GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
_JVM_OPTS_ENV = {"JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS",
                 "MAVEN_OPTS", "GRADLE_OPTS", "JAVA_OPTS"}

# ─── balde 2: a lista auditada de inocentes ─────────────────────────────────
#
# Verbos que não escrevem arquivo nem executam código trazido pela linha de
# comando. Os argumentos deles não importam; escrita, se houver, só por
# redirecionamento — e redirecionamento é balde 1. Quem tem flag perigosa NÃO
# entra aqui: vai para _HANDLERS, com a flag negada.
_SIMPLE = frozenset("""
    ls cat head tail wc grep egrep fgrep zgrep ag diff diff3 cmp comm stat file
    du df pwd echo printf true false : test [ [[ ]] which whereis type basename
    dirname realpath readlink date whoami id hostname uname printenv cut tr nl
    paste column rev fold expand unexpand fmt tac seq sleep wait read exit return
    shift set unset shopt umask ulimit tput clear ps pgrep lsof uptime md5 md5sum
    shasum sha1sum sha256sum sha512sum cksum od hexdump strings jq zcat bzcat
    xzcat let getopts arch sw_vers nproc locale tty groups logname users who
    netstat cal look jobs fi done esac } for select
""".split())

# Palavras de controle que abrem um comando: a palavra sai, o comando fica.
_LEADING_KEYWORDS = {"if", "then", "do", "else", "elif", "while", "until", "!", "{"}

# Verbos cujas escritas estão todas na linha de comando (balde 1).
_WRITERS = frozenset("""
    cp mv install tee dd truncate touch rsync mkdir rmdir rm unlink ln chmod
    chown chgrp
""".split())


class _Negado(Exception):
    def __init__(self, balde, verbo, motivo, segmento="", alvos=None):
        super().__init__(motivo)
        self.balde = balde
        self.verbo = verbo
        self.motivo = motivo
        self.segmento = segmento
        self.alvos = alvos or []


class _Arg:
    """Um token do argv com as variáveis conhecidas expandidas.

    `value` troca o que não dá para saber por _UNKNOWN. `lead_unknown` diz se
    o token COMEÇA com algo desconhecido — só esse pode esconder uma flag
    (`sed $X arquivo` com X=-i), então só ele pesa na decisão.
    """
    __slots__ = ("raw", "value", "known", "lead_unknown")

    def __init__(self, raw, value):
        self.raw = raw
        self.value = value
        self.known = _UNKNOWN not in value
        self.lead_unknown = value.startswith(_UNKNOWN)


class _Ctx:
    def __init__(self, root, agent, allowed, pl, shadow):
        self.root = root
        self.agent = agent
        self.allowed = allowed
        self.pl = pl
        self.shadow = shadow
        self.vars = {}
        self.sub_values = {}
        self.would = []     # negações do balde 4 em modo sombra
        self.events = []    # (evento, campos) para o ledger
        self.sub_base = 0   # numeração global das substituições


# ─── leitura da linha: substituições e heredocs ─────────────────────────────

def _heredoc_at(s, i):
    """Se há um operador de heredoc em s[i:], devolve (fim, delim, apara, citado)."""
    n = len(s)
    if s[i:i + 2] != "<<" or s[i:i + 3] == "<<<":
        return None
    k = i + 2
    apara = k < n and s[k] == "-"
    if apara:
        k += 1
    while k < n and s[k] in " \t":
        k += 1
    citado = False
    q = None
    if k < n and s[k] in "\"'":
        q = s[k]
        citado = True
        k += 1
    elif k < n and s[k] == "\\":
        citado = True
        k += 1
    ini = k
    while k < n and (s[k].isalnum() or s[k] in "_-."):
        k += 1
    delim = s[ini:k]
    if q and k < n and s[k] == q:
        k += 1
    if not delim:
        return None
    return k, delim, apara, citado


def _skip_heredoc_body(s, j, delim, apara):
    """A partir do início do corpo (j), devolve o índice logo após a linha do delimitador."""
    n = len(s)
    while j < n:
        fim = s.find("\n", j)
        if fim == -1:
            fim = n
        linha = s[j:fim]
        j = fim + 1 if fim < n else n
        if (linha.lstrip("\t") if apara else linha).strip() == delim:
            break
    return j


def _match_close(s, i, closer):
    """Índice do fechamento de uma substituição aberta logo antes de s[i].

    Respeita aspas, escapes, substituições aninhadas e corpo de heredoc (a
    mensagem de commit no padrão `"$(cat <<'EOF' ... EOF)"` tem apóstrofos e
    parênteses na prosa). Devolve -1 se não fecha.
    """
    n = len(s)
    depth = 1
    quote = None
    pend = []
    while i < n:
        c = s[i]
        if quote == "'":
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\":
            i += 2
            continue
        if quote == '"':
            if c == '"':
                quote = None
            elif s.startswith("$(", i):
                j = _match_close(s, i + 2, ")")
                if j < 0:
                    return -1
                i = j + 1
                continue
            elif c == "`":
                j = _match_close(s, i + 1, "`")
                if j < 0:
                    return -1
                i = j + 1
                continue
            i += 1
            continue
        if closer == "`" and c == "`":
            return i
        if c == "\n" and pend:
            j = i + 1
            for delim, apara in pend:
                j = _skip_heredoc_body(s, j, delim, apara)
            pend = []
            i = j
            continue
        if s.startswith("<<<", i):
            i += 3
            continue
        h = _heredoc_at(s, i)
        if h:
            pend.append((h[1], h[2]))
            i = h[0]
            continue
        if c in "\"'":
            quote = c
        elif closer == ")" and c == "(":
            depth += 1
        elif closer == ")" and c == ")":
            depth -= 1
            if depth == 0:
                return i
        elif closer == ")" and c == "`":
            j = _match_close(s, i + 1, "`")
            if j < 0:
                return -1
            i = j
        i += 1
    return -1


def _flatten(command):
    """Troca cada `$(...)`, crase, `<(...)` e `>(...)` por uma marca e tira os
    corpos de heredoc.

    Devolve (linha_plana, substituicoes, orfas). Substituição é outro comando,
    que roda ANTES do segmento que a contém — então é classificada como
    comando, com as mesmas regras. É o gap do desenho: `echo $(python3 -c ...)`
    tinha verbo inocente na frente e código arbitrário dentro. `orfas` são as
    substituições no corpo de heredoc sem aspas no delimitador (o shell as
    expande).
    """
    s = command
    n = len(s)
    out = []
    subs = []
    orfas = []
    quote = None
    pend = []
    i = 0

    def add_sub(inner):
        subs.append(inner)
        return _SUB_MARK.format(len(subs) - 1)

    while i < n:
        c = s[i]
        if quote == "'":
            out.append(c)
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(s[i:i + 2])
            i += 2
            continue
        is_sub = s.startswith("$(", i) and not s.startswith("$((", i)
        is_proc = quote is None and (s.startswith("<(", i) or s.startswith(">(", i))
        if is_sub or is_proc:
            j = _match_close(s, i + 2, ")")
            inner = s[i + 2:j] if j >= 0 else s[i + 2:]
            out.append(add_sub(inner))
            i = j + 1 if j >= 0 else n
            continue
        if s.startswith("$((", i):
            # Aritmética não é comando — mas pode esconder `$(...)` dentro.
            j = _match_close(s, i + 3, ")")
            inner = s[i + 3:j] if j >= 0 else s[i + 3:]
            f_inner, f_subs, _ = _flatten(inner)
            base = len(subs)
            subs.extend(f_subs)
            f_inner = _SUB_MARK_RE.sub(
                lambda m: _SUB_MARK.format(base + int(m.group(1))), f_inner)
            out.append("__CEPAARITH__")
            orfas.extend(range(base, len(subs)))
            del f_inner
            i = (j + 2) if j >= 0 else n
            continue
        if c == "`":
            j = _match_close(s, i + 1, "`")
            inner = s[i + 1:j] if j >= 0 else s[i + 1:]
            out.append(add_sub(inner))
            i = j + 1 if j >= 0 else n
            continue
        if quote == '"':
            out.append(c)
            if c == '"':
                quote = None
            i += 1
            continue
        # fora de aspas
        if c in "\"'":
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "\n" and pend:
            out.append("\n")
            j = i + 1
            for delim, apara, citado in pend:
                fim = _skip_heredoc_body(s, j, delim, apara)
                corpo = s[j:fim]
                if not citado:
                    # corpo sem aspas no delimitador: `$(...)` ali EXECUTA
                    _, c_subs, c_orf = _flatten('"' + corpo.replace('"', " ") + '"')
                    base = len(subs)
                    subs.extend(c_subs)
                    orfas.extend(range(base, len(subs)))
                j = fim
            pend = []
            i = j
            continue
        if s.startswith("<<<", i):
            out.append("<<<")  # here-string: não abre corpo
            i += 3
            continue
        h = _heredoc_at(s, i)
        if h:
            pend.append((h[1], h[2], h[3]))
            out.append(" " + _HEREDOC_MARK + " ")
            i = h[0]
            continue
        out.append(c)
        i += 1
    return "".join(out), subs, orfas


def _split_with_seps(command):
    """Segmentos com o separador que os PRECEDE: '', '&&', '||', ';', '|', '&', '\\n'.

    Diferente do _split_segments compartilhado em dois pontos que decidem
    balde: guarda o separador (um `cd` só vale para o próximo segmento se veio
    `&&`) e não corta no `&` de `2>&1` / `&>` — cortar ali transformava o `1`
    de `./mvnw test 2>&1 | tail` num "comando" desconhecido.
    """
    mask = _quoted_mask(command)
    out = []
    start = i = 0
    sep = ""
    n = len(command)
    while i < n:
        if mask[i]:
            i += 1
            continue
        two = command[i:i + 2]
        if two in ("&&", "||"):
            out.append((sep, command[start:i]))
            sep = two
            i += 2
            start = i
            continue
        c = command[i]
        if c == "&" and ((i > 0 and command[i - 1] in "<>") or command[i + 1:i + 2] == ">"):
            i += 1
            continue
        if c == "|" and i > 0 and command[i - 1] == ">":
            i += 1  # `>|` é redirecionamento, não pipe
            continue
        if c in ";|&\n":
            out.append((sep, command[start:i]))
            sep = c
            i += 1
            start = i
            continue
        i += 1
    out.append((sep, command[start:]))
    return out


# ─── expansão e resolução ───────────────────────────────────────────────────

def _expand(ctx, raw, cwds):
    def var(m):
        name = m.group(1) or m.group(2)
        if not name:
            return _UNKNOWN
        if name in ctx.vars:
            v = ctx.vars[name]
            return _UNKNOWN if v is None else v
        if name == "PWD" and len(cwds) == 1:
            return str(next(iter(cwds)))
        v = os.environ.get(name)
        return _UNKNOWN if v is None else v

    def sub(m):
        v = ctx.sub_values.get(int(m.group(1)))
        return _UNKNOWN if v is None else v

    val = _SUB_MARK_RE.sub(sub, raw)
    val = val.replace("__CEPAARITH__", "0")
    val = _VAR_RE.sub(var, val)
    return _Arg(raw, val)


def _resolve_all(val, cwds):
    v = os.path.expanduser(val)
    if os.path.isabs(v):
        return [Path(v).resolve()]
    return [(Path(c) / v).resolve() for c in cwds]


def _inside(p, root):
    try:
        Path(p).relative_to(root)
        return True
    except ValueError:
        return False


def _refs_root(ctx, text, args, cwds):
    """A linha cita a raiz? (condição para o balde 3 NÃO valer)

    Checagem de string, declarada como tal: um caminho montado em tempo de
    execução (`$(echo L3Jvb3Q= | base64 -d)`) escapa. O desenho aceita esse
    residual — ofuscar depois de um deny é dolo, não descoberta.
    """
    root_s = str(ctx.root)
    if root_s in text:
        return True
    for a in args:
        if not a.known:
            return True
        v = a.value
        if root_s in v:
            return True
        if v.startswith("~") or ".." in v or os.path.isabs(v):
            for p in _resolve_all(v.split("=", 1)[-1] if v.startswith("-") else v, cwds):
                if _inside(p, ctx.root):
                    return True
    return False


def _deny(balde, verbo, motivo, seg):
    raise _Negado(balde, verbo, motivo, seg)


def _check_targets(ctx, targets, cwds, verbo, seg):
    """Balde 1: todo alvo dentro da raiz tem de estar na pista do agente."""
    fora = []
    for t in targets:
        val = t.value if isinstance(t, _Arg) else t
        raw = t.raw if isinstance(t, _Arg) else t
        val = _unquote(val).strip()
        if _UNKNOWN in val:
            raise _Negado(1, verbo, f"alvo de escrita que não sei resolver: {raw}",
                          seg, [raw])
        if not val or val in _PSEUDO or val.startswith("&") or val == "-":
            continue
        for p in _resolve_all(val, cwds):
            if not _inside(p, ctx.root):
                continue
            ps = str(p)
            if ctx.pl.is_own_expertise_file(ps, ctx.agent):
                continue
            if ctx.allowed and ctx.pl.path_matches(ps, ctx.allowed, ctx.root):
                continue
            fora.append(raw)
            break
    if fora:
        raise _Negado(1, verbo, "escrita fora da sua pista", seg, fora)


def _no_hidden_flags(args, verbo, seg, value_flags=()):
    """Token que COMEÇA com valor desconhecido pode ser uma flag disfarçada."""
    prev = None
    for a in args:
        if a.lead_unknown and prev not in value_flags:
            _deny(4, verbo, f"argumento que não sei avaliar ({a.raw}) pode esconder "
                            f"uma flag que torna `{verbo}` escritor ou executor", seg)
        prev = a.value if a.known else None


def _script_rule(ctx, arg, cwds, verbo, seg):
    """Executar um arquivo é inocente só se o agente NÃO pode tê-lo escrito.

    Script do projeto fora da pista (`./mvnw`, `bash scripts/build.sh`,
    `source .venv/bin/activate`): foi escrito por outro — é o equivalente a um
    `npm test`. Script fora da raiz (/tmp) ou dentro da própria pista: o agente
    pode tê-lo escrito agora mesmo, então executar é escrever arbitrariamente.
    """
    if not arg.known:
        _deny(4, verbo, f"o arquivo executado vem de valor que não sei avaliar ({arg.raw})", seg)
    for p in _resolve_all(arg.value, cwds):
        if not _inside(p, ctx.root):
            _deny(4, verbo, f"executar arquivo fora do projeto ({arg.value}) — "
                            f"você pode tê-lo escrito, e aí ele escreve o que quiser", seg)
        ps = str(p)
        if ctx.pl.is_own_expertise_file(ps, ctx.agent) or (
                ctx.allowed and ctx.pl.path_matches(ps, ctx.allowed, ctx.root)):
            _deny(4, verbo, f"executar arquivo da sua própria pista ({arg.value}) — "
                            f"é código que você mesmo pode ter escrito", seg)


# ─── handlers por verbo (balde 2 com flag negada, ou balde 1) ───────────────

def _vals(args):
    return [a.value for a in args]


def _nonflags(args, value_flags=()):
    out = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a.known and a.value in value_flags:
            skip = True
            continue
        if a.known and _is_flag(a.value):
            continue
        out.append(a)
    return out


def _generic_targets(verbo, args):
    """Alvos pelo extrator compartilhado (_segment_targets) + os que faltavam lá."""
    vals = [verbo] + _vals(args)
    linha = " ".join(shlex.quote(v) for v in vals)
    alvos = list(_segment_targets(linha))
    rest = vals[1:]
    nf = [v for v in rest if v and not _is_flag(v)]
    if verbo in ("cp", "mv", "install", "ln"):
        for k, v in enumerate(rest):
            if v in ("-t", "--target-directory") and k + 1 < len(rest):
                alvos.append(rest[k + 1])
            elif v.startswith("--target-directory="):
                alvos.append(v.split("=", 1)[1])
    if verbo == "ln":
        if len(nf) >= 2:
            alvos.append(nf[-1])
        elif nf:
            alvos.append(os.path.basename(nf[0].rstrip("/")))
    elif verbo in ("mkdir", "rmdir", "rm", "unlink"):
        alvos.extend(nf)
    elif verbo in ("chmod", "chown", "chgrp"):
        alvos.extend(nf[1:])
    return alvos


def _h_writer(ctx, verbo, args, cwds, seg):
    if verbo == "rsync" and any(a.value in ("-e", "--rsh", "--rsync-path") or
                               a.value.startswith(("--rsh=", "--rsync-path="))
                               for a in args):
        _deny(4, verbo, "rsync -e/--rsh executa um comando", seg)
    _check_targets(ctx, _generic_targets(verbo, args), cwds, verbo, seg)


def _h_sed(ctx, verbo, args, cwds, seg):
    vals = _vals(args)
    if any(v in ("-f", "--file") or v.startswith("--file=") for v in vals):
        _deny(4, verbo, "sed -f lê o programa de um arquivo — não sei o que ele faz", seg)
    _no_hidden_flags(args, verbo, seg, ("-e", "--expression"))
    scripts = []
    for k, v in enumerate(vals):
        if v in ("-e", "--expression") and k + 1 < len(vals):
            scripts.append(vals[k + 1])
        elif v.startswith("--expression="):
            scripts.append(v.split("=", 1)[1])
    if not scripts:
        nf = [a.value for a in _nonflags(args, ("-e", "--expression", "-l"))]
        nf = [v for v in nf if v]  # `sed -i ''` (BSD): o sufixo vazio não é script
        if nf:
            scripts.append(nf[0])
    for sc in scripts:
        if _sed_executes_or_writes(sc):
            _deny(4, verbo, "o programa do sed escreve arquivo (w/W) ou executa (e)", seg)
    if any(v == "-i" or v.startswith("-i") or v.startswith("--in-place") for v in vals):
        _check_targets(ctx, _generic_targets("sed", args), cwds, verbo, seg)


_SED_CMD_RE = re.compile(
    r"(?:^|[;\n{}])\s*(?:[0-9$]+|/(?:\\.|[^/\\])*/)?"
    r"(?:\s*,\s*(?:[0-9$]+|/(?:\\.|[^/\\])*/))?\s*!?\s*[wWe](?:\s|$|;)"
)


def _sed_executes_or_writes(script):
    if _SED_CMD_RE.search(script):
        return True
    # flags do comando s: s<d>padrão<d>troca<d>FLAGS — `w arquivo` e `e` são perigosas
    i, n = 0, len(script)
    while i < n:
        if script[i] == "s" and i + 1 < n and script[i + 1] not in " \t\n;\\":
            if i > 0 and (script[i - 1].isalnum() or script[i - 1] == "_"):
                i += 1
                continue
            d = script[i + 1]
            j = i + 2
            partes = 0
            while j < n and partes < 2:
                if script[j] == "\\":
                    j += 2
                    continue
                if script[j] == d:
                    partes += 1
                j += 1
            if partes == 2:
                k = j
                while k < n and script[k] not in " \t\n;}":
                    k += 1
                flags = script[j:k]
                if "e" in flags or "w" in flags:
                    return True
                i = k
                continue
        i += 1
    return False


def _h_awk(ctx, verbo, args, cwds, seg):
    vals = _vals(args)
    for v in vals:
        if v in ("-f", "--file", "-i", "--include", "-l", "--load", "-E", "--exec") \
                or v.startswith(("--file=", "--include=", "--load=", "--exec=")):
            _deny(4, verbo, f"awk {v} carrega programa de fora da linha", seg)
    nf = _nonflags(args, ("-F", "-v", "--field-separator", "--assign"))
    if not nf:
        return
    prog = nf[0].raw
    # `>` e `|` só escrevem/executam no contexto de print/printf; fora dele são
    # comparação (`NR>1`) e alternância de regex (`/a|b/`), leitura pura.
    if re.search(r"\bsystem\s*\(|\bgetline\b|@(?:include|load|namespace)\b", prog) or \
            re.search(r"\bprintf?\b[^;{}]*[>|]", prog):
        _deny(4, verbo, "o programa awk escreve (print > arquivo), abre pipe ou "
                        "executa (system/getline)", seg)


def _h_find(ctx, verbo, args, cwds, seg):
    _no_hidden_flags(args, verbo, seg)
    ruins = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0",
             "-fprintf", "-fls"}
    for a in args:
        if a.value in ruins:
            _deny(4, verbo, f"find {a.value} executa comando ou apaga/escreve arquivo", seg)


def _h_flagdeny(bad, prefixes=()):
    def h(ctx, verbo, args, cwds, seg):
        _no_hidden_flags(args, verbo, seg)
        for a in args:
            if a.value in bad or (prefixes and a.value.startswith(prefixes)):
                _deny(4, verbo, f"{verbo} {a.value} escreve arquivo ou executa comando", seg)
    return h


def _h_output_flag(flags):
    """Verbo inocente cuja flag de saída vira alvo de escrita (sort -o, tree -o)."""
    def h(ctx, verbo, args, cwds, seg):
        _no_hidden_flags(args, verbo, seg, flags)
        vals = _vals(args)
        alvos = []
        for k, v in enumerate(vals):
            if v in flags and k + 1 < len(vals):
                alvos.append(args[k + 1])
            for f in flags:
                if f.startswith("--") and v.startswith(f + "="):
                    alvos.append(v.split("=", 1)[1])
                elif not f.startswith("--") and v.startswith(f) and len(v) > len(f):
                    alvos.append(v[len(f):])
        _check_targets(ctx, alvos, cwds, verbo, seg)
    return h


def _h_second_operand(ctx, verbo, args, cwds, seg):
    """`uniq entrada saida`, `xxd entrada saida`: o 2º operando é escrito."""
    _no_hidden_flags(args, verbo, seg)
    nf = _nonflags(args, ("-s", "-f", "-c", "-l", "-g", "-o", "-n", "-w"))
    if len(nf) >= 2:
        _check_targets(ctx, [nf[1]], cwds, verbo, seg)


def _h_mktemp(ctx, verbo, args, cwds, seg):
    _no_hidden_flags(args, verbo, seg, ("-p", "--tmpdir", "-t", "--suffix"))
    alvos = []
    vals = _vals(args)
    for k, v in enumerate(vals):
        if v in ("-p", "--tmpdir") and k + 1 < len(vals):
            alvos.append(os.path.join(vals[k + 1], "x"))
        elif v.startswith("--tmpdir="):
            alvos.append(os.path.join(v.split("=", 1)[1], "x"))
    nf = _nonflags(args, ("-p", "--tmpdir", "-t", "--suffix"))
    if nf and not alvos:
        alvos.append(nf[0])
    _check_targets(ctx, alvos, cwds, verbo, seg)


def _h_curl(ctx, verbo, args, cwds, seg):
    _no_hidden_flags(args, verbo, seg, ("-o", "--output", "-d", "--data", "-H",
                                        "--header", "-u", "--user", "-X", "-F"))
    vals = _vals(args)
    alvos = []
    for k, v in enumerate(vals):
        if v in ("-O", "--remote-name", "--remote-name-all", "-J",
                 "--remote-header-name", "--output-dir", "-K", "--config") \
                or v.startswith(("--output-dir=", "--config=")):
            _deny(4, verbo, f"curl {v} grava com nome que a linha não diz", seg)
        if v in ("-o", "--output") and k + 1 < len(vals):
            alvos.append(args[k + 1])
        elif v.startswith("--output="):
            alvos.append(v.split("=", 1)[1])
        elif re.match(r"^-[a-zA-Z]+$", v) and not v.startswith("--"):
            letras = v[1:]
            if "O" in letras or "K" in letras or "J" in letras:
                _deny(4, verbo, f"curl {v} grava com nome que a linha não diz", seg)
            if "o" in letras:
                resto = letras[letras.index("o") + 1:]
                if resto:
                    alvos.append(resto)
                elif k + 1 < len(vals):
                    alvos.append(args[k + 1])
    _check_targets(ctx, alvos, cwds, verbo, seg)


def _h_wget(ctx, verbo, args, cwds, seg):
    vals = _vals(args)
    alvos = []
    for k, v in enumerate(vals):
        if v in ("-O", "--output-document") and k + 1 < len(vals):
            alvos.append(args[k + 1])
        elif v.startswith("--output-document="):
            alvos.append(v.split("=", 1)[1])
        elif re.match(r"^-[a-zA-Z]*O", v):
            resto = v[v.index("O") + 1:]
            alvos.append(resto if resto else (vals[k + 1] if k + 1 < len(vals) else "?"))
    if not alvos and "--spider" not in vals:
        _deny(4, verbo, "wget sem -O grava com o nome remoto no diretório corrente", seg)
    _check_targets(ctx, alvos, cwds, verbo, seg)


def _h_archive_readonly(modes_ok):
    def h(ctx, verbo, args, cwds, seg):
        vals = _vals(args)
        if verbo == "tar":
            letras = ""
            for k, v in enumerate(vals):
                if v.startswith("--"):
                    letras += {"--list": "t", "--extract": "x", "--get": "x",
                               "--create": "c", "--append": "r",
                               "--update": "u"}.get(v, "")
                elif v.startswith("-") or k == 0:
                    letras += v.lstrip("-")
            if "t" in letras and not any(m in letras for m in "xcruA"):
                return
            _deny(4, verbo, "tar só é inocente listando (-t); extrair/criar escreve "
                            "onde a linha não diz", seg)
        if not any(v in modes_ok for v in vals):
            _deny(4, verbo, f"{verbo} só é inocente em modo de leitura "
                            f"({', '.join(sorted(modes_ok))})", seg)
    return h


def _wrapper_inner(verbo, args):
    """Tira as opções de um wrapper finito e devolve o comando embrulhado."""
    vals = _vals(args)
    i = 0
    if verbo == "time":
        while i < len(vals) and vals[i] in ("-p", "-l"):
            i += 1
    elif verbo == "nohup":
        pass
    elif verbo == "nice":
        while i < len(vals) and _is_flag(vals[i]):
            i += 2 if vals[i] in ("-n", "--adjustment") else 1
    elif verbo == "timeout":
        while i < len(vals) and _is_flag(vals[i]):
            i += 2 if vals[i] in ("-s", "--signal", "-k", "--kill-after") else 1
        i += 1  # a duração
    elif verbo == "stdbuf":
        while i < len(vals) and _is_flag(vals[i]):
            i += 2 if vals[i] in ("-i", "-o", "-e") else 1
    elif verbo == "command":
        while i < len(vals) and vals[i] == "-p":
            i += 1
    return args[i:]


def _h_wrapper(ctx, verbo, args, cwds, seg):
    if verbo == "command" and any(a.value in ("-v", "-V") for a in args):
        return
    for a in args:
        if a.lead_unknown:
            _deny(4, verbo, f"{verbo} com argumento que não sei avaliar ({a.raw})", seg)
    inner = _wrapper_inner(verbo, args)
    if inner:
        _dispatch(ctx, inner, cwds, seg)


def _h_env(ctx, verbo, args, cwds, seg):
    i = 0
    vals = _vals(args)
    while i < len(vals):
        v = vals[i]
        if v in ("-S", "--split-string", "-C", "--chdir") or v.startswith(
                ("--split-string=", "--chdir=")) or (re.match(r"^-[a-zA-Z]+$", v)
                                                     and ("S" in v or "C" in v)):
            _deny(4, verbo, "env -S/-C monta ou muda o comando por fora da linha", seg)
        if v in ("-u", "--unset"):
            i += 2
            continue
        if _is_flag(v) and not _ASSIGN_RE.match(v):
            i += 1
            continue
        break
    inner = args[i:]
    if inner:
        _dispatch(ctx, inner, cwds, seg)


_XARGS_VALUE_FLAGS = {"-I", "-L", "-l", "-n", "-P", "-s", "-d", "-E", "-e", "-a",
                      "--max-args", "--max-procs", "--delimiter", "--arg-file",
                      "--replace", "--max-lines", "--eof", "--max-chars"}


def _h_xargs(ctx, verbo, args, cwds, seg):
    vals = _vals(args)
    i = 0
    while i < len(vals) and _is_flag(vals[i]):
        i += 2 if vals[i] in _XARGS_VALUE_FLAGS else 1
    inner = args[i:]
    if not inner:
        return  # xargs sem comando = echo
    iv = inner[0].value if inner[0].known else ""
    if iv not in _SIMPLE and iv not in ("sed", "awk", "find", "rg", "fd", "jq"):
        _deny(4, verbo, f"xargs executa `{inner[0].raw}` com argumentos vindos da "
                        f"entrada — só verbos de leitura passam por xargs", seg)
    _dispatch(ctx, inner, cwds, seg)


_PY_MODULES_OK = {"pytest", "unittest", "json.tool", "py_compile", "compileall",
                  "mypy", "flake8", "pylint", "pyflakes", "pycodestyle", "platform",
                  "sysconfig", "site", "tabnanny"}


def _h_pylike_tool(ctx, tool, args, cwds, seg):
    """Ferramentas python que podem ser chamadas soltas ou via `-m`."""
    vals = _vals(args)
    nf = [a.value for a in _nonflags(args)]
    if tool == "pip" or tool == "pip3":
        if nf and nf[0] in ("list", "show", "freeze", "check", "debug") or \
                any(v in ("--version", "-V") for v in vals):
            return
        _deny(4, tool, "pip só é inocente consultando (list/show/freeze/check)", seg)
    if tool == "ruff":
        if "--fix" in vals or (nf and nf[0] == "format" and not
                               any(v in ("--check", "--diff") for v in vals)):
            _deny(4, tool, "ruff --fix/format reescreve arquivos", seg)
        return
    if tool == "black" or tool == "isort":
        if not any(v in ("--check", "--diff", "--check-only", "-c") for v in vals):
            _deny(4, tool, f"{tool} sem --check/--diff reescreve arquivos", seg)
        return
    if tool == "coverage":
        if nf and nf[0] == "run":
            rest = args[[a.value for a in args].index("run") + 1:]
            rv = _vals(rest)
            if "-m" in rv:
                k = rv.index("-m")
                if k + 1 >= len(rv) or rv[k + 1] not in _PY_MODULES_OK:
                    _deny(4, tool, "coverage run -m com módulo fora da lista", seg)
                return
            rnf = _nonflags(rest, ("--rcfile", "--source", "--omit", "--include",
                                   "--data-file", "--context"))
            if rnf:
                _script_rule(ctx, rnf[0], cwds, tool, seg)
        return
    # mypy, flake8, pylint...: só leem
    return


def _h_python(ctx, verbo, args, cwds, seg):
    vals = _vals(args)
    i = 0
    while i < len(vals):
        a = args[i]
        v = vals[i]
        if a.lead_unknown:
            _deny(4, verbo, f"argumento que não sei avaliar ({a.raw})", seg)
        if v in ("-V", "--version", "-h", "--help", "-VV"):
            return
        if v == "--":
            i += 1
            break
        if v in ("-W", "-X"):
            i += 2
            continue
        if v.startswith(("-W", "-X")):
            i += 1
            continue
        if v == "-m" or (re.match(r"^-[a-zA-Z]+$", v) and "m" in v and "c" not in v):
            if v == "-m":
                mod = vals[i + 1] if i + 1 < len(vals) else ""
                rest = args[i + 2:]
            else:
                resto = v[v.index("m") + 1:]
                mod = resto or (vals[i + 1] if i + 1 < len(vals) else "")
                rest = args[i + 1:] if resto else args[i + 2:]
            if mod in _PY_MODULES_OK:
                return
            if mod in ("pip", "ruff", "black", "isort", "coverage"):
                _h_pylike_tool(ctx, mod, rest, cwds, seg)
                return
            _deny(4, verbo, f"`{verbo} -m {mod}` — módulo fora da lista de inocentes", seg)
        if v.startswith("--"):
            i += 1
            continue
        if v.startswith("-") and v != "-":
            letras = v[1:]
            if "c" in letras:
                _deny(4, verbo, f"`{verbo} -c` roda código inline — código arbitrário "
                                f"é escrita arbitrária", seg)
            if "i" in letras:
                _deny(4, verbo, f"`{verbo} -i` é interpretador interativo", seg)
            i += 1
            continue
        break
    if i >= len(vals) or vals[i] == "-":
        _deny(4, verbo, f"`{verbo}` lendo o programa da entrada (heredoc/pipe) — "
                        f"código arbitrário é escrita arbitrária", seg)
    _script_rule(ctx, args[i], cwds, verbo, seg)


def _h_node(ctx, verbo, args, cwds, seg):
    vals = _vals(args)
    ruins = ("-e", "--eval", "-p", "--print", "-r", "--require", "--import",
             "--loader", "--experimental-loader", "-i", "--interactive", "-pe")
    for a in args:
        if a.lead_unknown:
            _deny(4, verbo, f"argumento que não sei avaliar ({a.raw})", seg)
        v = a.value
        if v in ruins or v.startswith(tuple(r + "=" for r in ruins if r.startswith("--"))):
            _deny(4, verbo, f"`node {v}` roda código inline — código arbitrário é "
                            f"escrita arbitrária", seg)
    if any(v in ("-v", "--version", "-h", "--help") for v in vals) or "--test" in vals:
        return
    nf = _nonflags(args)
    if not nf or nf[0].value == "-":
        _deny(4, verbo, "`node` lendo o programa da entrada", seg)
    _script_rule(ctx, nf[0], cwds, verbo, seg)


def _h_shell(ctx, verbo, args, cwds, seg):
    vals = _vals(args)
    i = 0
    while i < len(vals):
        v = vals[i]
        if args[i].lead_unknown:
            _deny(4, verbo, f"argumento que não sei avaliar ({args[i].raw})", seg)
        if v == "--":
            i += 1
            break
        if v in ("-o", "+o"):
            i += 2
            continue
        if re.match(r"^[-+][a-zA-Z]+$", v):
            if any(x in v[1:] for x in "csi"):
                _deny(4, verbo, f"`{verbo} {v}` roda comando de uma string ou da "
                                f"entrada — shell aninhado não é analisável", seg)
            i += 1
            continue
        if v.startswith("--"):
            i += 1
            continue
        break
    if i >= len(vals):
        _deny(4, verbo, f"`{verbo}` lendo comandos da entrada (heredoc/pipe)", seg)
    _script_rule(ctx, args[i], cwds, verbo, seg)


def _h_source(ctx, verbo, args, cwds, seg):
    nf = _nonflags(args)
    if not nf:
        _deny(4, verbo, "source sem arquivo", seg)
    _script_rule(ctx, nf[0], cwds, verbo, seg)


def _mvn_args(ctx, verbo, args, seg):
    for a in args:
        if a.lead_unknown:
            _deny(4, verbo, f"argumento que não sei avaliar ({a.raw}) pode esconder "
                            f"um goal que executa comando", seg)
        v = a.value
        if v.startswith(("exec:", "antrun:")) or any(
                p in v for p in ("exec-maven-plugin", "maven-antrun-plugin",
                                 "gmavenplus", "groovy-maven-plugin")):
            _deny(4, verbo, f"goal `{v}` executa comando arbitrário", seg)


def _h_mvn(ctx, verbo, args, cwds, seg):
    _mvn_args(ctx, verbo, args, seg)


def _h_gradle(ctx, verbo, args, cwds, seg):
    _no_hidden_flags(args, verbo, seg)


def _h_make(ctx, verbo, args, cwds, seg):
    _no_hidden_flags(args, verbo, seg, ("-C", "-j"))
    for v in _vals(args):
        if v in ("-f", "--file", "--makefile", "--eval", "-E") or v.startswith(
                ("--file=", "--makefile=", "--eval=")):
            _deny(4, verbo, f"make {v} lê receita de fora do projeto", seg)


_NPM_VALUE_FLAGS = {"--prefix", "-C", "--dir", "-w", "--workspace", "--filter",
                    "--cwd", "-F"}
_NPM_OK = {"test", "t", "tst", "run", "run-script", "rum", "urn", "start", "stop",
           "restart", "ci", "install", "i", "in", "ins", "inst", "insta", "instal",
           "isnt", "isnta", "isntal", "ls", "list", "ll", "la", "view", "v", "info",
           "show", "outdated", "audit", "explain", "why", "config", "c", "prefix",
           "root", "bin", "help", "doctor", "whoami", "ping", "search", "fund",
           "version", "build", "lint", "typecheck"}
_PM_DENY = {"exec", "x", "dlx", "node", "add", "remove", "rm", "uninstall", "un",
            "unlink", "link", "ln", "up", "upgrade", "update", "patch",
            "patch-commit", "set", "plugin", "create", "init", "import", "publish",
            "pack", "rebuild", "dedupe", "prune", "pkg", "set-script", "edit"}


def _h_pm(ctx, verbo, args, cwds, seg):
    """npm / pnpm / yarn."""
    _no_hidden_flags(args, verbo, seg, tuple(_NPM_VALUE_FLAGS))
    vals = _vals(args)
    if any(v in ("--fix", "--write") for v in vals):
        _deny(4, verbo, f"{verbo} ... --fix/--write reescreve arquivos de outras pistas", seg)
    nf = _nonflags(args, _NPM_VALUE_FLAGS)
    if not nf:
        return  # `npm --version`, `yarn` (= install)
    sub = nf[0].value
    if sub in _PM_DENY:
        _deny(4, verbo, f"`{verbo} {sub}` instala/executa/reescreve fora da lista", seg)
    if sub in ("install", "i", "in", "ins", "inst", "insta", "instal", "isnt",
               "isnta", "isntal") and len(nf) > 1:
        _deny(4, verbo, f"`{verbo} {sub} <pacote>` muda o package.json", seg)
    if sub == "audit" and len(nf) > 1 and nf[1].value == "fix":
        _deny(4, verbo, "`audit fix` reescreve package.json/lockfile", seg)
    if sub in ("config", "c") and len(nf) > 1 and nf[1].value not in ("get", "list", "ls"):
        _deny(4, verbo, "config que grava", seg)
    if sub == "version" and len(nf) > 1:
        _deny(4, verbo, "`version <x>` reescreve o package.json", seg)
    if verbo == "npm" and sub not in _NPM_OK:
        _deny(4, verbo, f"`npm {sub}` fora da lista de inocentes", seg)


_NPX_DENY_PKGS = {"node", "ts-node", "tsx", "bun", "deno", "zx", "sh", "bash",
                  "python", "python3", "perl", "ruby", "rimraf", "shx", "cross-env",
                  "del-cli", "trash-cli", "cpy-cli", "cpx", "ncp", "copyfiles", "mv",
                  "rm", "npm", "pnpm", "yarn"}


def _h_npx(ctx, verbo, args, cwds, seg):
    vals = _vals(args)
    _no_hidden_flags(args, verbo, seg, ("-p", "--package"))
    for v in vals:
        if v in ("-c", "--call") or v.startswith("--call="):
            _deny(4, verbo, "`npx -c` roda uma string de shell", seg)
        if v in ("--fix", "--write"):
            _deny(4, verbo, f"npx ... {v} reescreve arquivos de outras pistas", seg)
    nf = _nonflags(args, ("-p", "--package"))
    if not nf:
        _deny(4, verbo, "npx sem pacote", seg)
    pkg = nf[0].value
    base = pkg.rsplit("@", 1)[0] if pkg.count("@") and not pkg.startswith("@") else pkg
    if base.split("/")[-1] in _NPX_DENY_PKGS or base in _NPX_DENY_PKGS:
        _deny(4, verbo, f"`npx {pkg}` executa código arbitrário ou apaga/copia arquivo", seg)
    if base.endswith("prettier") and "-w" in vals:
        _deny(4, verbo, "prettier -w reescreve arquivos", seg)


def _h_js_tool(ctx, verbo, args, cwds, seg):
    vals = _vals(args)
    _no_hidden_flags(args, verbo, seg)
    if verbo == "eslint" and "--fix" in vals:
        _deny(4, verbo, "eslint --fix reescreve arquivos", seg)
    if verbo == "prettier" and any(v in ("--write", "-w") for v in vals):
        _deny(4, verbo, "prettier --write reescreve arquivos", seg)


def _h_sub_allow(allowed_subs, deny_flags=()):
    def h(ctx, verbo, args, cwds, seg):
        _no_hidden_flags(args, verbo, seg)
        vals = _vals(args)
        if any(v in ("--version", "-V", "version", "--help", "-h") for v in vals[:1]):
            return
        for f in deny_flags:
            if f in vals:
                _deny(4, verbo, f"{verbo} {f} reescreve arquivos", seg)
        nf = _nonflags(args)
        if not nf or nf[0].value not in allowed_subs:
            sub = nf[0].value if nf else "(nada)"
            _deny(4, verbo, f"`{verbo} {sub}` fora da lista de inocentes "
                            f"({', '.join(sorted(allowed_subs))})", seg)
    return h


def _h_java(ctx, verbo, args, cwds, seg):
    if all(a.value in ("-version", "--version", "-showversion") for a in args) and args:
        return
    _deny(4, verbo, "java roda bytecode/fonte arbitrário — use o build (./mvnw)", seg)


_DOCKER_OK = {"ps", "images", "image", "logs", "inspect", "version", "info", "stats",
              "top", "port", "pull", "build", "stop", "start", "restart", "rm", "rmi",
              "kill", "exec", "network", "volume", "container", "system", "context",
              "events", "wait", "compose", "run", "cp", "create", "pause", "unpause",
              "ls", "config", "down", "up", "buildx"}
_DOCKER_VALUE_FLAGS = ("-H", "--host", "--context", "-c", "-f", "--file", "-p",
                       "--project-name", "--project-directory", "--profile",
                       "--env-file", "--log-level")


def _h_docker(ctx, verbo, args, cwds, seg):
    _no_hidden_flags(args, verbo, seg, _DOCKER_VALUE_FLAGS)
    nf = _nonflags(args, _DOCKER_VALUE_FLAGS)
    if not nf:
        return
    k = 0
    if nf[0].value == "compose":
        k = 1
    if len(nf) <= k:
        return
    sub = nf[k].value
    if sub not in _DOCKER_OK:
        _deny(4, verbo, f"`{verbo} {sub}` fora da lista de inocentes", seg)
    vals = _vals(args)
    if sub == "build" and any(v in ("-o", "--output") or v.startswith("--output=")
                              for v in vals):
        _deny(4, verbo, "docker build --output grava no disco local", seg)
    if sub in ("run", "create"):
        for i, v in enumerate(vals):
            src = None
            if v in ("-v", "--volume", "--mount") and i + 1 < len(args):
                src = args[i + 1]
            elif v.startswith(("--volume=", "--mount=")):
                src = _Arg(v, v.split("=", 1)[1])
            if src is None:
                continue
            origem = src.value.split(":", 1)[0]
            if src.value.startswith("type="):
                m = re.search(r"(?:source|src)=([^,]+)", src.value)
                origem = m.group(1) if m else ""
            if not src.known or not os.path.isabs(os.path.expanduser(origem)) or any(
                    _inside(p, ctx.root) for p in _resolve_all(origem, cwds)):
                _deny(4, verbo, "docker run montando pasta do projeto: o container "
                                "escreve nela sem passar pelo cadeado", seg)
    if sub == "cp" and len(nf) >= k + 3:
        destino = nf[-1]
        if ":" not in destino.value.split("/")[0]:
            _check_targets(ctx, [destino], cwds, verbo, seg)


def _h_gh(ctx, verbo, args, cwds, seg):
    _no_hidden_flags(args, verbo, seg, ("-R", "--repo", "-b", "--body", "-t",
                                        "--title", "-F", "--body-file", "-q", "--jq"))
    nf = [a.value for a in _nonflags(args, ("-R", "--repo", "-b", "--body", "-t",
                                           "--title", "-F", "--body-file", "-q",
                                           "--jq"))]
    par = tuple(nf[:2])
    if par in {("repo", "clone"), ("run", "download"), ("release", "download"),
               ("pr", "checkout"), ("gist", "clone")} or (nf and nf[0] in
                                                          ("alias", "extension", "ext")):
        _deny(4, verbo, f"`gh {' '.join(par)}` grava arquivos ou executa extensão", seg)


# git ─────────────────────────────────────────────────────────────────────────

_GIT_READONLY = {
    "status", "log", "diff", "show", "blame", "annotate", "rev-parse", "rev-list",
    "ls-files", "ls-tree", "ls-remote", "cat-file", "describe", "shortlog",
    "merge-base", "name-rev", "for-each-ref", "show-ref", "show-branch",
    "whatchanged", "count-objects", "version", "help", "check-ignore", "check-attr",
    "check-ref-format", "var", "diff-tree", "diff-files", "diff-index",
    "range-diff", "cherry", "fetch", "add", "commit", "branch", "tag", "push",
    "switch", "fsck", "verify-commit", "verify-tag", "symbolic-ref", "merge",
    "grep",
}
# `git -c chave=valor`: só chaves que não executam nada.
_GIT_C_OK = ("color.", "core.quotepath", "user.", "log.", "advice.",
             "init.defaultbranch", "commit.gpgsign", "gc.auto", "diff.renames",
             "diff.noprefix", "merge.conflictstyle", "pull.rebase", "push.default",
             "safe.directory", "core.autocrlf", "core.filemode", "column.")
_GIT_VALUE_FLAGS_COMMIT = ("-m", "--message", "-F", "--file", "--author", "--date",
                           "-C", "-c", "--reuse-message", "--reedit-message",
                           "--fixup", "--squash", "-t", "--template")


def _looks_like_path(v, cwds):
    if any(p.exists() for p in _resolve_all(v, cwds)):
        return True
    return "/" in v and bool(re.search(r"\.[A-Za-z][A-Za-z0-9]{0,5}$", v))


def _h_git(ctx, verbo, args, cwds, seg):
    vals = _vals(args)
    i = 0
    git_cwds = cwds
    while i < len(vals):
        v = vals[i]
        a = args[i]
        if a.lead_unknown:
            _deny(4, verbo, f"argumento que não sei avaliar ({a.raw})", seg)
        if v == "-C" and i + 1 < len(args):
            alvo = args[i + 1]
            if not alvo.known:
                _deny(4, verbo, f"git -C com caminho que não sei avaliar ({alvo.raw})", seg)
            git_cwds = {p for p in _resolve_all(alvo.value, git_cwds)}
            i += 2
            continue
        if v == "-c" and i + 1 < len(args):
            chave = vals[i + 1].split("=", 1)[0].lower()
            if not chave.startswith(_GIT_C_OK):
                _deny(4, verbo, f"git -c {chave}=... pode fazer o git executar um "
                                f"comando (pager, editor, alias, hook)", seg)
            i += 2
            continue
        if v in ("--git-dir", "--work-tree") or v.startswith(("--git-dir=", "--work-tree=")):
            _deny(4, verbo, f"git {v} aponta o git para outra árvore — use git -C", seg)
        if v.startswith("-"):
            i += 1
            continue
        break
    # git -C <fora da raiz> sem citar a raiz: é o worktree descartável (balde 3)
    resto_args = args[i:]
    if git_cwds is not cwds and all(not _inside(c, ctx.root) for c in git_cwds) and \
            not _refs_root(ctx, seg, resto_args, git_cwds):
        return
    if i >= len(vals):
        return  # `git --version`, `git -C x`
    sub = vals[i]
    rest = args[i + 1:]
    rv = _vals(rest)
    cw = git_cwds

    def writer(alvos):
        _check_targets(ctx, alvos, cw, "git", seg)

    if sub in ("diff", "show", "log", "format-patch"):
        if sub == "format-patch":
            _deny(4, verbo, "git format-patch grava arquivos", seg)
        for k, x in enumerate(rv):
            if x == "--output" and k + 1 < len(rest):
                writer([rest[k + 1]])
            elif x.startswith("--output="):
                writer([x.split("=", 1)[1]])
        return
    if sub == "grep":
        if any(x in ("-O", "--open-files-in-pager") or x.startswith(
                ("-O", "--open-files-in-pager=")) for x in rv):
            _deny(4, verbo, "git grep -O abre um pager/editor", seg)
        return
    if sub == "commit":
        return
    if sub in _GIT_READONLY:
        return
    if sub == "mv":
        writer([t for t in _segment_targets(
            " ".join(shlex.quote(x) for x in ["git", "mv"] + rv))])
        return
    if sub == "rm":
        writer([a for a in _nonflags(rest)])
        return
    if sub == "restore":
        writer(_nonflags(rest, ("-s", "--source")))
        return
    if sub == "checkout":
        if "--" in rv:
            writer(rest[rv.index("--") + 1:])
            return
        nf = _nonflags(rest, ("-b", "-B", "--orphan", "--conflict"))
        if any(x in ("-b", "-B", "--orphan") for x in rv):
            if len(nf) >= 2:
                writer(nf[1:])
            return
        if any(not a.known for a in nf):
            _deny(4, verbo, "git checkout com argumento que não sei avaliar pode "
                            "sobrescrever arquivo", seg)
        if len(nf) >= 2:
            writer(nf[1:])  # `git checkout <ref> <caminho>` sem `--`
        elif len(nf) == 1 and nf[0].known and _looks_like_path(nf[0].value, cw):
            writer(nf)      # `git checkout <arquivo>`: sobrescreve o arquivo
        return
    if sub == "reset":
        if any(x in ("--hard", "--merge", "--keep") for x in rv):
            _deny(4, verbo, "git reset --hard/--merge/--keep reescreve arquivos da árvore", seg)
        return
    if sub == "stash":
        if rv and rv[0] in ("list", "show"):
            return
        _deny(4, verbo, "git stash (push/pop/apply) reescreve arquivos da árvore", seg)
    if sub == "config":
        leitura = ("--get", "--get-all", "--get-regexp", "--list", "-l",
                   "--get-urlmatch", "--show-origin", "--show-scope", "--name-only")
        nf = _nonflags(rest, ("--file", "-f", "--blob", "--type"))
        if any(x in leitura for x in rv) or len(nf) <= 1:
            return
        _deny(4, verbo, "git config que grava (core.hooksPath, alias, pager executam "
                        "comandos)", seg)
    if sub == "remote":
        nf = _nonflags(rest)
        if not nf or nf[0].value in ("show", "get-url"):
            return
        _deny(4, verbo, "git remote que grava", seg)
    if sub == "reflog":
        if not rv or rv[0] in ("show",) or _is_flag(rv[0]):
            return
        _deny(4, verbo, "git reflog expire/delete", seg)
    if sub == "submodule":
        if rv and rv[0] in ("status", "summary"):
            return
        _deny(4, verbo, "git submodule que grava ou executa (foreach)", seg)
    if sub == "worktree":
        acao = rv[0] if rv else ""
        if acao in ("list", "prune", "lock", "unlock", "repair", "remove"):
            return
        if acao == "add":
            nf = _nonflags(rest[1:], ("-b", "-B", "--reason"))
            if not nf:
                _deny(4, verbo, "git worktree add sem caminho", seg)
            dest = nf[0]
            if not dest.known:
                _deny(4, verbo, f"git worktree add num caminho que não sei avaliar "
                                f"({dest.raw})", seg)
            if any(_inside(p, ctx.root) for p in _resolve_all(dest.value, cw)):
                _deny(4, verbo, "git worktree add DENTRO da raiz duplica o código na "
                                "árvore — crie fora: D=$(mktemp -d) && git worktree "
                                "add --detach \"$D/red\" HEAD", seg)
            ctx.events.append(("perturb_worktree_created", {}))
            return
        _deny(4, verbo, f"git worktree {acao}", seg)
    _deny(4, verbo, f"`git {sub}` reescreve arquivos da árvore ou não está na lista "
                    f"de subcomandos inocentes", seg)


def _h_decl(ctx, verbo, args, cwds, seg):
    """export / declare / local / typeset / readonly: atribuições que persistem."""
    for a in args:
        m = _ASSIGN_RE.match(a.raw)
        if not m:
            continue
        _check_env_assign(m.group(1), a, seg)
        ctx.vars[m.group(1)] = _expand(ctx, m.group(3), cwds).value if \
            _expand(ctx, m.group(3), cwds).known else None


def _check_env_assign(name, arg, seg):
    if name in _DANGEROUS_ENV or name.startswith(_DANGEROUS_ENV_PREFIX):
        _deny(4, name, f"`{name}=` faz um verbo inocente executar outro programa "
                       f"(pager, editor, diff externo, PATH, pré-carga)", seg)
    if name in _JVM_OPTS_ENV and (not arg.known or any(
            x in arg.value for x in ("-javaagent", "-agentpath", "-agentlib"))):
        _deny(4, name, f"`{name}` com agente JVM executa código arbitrário", seg)


_HANDLERS = {
    "sed": _h_sed, "gsed": _h_sed,
    "awk": _h_awk, "gawk": _h_awk, "nawk": _h_awk, "mawk": _h_awk,
    "find": _h_find,
    "rg": _h_flagdeny({"--pre"}, ("--pre=",)),
    "fd": _h_flagdeny({"-x", "--exec", "-X", "--exec-batch"}),
    "yq": _h_flagdeny({"-i", "--inplace"}),
    "sort": _h_output_flag(("-o", "--output")),
    "tree": _h_output_flag(("-o",)),
    "base64": _h_output_flag(("-o", "--output")),
    "uniq": _h_second_operand, "xxd": _h_second_operand,
    "mktemp": _h_mktemp,
    "curl": _h_curl, "wget": _h_wget,
    "tar": _h_archive_readonly(set()),
    "unzip": _h_archive_readonly({"-l", "-Z", "-t", "-v"}),
    "gzip": _h_archive_readonly({"-c", "-l", "-t", "--stdout", "--list", "--test"}),
    "gunzip": _h_archive_readonly({"-c", "-l", "-t", "--stdout", "--list", "--test"}),
    "bzip2": _h_archive_readonly({"-c", "-t", "--stdout", "--test"}),
    "xz": _h_archive_readonly({"-c", "-l", "-t", "--stdout", "--list", "--test"}),
    "time": _h_wrapper, "nohup": _h_wrapper, "nice": _h_wrapper,
    "timeout": _h_wrapper, "gtimeout": _h_wrapper, "stdbuf": _h_wrapper,
    "command": _h_wrapper,
    "env": _h_env, "xargs": _h_xargs,
    "python": _h_python, "python3": _h_python,
    "node": _h_node,
    "bash": _h_shell, "sh": _h_shell, "zsh": _h_shell, "dash": _h_shell, "ksh": _h_shell,
    "source": _h_source, ".": _h_source,
    "mvn": _h_mvn, "gradle": _h_gradle, "make": _h_make, "gmake": _h_make,
    "npm": _h_pm, "pnpm": _h_pm, "yarn": _h_pm,
    "npx": _h_npx,
    "jest": _h_js_tool, "vitest": _h_js_tool, "mocha": _h_js_tool, "tsc": _h_js_tool,
    "eslint": _h_js_tool, "prettier": _h_js_tool, "playwright": _h_js_tool,
    "pytest": _h_gradle, "py.test": _h_gradle,
    "pip": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "pip3": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "ruff": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "black": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "isort": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "coverage": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "mypy": _h_gradle, "flake8": _h_gradle, "pylint": _h_gradle,
    "go": _h_sub_allow({"test", "vet", "list", "version", "env", "build", "doc", "help"}),
    "cargo": _h_sub_allow({"test", "build", "check", "clippy", "doc", "tree",
                           "metadata", "bench"}, ("--fix",)),
    "dotnet": _h_sub_allow({"test", "build", "restore", "--info", "--list-sdks",
                            "--list-runtimes"}),
    "java": _h_java,
    "docker": _h_docker, "docker-compose": _h_docker, "podman": _h_docker,
    "gh": _h_gh,
    "git": _h_git,
    "export": _h_decl, "declare": _h_decl, "local": _h_decl, "typeset": _h_decl,
    "readonly": _h_decl,
}
for _w in _WRITERS:
    _HANDLERS[_w] = _h_writer


def _dispatch(ctx, args, cwds, seg):
    """Classifica um argv já expandido: balde 1, 2 ou 4."""
    assigns = []
    while args and args[0].raw in _LEADING_KEYWORDS:
        args = args[1:]
    while args:
        m = _ASSIGN_RE.match(args[0].raw)
        if not m:
            break
        _check_env_assign(m.group(1), _expand(ctx, m.group(3), cwds), seg)
        assigns.append((m.group(1), m.group(3)))
        args = args[1:]
    if not args:
        # atribuição pura: persiste para os próximos segmentos
        for nome, bruto in assigns:
            e = _expand(ctx, bruto, cwds)
            ctx.vars[nome] = e.value if e.known else None
        return
    va = args[0]
    rest = args[1:]
    if not va.known:
        _deny(4, va.raw, f"o verbo vem de variável ou substituição que não sei "
                         f"avaliar ({va.raw})", seg)
    v = va.value
    if "/" in v:
        d, b = os.path.split(v)
        if d in _SYSTEM_BIN_DIRS:
            v = b
        else:
            _script_rule(ctx, va, cwds, b, seg)
            if b == "mvnw":
                _mvn_args(ctx, b, rest, seg)
            elif b == "gradlew":
                _no_hidden_flags(rest, b, seg)
            return
    if re.match(r"^python[0-9.]*$", v):
        v = "python3"
    if v in _SIMPLE:
        return
    h = _HANDLERS.get(v)
    if h:
        h(ctx, v, rest, cwds, seg)
        return
    _deny(4, v, f"`{v}` não está na lista de verbos inocentes", seg)


def _sub_value(ctx, inner, cwds):
    """O valor de uma substituição, quando dá para saber sem executá-la."""
    try:
        argv = shlex.split(inner.strip(), posix=True)
    except ValueError:
        return None
    if not argv:
        return None
    v = argv[0]
    if v == "mktemp":
        nf = [x for x in argv[1:] if not _is_flag(x)]
        for k, x in enumerate(argv):
            if x in ("-p", "--tmpdir") and k + 1 < len(argv):
                return os.path.join(argv[k + 1], "cepa-mktemp")
        if nf:
            return str(_resolve_all(nf[0], cwds)[0])
        return os.path.join(tempfile.gettempdir(), "cepa-mktemp")
    if v == "pwd" and len(cwds) == 1:
        return str(next(iter(cwds)))
    if v == "git" and "--show-toplevel" in argv and len(cwds) == 1:
        c = next(iter(cwds))
        return str(ctx.root) if _inside(c, ctx.root) else None
    # `$(echo palavra)`: só um literal único, que não começa com `-` e não se
    # parte em palavras. Sem isso, `sed $(printf -- -i) ...` escondia o `-i`.
    if v in ("echo", "printf") and len(argv) == 2 and not argv[1].startswith("-") \
            and not re.search(r"[\s*?\[\\%$`]", argv[1]):
        return argv[1]
    return None


def _classify(ctx, command, cwds, depth=0):
    """Classifica a linha inteira; levanta _Negado no primeiro problema."""
    if depth > _MAX_DEPTH:
        _deny(4, "", "substituições aninhadas demais para analisar", command[:120])
    flat, subs, orfas = _flatten(command)
    base = ctx.sub_base
    ctx.sub_base += len(subs) + 1
    # as marcas são locais a esta chamada: renumera para não colidir com a de fora
    flat = _SUB_MARK_RE.sub(lambda m: _SUB_MARK.format(base + int(m.group(1))), flat)
    done = set()

    def run_sub(idx, where):
        if idx in done:
            return
        done.add(idx)
        salvo = dict(ctx.vars)
        try:
            _guard(ctx, lambda: _classify(ctx, subs[idx], where, depth + 1))
        finally:
            ctx.vars = salvo
        ctx.sub_values[base + idx] = _sub_value(ctx, subs[idx], where)

    state_in = frozenset(cwds)
    history = set(state_in)
    prev = None
    stack = []
    for sep, seg in _split_with_seps(flat):
        if prev is not None:
            p_in, p_ok, p_fail = prev
            if sep == "&&":
                state_in = p_ok
            elif sep in ("|", "&"):
                state_in = p_in
            else:
                state_in = frozenset(history | p_ok | p_fail)
        text = seg.strip()
        if not text:
            prev = (state_in, state_in, state_in)
            continue
        while text.startswith("(") and not text.startswith("(("):
            stack.append(state_in)
            text = text[1:].lstrip()
        m = _quoted_mask(text)
        abre = sum(1 for c, q in zip(text, m) if c == "(" and not q)
        fecha = sum(1 for c, q in zip(text, m) if c == ")" and not q)
        pops = max(0, fecha - abre)
        for _ in range(pops):
            text = text.rstrip()
            if text.endswith(")"):
                text = text[:-1]
        for sm in _SUB_MARK_RE.finditer(text):
            run_sub(int(sm.group(1)) - base, state_in)
        ok = fail = state_in
        if text.strip() and not text.startswith("(("):
            res = _guard(ctx, lambda: _classify_segment(ctx, text.strip(), state_in))
            if res is not None:
                ok, fail = res
        for _ in range(pops):
            ok = fail = stack.pop() if stack else frozenset(cwds)
        history |= ok | fail | state_in
        prev = (state_in, ok, fail)
    for idx in orfas:
        run_sub(idx, frozenset(cwds))
    for idx in range(len(subs)):
        run_sub(idx, frozenset(cwds))


def _guard(ctx, fn):
    """Em modo sombra, o balde 4 anota em vez de negar — e a análise segue."""
    try:
        return fn()
    except _Negado as n:
        if ctx.shadow and n.balde == 4:
            ctx.would.append(n)
            return None
        raise


def _classify_segment(ctx, text, cwds):
    """Um segmento. Devolve (cwds se deu certo, cwds se falhou)."""
    mask = _quoted_mask(text)
    redirs = []
    for rx in (_REDIR_RE, _EXTRA_REDIR_RE):
        for m in rx.finditer(text):
            if not mask[m.start()]:
                redirs.append(_expand(ctx, _unquote(m.group(1)), cwds))
    sem = _strip_redirections(text, mask)
    try:
        argv = shlex.split(sem, posix=True)
    except ValueError:
        _deny(4, "", "não consegui ler a linha (aspas desbalanceadas?)", text)
    args = [_expand(ctx, t, cwds) for t in argv]
    while args and args[0].raw in _LEADING_KEYWORDS:
        args = args[1:]

    # cd / pushd / popd mudam onde os PRÓXIMOS segmentos rodam
    if args and args[0].raw in ("cd", "pushd", "popd"):
        verbo = args[0].raw
        _check_targets(ctx, redirs, cwds, verbo, text)
        if verbo == "popd":
            return frozenset(set(cwds) | {ctx.root}), frozenset(cwds)
        nf = _nonflags(args[1:])
        if not nf:
            destino = {Path.home().resolve()}
        elif not nf[0].known or nf[0].value == "-":
            destino = {ctx.root}   # não sei para onde foi: trato como a raiz
        else:
            destino = set(_resolve_all(nf[0].value, cwds))
        return frozenset(destino), frozenset(cwds)

    # balde 3 — tudo fora da raiz, e a linha não cita a raiz
    if all(not _inside(c, ctx.root) for c in cwds) and not _refs_root(
            ctx, text, args + redirs, cwds):
        if args and _ASSIGN_RE.match(args[0].raw) and all(
                _ASSIGN_RE.match(a.raw) for a in args):
            for a in args:
                mm = _ASSIGN_RE.match(a.raw)
                e = _expand(ctx, mm.group(3), cwds)
                ctx.vars[mm.group(1)] = e.value if e.known else None
        return cwds, cwds

    # balde 1 — redirecionamentos
    verbo = args[0].value if args and args[0].known else "?"
    _check_targets(ctx, redirs, cwds, verbo, text)
    if args:
        _dispatch(ctx, args, cwds, text)
    return cwds, cwds


# ─── telemetria (espelho mínimo de common/hooks/_telemetry.py) ─────────────

def _t_emit(event: str, cwd: str = None, **fields) -> None:
    """Espelho mínimo de common/hooks/_telemetry.py (import cross-plugin é
    frágil entre diretórios de cache versionados). Estritamente fail-silent."""
    try:
        import subprocess
        from datetime import datetime, timezone
        repo = ""
        try:
            out = subprocess.run(
                ["git", "-C", cwd or os.getcwd(), "rev-parse",
                 "--path-format=absolute", "--git-common-dir"],
                capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                common = out.stdout.strip()
                repo = Path(common).parent.name if common.endswith("/.git") else Path(common).name
            else:
                repo = Path(cwd or os.getcwd()).name
        except Exception:
            pass
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "event": event, "repo": repo, "topology": PLUGIN_NAME}
        for k, v in fields.items():
            entry[k] = v[:200] if isinstance(v, str) else v
        tdir = Path(os.environ.get("CEPA_TELEMETRY_DIR") or
                    (Path.home() / ".claude" / "cepa-telemetry"))
        tdir.mkdir(parents=True, exist_ok=True)
        with open(tdir / f"events-{entry['ts'][:7]}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _cmd_hash(command: str) -> str:
    import hashlib
    return hashlib.blake2b(command.encode("utf-8", "replace"), digest_size=6).hexdigest()


_BALDE_NOME = {
    1: "balde 1 — escrita fora da sua pista",
    4: "balde 4 — fora da lista de comandos inocentes",
}


def _mensagem(n, agent, command, allowed):
    globs = "\n      - ".join(allowed or ["(nenhum — só o seu arquivo de expertise)"])
    linhas = [
        f"[design bash-path-lock] NEGADO ({_BALDE_NOME.get(n.balde, n.balde)}): "
        f"agente {agent!r}.",
        f"  Motivo: {n.motivo}",
    ]
    if n.alvos:
        linhas.append(f"  Alvo(s) fora da pista: {', '.join(n.alvos)}")
    if n.segmento and n.segmento.strip() != command.strip():
        linhas.append(f"  Trecho: {n.segmento.strip()[:200]}")
    linhas += [
        f"  Comando: {command[:300]}",
        "",
        "  Este cadeado só deixa passar o que é comprovadamente inofensivo: escrita",
        "  com alvo visível dentro da sua pista, verbo da lista de inocentes, ou",
        "  comando rodando FORA da raiz do projeto. Código inline (python3 -c,",
        "  node -e, bash -c, heredoc para interpretador) é escrita arbitrária.",
        "  Escrever artefatos por Bash para contornar o path-lock é bypass de delegação.",
        "",
        "  O que fazer em vez disso:",
        f"    - escrever nos SEUS caminhos: use Write/Edit (o path-lock governa). Globs:",
        f"      - {globs}",
        "    - escrever fora da sua pista: delegue ao worker dono do caminho;",
        "    - provar RED revertendo código: worktree descartável FORA da raiz",
        "      (lá o cadeado não tem jurisdição, e a reversão nunca vaza para o diff):",
        "        D=$(mktemp -d) && git worktree add --detach \"$D/red\" HEAD && "
        "cd \"$D/red\" && <reverta e rode o teste>",
        "        git worktree remove --force \"$D/red\"",
        "    - verbo legítimo que faltou na lista: diga no seu relatório — quem",
        "      decide incluir é o humano, nunca o agente bloqueado.",
        "",
        "  A negação foi registrada no ledger de telemetria. Contornar depois de",
        "  negado não é esperteza: é violação auditada.",
    ]
    texto = "\n".join(linhas)
    # as marcas internas da leitura da linha voltam à forma que o agente escreveu
    texto = _SUB_MARK_RE.sub("$(…)", texto).replace(_HEREDOC_MARK, "<<…")
    return texto.replace("__CEPAARITH__", "$((…))")


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[design bash-path-lock] could not parse hook payload; allowing",
              file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name", "") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command.strip():
        sys.exit(0)

    # Only act on THIS plugin's subagents. No prefix → main session or a
    # built-in agent → not ours. Same fail-open contract as path-lock.py.
    raw_agent_type = payload.get("agent_type", "") or ""
    if ":" not in raw_agent_type or raw_agent_type.split(":", 1)[0] != PLUGIN_NAME:
        sys.exit(0)

    pl = _load_pathlock_module()
    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()
    agent = pl.detect_agent(payload)
    allowed = pl.ALLOWED_WRITES.get(agent)

    shadow = os.environ.get(_ENFORCE_ENV, "1").strip() == "0"
    ctx = _Ctx(project_root, agent, allowed, pl, shadow)
    cwd_s = str(project_root)
    try:
        try:
            _classify(ctx, command, [project_root])
        except _Negado:
            raise
        except Exception as e:  # noqa: BLE001
            # Defeito do próprio classificador. Liberar calado seria a falha
            # silenciosa que esta camada existe para matar; negar é barulhento
            # e aparece no ledger. No modo sombra, só registra.
            if shadow:
                _t_emit("bash_pathlock_would_deny", cwd=cwd_s, agent=agent, bucket=0,
                        verb="?", cmd_hash=_cmd_hash(command), erro=type(e).__name__)
                sys.exit(0)
            raise _Negado(4, "?", f"erro interno do classificador ({type(e).__name__}: "
                                  f"{e}) — relate este comando no seu relatório", command)
    except _Negado as n:
        _t_emit("bash_pathlock_deny", cwd=cwd_s, agent=agent, bucket=n.balde,
                verb=n.verbo, cmd_hash=_cmd_hash(command),
                card=os.environ.get("CLAUDE_AUTONOMOUS_RUN_ID", ""))
        print(_mensagem(n, agent, command, allowed), file=sys.stderr)
        sys.exit(2)

    for n in ctx.would:
        _t_emit("bash_pathlock_would_deny", cwd=cwd_s, agent=agent, bucket=n.balde,
                verb=n.verbo, cmd_hash=_cmd_hash(command))
    for ev, campos in ctx.events:
        _t_emit(ev, cwd=cwd_s, agent=agent, **campos)
    sys.exit(0)


if __name__ == "__main__":
    main()
