#!/usr/bin/env python3
"""Text between quotes is not shell — regression of the multi-line commit.

No dependencies: `python3 tests/test_multiline_quoted_shell.py`. Exits non-zero
on the first failure.

## The bug this file exists to catch

The three hooks that analyze Bash commands — the five `bash-path-lock.py`, the
`enforcement-guard.py` and the `maven-reactor-guard.py` — split the command into
segments using `\n` as a separator, together with `;`, `|`, `&&`. That holds for
a multi-line script, and is wrong for a multi-line ARGUMENT.

The real case (2026-08-22, WEGO-2087, wego-acesso-backend): the dev ran

    git commit -m "feat: something

    The flow goes from A -> B now.
    "

Each line of the message body became a "segment" analyzed as if it were a
command. The line with the arrow matched the redirection regex (`>` not
preceded by a digit or `&`), and `B` was registered as a write target — outside
the agent's lane. The lock blocked the commit over a write that does not exist. The
dev could only commit after shortening the message to one line.

## The fix

`_quoted_mask` marks each character that is inside quotes (or escaped);
`_split_segments` only splits at an unmasked separator, and the search for a
redirection only accepts an unmasked `>`.

## Perturbation (how to know this test proves something)

In `common/hooks/_templates/bash-path-lock.py.tmpl`, swap the body of
`_split_segments` for `return _SEP_RE.split(command)` (or make `_quoted_mask`
return just `False`), run `python3 bin/gen-locks.py --write` and run this
file: it turns red naming the copies. If it stays green, it proves nothing.
"""

import importlib.util
import sys
from pathlib import Path

# This test cites a telemetry emitter hook. Today it does not get to execute it,
# but citing and executing are one step apart, and that distance is what
# left 7 tests polluting the real ledger for a month. See
# tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()


REPO = Path(__file__).resolve().parent.parent
HOOKS = sorted(REPO.glob("*/hooks/bash-path-lock.py"))

# The incident message, byte for byte as the dev wrote it.
COMMIT_ARROW = 'git commit -m "feat: algo\n\nO fluxo vai de A -> B agora.\n"'
# Same bug through the separator route: the body cites a write command.
COMMIT_TEE = 'git commit -m "fix: algo\n\nAntes eu fazia tee saida.txt na mão.\n"'
# And through the `&&` route: the body has a shell operator in the middle of the prose.
COMMIT_AND = 'git commit -m "fix: algo\n\nroda A && B, nessa ordem.\n"'
# The case measured on 2026-09-04: the commit message of this very fix
# CITED an infinite loop, and `no-busy-wait` blocked the commit as busy
# waiting. The citation was in the BODY of a heredoc, not in a command line.
HEREDOC_ARROW = ("git commit -q -F - <<'MSG'\n"
                "fix: algo\n\nO fluxo vai de A -> plugins/common/hooks/x.py agora.\n"
                "MSG")
HEREDOC_TEE = ("git commit -F - <<MSG\n"
               "fix: algo\n\nAntes eu fazia tee saida.txt na mao.\n"
               "MSG")
HEREDOC_INDENT = "cat <<-EOF\n\ttee saida.txt\n\tEOF"


