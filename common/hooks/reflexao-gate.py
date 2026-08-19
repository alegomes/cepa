#!/usr/bin/env python3
"""PreToolUse hook (common) — integridade do relatório de Reflexão.

Irmão do ui-proof-verdict-guard: o veredito não é uma opinião que o agente
escreve, é um valor recalculado do conteúdo e barrado quando não bate.

A condição de saída da Reflexão é **nenhum achado sem destino**: cada achado ou
virou card, ou foi descartado com motivo escrito (docs/modos-de-trabalho.md).
O motivo é o sintoma que originou os modos — achado solto não some, ele volta
como micro-ajuste no meio da próxima construção. Relatório é o lugar certo para
cobrar isso, porque é onde o achado nasce.

Barra o Write de `.claude/reflexao/*.yaml` que declare `fechado: true` com
qualquer achado sem `destino`, ou com um descarte cujo motivo é vazio ou
decorativo ("n/a", "-", "ok"). Um motivo curto demais é o mesmo que motivo
nenhum: ele existe para você reencontrar a decisão daqui a três meses.

Conservador de propósito, como o irmão: age só sobre contradição confirmada.
Arquivo que não é relatório de reflexão, YAML que não parseia, ou `fechado`
ausente/false → deixa passar. Nunca inventa bloqueio. Desliga com CEPA_MODO=off.
"""

import json
import os
import re
import sys

MOTIVO_MINIMO = 12
DECORATIVOS = {"n/a", "na", "-", "--", "ok", "nao", "não", "sim", "ja", "já",
               "nada", "none", "tbd", "?", "x"}


def eh_relatorio(file_path):
    p = file_path.replace(os.sep, "/")
    return "/.claude/reflexao/" in f"/{p.lstrip('/')}" and p.endswith((".yaml", ".yml"))


def carrega(texto):
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(texto)
    except Exception:  # noqa: BLE001
        return None


def motivo_vazio(motivo):
    if motivo is None:
        return True
    m = str(motivo).strip()
    return (not m) or m.lower() in DECORATIVOS or len(m) < MOTIVO_MINIMO


def sem_destino(achados):
    """Devolve (indice, achado, por_que) do primeiro achado que não fecha."""
    for i, a in enumerate(achados, 1):
        if not isinstance(a, dict):
            return i, a, "o achado não é um mapa com campos"
        destino = a.get("destino")
        descartado = a.get("descartado")
        if destino not in (None, "", "null"):
            continue
        if descartado is None:
            return i, a, "não tem `destino:` nem `descartado:`"
        if motivo_vazio(descartado):
            return i, a, (f"o motivo do descarte é vazio ou decorativo "
                          f"({descartado!r}) — precisa de pelo menos "
                          f"{MOTIVO_MINIMO} caracteres dizendo por quê")
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    try:
        if os.environ.get("CEPA_MODO", "on") == "off":
            sys.exit(0)

        ti = payload.get("tool_input") or {}
        fp = ti.get("file_path", "")
        if not fp or not eh_relatorio(fp):
            sys.exit(0)

        conteudo = ti.get("content")
        if not isinstance(conteudo, str):
            sys.exit(0)

        doc = carrega(conteudo)
        if not isinstance(doc, dict):
            sys.exit(0)
        if doc.get("fechado") is not True:
            sys.exit(0)

        achados = doc.get("achados")
        if not isinstance(achados, list) or not achados:
            sys.exit(0)

        falha = sem_destino(achados)
        if not falha:
            sys.exit(0)

        i, a, por_que = falha
        rotulo = (a.get("o_que") or a.get("titulo") or f"achado #{i}") \
            if isinstance(a, dict) else f"achado #{i}"
        print(
            f"[reflexao-gate] BLOQUEADO: {fp} declara `fechado: true`, mas o "
            f"achado #{i} não tem destino.\n"
            f"  Achado: {str(rotulo)[:120]}\n"
            f"  Problema: {por_que}.\n"
            f"  A Reflexão fecha quando NENHUM achado ficou solto. Achado solto "
            f"não some — ele volta como micro-ajuste no meio da próxima "
            f"construção, que é o vazamento que os modos existem para impedir.\n"
            f"  Escreva uma das duas coisas neste achado:\n"
            f"    destino: WEGO-1234        (ou a linha em .claude/desvios.md)\n"
            f"    descartado: <por que não vale a pena, em uma frase>\n"
            f"  Ou grave o relatório com `fechado: false` enquanto ainda "
            f"estiver triando.",
            file=sys.stderr,
        )
        sys.exit(2)
    except Exception as e:  # noqa: BLE001
        print(f"[reflexao-gate] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
