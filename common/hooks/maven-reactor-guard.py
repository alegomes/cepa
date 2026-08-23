#!/usr/bin/env python3
"""PreToolUse hook (common) — `-pl <modulo>` sem `-am` mente. Bloqueia.

WHY THIS EXISTS
---------------
Rodar `./mvnw test -pl <modulo>` SEM `-am` faz o Maven resolver as dependências
entre módulos pelos jars já instalados no `~/.m2`, em vez de recompilar o
reator. Se o cache local estiver defasado, os testes rodam contra código ANTIGO
e produzem **vermelho falso**: falhas determinísticas, reproduzíveis e
completamente irreais.

Determinístico não é o mesmo que real. Repetir a execução só confirma o mesmo
defeito de ambiente — foi exatamente o que aconteceu no episódio de 2026-07-21
(WEGO-1949): 5 testes E2E fecharam vermelho de forma estável em `main`, foram
reproduzidos isoladamente (o que *reforçou* a leitura errada de "bug funcional"),
e a causa era um jar de 16/jul no `~/.m2` cujo `PlugSignAdapter` sequer tinha o
método `trocarSignatario`. Custou uma investigação inteira, gerou um card
acusando indevidamente uma feature entregue e quase produziu um "fix" para um
bug inexistente.

O padrão já estava documentado (README do repo, memória de projeto) e REINCIDIU
mesmo assim. Documentar não bastou — por isso a barreira é mecânica, e bloqueia
em vez de avisar.

ESCOPO — o hook só se mete quando os três valem:
  1. o comando invoca de fato o Maven (`mvn` / `mvnw` / `./mvnw`), não é uma
     string dentro de um `echo`/`grep`;
  2. passa `-pl` / `--projects` e NÃO passa `-am` / `--also-make`
     (`-amd` / `--also-make-dependents` NÃO conta: constrói os dependentes,
     não as dependências — o buraco continua aberto);
  3. o cwd é a raiz de um reator multi-módulo (`<modules>` no pom.xml). Repo
     de módulo único não tem o problema e nunca é bloqueado.

ESCAPE HATCH: incluir `stale-ok` no comando (tipicamente como comentário,
`# stale-ok`) libera a execução. Use quando você ACABOU de instalar o reator
(`./mvnw install -DskipTests`) e sabe que o `~/.m2` está fresco. Usar por
reflexo para se livrar do bloqueio devolve o vermelho falso.

Exit codes:
  0 — liberado (não é Maven, tem -am, repo single-module, ou escape hatch)
  2 — bloqueado: `-pl` sem `-am` num reator multi-módulo
"""

import json
import os
import shlex
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _telemetry as T
except Exception:  # telemetria nunca pode quebrar o gate

    class T:  # type: ignore
        @staticmethod
        def emit(*a, **k):
            pass


# O motor de leitura da linha de comando — máscara de aspas e quebra em
# segmentos — vive em _shellscan.py e é COMPARTILHADO com o enforcement-guard.
# Era cópia manual até 23/08/2026, e a cópia atrasou consertos: quebrar em `\n`
# sem olhar aspas fazia cada linha do corpo de uma mensagem de commit virar um
# "segmento", e uma linha começando com `./mvnw -pl core` era acusada de reator
# parcial (22/08/2026, WEGO-2087). O sys.path já foi ajustado acima.
import _shellscan as S  # noqa: E402

_split_segments = S._split_segments

_MAVEN_BIN = {"mvn", "mvnw", "mvnw.cmd"}
# Envoltórios que só prefixam o comando real — o Maven depois deles ainda é
# uma invocação de verdade. `echo`/`grep`/`cat` deliberadamente FORA da lista.
_WRAPPERS = {"timeout", "nice", "env", "time", "exec", "sudo", "stdbuf", "caffeinate"}
# Comandos que TRATAM o resto como texto. Um `mvn` depois deles é string citada,
# nunca execução — mesmo aninhado num wrapper (`timeout 5 echo './mvnw -pl x'`).
_TEXT_CMDS = {"echo", "printf", "cat", "grep", "rg", "sed", "awk", "less", "head", "tail"}
_PL_FLAGS = ("-pl", "--projects")
_AM_FLAGS = {"-am", "--also-make"}
_ESCAPE = "stale-ok"


