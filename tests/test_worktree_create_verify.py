#!/usr/bin/env python3
"""Contract test: /maestro:run confere no GIT que a worktree da slice existe.

A perda que isto guarda, medida numa execução real (programa WEGO-paralelo,
onda 2, repo wego-acesso-backend, 2026-08-24, herdr 0.7.3): em 4 de 5 chamadas
o `herdr worktree create --json` devolveu JSON de sucesso COMPLETO — com
`path`, `branch`, `workspace_id` e `"is_prunable": false` — e o git não
registrou worktree nenhuma; os diretórios também não existiam. O
`herdr worktree list` seguia mostrando as fantasmas, porque o herdr mantém
registro próprio. Sem conferir `git worktree list` na mão, os passos seguintes
(seed do .env, maestro-fork-settings, herdr agent start) rodariam contra
caminhos inexistentes e a onda inteira nasceria morta — falhando de um jeito
que parece problema das filhas, não do fork.

O gatilho está no herdr, fora do nosso alcance. O que é nosso: não aceitar a
palavra de ferramenta externa sobre um efeito que o git confere em um comando —
o mesmo padrão do marcador `MAESTRO-EXIT`, que sincroniza por ARQUIVO e não
pelo pane.

Como o contrato mora em prosa de comando (o modelo é quem executa), o guard tem
de ser mecânico, no molde de tests/test_plan_anchor_root.py: prosa dizendo
"confie no --json" é exatamente o que erode em silêncio.

Run: python3 tests/test_worktree_create_verify.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUN = REPO / "maestro" / "commands" / "run.md"
RESUME = REPO / "maestro" / "commands" / "resume.md"

FAILURES = []


def check(label, cond, extra=""):
    if cond:
        print(f"✓ {label}")
    else:
        print(f"✗ {label}" + (f" — {extra}" if extra else ""))
        FAILURES.append(label)


def flat(txt):
    """Texto com espaços colapsados: as checagens casam FRASE, não quebra de
    linha — senão uma re-quebra inocente fica vermelha e ensina a afrouxar o
    guard, que é como um guard mecânico vira decoração."""
    return " ".join(txt.split())


def passo_6a(txt):
    """O trecho do passo 6a — do 'a. **Worktree herdr**' até o item 'b.'."""
    ini = txt.find("a. **Worktree herdr**")
    if ini == -1:
        return ""
    fim = txt.find("\n   b. ", ini)
    return txt[ini:fim if fim != -1 else len(txt)]


def main():
    run = RUN.read_text(encoding="utf-8")
    bloco = passo_6a(run)
    check("run.md ainda tem o passo 6a (fork da worktree da slice)", bool(bloco),
          "o passo mudou de forma — reancore este teste antes de seguir")
    fb = flat(bloco)

    check("6a: chama o `herdr worktree create`",
          "herdr worktree create" in fb)
    check("6a: confere o resultado com `git worktree list`",
          "git worktree list" in fb,
          "sem esta conferência o fork confia no exit code do herdr")
    check("6a: confere no CLONE PRINCIPAL, não na árvore corrente",
          "git -C <raiz-principal> worktree list" in fb)
    check("6a: diz explicitamente que o JSON de sucesso não basta",
          "não basta" in fb or "não implica" in fb,
          "a prosa tem de nomear o motivo, senão alguém 'simplifica' de volta")
    check("6a: registra a evidência que originou a checagem",
          "2026-08-24" in fb and "is_prunable" in fb)
    check("6a: manda tentar de novo UMA vez",
          "uma** vez mais" in fb or "uma vez mais" in fb)
    check("6a: marca a slice como FAIL com detalhe nomeado quando persiste",
          "set-slice" in fb and "fail" in fb and "--detail" in fb)
    check("6a: proíbe forkar as demais slices em silêncio",
          "em silêncio" in fb)

    # resume.md hoje NÃO cria worktree (só reconcilia e retoma o event loop).
    # Se um dia passar a criar, a mesma conferência tem de vir junto — este é o
    # guard que impede a regra nascer só num dos dois comandos.
    res = flat(RESUME.read_text(encoding="utf-8"))
    if "herdr worktree create" in res:
        check("resume.md: se cria worktree, confere por `git worktree list`",
              "git worktree list" in res,
              "resume passou a forkar sem herdar a conferência do run.md")
    else:
        print("✓ resume.md não cria worktree (nada a conferir lá)")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
