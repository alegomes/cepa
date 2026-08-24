#!/usr/bin/env python3
"""O porteiro classifica a LINHA INTEIRA, não a primeira palavra.

Roda contra o lote de sombra congelado em
`tests/fixtures/gatekeeper-shadow-wego-paralelo/` — as 73 decisões que o
`maestro-gatekeeper` tomou na primeira vez que rodou contra trabalho real
(onda 1 do programa WEGO-paralelo, 2026-08-24, em --shadow).

O que o lote revelou, e que estes testes travam:

1. **8 ALLOWs escreviam arquivo.** A regra `read-only` era uma regex ancorada no
   início da linha, então `cat > api-rest/.../CaminhoNormalizadoPolicyTest.java
   <<'EOF'` casava por causa do `cat`. Uma das linhas liberadas terminava em
   `git add -A && git commit -q -m "..."`: o porteiro liberou um commit achando
   que era leitura. Em sombra não custou nada; ligado, torna a camada 3
   decorativa para qualquer coisa escrita como `<leitura> && <o que eu quiser>`.
2. **1 falso delete-broad.** O padrão `rm -rf` casou com um
   `trap 'rm -rf "${SANDBOX}"' EXIT` DENTRO do corpo do heredoc de um script de
   teste sendo criado — conteúdo, não comando.
3. **23 escalações de ruído.** `sed -n '340,420p' arquivo` e
   `./mvnw -pl X -am test -Dtest=Y 2>&1 | tail -30` já vinham pré-aprovados nas
   settings da filha, mas o allow do Claude Code não sobrevive ao cano.

Sem deps. Rode: python3 tests/test_gatekeeper_classifica_linha_inteira.py
"""
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOTE = REPO / "tests" / "fixtures" / "gatekeeper-shadow-wego-paralelo" / "decisions.jsonl"
FALHAS = []


def check(nome, cond, detalhe=""):
    print(("  ok  " if cond else "FAIL  ") + nome + ("" if cond else f"  {detalhe}"))
    if not cond:
        FALHAS.append(nome)


def carregar_porteiro():
    spec = importlib.util.spec_from_loader(
        "gk", importlib.machinery.SourceFileLoader(
            "gk", str(REPO / "maestro" / "bin" / "maestro-gatekeeper")))
    gk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gk)
    gk._carregar_shellscan()
    return gk


def bash(cmd):
    return "Bash", {"command": cmd}


def test_unidade(gk):
    check("motor de leitura carregado (senão tudo escala)", gk._S is not None,
          gk._SHELLSCAN_ERRO)

    # --- o defeito principal: escrita disfarçada de leitura
    escritas = [
        "cat > api-rest/src/test/java/Foo.java <<'EOF'\nclass Foo {}\nEOF",
        "cat > /tmp/patch.py <<'PY'\nprint(1)\nPY",
        "cat resultado.txt && git add -A && git commit -q -m 'x'",
        "grep -n foo bar.txt > achados.txt",
        "sed -i 's/a/b/' arquivo.java",
        "cp /tmp/X.bak domain/src/main/java/X.java",
        "echo oi | tee saida.txt",
        "mkdir -p bin/tests && cat > bin/tests/t.sh <<'EOF'\n#!/bin/sh\nEOF",
    ]
    for c in escritas:
        regra, ok = gk.allow_mecanico(*bash(c))
        check(f"NÃO libera escrita: {c.splitlines()[0][:52]}", not ok, regra)

    # --- leitura de verdade continua liberada
    leituras = [
        "sed -n '340,420p' bin/run-dev.sh",
        "ls application/src/test/java/ 2>/dev/null",
        "grep -rn 'WEGO-2050' --include=* -l . | head -20",
        "cat pom.xml | head -40",
        "git status --short && git diff --stat",
        "find . -name '*.java' | wc -l",
    ]
    for c in leituras:
        regra, ok = gk.allow_mecanico(*bash(c))
        check(f"libera leitura como read-only: {c[:52]}",
              ok and regra == "read-only", regra)

    # --- build/teste com cano: era ruído, agora passa nomeado
    builds = [
        "./mvnw -pl application -am test -Dtest=FooTest 2>&1 | tail -30",
        "./mvnw -pl api-rest -am test -Dtest=BarTest 2>&1 | grep -E 'ERROR|BUILD'",
    ]
    for c in builds:
        regra, ok = gk.allow_mecanico(*bash(c))
        check(f"libera build/teste como base-pipeline: {c[:52]}",
              ok and regra == "base-pipeline", regra)

    # --- interpretador nunca é pré-aprovado (zona cinza legítima)
    for c in ["python3 - <<'EOF'\nopen('X.java','w').write('')\nEOF",
              "perl -0pi -e 's/a/b/' X.java"]:
        _, ok = gk.allow_mecanico(*bash(c))
        check(f"interpretador escala: {c.splitlines()[0][:52]}", not ok)

    # --- corpo de heredoc é conteúdo, não comando
    script = ("mkdir -p bin/tests && cat > bin/tests/t.sh <<'EOF'\n"
              "trap 'rm -rf \"${SANDBOX}\"' EXIT\nEOF")
    scan = gk.texto_analisavel(*bash(script))
    check("corpo de heredoc sai do texto varrido pelos padrões estratégicos",
          "rm -rf" not in scan, scan[:120])
    check("um rm -rf REAL continua visível",
          "rm -rf" in gk.texto_analisavel(*bash("rm -rf build/")))


def test_reprocessa_o_lote(gk):
    if not LOTE.is_file():
        check("lote de sombra presente", False, str(LOTE))
        return
    linhas = [json.loads(l) for l in LOTE.read_text().splitlines() if l.strip()]
    check("lote tem as 74 decisões do 1º programa (31 allow + 43 escalação)",
          len(linhas) == 74, len(linhas))

    liberados_que_escrevem, delete_broad, ruido_resolvido = [], [], 0
    for d in linhas:
        ti = d.get("input") or {}
        tn = d.get("tool_name") or "Bash"
        regra, ok = gk.allow_mecanico(tn, ti)
        cmd = ti.get("command", "") if isinstance(ti, dict) else ""
        if ok and cmd and gk.escreve_alguma_coisa(cmd):
            liberados_que_escrevem.append(cmd[:70])
        # padrões estratégicos sobre o texto analisável
        import re
        for rule, pat in gk.STRATEGIC:
            if re.search(pat, gk.texto_analisavel(tn, ti), re.I):
                delete_broad.append((rule, cmd[:70]))
                break
        if d.get("decisao") == "escalate" and ok:
            ruido_resolvido += 1

    check("NENHUM allow escreve arquivo (eram 8)",
          not liberados_que_escrevem, liberados_que_escrevem[:3])
    check("NENHUM delete-broad no lote (era 1, falso, dentro de heredoc)",
          not [x for x in delete_broad if x[0] == "delete-broad"],
          [x for x in delete_broad if x[0] == "delete-broad"][:2])
    check(f"ruído resolvido sozinho: {ruido_resolvido} escalações viram allow",
          ruido_resolvido >= 20, ruido_resolvido)


if __name__ == "__main__":
    gk = carregar_porteiro()
    test_unidade(gk)
    test_reprocessa_o_lote(gk)
    print()
    if FALHAS:
        print(f"{len(FALHAS)} falha(s): " + ", ".join(FALHAS))
        sys.exit(1)
    print("all green")
