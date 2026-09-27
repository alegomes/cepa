#!/usr/bin/env python3
"""Ponta a ponta do item `until-build-longo-sem-trava`: um `claude -p` de
verdade, dentro de uma janela do `cepa-until`, colhe um build que passa de 10
minutos.

NÃO faz parte da suíte (`tests/run-all.sh` só roda `test_*.py`): chama o
`claude` de verdade, custa dinheiro (uns US$ 0,20 com o sonnet) e leva o tempo
do build mais uns minutos. Rode à mão quando mexer no `no-background-build` ou
quando o `claude` mudar de versão:

    python3 tests/e2e_build_longo_claude_p.py            # build de 700s
    python3 tests/e2e_build_longo_claude_p.py --segundos 660 --modelo haiku

## Por que existe

O teste de unidade do hook (`test_no_background_build.py`) prova a DECISÃO do
hook sobre um payload montado à mão. Ele não prova que um agente, recebendo só
o pedido "rode o build e colha o resultado", sai do outro lado com o resultado
colhido. Isso depende de duas coisas que só um `claude -p` de verdade mostra, e
que em 27/09/2026 (claude 2.1.283) eram:

  - o `claude -p` mata o segundo plano quando o turno acaba, com
    `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` em 0, ausente ou 120000;
  - um `Monitor` armado não segura o turno.

Se um dia o `claude` passar a esperar o segundo plano, este script continua
verde; se o hook parar de conduzir o agente, ele fica vermelho.

O pedido não ensina a receita de propósito: quem tem de ensinar é o hook.
Os hooks carregados são SÓ os desta árvore (`--setting-sources local` desliga
os plugins do usuário), para medir o código daqui e não o instalado.

Sai 0 com o resultado colhido, 1 sem ele.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"

PEDIDO = ("Neste diretório, rode `make verify` (é o build do projeto; leva uns "
          "{minutos} minutos) e colha o resultado: grave em resultado.txt a "
          "última linha que o build imprimiu e o código de saída dele. Só isso.")


def settings():
    bg = f"python3 {HOOKS / 'no-background-build.py'}"
    busy = f"python3 {HOOKS / 'no-busy-wait.py'}"
    return {"hooks": {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": bg},
                                          {"type": "command", "command": busy}]},
            {"matcher": "Monitor", "hooks": [{"type": "command", "command": bg}]},
        ],
        "Stop": [{"hooks": [{"type": "command", "command": bg}]}],
    }}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segundos", type=int, default=700,
                    help="duração do build sintético (default 700: passa do "
                         "teto de 10 min do Bash, que é o caso do item)")
    ap.add_argument("--modelo", default="sonnet")
    ap.add_argument("--dir", help="onde montar o cenário (default: tmp novo)")
    a = ap.parse_args()

    d = Path(a.dir or tempfile.mkdtemp(prefix="e2e-build-longo-"))
    d.mkdir(parents=True, exist_ok=True)
    (d / "Makefile").write_text(
        f"verify:\n\tsleep {a.segundos}\n\t@echo \"BUILD SUCCESS\"\n")
    (d / "settings.json").write_text(json.dumps(settings(), indent=1))

    env = dict(os.environ)
    env["CEPA_UNTIL_RUN"] = "1"
    env["CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"] = "0"  # o que o cepa-until exporta
    pedido = PEDIDO.format(minutos=max(1, round(a.segundos / 60)))
    print(f"cenário em {d}; build de {a.segundos}s; modelo {a.modelo}")
    inicio = time.time()
    p = subprocess.run(
        ["claude", "-p", pedido, "--model", a.modelo,
         "--dangerously-skip-permissions", "--setting-sources", "local",
         "--settings", str(d / "settings.json"), "--output-format", "json"],
        cwd=d, env=env, capture_output=True, text=True)
    gasto = time.time() - inicio
    (d / "saida.json").write_text(p.stdout)
    (d / "stderr.txt").write_text(p.stderr)

    resultado = d / "resultado.txt"
    linhas = resultado.read_text().split() if resultado.exists() else []
    colhido = "SUCCESS" in " ".join(linhas) and "0" in linhas
    try:
        custo = json.loads(p.stdout).get("total_cost_usd")
    except (json.JSONDecodeError, AttributeError):
        custo = None
    print(f"claude saiu {p.returncode} em {gasto:.0f}s (custo {custo})")
    print(f"resultado.txt: {linhas or 'ausente'}")
    if gasto < a.segundos:
        print("FAIL  o claude saiu antes de o build terminar: o build morreu "
              "com o turno")
        return 1
    if not colhido:
        print("FAIL  o build não foi colhido")
        return 1
    print("ok  build de mais de 10 min colhido dentro da janela")
    return 0


if __name__ == "__main__":
    sys.exit(main())
