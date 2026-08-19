#!/usr/bin/env python3
"""Injeta o modo de trabalho ativo no contexto, a cada turno.

O modo é declarado no `cepa --modo <x>` e gravado em .claude/session-mode. Ele é
um ESTADO que dura a sessão inteira — diferente da rotina, que é uma tarefa que
acaba. Desenho completo: docs/modos-de-trabalho.md.

Por que UserPromptSubmit e não SessionStart: a fronteira precisa estar presente
no turno em que o desvio aparece. Injetado só na abertura, o modo some do
contexto útil justamente nas sessões longas, que são onde o vazamento entre
atividades acontece.

Saída enxuta de propósito (cabe em poucas linhas): ela paga pedágio em todo
turno. Diz o modo, a condição de saída dele e a regra do desvio — nada mais.

Nunca bloqueia nada. Sem arquivo de modo, é silencioso.
"""

import json
import os
import subprocess
import sys

# Condição de saída de cada modo — o que precisa ser verdade para ele fechar.
# Sem isso o modo é rótulo, não fronteira.
SAIDA = {
    "exploracao": "um documento de estratégia com 2+ caminhos considerados, "
                  "passado pelo painel /common:advisors com as discordâncias nomeadas",
    "descoberta": "evidence-auditor Confirmed nas suposições de risco + os "
                  "critérios de aceite escritos na altitude + o teste vermelho de cada um",
    "design": "design-critic devolvendo SHIP",
    "construcao": "completion-auditor COMPLETE e proof-reviewer PROVEN",
    "reforma": "o orçamento declarado exaurido, build verde, e NENHUM teste "
               "externo editado (teste editado = mudou comportamento = não era reforma)",
    "reflexao": "nenhum achado sem destino — cada um virou card ou foi "
                "descartado com motivo escrito",
    "documentacao": "consistency-reviewer PASS e sua assinatura em /docs:finalize",
}


def repo_root(cwd):
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd,
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else cwd
    except Exception:  # noqa: BLE001
        return cwd


def read_mode(root):
    """Lê o .claude/session-mode. Formato raso o bastante para não exigir PyYAML
    (o hook roda em todo turno; importar yaml aqui seria pedágio à toa)."""
    path = os.path.join(root, ".claude", "session-mode")
    if not os.path.isfile(path):
        return None
    data = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if ":" not in line:
                    continue
                k, _, v = line.partition(":")
                v = v.strip().strip('"')
                data[k.strip()] = None if v in ("null", "") else v
    except Exception:  # noqa: BLE001
        return None
    return data if data.get("modo") else None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    try:
        if os.environ.get("CEPA_MODO", "on") == "off":
            sys.exit(0)

        cwd = payload.get("cwd") or os.getcwd()
        mode = read_mode(repo_root(cwd))
        if not mode:
            sys.exit(0)

        nome = mode["modo"]
        linhas = [f"[modo] Esta sessão opera em **{nome}**."]
        if mode.get("orcamento"):
            linhas.append(f"Orçamento declarado: {mode['orcamento']}.")
        if nome in SAIDA:
            linhas.append(f"Fecha quando: {SAIDA[nome]}.")
        linhas.append(
            "Ação fora deste modo NÃO vira pergunta e NÃO vira trabalho agora: "
            "registre pelo skill `off-mode-capture` e siga. As capturas entram "
            "no relatório final."
        )
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": " ".join(linhas),
        }}))
    except Exception as e:  # noqa: BLE001
        print(f"[session-mode] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
