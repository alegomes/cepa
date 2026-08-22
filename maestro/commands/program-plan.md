---
description: Planeja um programa do Maestro — conversa sobre um universo de demandas (default BACKLOG.md), propõe ondas de slices com superfícies disjuntas e fork points, escreve .claude/programs/<nome>/plan.yaml (schema v2, canônico em common/plan-schema.yaml; v1 segue lida sem migração) e roda o intake gate (cepa-dor) até cada slice sair READY ou ter a lacuna nomeada. Não executa nada — /maestro:run (passo 3 da construção) é quem forka. Piso de uso: ≥4 demandas (D7); com menos, /board-flow:drain ou sessão única ganham.
argument-hint: [nome-do-programa] [--source ARQUIVO] [--demandas "P9,P10,..."]
interaction: conversational
---

# /maestro:program-plan

## Purpose

Transformar "quero tocar estas N demandas em paralelo" num plan.yaml que o
motor consegue executar sem mediação improvisada. O v0 (melhorias-2026-07)
provou o formato e pagou uma lição: dois slices tocaram o mesmo arquivo porque
a superfície não era declarada nem checada — 1 conflito real de merge. Este
comando existe para que TODO plano nasça com superfícies declaradas, disjuntas
e verificadas mecanicamente antes de qualquer fork.

**Invariante de costura:** `/maestro:run` lê exclusivamente o plan.yaml. Este
comando é o único lugar onde BACKLOG.md (ou outra fonte) é interpretado.

## Steps

1. **Fonte e universo.** Leia a fonte (`--source`, default `BACKLOG.md`) e
   identifique as demandas candidatas (as passadas em `--demandas`, ou as que
   o usuário descrever). Menos de 4 demandas → pare e diga que o piso (D7) não
   foi atingido; recomende /board-flow:drain ou sessão única.

2. **Análise por demanda** (leitura do repo, sem escrever nada):
   - **superfície**: quais arquivos/globs a demanda realisticamente toca —
     derive do texto da demanda + grep/glob no código; na dúvida, declare o
     glob mais largo e honesto;
   - **dependências** entre demandas (uma cria o que a outra consome → ondas
     diferentes, `fork_after`);
   - **gate humano**: existe decisão estratégica em aberto (escopo, contrato,
     naming user-facing, breaking change)? Ela precisa ser tomada AGORA, na
     conversa, e registrada no `human_gate` — ou a demanda fica fora da onda;
   - **critério de aceite executável** (`acceptance` + `acceptance_cmd` — o
     repo é `.claude/no-build`, então `acceptance_cmd` é obrigatório);
   - **forma do aceite** (`acceptance_form`): se a demanda só nomeia passos
     privados de implementação — nenhum Given/When/Then observável em alguma
     superfície — ela não é US. Ou o `acceptance` ganha a tripla observável
     (`acceptance_form: bdd`), ou o slice **assume** que é substrato
     (`acceptance_form: substrate`). Sem uma das duas, o intake reprova.

3. **Proposta de ondas.** Agrupe slices de superfícies disjuntas na mesma onda
   (teto `max_concurrent_slices`, default 3); dependências e decisões pesadas
   empurram para ondas posteriores. Apresente a proposta ao usuário em tabela
   (onda · slice · demanda · superfície · gate humano · aceite) e discuta.

4. **Escrever o plano.** Com o desenho acordado, escreva
   `<raiz-principal>/.claude/programs/<nome>/plan.yaml` seguindo
   `common/plan-schema.yaml` (`schema_version: 2`, `mode: parallel-waves`). Um
   slice por demanda, salvo demanda grande que o usuário concorde em fatiar. O `mode` é explícito porque
   o mesmo schema também serve o `single-track` do board-flow — é o campo que
   diz a quem lê qual dos dois este plano é. Planos v1 no disco (sem `mode`)
   continuam válidos e **não precisam ser migrados**.

   **`<raiz-principal>`** é o pai de `git rev-parse --git-common-dir` sem o
   `/.git` final — em worktree ligada isso aponta para o CLONE PRINCIPAL, não
   para a árvore atual; fora dela é o mesmo que `git rev-parse --show-toplevel`.
   O plano é estado do repo, não da sessão: escrito dentro de worktree de
   sessão, morre com ela, e num repo cujo `.gitignore` cobre `.claude/` inteiro
   nenhuma guarda do caminho de remoção enxerga o arquivo. Vale para ler e para
   escrever. Ver `docs/execution-plan.md`, "Where the file lives".

5. **Intake gate.** Rode:

   ```
   python3 common/bin/cepa-dor <raiz-principal>/.claude/programs/<nome>/plan.yaml --wave 1 --repo .
   ```

   Para cada NOT-READY, corrija COM o usuário (ajustar globs, registrar a
   decisão do human_gate, escrever acceptance_cmd) e rode de novo, até a onda 1
   sair READY (avisos ⚠ são aceitáveis e ficam anotados no plano). Repita para
   as demais ondas se o usuário quiser antecipar.

6. **Encerramento.** Mostre o veredito final do cepa-dor e o caminho do plano.
   Diga explicitamente: a execução é `/maestro:run` (ainda não construído —
   passo 3 da ordem de construção; até lá, o plano serve para as ondas manuais
   com worktrees, como no v0).

## Notes

- Este comando NÃO executa demandas, não cria worktrees, não sobe porteiro.
- Superfície é promessa de escrita, não de leitura — a filha pode ler o repo
  inteiro; só escreve dentro dos globs (camada 1 das settings geradas).
- A zona de enforcement (plugins/, hooks/, .claude/settings*, plugin-cache) é
  veto incondicional do cepa-dor: nenhum glob de slice pode incluí-la.
- Arquivos de alto atrito não declarados (lockfiles, migrations, index/barrel)
  viram aviso, não veto — o verify pós-merge do merge train é quem pega
  conflito incidental.
- `acceptance_form: substrate` não é escape hatch: é uma **declaração**. Um
  slice de substrato aceita ser verificado por critério técnico porque ninguém
  finge que ele tem superfície observável. Marcar `substrate` numa demanda que
  o usuário enxerga é mentir para o gate — e o gate acredita.
