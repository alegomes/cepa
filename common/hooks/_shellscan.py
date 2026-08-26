#!/usr/bin/env python3
"""_shellscan — o motor de leitura de linha de comando compartilhado do common.

## Por que existe

Dois hooks do `common` analisam comando Bash para decidir se barram: o
`enforcement-guard.py` (nenhum subagente escreve em `plugins/`, `hooks/` ou
`settings.json`) e o `maven-reactor-guard.py` (nenhum build de reator parcial
sem `-am`). Os dois tinham cópia manual do mesmo motor de parsing, copiada do
`bash-path-lock.py`, e essa duplicação silenciosa já custou caro:

- o falso-positivo do `>=` (o `>` do operador de comparação lido como
  redirecionamento) foi consertado nas 5 cópias do `bash-path-lock` em
  11/06/2026 e **sobreviveu 2 meses** no `enforcement-guard`, porque o detector
  de divergência entre cópias (`tests/test_lock_copies_drift.py`) e o gerador
  (`bin/gen-locks.py`) só conheciam aquelas 5;
- o mesmo aconteceu com o commit de várias linhas (22/08/2026, WEGO-2087): o
  buraco estava em 7 hooks e o radar cobria 5.

Aqui os dois guards importam em vez de copiar. As 5 cópias do
`bash-path-lock.py` continuam geradas do molde — elas vivem em outros plugins e
não podem importar do `common`. Sobram, então, **duas** fontes do motor em vez
de sete, e `tests/test_lock_copies_drift.py` compara as duas por árvore
sintática.

Uso, seguindo o padrão dos outros helpers privados desta pasta:

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _shellscan as S
"""

import os
import re
import shlex

# Redirection: `>` or `>>`, NOT preceded by a digit or `&` (excludes `2>`,
# `&>`, `1>&2`), and the target must not start with `&` (excludes `>&1`) or `=`
# (excludes the `>=` comparison operator — `>` immediately followed by `=` is
# never a redirect; without this, `sed -i 's/>=/>/'`, `grep '>='`, and
# `[[ $a >= $b ]]` capture junk targets and get falsely blocked).
_REDIR_RE = re.compile(r"""(?<![0-9&])>>?\s*(?![&=])("[^"]+"|'[^']+'|[^\s;&|<>()]+)""")

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
    """
    mask = [False] * len(s)
    quote = None
    i = 0
    while i < len(s):
        c = s[i]
        if quote is None:
            if c == "\\":
                mask[i] = True
                if i + 1 < len(s):
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
            if i + 1 < len(s):
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


# ─────────────────────────────────────────────────────────────────────────────
# Extração de ALVOS DE ESCRITA — o degrau acima do parsing.
#
# Portado verbatim do `bash-path-lock.py` do build-hex em 26/08/2026, quando o
# `modo-escrita-gate` precisou da mesma pergunta que os locks já respondiam:
# "que arquivos esta linha de comando ESCREVE?". A cópia que existia no
# `enforcement-guard.py` já havia divergido em silêncio — ela não conhece
# `git mv` nem conta a ORIGEM de um `mv` como escrita, então um agente move um
# arquivo para fora da pista e o guard vê só o destino. Copiar uma terceira vez
# seria repetir a doença que este módulo trata; `tests/test_lock_copies_drift.py`
# compara estas duas funções entre as duas fontes do motor.
# ─────────────────────────────────────────────────────────────────────────────

# Constructs we cannot statically analyze — fail open but log.
_UNCOVERED_RE = re.compile(
    r"""(?:
        \bpython3?\s+-c\b | \bperl\s+-[eE]\b | \bruby\s+-e\b | \bnode\s+-e\b |
        \bawk\b[^|;&]*\b-i\b | \b-i\s+inplace\b | \bgawk\b[^|;&]*\binplace\b |
        \bed\b | \bpatch\b | <<-?\s*['"]?\w+   # heredoc
    )""",
    re.VERBOSE,
)


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
