#!/usr/bin/env python3
"""The gatekeeper classifies the WHOLE LINE, not the first word.

Runs against the frozen shadow batch in
`tests/fixtures/gatekeeper-shadow-wego-paralelo/` — the 73 decisions the
`maestro-gatekeeper` made the first time it ran against real work
(wave 1 of the WEGO-paralelo program, 2026-08-24, in --shadow).

What the batch revealed, and what these tests lock:

1. **8 ALLOWs wrote a file.** The `read-only` rule was a regex anchored at the
   start of the line, so `cat > api-rest/.../CaminhoNormalizadoPolicyTest.java
   <<'EOF'` matched because of the `cat`. One of the allowed lines ended in
   `git add -A && git commit -q -m "..."`: the gatekeeper allowed a commit thinking it
   was a read. In shadow it cost nothing; switched on, it makes layer 3
   decorative for anything written as `<read> && <whatever I want>`.
2. **1 false delete-broad.** The `rm -rf` pattern matched a
   `trap 'rm -rf "${SANDBOX}"' EXIT` INSIDE the heredoc body of a test
   script being created — content, not command.
3. **23 noise escalations.** `sed -n '340,420p' file` and
   `./mvnw -pl X -am test -Dtest=Y 2>&1 | tail -30` already came pre-approved in the
   daughter's settings, but Claude Code's allow does not survive the pipe.

No deps. Run: python3 tests/test_gatekeeper_classifies_whole_line.py
"""
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BATCH = REPO / "tests" / "fixtures" / "gatekeeper-shadow-wego-paralelo" / "decisions.jsonl"
FAILURES = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILURES.append(name)


def load_gatekeeper():
    spec = importlib.util.spec_from_loader(
        "gk", importlib.machinery.SourceFileLoader(
            "gk", str(REPO / "maestro" / "bin" / "maestro-gatekeeper")))
    gk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gk)
    gk._carregar_shellscan()
    return gk


def bash(cmd):
    return "Bash", {"command": cmd}


def test_unit(gk):
    check("motor de leitura carregado (senão tudo escala)", gk._S is not None,
          gk._SHELLSCAN_ERRO)

    # --- the main defect: a write disguised as a read
    writes = [
        "cat > api-rest/src/test/java/Foo.java <<'EOF'\nclass Foo {}\nEOF",
        "cat > /tmp/patch.py <<'PY'\nprint(1)\nPY",
        "cat resultado.txt && git add -A && git commit -q -m 'x'",
        "grep -n foo bar.txt > achados.txt",
        "sed -i 's/a/b/' arquivo.java",
        "cp /tmp/X.bak domain/src/main/java/X.java",
        "echo oi | tee saida.txt",
        "mkdir -p bin/tests && cat > bin/tests/t.sh <<'EOF'\n#!/bin/sh\nEOF",
    ]
    for c in writes:
        rule_text, ok = gk.allow_mecanico(*bash(c))
        check(f"NÃO libera escrita: {c.splitlines()[0][:52]}", not ok, rule_text)

    # --- a real read remains allowed
    reads = [
        "sed -n '340,420p' bin/run-dev.sh",
        "ls application/src/test/java/ 2>/dev/null",
        "grep -rn 'WEGO-2050' --include=* -l . | head -20",
        "cat pom.xml | head -40",
        "git status --short && git diff --stat",
        "find . -name '*.java' | wc -l",
    ]
    for c in reads:
        rule_text, ok = gk.allow_mecanico(*bash(c))
        check(f"libera leitura como read-only: {c[:52]}",
              ok and rule_text == "read-only", rule_text)

    # --- build/test with a pipe: it was noise, now it passes named
    builds = [
        "./mvnw -pl application -am test -Dtest=FooTest 2>&1 | tail -30",
        "./mvnw -pl api-rest -am test -Dtest=BarTest 2>&1 | grep -E 'ERROR|BUILD'",
    ]
    for c in builds:
        rule_text, ok = gk.allow_mecanico(*bash(c))
        check(f"libera build/teste como base-pipeline: {c[:52]}",
              ok and rule_text == "base-pipeline", rule_text)

    # --- an interpreter is never pre-approved (legitimate gray zone)
    for c in ["python3 - <<'EOF'\nopen('X.java','w').write('')\nEOF",
              "perl -0pi -e 's/a/b/' X.java"]:
        _, ok = gk.allow_mecanico(*bash(c))
        check(f"interpretador escala: {c.splitlines()[0][:52]}", not ok)

    # --- heredoc body is content, not a command
    script = ("mkdir -p bin/tests && cat > bin/tests/t.sh <<'EOF'\n"
              "trap 'rm -rf \"${SANDBOX}\"' EXIT\nEOF")
    scan = gk.texto_analisavel(*bash(script))
    check("corpo de heredoc sai do texto varrido pelos padrões estratégicos",
          "rm -rf" not in scan, scan[:120])
    check("um rm -rf REAL continua visível",
          "rm -rf" in gk.texto_analisavel(*bash("rm -rf build/")))


def test_reprocesses_the_batch(gk):
    if not BATCH.is_file():
        check("lote de sombra presente", False, str(BATCH))
        return
    lines = [json.loads(l) for l in BATCH.read_text().splitlines() if l.strip()]
    check("lote tem as 74 decisões do 1º programa (31 allow + 43 escalação)",
          len(lines) == 74, len(lines))

    allowed_that_write, delete_broad, noise_resolved = [], [], 0
    for d in lines:
        ti = d.get("input") or {}
        tn = d.get("tool_name") or "Bash"
        rule_text, ok = gk.allow_mecanico(tn, ti)
        cmd = ti.get("command", "") if isinstance(ti, dict) else ""
        if ok and cmd and gk.escreve_alguma_coisa(cmd):
            allowed_that_write.append(cmd[:70])
        # strategic patterns over the analyzable text
        import re
        for rule, pat in gk.STRATEGIC:
            if re.search(pat, gk.texto_analisavel(tn, ti), re.I):
                delete_broad.append((rule, cmd[:70]))
                break
        if d.get("decisao") == "escalate" and ok:
            noise_resolved += 1

    check("NENHUM allow escreve arquivo (eram 8)",
          not allowed_that_write, allowed_that_write[:3])
    check("NENHUM delete-broad no lote (era 1, falso, dentro de heredoc)",
          not [x for x in delete_broad if x[0] == "delete-broad"],
          [x for x in delete_broad if x[0] == "delete-broad"][:2])
    check(f"ruído resolvido sozinho: {noise_resolved} escalações viram allow",
          noise_resolved >= 20, noise_resolved)


if __name__ == "__main__":
    gk = load_gatekeeper()
    test_unit(gk)
    test_reprocesses_the_batch(gk)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s): " + ", ".join(FAILURES))
        sys.exit(1)
    print("all green")
