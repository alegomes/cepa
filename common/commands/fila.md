---
description: Lista a fila single-track do repo inteira, agrupada por status (em andamento, pendentes, bloqueados, concluídos, descartados), na ordem gravada, com o motivo de cada bloqueio e as ações humanas abertas. Responde "como está a fila agora?" sem abrir o plan.yaml. Só lê — não reserva, não executa e não reconcilia com o Jira.
argument-hint: [nome-da-fila] [--status pending|in_progress|blocked|done|dropped]
interaction: conversational
---

# /common:fila

## Purpose

Os outros comandos da fila respondem outras perguntas. O `/common:next` aponta
**um** próximo passo. O `/common:drain-plan` executa. O `cepa-plan queue` mostra
só o que o próximo lote rodaria, esconde o que já fechou e para no primeiro
travamento. Nenhum responde "como está a fila agora?", e em 2026-09-28 a única
saída era abrir o `plan.yaml` de 72 itens à mão.

Este comando é a listagem e nada além dela.

**Só leitura.** Não reserva item, não muda status, não chama o Jira. Para
reconciliar com o quadro, `/common:next --sync`.

## Steps

1. Rode, repassando o argumento verbatim:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-plan" status $ARGUMENTS --repo .
   ```

   Sem nome, o script usa a única fila do repo. Com mais de uma, ele sai com
   código 2 e lista os nomes: mostre a lista e peça o nome, não escolha.

2. Mostre a saída **na íntegra**, dentro de um bloco de código. Ela já sai em
   pt-BR, agrupada e na ordem gravada. Não resuma, não reordene e não escolha
   "os mais relevantes": quem pediu quer a fila, e um resumo devolve o mesmo
   buraco que o comando existe para tapar.

3. Não acrescente recomendação nem próximo passo. Se o usuário quiser saber o
   que fazer, o comando é o `/common:next`.

## Notes

- A fila mora no clone principal (`<raiz>/.claude/programs/<nome>/plan.yaml`),
  mesmo quando a sessão roda numa worktree. O `cepa-plan` resolve isso sozinho.
- O número antes de cada item é a posição dele na fila gravada, não a ordem de
  execução: um item pendente pode esperar outro que está mais abaixo.
- Concluídos e descartados saem numa linha só cada, sem evidência. Para ver a
  evidência de um item, `--status done` com `--json` traz tudo.
