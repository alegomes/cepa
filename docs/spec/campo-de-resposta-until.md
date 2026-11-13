# Especificação: campo de resposta do cepa-until

**Status:** ready-to-build
**Aberta em:** 2026-11-13            **Fechada em:** 2026-11-13
**Fontes lidas:** common/bin/cepa-until (read_line, _read_line, painel da rota humana, linhas 2495-2530 e 2900-2975), docs/spec/perguntas-da-largada-legiveis.md, tests/test_cepa_until_decide.py, tests/test_cepa_until.py

## Como chegamos aqui
"O campo de resposta do cepa until tem alguns problemas. As setas de navegação não funcionam, não é possível mover o cursor entre linhas e, agora, ainda deu este erro [could not read that line (an accent arrived half-way); type it again]. O que é possível fazer para melhorar sua experiência de uso?" (dono, 2026-11-13, ao responder C1-47 da fila kairos-etapa-1 do wego-faturamento-backend).

## Problema
Ao responder uma rota humana no fim do run, o dono não consegue corrigir o que digitou: seta esquerda e direita imprimem lixo e não movem o cursor. Ao colar uma resposta longa e com acentos (cerca de 1.150 caracteres em C1-47), o `cepa-until` recusou a linha com "an accent arrived half-way" e a resposta inteira se perdeu. O item foi gravado como `pending` sem o texto que o dono escreveu.

Causa, lida no código e reproduzida em 2026-11-13: `_read_line` usa `input()` sem importar `readline`. Sem `readline`, o terminal fica em modo canônico, sem edição de linha, e o macOS corta a linha em 1024 bytes (`getconf MAX_CANON /dev/tty` = 1024). Num pty simulado, `input()` puro recebe 505 bytes normalmente e, com 1.227 bytes, engole o Enter e não devolve nada. Com `import readline` os mesmos 1.227 bytes chegam inteiros. No caso real, o corte caiu no meio de um caractere acentuado e virou `UnicodeDecodeError`.

## Escopo
### Entra
- Edição na linha: setas esquerda e direita, Home e End, apagar no meio do texto, colar texto com mais de 1024 bytes (via `readline`).
- Uma forma de abrir o editor do sistema (`$VISUAL`/`$EDITOR`) para escrever respostas longas ou com várias linhas.
- Leitura que nunca perde o texto: um caractere ilegível vira `?`, o texto lido é mostrado e o dono confirma.
- Todos os pontos do `cepa-until` que leem uma linha do dono passam pela mesma leitura (Why, Your answer, Anything to add, escolha da leitura prévia e o menu de teclas).
### Não entra
- Campo de várias linhas com setas para cima e para baixo dentro do terminal (prompt_toolkit): traria uma dependência externa ao `cepa-until`, que hoje usa só a biblioteca padrão.

## Estado e migração
O formato do `queue.yaml` não muda e as filas existentes continuam válidas. A única novidade nos dados é que uma resposta escrita no editor pode trazer quebras de linha dentro do texto gravado no item.

O teste `test_invalid_byte_on_terminal_does_not_crash_decide` (em `tests/test_cepa_until_decide.py`) hoje exige "could not read that line" e um novo pedido. Ele passa a exigir o comportamento do CS-5.

## Critérios de sucesso

### CS-1: uma resposta colada com mais de 1024 bytes e acentos chega inteira ao item
**Surface:** cli
**Red test:** num pty, `cepa-until decide` recebe `s` no menu e, em "Anything to add", 1.500 bytes com "ção" atravessando o byte 1024, seguidos de Enter. O `evidence` do item no `queue.yaml` termina com os 1.500 bytes intactos. Hoje o Enter é engolido ou a leitura falha com "an accent arrived half-way", e o texto não chega.

### CS-2: setas e Home/End editam a linha em qualquer campo de texto
**Surface:** cli
**Red test:** num pty, em "Anything to add", o dono digita `abd`, seta esquerda, `c`, Home, `>`, End, `!` e Enter. O `evidence` do item termina com `>abcd!`. O mesmo roteiro em "Your choice" da leitura prévia grava `>abcd!` como escolha. Hoje o texto gravado traz as sequências de escape das setas (`\x1b[D`, `\x1b[H`, `\x1b[F`) misturadas às letras.

