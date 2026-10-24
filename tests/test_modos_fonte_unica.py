#!/usr/bin/env python3
"""A tabela de modos tem uma fonte só, e ela não pode divergir do `cepa`.

Sem dependência externa — rode com `python3 tests/test_modos_fonte_unica.py`.

## Por que existe

A definição dos modos de trabalho estava em três lugares: a lista de nomes
válidos no `common/bin/cepa` (`MODOS=`), as condições de saída no
`common/hooks/session-mode.py`, e a prosa em `docs/modos-de-trabalho.md`. Três
cópias da mesma tabela é exatamente o padrão que este repo já pagou caro — a
memória `hooks-texto-citado-nao-e-shell` registra 7 cópias do mesmo parser com o
conserto aplicado em 5.

A tabela virou `common/hooks/_modos.py`. Este teste garante que ela e o `cepa`
continuem falando dos mesmos modos: um modo novo aceito pelo `--mode` mas ausente
da tabela sobe uma sessão cujo hook não sabe dizer quando ela fecha, e um modo na
tabela que o `cepa` recusa é documentação de algo que ninguém consegue usar.

Confere também que cada modo tem os cinco campos preenchidos: propósito,
entrada, produz, saída e gate. O propósito é o que a ajuda do menu do `cepa`
mostra — um modo sem ele volta a ser escolhido pelo nome. Um modo sem condição
de saída é rótulo, não fronteira — que é a tese inteira de
`docs/modos-de-trabalho.md`.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "common" / "hooks"))

CAMPOS = ("proposito", "entrada", "produz", "saida", "gate")


def modos_do_cepa():
    """A lista que o `cepa --mode` aceita, lida do shell script."""
    texto = (REPO / "common" / "bin" / "cepa").read_text(encoding="utf-8")
    m = re.search(r'^MODOS="([^"]+)"', texto, flags=re.M)
    if not m:
        return None
    return m.group(1).split()


def main():
    try:
        from _modos import MODOS, SAIDA
    except ImportError as e:
        print(f"FAIL: não consegui importar common/hooks/_modos.py ({e})", file=sys.stderr)
        return 1

    falhas = []

    do_cepa = modos_do_cepa()
    if do_cepa is None:
        falhas.append("não achei `MODOS=\"...\"` em common/bin/cepa — o detector "
                      "quebrou, não o repo")
    else:
        so_no_cepa = [m for m in do_cepa if m not in MODOS]
        so_na_tabela = [m for m in MODOS if m not in do_cepa]
        for m in so_no_cepa:
            falhas.append(f"`{m}` é aceito pelo `cepa --mode` e NÃO está em "
                          f"_modos.py — sessão que não sabe quando fecha")
        for m in so_na_tabela:
            falhas.append(f"`{m}` está em _modos.py e o `cepa --mode` RECUSA — "
                          f"documentação de algo inusável")
        if do_cepa == list(MODOS) and not falhas:
            pass  # ordem também bate; não é exigência, mas é bom sinal

    for nome, d in MODOS.items():
        for campo in CAMPOS:
            if not (d.get(campo) or "").strip():
                falhas.append(f"`{nome}`: campo `{campo}` vazio — modo sem "
                              f"{campo} não é fronteira")

    if set(SAIDA) != set(MODOS):
        falhas.append("SAIDA e MODOS discordam — SAIDA é derivado, alguém o "
                      "reescreveu à mão")

    # --- interface em inglês (item `interface-in-english`) -------------------
    nomes_novos = ["exploration", "discovery", "design", "construction",
                   "refactor", "reflection", "documentation"]
    if list(MODOS) != nomes_novos:
        falhas.append(f"os modos deveriam ser {nomes_novos}, são {list(MODOS)}")
    if do_cepa is not None and do_cepa != nomes_novos:
        falhas.append(f"`MODOS=` do cepa deveria ser {nomes_novos}, é {do_cepa}")
    from _modos import MODO_ANTIGO_PARA_NOVO, normalize_mode
    for velho, novo in (("exploracao", "exploration"), ("descoberta", "discovery"),
                        ("design", "design"), ("construcao", "construction"),
                        ("reforma", "refactor"), ("reflexao", "reflection"),
                        ("documentacao", "documentation")):
        if normalize_mode(velho) != novo or MODO_ANTIGO_PARA_NOVO.get(velho) != novo:
            falhas.append(f"o nome antigo `{velho}` deveria virar `{novo}`")
        if normalize_mode(novo) != novo:
            falhas.append(f"o nome novo `{novo}` deveria ficar como está")
    # alias: o script antigo `cepa-modos` imprime o mesmo que `cepa-modes`
    bindir = REPO / "common" / "bin"
    for args in (["--json"], ["--purposes", "--no-color"], ["refactor", "--no-color"],
                 ["reforma", "--no-color"], ["--propositos", "--sem-cor"]):
        novo = subprocess.run([sys.executable, str(bindir / "cepa-modes"), *args],
                              capture_output=True, text=True, timeout=30)
        velho = subprocess.run([sys.executable, str(bindir / "cepa-modos"), *args],
                               capture_output=True, text=True, timeout=30)
        if novo.returncode != 0 or not novo.stdout.strip():
            falhas.append(f"cepa-modes {' '.join(args)} falhou: {novo.stderr[:200]}")
        if (novo.returncode, novo.stdout) != (velho.returncode, velho.stdout):
            falhas.append(f"o atalho cepa-modos {' '.join(args)} não imprime o mesmo que cepa-modes")
    # o atalho também roda como executável direto (não só via `python3`)
    direto = subprocess.run([str(bindir / "cepa-modos"), "--purposes", "--no-color"],
                            capture_output=True, text=True, timeout=30)
    if direto.returncode != 0 or "construction" not in direto.stdout:
        falhas.append("o atalho cepa-modos não roda como executável direto")

    for f in falhas:
        print("FAIL:", f, file=sys.stderr)
    if falhas:
        print(f"\n{len(falhas)} falha(s).", file=sys.stderr)
        return 1

    print(f"ok — {len(MODOS)} modos, mesma lista no `cepa` e em _modos.py, "
          f"todos com os {len(CAMPOS)} campos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
