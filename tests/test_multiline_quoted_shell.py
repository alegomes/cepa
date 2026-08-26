#!/usr/bin/env python3
"""Texto entre aspas não é shell — regressão do commit de várias linhas.

Sem dependências: `python3 tests/test_multiline_quoted_shell.py`. Sai não-zero
na primeira falha.

## O bug que este arquivo existe para pegar

Os três hooks que analisam comandos Bash — os cinco `bash-path-lock.py`, o
`enforcement-guard.py` e o `maven-reactor-guard.py` — quebravam o comando em
segmentos usando `\n` como separador, junto com `;`, `|`, `&&`. Isso vale para
um script de várias linhas, e é errado para um ARGUMENTO de várias linhas.

O caso real (22/08/2026, WEGO-2087, wego-acesso-backend): o dev rodou

    git commit -m "feat: algo

    O fluxo vai de A -> B agora.
    "

Cada linha do corpo da mensagem virou um "segmento" analisado como se fosse
comando. A linha com a seta casou com o regex de redirecionamento (`>` não
precedido de dígito nem `&`), e `B` foi registrado como alvo de escrita — fora
da pista do agente. O cadeado barrou o commit por uma escrita que não existe. O
dev só conseguiu commitar depois de encurtar a mensagem para uma linha.

## O conserto

`_quoted_mask` marca cada caractere que está dentro de aspas (ou escapado);
`_split_segments` só quebra em separador desmascarado, e a busca por
redirecionamento só aceita `>` desmascarado.

## Perturbação (como saber que este teste prova algo)

Em `common/hooks/_templates/bash-path-lock.py.tmpl`, troque o corpo de
`_split_segments` por `return _SEP_RE.split(command)` (ou faça `_quoted_mask`
devolver só `False`), rode `python3 bin/gen-locks.py --write` e rode este
arquivo: ele fica vermelho nomeando as cópias. Se ficar verde, não prova nada.
"""

import importlib.util
import sys
from pathlib import Path

# Este teste cita hook emissor de telemetria. Hoje ele não chega a executá-lo,
# mas citar e executar são um passo um do outro, e foi essa distância que
# deixou 7 testes poluindo o ledger real por um mês. Ver
# tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()


REPO = Path(__file__).resolve().parent.parent
HOOKS = sorted(REPO.glob("*/hooks/bash-path-lock.py"))

# A mensagem do incidente, byte a byte como o dev a escreveu.
COMMIT_SETA = 'git commit -m "feat: algo\n\nO fluxo vai de A -> B agora.\n"'
# Mesmo bug pela via do separador: o corpo cita um comando de escrita.
COMMIT_TEE = 'git commit -m "fix: algo\n\nAntes eu fazia tee saida.txt na mão.\n"'
# E pela via do `&&`: o corpo tem um operador de shell no meio da prosa.
COMMIT_AND = 'git commit -m "fix: algo\n\nroda A && B, nessa ordem.\n"'


def load(path, alias):
    spec = importlib.util.spec_from_file_location(alias, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# (rótulo, comando, predicado(alvos) -> bool, o que se espera)
PATHLOCK_CASES = [
    ("seta na mensagem", COMMIT_SETA,
     lambda t: t == [], "prosa citada não escreve nada"),
    ("tee na mensagem", COMMIT_TEE,
     lambda t: t == [], "prosa citada não escreve nada"),
    ("&& na mensagem", COMMIT_AND,
     lambda t: t == [], "prosa citada não escreve nada"),
    # --- nada de correção exagerada: o que é escrita de verdade continua vista
    ("redirecionamento real", 'echo "x" > out.txt',
     lambda t: t == ["out.txt"], "out.txt detectado"),
    ("mensagem E redirecionamento", COMMIT_SETA + " && cat a > b.txt",
     lambda t: t == ["b.txt"], "só o redirecionamento fora das aspas"),
    ("script de VÁRIAS LINHAS de verdade", "cat a > um.txt\ntee dois.txt",
     lambda t: t == ["um.txt", "dois.txt"], "\\n fora de aspas ainda separa comandos"),
    ("alvo com espaço entre aspas", 'echo x > "meu arquivo.txt"',
     lambda t: t == ["meu arquivo.txt"], "alvo citado continua detectado"),
    ("seta fora de aspas É redirecionamento", "echo A -> B",
     lambda t: t == ["B"], "sem aspas, `-> B` redireciona de verdade"),
    # --- operando de LEITURA não é alvo de escrita (a regra do `tee` pegava
    #     todo argumento sem flag, `<` e o arquivo de entrada inclusive) ---
    ("tee com entrada redirecionada", "tee saida.txt < entrada.txt",
     lambda t: t == ["saida.txt"], "entrada.txt está sendo lido, não escrito"),
    ("tee com stderr desviado", "tee saida.txt 2> err.log",
     lambda t: t == ["saida.txt"], "2> é fora de escopo, e não vira operando"),
    ("tee com vários destinos", "tee a.txt b.txt",
     lambda t: t == ["a.txt", "b.txt"], "os dois destinos continuam vistos"),
]

# (rótulo, comando, esperado para o sinal "não sei analisar isto")
UNCOVERED_CASES = [
    ("prosa citada não é construção indecidível",
     'git commit -m "corpo com ed e << no meio da frase"', False),
    ("python3 -c continua sinalizado", 'python3 -c "print(1)"', True),
    ("heredoc continua sinalizado", "cat <<EOF > out.txt", True),
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


def run(rotulo, chamada, casos):
    falhas = 0
    for label, cmd, ok, expect in casos:
        got = chamada(cmd)
        if ok(got):
            print(f"PASS [{rotulo:17}] {label:34} -> {got}")
        else:
            falhas += 1
            print(f"FAIL [{rotulo:17}] {label:34} -> {got}  (esperado: {expect})")
    return falhas


def main():
    if not HOOKS:
        print("FAIL: nenhum */hooks/bash-path-lock.py encontrado em", REPO)
        return 1

    falhas = 0
    for hook in HOOKS:
        topo = hook.parent.parent.name
        mod = load(hook, f"bpl_{topo}")
        falhas += run(topo, lambda c: mod.extract_write_targets(c)[0], PATHLOCK_CASES)
        falhas += run(topo, lambda c: mod.extract_write_targets(c)[1],
                      [(lb, cmd, (lambda e: lambda got: got is e)(esp),
                        f"sinal {esp}") for lb, cmd, esp in UNCOVERED_CASES])

    eg = load(REPO / "common" / "hooks" / "enforcement-guard.py", "enforcement_guard")
    falhas += run("enforcement-guard", eg.extract_bash_targets, ENFORCEMENT_CASES)

    mg = load(REPO / "common" / "hooks" / "maven-reactor-guard.py", "maven_reactor_guard")
    falhas += run("maven-reactor", mg.offending_segment, MAVEN_CASES)

    print()
    if falhas:
        print(f"{falhas} falha(s)")
        return 1
    print(f"tudo verde em {len(HOOKS)} cópias do bash-path-lock + os 2 guards do common")
    return 0


if __name__ == "__main__":
    sys.exit(main())
