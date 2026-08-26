#!/usr/bin/env python3
"""Gate de escrita por modo: cada modo só escreve o que ele PRODUZ.

## O buraco que este hook fecha

O modo de uma sessão era prosa. O `session-mode.py` injeta a cada turno:

    ação fora deste modo NÃO vira pergunta e NÃO vira trabalho agora;
    registre pelo `off-mode-capture` e siga.

Nada barrava. Na sessão `session/drain-plan-speed` (26/08/2026) o agente fez o
oposto das duas metades sete vezes seguidas: transformou cada desvio numa
pergunta fechada com "Recomendo sim", colheu o sim, e construiu. A condição de
saída da exploração — um documento de estratégia com 2+ caminhos, passado pelo
painel de advisors — foi satisfeita no PRIMEIRO dos sete commits; os quatro
seguintes eram construção. Nenhuma captura de desvio foi registrada; o
`off-mode-capture` não foi invocado uma vez sequer.

Duas skills se aplicavam e nunca foram confrontadas: a `default-yes` manda
decidir sozinho em ação reversível, e o modo manda não trabalhar fora dele. A
`default-yes` ganhou todas, e o agente nunca nomeou o conflito para o dono.

É o padrão que este repo já catalogou três vezes (memória
`gate-por-nome-de-ferramenta-falha-aberto`): **controle que depende do agente se
comportar não é controle.** Aqui o contorno teve aval do dono a cada passo, o
que o torna mais difícil de enxergar, não menos real.

## Como funciona

Irmão do `reforma-gate.py`, que já é um gate de escrita escopado por modo. A
regra é uma lista branca de DESTINOS por modo — o que aquele modo produz — e ela
mora em `_modos.py`, junto com o resto da tabela, e não aqui: uma segunda tabela
de modos é a doença que aquele arquivo trata.

`construcao` e `reforma` declaram `"tudo"`. Isso não é ausência de cobrança: na
construção quem cobra são o completion-auditor e o proof-reviewer, e na reforma
o `reforma-gate.py`.

Três decisões que vieram de estrago já pago neste repo:

1. **Bash também.** Barrar só `Write`/`Edit` deixa `sed -i`, `cat >`, `tee` e
   `git mv` passarem — memória `bash-pathlock-bypass`, que custou um conserto em
   5 topologias. A leitura da linha de comando é a do `_shellscan.py`, a fonte
   compartilhada, e não uma cópia nova.
2. **Escrita fora da raiz da sessão passa.** A worktree de perturbação em `/tmp`
   e o scratchpad não pertencem a modo nenhum; estreitar o gate para fora da
   raiz foi o que travou o proof-reviewer em 18/06/2026 e deixou 5 cards presos
   em NEEDS-HUMAN (memória `path-lock-out-of-root`).
3. **O escape não é barato e não é anunciado.** Um `# modo-ok` no comando seria a
   mesma fuga de novo — o agente digita e segue. O escape honesto é encerrar o
   modo e abrir o modo do trabalho que se quer fazer, que é uma sessão nova, e é
   o custo certo: trocar de atividade DEVERIA custar. O `CEPA_MODO=off` desliga
   a mecânica inteira e é visível, mas a mensagem de bloqueio não o oferece — o
   modo de falha seguinte, se ele for oferecido, é o agente passar a pedir para
   desligar o gate, e aí o buraco só mudou de lugar.

O que este gate NÃO alcança é a metade "não vira pergunta": isso é texto do
agente, não chamada de ferramenta, e nenhum hook lê a redação de uma resposta.
Mas a trava de escrita torna a pergunta inútil — não há o que oferecer quando o
passo seguinte está barrado.
"""

import fnmatch
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _modos  # noqa: E402
import _shellscan as S  # noqa: E402
import _wtlib  # noqa: E402

_TOOLS_ARQUIVO = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def modo_ativo(root):
    """O modo declarado desta sessão, ou None."""
    path = os.path.join(root, ".claude", "session-mode")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                k, _, v = line.partition(":")
                if k.strip() == "modo":
                    return v.strip().strip('"') or None
    except Exception:  # noqa: BLE001
        return None
    return None


def alvos(tool, inp):
    """Caminhos que esta chamada vai escrever."""
    if tool in _TOOLS_ARQUIVO:
        t = inp.get("file_path") or inp.get("notebook_path")
        return [t] if t else []
    if tool == "Bash":
        encontrados, _ = S.extract_write_targets(inp.get("command") or "")
        return encontrados
    return []


def relativo(alvo, root):
    """O alvo em relação à raiz da sessão, ou None se estiver fora dela.

    Fora da raiz o gate não opina: ver a decisão 2 do cabeçalho.
    """
    caminho = os.path.expandvars(os.path.expanduser(alvo))
    if not os.path.isabs(caminho):
        caminho = os.path.join(root, caminho)
    caminho = os.path.normpath(caminho)
    raiz = os.path.normpath(root)
    if caminho == raiz:
        return None
    if not caminho.startswith(raiz + os.sep):
        return None
    return os.path.relpath(caminho, raiz).replace(os.sep, "/")


def permitido(rel, padroes):
    """`docs/**` é prefixo de diretório; o resto é fnmatch sobre o caminho.

    `fnmatch` sozinho não serve para a distinção que a tabela faz: o `*` dele
    atravessa `/`, então `docs/design/*` casaria `docs/design/a/b/c` — o que até
    é desejado — mas `docs/*` também casaria `docs/design/x`, e aí a lista da
    descoberta (`docs/discovery/**`, `docs/spec/**`) deixaria de significar o
    que ela diz.
    """
    for pat in padroes:
        if pat.endswith("/**"):
            prefixo = pat[:-2]  # mantém a barra final
            if rel.startswith(prefixo):
                return True
        elif fnmatch.fnmatch(rel, pat):
            return True
    return False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    try:
        if os.environ.get("CEPA_MODO", "on") == "off":
            sys.exit(0)

        cwd = payload.get("cwd") or os.getcwd()
        root = _wtlib.session_root(cwd)
        modo = modo_ativo(root)
        if not modo:
            sys.exit(0)

        padroes = (_modos.MODOS.get(modo) or {}).get("escrita")
        # Modo desconhecido (ou sem tabela) não barra nada: o gate CONCEDE o
        # bloqueio, e na dúvida ele não concede.
        if not padroes or padroes == "tudo":
            sys.exit(0)

        for alvo in alvos(payload.get("tool_name", ""),
                          payload.get("tool_input", {}) or {}):
            rel = relativo(alvo, root)
            if rel is None or permitido(rel, padroes):
                continue
            produz = (_modos.MODOS.get(modo) or {}).get("produz", "")
            print(
                f"[modo-escrita-gate] BLOQUEADO: esta sessão opera em modo "
                f"{modo} e você ia escrever fora do que esse modo produz.\n"
                f"  Alvo: {alvo}\n"
                f"  O modo {modo} produz: {produz}\n"
                f"  Destinos liberados: {', '.join(padroes)}\n"
                f"  O que fazer: registre este desvio pelo skill "
                f"off-mode-capture e siga o trabalho do modo. Se o desvio "
                f"precisa mesmo acontecer AGORA, encerre este modo e abra uma "
                f"sessão no modo a que ele pertence — trocar de atividade tem "
                f"custo, e é esse custo que o modo existe para cobrar.",
                file=sys.stderr,
            )
            sys.exit(2)
    except Exception as e:  # noqa: BLE001
        print(f"[modo-escrita-gate] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
