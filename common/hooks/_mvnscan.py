#!/usr/bin/env python3
"""_mvnscan — leitura de invocação Maven compartilhada entre
`maven-reactor-guard.py` e `capture-build-result.py`.

WHY THIS EXISTS
----------------
O primeiro parsing de argv do Maven (reconhecer `mvn`/`mvnw` atrás de prefixo
de env e wrapper, distinguir invocação real de texto citado em `echo`/`grep`)
nasceu dentro do `maven-reactor-guard.py` para responder só "tem `-pl` sem
`-am`?" (WEGO-1949). Em 2026-09-27 o guard passou a precisar também dos GOALS
da invocação (liberar quando nenhum goal compila) e o `capture-build-result.py`
passou a precisar da mesma pergunta sobre outro comando (rodou `install` sobre
o reator inteiro, sem `-pl`?). Copiar o parsing pela segunda vez repetiria o
que `_shellscan.py` documenta ter custado caro: divergência silenciosa entre
cópias do mesmo motor. Os dois hooks importam daqui.
"""

import os
import re
import shlex

MAVEN_BIN = {"mvn", "mvnw", "mvnw.cmd"}
# Envoltórios que só prefixam o comando real.
WRAPPERS = {"timeout", "nice", "env", "time", "exec", "sudo", "stdbuf", "caffeinate"}
# Comandos que tratam o resto da linha como texto, nunca execução.
TEXT_CMDS = {"echo", "printf", "cat", "grep", "rg", "sed", "awk", "less", "head", "tail"}

PL_FLAGS = ("-pl", "--projects")
AM_FLAGS = {"-am", "--also-make"}
RF_FLAGS = ("-rf", "--resume-from")
FILE_FLAGS = ("-f", "--file")

# Flags do Maven que consomem o TOKEN seguinte como valor, na forma separada
# por espaço (`-pl X`, `-f X`...). `-D` fica de fora de propósito: é sempre
# colada (`-Dk=v`), nunca `-D k=v` — não há valor separado para pular.
VALUE_FLAGS = {
    "-pl", "--projects", "-f", "--file", "-s", "--settings",
    "-P", "--activate-profiles", "-T", "--threads", "-rf", "--resume-from",
}

# Redirecionamento de shell (`2>&1`, `>&2`, `2> arquivo`, `>> log`) que pode
# sobrar DENTRO de um segmento — `_split_segments` só separa em `;|&\n`, não
# em `>`. É o padrão mais comum nos comandos reais investigados
# (docs/investigations/2026-09-25-stale-e-reactor-no-wego.md, seção 2: "111
# `./mvnw -pl <M> test -Dtest=<X> 2>`"). Sem filtrar, um `2>&1` sobra como
# "goal" espúrio e faz a regra de "todo goal não compila" nunca liberar um
# `clean`/`dependency:tree` legítimo só porque a linha também redireciona.
_REDIR_TOKEN_RE = re.compile(r"^[0-9]*(?:>>?|<<?)")


def is_maven_token(tok: str) -> bool:
    return os.path.basename(tok) in MAVEN_BIN


def maven_args(segment: str):
    """Args do Maven se `segment` for uma invocação real, senão None.

    Aceita prefixo de env (`FOO=bar ./mvnw ...`) e wrapper conhecido
    (`timeout 600 mvn`). Rejeita o token Maven que apareça depois de qualquer
    outra coisa — é texto citado, não execução (`echo "./mvnw test -pl x"`).
    """
    try:
        argv = shlex.split(segment, posix=True)
    except ValueError:
        argv = segment.split()
    i, seen_wrapper = 0, False
    while i < len(argv):
        tok = argv[i]
        if is_maven_token(tok):
            return argv[i + 1:]
        base = os.path.basename(tok)
        if base in TEXT_CMDS:
            return None  # o resto da linha é texto citado, não execução
        if "=" in tok and not tok.startswith("-"):
            i += 1
            continue
        if base in WRAPPERS:
            seen_wrapper = True
            i += 1
            continue
        if tok.startswith("-") or seen_wrapper:
            i += 1
            continue
        return None  # qualquer outro comando: o Maven aqui é texto, não execução
    return None


def has_pl(args) -> bool:
    return any(a in PL_FLAGS or a.startswith(("-pl=", "--projects=")) for a in args)


def has_am(args) -> bool:
    # Igualdade exata de propósito: `-amd` / `--also-make-dependents` NÃO salva.
    return any(a in AM_FLAGS for a in args)


def has_resume_from(args) -> bool:
    """`-rf`/`--resume-from` retoma a partir de um módulo — o reator inteiro
    NÃO roda de novo desde o começo, então mesmo sem `-pl` isto não é um
    install completo da raiz (capture-build-result.py usa isto para não
    gravar o marcador de install fresco num `install -rf :bootstrap`)."""
    return any(a in RF_FLAGS or a.startswith(("-rf=", "--resume-from=")) for a in args)


def file_flag_target(args):
    """Valor passado a `-f`/`--file` (ou `-f=X`/`--file=X`); None se ausente.
    Maven aceita a flag repetida e a última vale — mesma regra aqui."""
    target = None
    i, n = 0, len(args)
    while i < n:
        tok = args[i]
        if tok in FILE_FLAGS:
            if i + 1 < n:
                target = args[i + 1]
            i += 2
            continue
        for flag in FILE_FLAGS:
            if tok.startswith(flag + "="):
                target = tok[len(flag) + 1:]
                break
        i += 1
    return target


def goals(args) -> list:
    """Os goals/fases desta invocação — os tokens que não são flag nem valor
    de flag nem redirecionamento de shell.

    Parsing: goal é todo argumento que não é flag; o valor de uma flag que
    toma valor separado (`-pl X`, `-f X`, `-s X`, `-P X`, `-T X`, `-rf X`,
    `--projects X`, `--file X`) é pulado junto com a flag; `-D` é sempre colada
    (`-Dk=v`) e nunca consome o token seguinte; `-e`/`-q`/`-B`/`-o`/`-U` e
    afins não tomam valor.
    """
    out = []
    i, n = 0, len(args)
    while i < n:
        tok = args[i]
        m = _REDIR_TOKEN_RE.match(tok)
        if m:
            self_contained = len(m.group()) < len(tok)
            i += 1
            if not self_contained and i < n and not args[i].startswith("-"):
                i += 1  # alvo do redirecionamento veio em token separado
            continue
        if tok.startswith("-"):
            if "=" in tok:
                i += 1
                continue
            if tok in VALUE_FLAGS:
                i += 2
                continue
            i += 1
            continue
        out.append(tok)
        i += 1
    return out
