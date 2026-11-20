# Especificação: sessão do cepa com nome próprio na lista Agents do herdr

**Status:** ready-to-build
**Aberta em:** 2026-11-20            **Fechada em:** 2026-11-20
**Fontes lidas:** common/bin/cepa (run_claude, linhas 366-395), tests/test_cepa_slice_isolation.py, ../floss/herdr-app/defaults/mods/agents/main.js (linhas 41-47, 280-296, 336-340), ../floss/herdr-app/src/model.rs (linhas 250-265), `claude --help` (opção -n/--name)

## Como chegamos aqui
"Mesmo nome de sessao em todos os agentes" (dono, 2026-11-20), com o print da lista Agents do herdr mostrando três linhas `cepa-divergencia`, duas delas com o mesmo subtítulo "Menu do modo discovery".

## Problema
Na lista Agents do herdr, toda sessão do Cepa aberta no mesmo space aparece igual. A linha mostra "nome do space · título da sessão". O space sem nome herda a pasta do primeiro terminal, e o título vem do primeiro prompt, que é o mesmo menu do modo para toda sessão. O dono não sabe qual linha é qual sessão.

## Escopo
### Entra
- O lançador `cepa`, na função `run_claude`, passa `--name <slice>` ao claude quando o branch atual é `session/<slice>`.
- Se o dono já passou `-n`, `--name` ou `--name=...` nos argumentos, o lançador não acrescenta o seu.

### Não entra
- Mudar o herdr-app (o nome do space ou a montagem da linha): é outro repo, e o `--name` já resolve pelo título.
- Dar nome a sessão no checkout principal, fora de branch `session/*`: ela já é única no space do repo.
- Renomear sessões já abertas: o nome vale a partir da próxima abertura.

## Estado e migração
Nada. Nenhum arquivo gravado muda. Sessões abertas antes da mudança continuam com o título antigo até fecharem.

## Critérios de sucesso

### CS-1: sessão aberta num worktree `session/<slice>` chega ao claude com `--name <slice>`
**Surface:** cli
**Red test:** com um claude falso (via `CLAUDE_WT_CLAUDE_BIN`, como em `tests/test_cepa_slice_isolation.py`) que grava seus argumentos, `cepa -s foo` num repo de teste resulta em argumentos que contêm `--name foo`. Na mesma bateria, `cepa -s foo --name bar` resulta em exatamente um `--name`, com valor `bar`, e `cepa` no checkout principal (branch `main`) resulta em argumentos sem `--name`. Hoje o primeiro caso falha: os argumentos não têm `--name`.

## Perguntas em aberto
- [x] Aplico a correção agora numa sessão de construção? — não, "Só faça a especificação e inclua o item na fila para ser executado via cepa until" (dono, 2026-11-20).

## Decided without asking
- O nome é só o slice (`pending-landings`), sem o nome do repo: a linha do herdr já mostra o space, e repetir o repo gasta a largura curta da coluna. Vete aqui se discordar.
- O `--name` vai antes dos argumentos do dono (`claude --name <slice> "$@"`): assim um `--resume` ou um prompt passado à mão segue funcionando. Vete aqui se discordar.
- Sessão encadeada (reaberta pelo `session-chain.py`) ganha o nome pelo mesmo caminho, porque toda abertura passa por `run_claude`. Não vira critério à parte. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- O efeito final, a linha do herdr mostrar o slice, depende de o Claude Code manter o título fixado pelo `--name` em vez de trocar pelo título gerado do primeiro prompt. A prova automática para no argumento passado ao claude. A conferência na lista do herdr é manual, na primeira sessão aberta depois do merge.
- Feedbacks de origem: `fb-20261120-4` e `fb-20261120-6` em `~/.claude/cepa-feedback/feedback-2026-11.jsonl`.