def _is_maven_token(tok: str) -> bool:
    return os.path.basename(tok) in _MAVEN_BIN


def _maven_args(segment: str):
    """Args do Maven se `segment` for uma invocação real, senão None.

    Aceita prefixos de env (`FOO=bar ./mvnw ...`) e wrappers (`timeout 600 mvn`),
    porque ambos aparecem em comandos legítimos do projeto. Rejeita o token
    Maven que apareça depois de qualquer outra coisa — é texto citado, não
    execução (`echo "./mvnw test -pl x"`).
    """
    try:
        argv = shlex.split(segment, posix=True)
    except ValueError:
        argv = segment.split()
    i, seen_wrapper = 0, False
    while i < len(argv):
        tok = argv[i]
        if _is_maven_token(tok):
            return argv[i + 1 :]
        base = os.path.basename(tok)
        if base in _TEXT_CMDS:
            return None  # o resto da linha é texto citado, não execução
        # prefixo tolerado: atribuição de env, wrapper conhecido, ou flag dele
        if "=" in tok and not tok.startswith("-"):
            i += 1
            continue
        if base in _WRAPPERS:
            seen_wrapper = True
            i += 1
            continue
        if tok.startswith("-") or seen_wrapper:
            # flags, e os argumentos do wrapper (`timeout 600 ./mvnw ...`)
            i += 1
            continue
        return None  # qualquer outro comando: o Maven aqui é texto, não execução
    return None


def _has_pl(args) -> bool:
    return any(a in _PL_FLAGS or a.startswith(("-pl=", "--projects=")) for a in args)


def _has_am(args) -> bool:
    # Igualdade exata de propósito: `-amd` / `--also-make-dependents` NÃO salva.
    return any(a in _AM_FLAGS for a in args)


def is_multi_module(root: Path) -> bool:
    pom = root / "pom.xml"
    try:
        return "<modules>" in pom.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False  # sem pom legível: fail open


def offending_segment(command: str):
    for seg in _split_segments(command):
        seg = seg.strip()
        if not seg:
            continue
        args = _maven_args(seg)
        if args is None:
            continue
        if _has_pl(args) and not _has_am(args):
            return seg
    return None


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[maven-reactor-guard] payload ilegível; liberando", file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "") or ""
    if not command or _ESCAPE in command:
        sys.exit(0)

    cwd = Path(payload.get("cwd") or os.getcwd())
    if not is_multi_module(cwd):
        sys.exit(0)

    seg = offending_segment(command)
    if not seg:
        sys.exit(0)

    T.emit("maven_reactor_block", cwd=str(cwd), reason="pl-without-am", segment=seg)
    print(
        "[maven-reactor-guard] BLOQUEADO: `-pl` sem `-am` num reator multi-módulo.\n"
        f"  Comando: {seg}\n\n"
        "  Sem `-am`, o Maven NÃO recompila os módulos dos quais este depende — ele\n"
        "  usa os jars já instalados no ~/.m2. Se estiverem defasados, os testes rodam\n"
        "  contra código antigo e o vermelho é FALSO: determinístico, reproduzível e\n"
        "  irreal. Repetir a execução só confirma o mesmo defeito de ambiente.\n\n"
        "  Faça uma destas:\n"
        "    1. acrescente `-am`            → recompila as dependências no reator;\n"
        "    2. rode da raiz (`./mvnw verify`) → veredito confiável, ~15 min;\n"
        "    3. se o ~/.m2 está comprovadamente fresco (você ACABOU de rodar\n"
        "       `./mvnw install -DskipTests`), acrescente `# stale-ok` ao comando.\n\n"
        "  A opção 3 é uma afirmação sua de que o cache está em dia. Usá-la por\n"
        "  reflexo, só para passar pelo bloqueio, devolve exatamente o vermelho falso\n"
        "  que este guard existe para impedir (WEGO-1949, 2026-07-21).",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
