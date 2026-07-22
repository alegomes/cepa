---
description: Valida a instalação do harness contra a realidade em 30 segundos — plugins habilitados e na versão instalada, hooks compilando, board-flow.yaml estrutural, baseline de build (status + idade), worktrees stale/órfãs e handoffs vencidos. Com --live, também confere o board-flow.yaml contra o Jira vivo via atlassian-expert. Rode no início do dia ou quando algo do harness parecer errado — cada check existe porque a falha correspondente já custou uma tarefa.
argument-hint: [--live]
---

# /common:doctor

## Purpose

Quase toda falha de infraestrutura do harness era descoberta no meio de uma
tarefa: plugin não carregado gerando cards sem custom fields, board-flow.yaml
de outro módulo, baseline FAILURE de semanas bloqueando push, worktree órfã,
handoff stale alimentando afirmações falsas. Este comando antecipa tudo isso
para um momento em que consertar é barato.

## Steps

1. Rode o diagnóstico mecânico:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-doctor"
   ```

2. Mostre a saída ao usuário na íntegra (✓/⚠/✗ por área, já em pt-BR).

3. **Se `--live` foi passado** e existe `board-flow.yaml` no projeto: delegue ao
   `board-flow:atlassian-expert` (se o plugin board-flow estiver instalado):

   > Sanity-check do board-flow.yaml contra o Jira vivo (sem mutação):
   > confirme que o project_key é visível, que cada valor de status_map
   > existe como status real do projeto, e que cada required_field existe no
   > metadata do issue type. Responda OK ou a lista de divergências.

   Anexe o resultado ao relatório.

4. Para cada ⚠/✗, proponha a correção específica (a própria mensagem já diz
   qual é — reinstalar, rodar verify, criar `.claude/no-build`, discard de
   worktree, apagar handoff). Execute **apenas** as que o usuário confirmar,
   exceto correções triviais e reversíveis explicitamente pedidas na mesma
   frase.

   **Área `ops` — trate com prioridade sobre as demais.** Ela responde "o
   harness que está rodando é o que eu acho que está?", e um ✗ aí contamina
   todo o resto do relatório: se o último install não terminou, os hooks live
   não são os do repo, e qualquer outro check pode estar medindo a coisa
   errada. Traduza sem jargão — "a última instalação morreu no meio, então o
   que está valendo agora não é nem o antigo nem o novo" — e ofereça as duas
   saídas explícitas: refazer (`bin/install.sh --clean`) ou voltar
   (`bin/install.sh --rollback`). Ver `docs/harness-ops.md`.

5. Exit code do script: 0 = saudável, 1 = só avisos, 2 = falhas. Se 2, sugira
   resolver antes de começar trabalho novo.

## Notes

- O script não toca em nada — é 100% leitura (o probe de telemetria cria e
  apaga um arquivo próprio). Toda mutação passa pelo passo 4 com confirmação.
- Checks de projeto rodam sobre o cwd; rode o comando de dentro do repo que
  quer diagnosticar.
- O check `ops` é a exceção: ele lê `~/.claude/ops/last-install.json`, que é
  **global** — descreve o cache de plugins da máquina, não deste repositório.
  Por isso ele vale igual em qualquer cwd, e por isso guarda `repo_dir` (de
  qual clone veio o que está instalado).