def load(path, alias):
    spec = importlib.util.spec_from_file_location(alias, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# (caption, command, predicate(targets) -> bool, what is expected)
PATHLOCK_CASES = [
    ("seta na mensagem", COMMIT_ARROW,
     lambda t: t == [], "prosa citada não escreve nada"),
    ("tee na mensagem", COMMIT_TEE,
     lambda t: t == [], "prosa citada não escreve nada"),
    ("&& na mensagem", COMMIT_AND,
     lambda t: t == [], "prosa citada não escreve nada"),
    # --- no over-correction: what is really a write is still seen
    ("redirecionamento real", 'echo "x" > out.txt',
     lambda t: t == ["out.txt"], "out.txt detectado"),
    ("mensagem E redirecionamento", COMMIT_ARROW + " && cat a > b.txt",
     lambda t: t == ["b.txt"], "só o redirecionamento fora das aspas"),
    ("script de VÁRIAS LINHAS de verdade", "cat a > um.txt\ntee dois.txt",
     lambda t: t == ["um.txt", "dois.txt"], "\\n fora de aspas ainda separa comandos"),
    ("alvo com espaço entre aspas", 'echo x > "meu arquivo.txt"',
     lambda t: t == ["meu arquivo.txt"], "alvo citado continua detectado"),
    ("seta fora de aspas É redirecionamento", "echo A -> B",
     lambda t: t == ["B"], "sem aspas, `-> B` redireciona de verdade"),
    # --- a READ operand is not a write target (the `tee` rule caught
    #     every argument without a flag, `<` and the input file included) ---
    ("tee com entrada redirecionada", "tee saida.txt < entrada.txt",
     lambda t: t == ["saida.txt"], "entrada.txt está sendo lido, não escrito"),
    ("tee com stderr desviado", "tee saida.txt 2> err.log",
     lambda t: t == ["saida.txt"], "2> é fora de escopo, e não vira operando"),
    ("tee com vários destinos", "tee a.txt b.txt",
     lambda t: t == ["a.txt", "b.txt"], "os dois destinos continuam vistos"),
    # --- heredoc body is DATA, not shell (2026-09-04). Same defect as the
    #     quotes, one step further: `git commit -F - <<'MSG'` with a message
    #     that CITES `tee` or `->` made the guard report a phantom write.
    ("corpo de heredoc com seta na prosa", HEREDOC_ARROW,
     lambda t: t == [], "a seta está no corpo da mensagem, não numa linha de comando"),
    ("corpo de heredoc com tee na prosa", HEREDOC_TEE,
     lambda t: t == [], "prosa do corpo não escreve nada"),
    ("heredoc com recuo (<<-)", HEREDOC_INDENT,
     lambda t: t == [], "o corpo continua dado mesmo com <<- e delimitador recuado"),
    # --- and no over-correction: the heredoc that really redirects
    #     is still a seen write.
    ("heredoc que redireciona de verdade", "cat > out.txt <<'EOF'\nlinha\nEOF",
     lambda t: t == ["out.txt"], "o `> out.txt` está FORA do corpo"),
]

# (caption, command, expected for the "I don't know how to analyze this" signal)
UNCOVERED_CASES = [
    ("prosa citada não é construção indecidível",
     'git commit -m "corpo com ed e << no meio da frase"', False),
    ("python3 -c continua sinalizado", 'python3 -c "print(1)"', True),
    ("heredoc continua sinalizado", "cat <<EOF > out.txt", True),
    # The operator remains VISIBLE after masking the body — and it is what
    # sustains the signal. Masking `<<EOF` together with the body would erase the signal and the
    # heredoc would go on writing in silence.
    ("heredoc com corpo continua sinalizado",
     "cat <<EOF > out.txt\nlinha\nEOF", True),
    # The signal comes from the OPERATOR, and so it also holds here: a heredoc is
    # undecidable regardless of what the body says.
    ("heredoc de mensagem tambem sinaliza, pelo operador", HEREDOC_TEE, True),
]

ENFORCEMENT_CASES = [
    ("seta apontando para plugins",
     'git commit -m "fix: x\n\nO fluxo vai de A -> plugins/common/hooks/x.py agora.\n"',
     lambda t: t == [], "prosa citada não escreve nada"),
    ("`>=` não é redirecionamento", "grep -n '>=' Foo.java",
     lambda t: t == [], "o `>` de `>=` nunca é redirecionamento"),
    ("escrita real em plugins", "cat x > plugins/common/hooks/y.py",
     lambda t: t == ["plugins/common/hooks/y.py"], "alvo real detectado"),
    ("tee em settings", "echo hi | tee .claude/settings.json",
     lambda t: t == [".claude/settings.json"], "alvo real detectado"),
    ("tee com entrada redirecionada", "tee plugins/x.py < entrada.txt",
     lambda t: t == ["plugins/x.py"], "entrada.txt está sendo lido, não escrito"),
]

MAVEN_CASES = [
    ("comando maven citado na mensagem",
     'git commit -m "fix: build\n\n./mvnw test -pl core rodou verde.\n"',
     lambda seg: seg is None, "prosa citada não é invocação do Maven"),
    ("-pl sem -am continua barrado", "./mvnw test -pl core",
     lambda seg: seg is not None, "invocação real segue detectada"),
    ("-pl com -am passa", "./mvnw test -pl core -am",
     lambda seg: seg is None, "-am torna a invocação legítima"),
]


def run(caption, call, cases):
    failures = 0
    for label, cmd, ok, expect in cases:
        got = call(cmd)
        if ok(got):
            print(f"PASS [{caption:17}] {label:34} -> {got}")
        else:
            failures += 1
            print(f"FAIL [{caption:17}] {label:34} -> {got}  (esperado: {expect})")
    return failures


def main():
    if not HOOKS:
        print("FAIL: nenhum */hooks/bash-path-lock.py encontrado em", REPO)
        return 1

    failures = 0
    for hook in HOOKS:
        top = hook.parent.parent.name
        mod = load(hook, f"bpl_{top}")
        failures += run(top, lambda c: mod.extract_write_targets(c)[0], PATHLOCK_CASES)
        failures += run(top, lambda c: mod.extract_write_targets(c)[1],
                      [(lb, cmd, (lambda e: lambda got: got is e)(want),
                        f"sinal {want}") for lb, cmd, want in UNCOVERED_CASES])

    eg = load(REPO / "common" / "hooks" / "enforcement-guard.py", "enforcement_guard")
    failures += run("enforcement-guard", eg.extract_bash_targets, ENFORCEMENT_CASES)

    mg = load(REPO / "common" / "hooks" / "maven-reactor-guard.py", "maven_reactor_guard")
    failures += run("maven-reactor", mg.offending_segment, MAVEN_CASES)

    print()
    if failures:
        print(f"{failures} falha(s)")
        return 1
    print(f"tudo verde em {len(HOOKS)} cópias do bash-path-lock + os 2 guards do common")
    return 0


if __name__ == "__main__":
    sys.exit(main())