### CS-3: a tecla `[v]` do menu abre o editor e o texto salvo vira a resposta, com as quebras de linha
**Surface:** cli
**Red test:** com `EDITOR` apontando para um editor falso que grava "linha 1\nlinha 2", num pty o menu mostra `[v] write in the editor`, o dono aperta `v` e responde `s` em "Send the item back to the queue". O `evidence` do item contém "linha 1\nlinha 2" com a quebra e o item volta para `pending`. Hoje `v` cai em "is not one of the options".

### CS-4: digitar só `v` em "Anything to add" ou "Why" abre o editor
**Surface:** cli
**Red test:** com o mesmo editor falso, num pty o dono aperta `s` no menu e digita `v` e Enter em "Anything to add". O `evidence` termina com "linha 1\nlinha 2", não com "v". O mesmo vale para `d` seguido de `v` em "Why". Hoje grava a letra `v` literal.

### CS-5: uma linha com byte ilegível é mostrada com `?` e o dono confirma, sem perder o texto
**Surface:** cli
**Red test:** num pty, depois de `t`, o dono envia `n\xcb\xc3\xa3o vira checklist` em "Your answer". A tela mostra "n?ão vira checklist" e pergunta "Use this text? [Y/n]". Com Enter, o `evidence` do item contém "n?ão vira checklist". Com `n`, o campo é pedido de novo. Hoje a tela diz "could not read that line" e o texto se perde.

### CS-6: editor salvo vazio ou fechado com erro não grava nada
**Surface:** cli
**Red test:** com `EDITOR` apontando para um editor falso que sai com código 1 (e outro que salva o arquivo vazio), num pty o dono aperta `v`. A tela avisa "nothing written in the editor", volta ao menu do mesmo item, e o `queue.yaml` não muda. Hoje a tecla `v` não existe.

## Perguntas em aberto
- [x] Q1. Onde gravar a spec, já que a worktree da sessão sumiu? — Nova worktree `session/campo-de-resposta` a partir da main (dono, 2026-11-13).
- [x] Q2. Qual nível de edição o campo deve ter? — readline (setas, Home/End, colar sem limite) e mais uma forma de abrir o `$EDITOR` para respostas longas ou de várias linhas, sem dependência nova (dono, 2026-11-13).
- [x] Q3. O que acontece com o texto quando a leitura falha? — Guardar e mostrar: troca o caractere ilegível por `?`, mostra o texto lido e pede confirmação (dono, 2026-11-13).
- [x] Q4. Vale para todos os campos de texto ou só para a rota humana? — Todos (dono, 2026-11-13).
- [x] Q5. Como o dono abre o editor? — Tecla nova `[v] write in the editor` no menu, ao lado de `[t]`, com o mesmo destino de `[t]`. Em "Anything to add" e "Why", digitar só `v` e Enter também abre o editor (dono, 2026-11-13).
- [x] Q6. Resposta de várias linhas mantém as quebras no `queue.yaml`? — Mantém (dono, 2026-11-13).

## Decided without asking
- O editor é escolhido nesta ordem: `$VISUAL`, `$EDITOR` e, sem nenhum dos dois, `vi`. É a ordem do git, que o dono já usa. Vete aqui se discordar. · mantida em 2026-11-13
- O arquivo aberto no editor traz a pergunta do item em linhas começadas por `#`, e essas linhas são descartadas ao salvar, como na mensagem de commit do git. Vete aqui se discordar. · mantida em 2026-11-13
- Seta para cima e para baixo trazem as respostas anteriores do mesmo `decide`. Esse histórico não é gravado em disco, para resposta do dono não vazar entre repos. Vete aqui se discordar. · mantida em 2026-11-13
- O `readline` só é ativado quando a entrada é um terminal. Em teste, `nohup` ou agente, a leitura e o texto da tela ficam byte a byte como hoje. Vete aqui se discordar. · mantida em 2026-11-13
- A confirmação do CS-5 tem Enter como sim, porque o texto com `?` quase sempre é o que o dono quis dizer. Vete aqui se discordar. · mantida em 2026-11-13

## Riscos e o que ficou de fora desta especificação
- O Python do macOS pode vir com `libedit` no lugar do GNU readline. Setas, Home/End e colar funcionam nos dois, mas atalhos menos comuns variam.
