---
description: Mostra a tabela dos modos de trabalho — o que cada modo pede para entrar, o que ele produz, e o que precisa ser verdade para fechar. Responde "em que modo eu estou mesmo, e qual era o propósito dele?" sem abrir o documento de 307 linhas. Marca o modo da sessão atual. Read-only, não muda modo nenhum.
argument-hint: [nome-do-modo]
interaction: conversational
---

# /common:modos

## Purpose

Toda sessão declara um modo, e o modo é um **estado que dura** até a condição de
saída ser satisfeita — não um rótulo. Só que a definição de cada um mora em
`docs/modos-de-trabalho.md`, com 307 linhas, e ninguém abre isso no meio do
trabalho. O que acontece no lugar é chutar o propósito do modo em que se está.

Este comando é a tabela e nada além dela.

**Não troca de modo.** Trocar exige nova sessão (`cepa --modo <x>`), de
propósito: se desse para trocar no meio, o modo voltaria a ser rótulo.

## Steps

1. Rode, repassando o argumento verbatim:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-modos" $ARGUMENTS
   ```

2. Mostre a saída **na íntegra**. Ela já sai em pt-BR e formatada — não resuma,
   não reordene, não escolha "os mais relevantes". A tabela inteira é o produto:
   quem pediu esqueceu qual era qual, e um resumo devolve o mesmo problema.

3. Se o usuário nomeou um modo (`/common:modos reforma`), o script já filtra —
   você não filtra nada por conta própria.

## Notes

- A fonte é `common/hooks/_modos.py`, o mesmo arquivo que o `session-mode.py` lê
  para injetar a condição de saída a cada turno. Uma tabela, dois leitores; o
  `tests/test_modos_fonte_unica.py` reprova se a lista de nomes válidos do
  `cepa` divergir dela.
- São 7 modos. O 8º do documento, `deploy`, está fora da rodada por decisão do
  dono — é o único que depende de infra externa (ambiente, credencial,
  pipeline) e travaria os outros se entrasse junto.
- Para saber só em que modo você está, sem a tabela: a statusline mostra
  `🎯 <modo>`.
