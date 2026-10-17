#!/usr/bin/env python3
"""C1-4 (intencao-c1): o contrato do passo 3b de /common:session.

A rotina grava a intenção da sessão pelo `cepa-intencao` logo depois da
largada, sem um segundo ritual. Aqui se garante que o comando documentado
existe entre os passos 3 e 4, trata a saída 4 (`--motivo`), avança o cursor,
não roda no `--help`, e que nenhum item de `--plano` tem ':' (o escritor
recusaria). E, mais forte que o texto: o comando documentado é EXECUTADO
contra o `cepa-intencao` real num repo temporário, com a saída 4 e o
`--motivo` da segunda gravação, e os dois `--passo`.

Sem deps de terceiros — rode com `python3 tests/test_session_intencao_contrato.py`.
"""

import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SESSION_MD = REPO / "common" / "commands" / "session.md"
PLUGIN_ROOT = REPO / "common"
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))
import _modos as M  # noqa: E402

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def main():
    txt = SESSION_MD.read_text(encoding="utf-8")
    i3 = txt.find("### 3. ")
    i3b = txt.find("### 3b. Gravar a intenção da sessão")
    i4 = txt.find("### 4. ")
    check("os passos 3, 3b e 4 existem", min(i3, i3b, i4) >= 0, f"{i3} {i3b} {i4}")
    check("o 3b fica entre o 3 e o 4", 0 <= i3 < i3b < i4, f"{i3} {i3b} {i4}")
    sec = txt[i3b:i4] if 0 <= i3b < i4 else ""

    check('contém cepa-intencao" gravar', 'cepa-intencao" gravar' in sec)
    check("trata a saída 4 com --motivo", "--motivo" in sec and "4" in sec)
    check("avança o cursor com --passo 2", "--passo 2" in sec)
    check("avança o cursor com --passo 3", "--passo 3" in sec)
    check("diz que não roda no --help", "--help" in sec and "nunca" in sec)
    plano = " ".join(sec.split())
    check("diz que substitui o pedido do hook (sem segundo ritual)",
          "não proponha à parte" in plano and "segundo ritual" in plano)
    check("diz que falha do escritor não para a rotina",
          "Falha do escritor não para a rotina" in plano)

    linha = next((l for l in sec.splitlines() if 'cepa-intencao" gravar' in l), "")
    check("achou a linha do comando documentado", bool(linha))
    m = re.search(r"--plano\s+(.*)$", linha)
    itens = []
    if m:
        try:
            itens = shlex.split(m.group(1))
        except ValueError:
            itens = []
    itens = [i for i in itens if not i.startswith("--")]
    check("o plano documentado tem 1 a 6 itens", 1 <= len(itens) <= 6, repr(itens))
    check("nenhum item do plano tem ':'", all(":" not in i for i in itens), repr(itens))

    executa(sec, linha)

    if failures:
        print(f"\n{len(failures)} FAIL")
        sys.exit(1)
    print("\nOK")


def roda(cmd, cwd, env):
    return subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=60)


def executa(sec, linha):
    """Roda a linha documentada (placeholder do propósito trocado) num repo novo."""
    print("o comando documentado roda contra o cepa-intencao real")
    cmd = re.sub(r'--proposito "<[^>]*>"', '--proposito "rodar prove-drain --max 5"', linha.strip())
    motivo = re.search(r'`(--motivo "[^"]*")`', sec)
    passos = re.findall(r'`(python3 "\$\{CLAUDE_PLUGIN_ROOT\}/bin/cepa-intencao" --passo \d)`', sec)
    with tempfile.TemporaryDirectory() as t:
        subprocess.run(["git", "init", "-q", t], check=True)
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
               "CEPA_TELEMETRY_DIR": os.path.join(t, ".tel"),
               "CLAUDE_CODE_SESSION_ID": "sess-contrato"}
        r = roda(cmd, t, env)
        check("a 1a gravação sai 0", r.returncode == 0, f"rc={r.returncode} {r.stderr!r}")
        d = M.read_intent(t) or {}
        check("o propósito é o da largada", d.get("proposito") == "rodar prove-drain --max 5",
              repr(d.get("proposito")))
        check("o plano gravado tem 3 passos, no passo 1",
              len(d.get("plano") or []) == 3 and d.get("passo") == 1, repr(d))
        r = roda(cmd, t, env)
        check("regravar sem --motivo sai 4, como o passo diz", r.returncode == 4,
              f"rc={r.returncode}")
        check("o passo documenta o --motivo", bool(motivo))
        if motivo:
            r = roda(f"{cmd} {motivo.group(1).replace('<rotina>', 'prove-drain')}", t, env)
            check("com o --motivo documentado sai 0", r.returncode == 0, r.stderr)
            d = M.read_intent(t) or {}
            check("a anterior foi para o histórico", len(d.get("historico") or []) == 1, repr(d))
        check("os dois --passo estão no formato executável", len(passos) == 2, repr(passos))
        for p in passos:
            r = roda(p, t, env)
            check(f"`{p[-9:]}` sai 0", r.returncode == 0, r.stderr)
        d = M.read_intent(t) or {}
        check("o cursor terminou no passo 3", d.get("passo") == 3, repr(d.get("passo")))


if __name__ == "__main__":
    main()
