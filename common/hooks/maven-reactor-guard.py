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

LIBERAÇÕES AUTOMÁTICAS (2026-09-27) — investigação
docs/investigations/2026-09-25-stale-e-reactor-no-wego.md, seção 5: no
wego-acesso-backend, 61,9% dos bloqueios foram retentados com `# stale-ok`
depois de um `install` que já tinha rodado — o guard cobrava uma afirmação que
o próprio histórico do comando já provava. Três liberações, tudo o resto
inalterado:

  1. **Nenhum goal do segmento compila.** Fases de lifecycle `pre-clean`,
     `clean`, `post-clean`, `validate`, `initialize`, e goals de plugin com
     prefixo `dependency:`/`help:` nunca produzem classe nova — não há
     vermelho falso possível. `install` DELIBERADAMENTE não entra nesta
     lista: `-pl domain install` compila `domain` contra o `~/.m2`, e uma
     dependência interna desatualizada ali É o vermelho falso que o guard
     existe para pegar. Qualquer goal fora da lista (compile, test, verify,
     package, install, `quarkus:*`, `exec:*`, desconhecido) conta como
     "compila", e um único goal que compila no segmento cancela a liberação.
     Comando ENCADEADO (`./mvnw -pl a clean && ./mvnw -pl b test`) pode ter
     mais de um segmento ofensor (`-pl` sem `-am`): o guard escolhe o primeiro
     que COMPILA para aplicar as regras 2/3 e a mensagem de bloqueio — só
     libera de fato quando TODOS os ofensores não compilam (bug reproduzido
     pelo pair-reviewer em 2026-09-27: olhar só o primeiro segmento deixava
     um `-pl b test` passar escondido atrás de um `-pl a clean` inofensivo).

  2. **`-pl` sem `-am` depois de um `install` fresco da raiz.** Amostrei 366
     transcritos com bloqueio no wego-acesso-backend: 187 tinham um `install`
     da raiz bem-sucedido DEPOIS da última edição de fonte (inocente — o
     `~/.m2` já estava em dia), 143 tinham edição de fonte DEPOIS do último
     install (o bloqueio protegia de verdade), 36 não tinham install nenhum.
     Então a liberação compara CARIMBOS DE TEMPO, não só "houve um install
     alguma vez": `capture-build-result.py` grava
     `.claude/last-root-install.json` (`{"at": ..., "command": ...}`) toda vez
     que um Maven SUCCESS roda `install` sem `-pl` sobre o reator inteiro; este
     guard libera quando esse arquivo existe na raiz da sessão
     (`_wtlib.session_root`) E nenhum arquivo-fonte do reator (mesmo critério
     de `mark-build-stale.is_source`, compartilhado via `_buildsource.py`) tem
     mtime posterior ao `at` gravado. Fail closed: arquivo ausente, ilegível
     ou com timestamp incoerente mantém o bloqueio de hoje.
     LIMITAÇÃO CONHECIDA: o `~/.m2` é compartilhado entre worktrees do mesmo
     repo; um `install` rodado em OUTRA worktree depois da nossa última
     edição não é visto por este guard — mesma cegueira que `stale-ok` já
     tinha (é uma afirmação sobre O QUE VOCÊ SABE, não sobre o disco inteiro).

  3. **`quarkus:*` nunca ganha a sugestão de `-am`.** BACKLOG "maven-reactor-guard
     barra o `quarkus:dev`": o plugin do Quarkus está declarado só no módulo
     alvo, e `-am` recompila o reator inteiro incluindo módulos sem o plugin —
     `./mvnw -pl bootstrap -am quarkus:help` falha com "No plugin found for
     prefix 'quarkus'", enquanto sem `-am` funciona. Um segmento com goal
     `quarkus:*` é liberado pela regra 2 (install fresco) como qualquer outro;
     sem isso, o bloqueio troca a orientação — nunca `-am` — por "instale a
     raiz e repita o MESMO comando sem `-am`".

Exit codes:
  0 — liberado (não é Maven, tem -am, repo single-module, escape hatch, goals
      que não compilam, ou install fresco da raiz)
  2 — bloqueado: `-pl` sem `-am` num reator multi-módulo (genérico, ou
      quarkus-específico quando o segmento roda um goal `quarkus:*`)
"""

import json
import os
import sys
from datetime import datetime
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
import _mvnscan as M  # noqa: E402
import _buildsource as B  # noqa: E402
import _wtlib as L  # noqa: E402

_split_segments = S._split_segments

# O parsing de argv do Maven (reconhecer `mvn`/`mvnw` atrás de env/wrapper,
# extrair goals, achar `-pl`/`-am`) mora em _mvnscan.py — compartilhado com
# capture-build-result.py, que precisa da mesma pergunta sobre outro comando
# (rodou `install` sobre o reator inteiro?). Ver docstring de _mvnscan.py.
_maven_args = M.maven_args
_has_pl = M.has_pl
_has_am = M.has_am
_ESCAPE = "stale-ok"

# Regra 1 (liberação automática): fases de lifecycle e prefixos de goal que
# NUNCA compilam nada — não há vermelho falso possível rodando só isto contra
# um ~/.m2 defasado. `install` fica deliberadamente FORA: `-pl domain install`
# compila `domain` contra o que já está no `~/.m2`, e é exatamente aí que uma
# dependência interna desatualizada produz o vermelho falso (WEGO-1949).
_NONCOMPILING_PHASES = {"pre-clean", "clean", "post-clean", "validate", "initialize"}
_NONCOMPILING_PREFIXES = ("dependency:", "help:")


def _is_noncompiling_goal(goal: str) -> bool:
    return goal in _NONCOMPILING_PHASES or goal.startswith(_NONCOMPILING_PREFIXES)


def _all_goals_noncompiling(args) -> bool:
    """True só quando HÁ goal(s) e TODOS não compilam. Sem goal (lifecycle
    default) ou com um único goal que compila (test/verify/package/install/
    quarkus:*/exec:*/desconhecido) cancela a liberação."""
    goals = M.goals(args)
    return bool(goals) and all(_is_noncompiling_goal(g) for g in goals)


def _is_quarkus_segment(args) -> bool:
    return any(g.startswith("quarkus:") for g in M.goals(args))


def _fresh_root_install(reactor_root: Path) -> bool:
    """Regra 2: `.claude/last-root-install.json` existe na raiz da sessão E
    nenhum arquivo-fonte do reator (mesmo critério de `mark-build-stale.is_source`,
    via `_buildsource.py`) tem mtime posterior ao horário gravado ali.

    Fail closed de propósito: arquivo ausente, ilegível, ou timestamp que não
    parseia mantém o bloqueio de hoje — melhor um turno cobrando `-am`/`stale-ok`
    de novo do que liberar sem prova de que o `~/.m2` está mesmo fresco.
    """
    session_root = Path(L.session_root(str(reactor_root)))
    marker = session_root / ".claude" / "last-root-install.json"
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        at = datetime.fromisoformat(data["at"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return False
    return not B.any_source_newer(str(reactor_root), at.timestamp())


def is_multi_module(root: Path) -> bool:
    pom = root / "pom.xml"
    try:
        return "<modules>" in pom.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False  # sem pom legível: fail open


def _offending_segments(command: str):
    """Todos os segmentos com `-pl` sem `-am`, na ordem em que aparecem, como
    pares `(seg, args)`. Um comando encadeado (`./mvnw -pl a clean && ./mvnw
    -pl b test`) pode ter MAIS de um — bug reproduzido pelo pair-reviewer em
    2026-09-27: olhar só o primeiro fazia a regra 1 (nenhum goal compila) ser
    avaliada apenas nele, e um segundo segmento que COMPILA (`-pl b test`)
    passava batido porque o primeiro (`-pl a clean`) já tinha liberado. `main()`
    usa esta lista para escolher o primeiro ofensor que COMPILA, não
    simplesmente o primeiro ofensor."""
    out = []
    for seg in _split_segments(command):
        seg = seg.strip()
        if not seg:
            continue
        args = _maven_args(seg)
        if args is None:
            continue
        if _has_pl(args) and not _has_am(args):
            out.append((seg, args))
    return out


def offending_segment(command: str):
    """Primeiro segmento com `-pl` sem `-am`, ignorando se compila ou não.
    Mantido para quem só quer checar detecção de invocação (ex.:
    test_multiline_quoted_shell.py) — `main()` usa `_offending_segments`
    para decidir QUAL segmento importa quando há mais de um ofensor."""
    segs = _offending_segments(command)
    return segs[0][0] if segs else None


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

    offenders = _offending_segments(command)
    if not offenders:
        sys.exit(0)

    # Regra 1 — nenhum goal do segmento compila: não há vermelho falso possível.
    # Aplicada por segmento: um comando encadeado pode ter vários ofensores
    # (`./mvnw -pl a clean && ./mvnw -pl b test`), e só liberar quando TODOS
    # eles não compilam evita que um `clean` inofensivo no primeiro segmento
    # blinde um `test` que compila no segundo.
    compiling = [(s, a) for s, a in offenders if not _all_goals_noncompiling(a)]
    if not compiling:
        T.emit("maven_reactor_allow", cwd=str(cwd), reason="non-compiling-goals",
               segment=offenders[0][0])
        sys.exit(0)

    seg, args = compiling[0]

    # Regra 2 — install fresco da raiz depois da última edição de fonte.
    if _fresh_root_install(cwd):
        T.emit("maven_reactor_allow", cwd=str(cwd), reason="fresh-root-install", segment=seg)
        sys.exit(0)

    # Regra 3 — goal `quarkus:*`: `-am` quebraria o comando, então a mensagem
    # nunca sugere `-am`; a saída é instalar a raiz (regra 2) e repetir.
    if _is_quarkus_segment(args):
        T.emit("maven_reactor_block", cwd=str(cwd),
               reason="quarkus-without-fresh-install", segment=seg)
        print(
            "[maven-reactor-guard] BLOQUEADO: `-pl` sem `-am` para um goal `quarkus:*`.\n"
            f"  Comando: {seg}\n\n"
            "  Aqui `-am` NÃO é o conserto: o plugin do Quarkus só está declarado no\n"
            "  módulo alvo, e `-am` recompila o reator inteiro incluindo módulos sem o\n"
            "  plugin — o prefixo `quarkus:` deixa de resolver e o comando falha com\n"
            "  \"No plugin found for prefix 'quarkus'\" (BACKLOG, achado do\n"
            "  completion-auditor em 2026-09-25).\n\n"
            "  Faça, nesta ordem:\n"
            "    1. na raiz do reator, rode `./mvnw install -DskipTests`;\n"
            "    2. repita o MESMO comando acima, sem `-am` — um install fresco da raiz\n"
            "       libera este bloqueio automaticamente (compara o horário do install\n"
            "       com o mtime dos arquivos-fonte do reator).",
            file=sys.stderr,
        )
        sys.exit(2)

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
        "  que este guard existe para impedir (WEGO-1949, 2026-07-21).\n\n"
        "  Desde 2026-09-27, um `./mvnw install -DskipTests` da RAIZ do reator,\n"
        "  rodado DEPOIS da última edição de código-fonte, libera este mesmo bloqueio\n"
        "  automaticamente na próxima tentativa — `# stale-ok` deixou de ser\n"
        "  necessário nesse caso (continua servindo para quando o install rodou em\n"
        "  outra worktree ou fora do Claude, que este guard não vê).",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
